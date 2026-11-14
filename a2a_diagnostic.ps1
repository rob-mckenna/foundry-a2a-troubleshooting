#requires -Version 7.0
<#
.SYNOPSIS
Safely checks a Foundry A2A v1 agent card; optionally sends one billable message.
.DESCRIPTION
ProjectId and SubAgentId are historical parameter names: supply the project NAME
and agent NAME, not resource IDs. Supply either all three name parameters or
ServerUrl, never both. Interactive prompts for names only when explicitly set.
SendMessage opts into model execution/cost. Prompt defaults to a synthetic probe;
custom prompts and remote replies are never included in evidence.
Dot-source to load functions without network calls or exiting the calling shell.
Run-Diagnostics returns sanitized evidence with ExitCode (0 pass, 1 runtime or
protocol failure, 2 invalid arguments). The executable exits with that code.
.EXAMPLE
.\a2a_diagnostic.ps1 -AccountName example -ProjectId project-name -SubAgentId agent-name
.EXAMPLE
.\a2a_diagnostic.ps1 -ServerUrl https://example.services.ai.azure.com/api/projects/project-name/agents/agent-name/endpoint/protocols/a2a -SendMessage -EvidencePath .\diagnostic.json
#>
[CmdletBinding()]
param(
    [string]$AccountName,
    [string]$ProjectId,
    [string]$SubAgentId,
    [switch]$Interactive,
    [string]$ServerUrl,
    [switch]$SendMessage,
    [string]$Prompt = 'Reply with exactly: A2A diagnostic OK',
    [string]$EvidencePath,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArguments
)

function Test-A2AServerURL {
    param([string]$Url)
    # Check the original string, not URI-normalized paths (which erase dot segments).
    $pattern = '\Ahttps://(?<account>[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)\.services\.ai\.azure\.com/api/projects/(?<project>[A-Za-z0-9_-]+)/agents/(?<agent>[A-Za-z0-9_-]+)/endpoint/protocols/a2a\z'
    $valid = $Url -cmatch $pattern
    if (-not $valid) { return @{ Valid = $false } }
    $uri = $null
    if (-not [Uri]::TryCreate($Url, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne 'https' -or $uri.Port -ne 443 -or
        $uri.UserInfo -or $uri.Query -or $uri.Fragment) {
        return @{ Valid = $false }
    }
    return @{ Valid = $true; Url = $Url; Hostname = $uri.DnsSafeHost }
}

function Invoke-AzureCli {
    param([string[]]$Arguments, [string]$Executable = 'az')
    # Capture stderr, rather than suppress it or expose arbitrary CLI diagnostics.
    # Only an allowlisted AADSTS code may leave this boundary.
    $ErrorActionPreference = 'Continue'
    $PSNativeCommandUseErrorActionPreference = $false
    try {
        $null = Get-Command $Executable -ErrorAction Stop
        $global:LASTEXITCODE = 0
        $records = @(& $Executable @Arguments 2>&1)
        $succeeded = $?
        $code = $global:LASTEXITCODE
        if (-not $succeeded -and $code -eq 0) { $code = 1 }
        $stdout = @($records | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] })
        $stderr = ($records | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] }) -join "`n"
        $category = 'cli-failure'
        if ($stderr -cmatch '\bAADSTS[0-9]{5,10}\b') { $category = "cli-$($Matches[0])" }
        if ($code -ne 0) { return @{ ExitCode = $code; Output = ''; Category = $category } }
        return @{ ExitCode = 0; Output = ($stdout -join "`n"); Category = $null }
    } catch {
        return @{ ExitCode = 1; Output = ''; Category = 'cli-unavailable' }
    }
}

function ConvertFrom-DiagnosticJson {
    param([string]$Content)
    try {
        $value = ConvertFrom-Json -InputObject $Content -AsHashtable -Depth 100 -ErrorAction Stop
        if ($value -isnot [System.Collections.IDictionary]) { throw 'shape' }
        return $value
    } catch { throw 'invalid-json' }
}

function Get-AzureToken {
    $reply = Invoke-AzureCli -Arguments @('account', 'get-access-token', '--resource', 'https://ai.azure.com', '-o', 'json')
    if ($reply.ExitCode -ne 0) { return @{ Success = $false; Category = $reply.Category } }
    try {
        $data = ConvertFrom-DiagnosticJson $reply.Output
        if ($data.accessToken -isnot [string] -or [string]::IsNullOrWhiteSpace($data.accessToken) -or
            $data.accessToken -match '\s') { throw 'token' }
        return @{ Success = $true; Token = $data.accessToken }
    } catch { return @{ Success = $false; Category = 'invalid-token-json' } }
}

function Test-DNSResolution {
    param([string]$Hostname)
    try { return [System.Net.Dns]::GetHostAddresses($Hostname).Count -gt 0 }
    catch { return $false }
}

function Invoke-A2AHttp {
    param([string]$Url, [string]$Token, [string]$Method, [string]$Body)
    $options = @{
        Uri = $Url; Method = $Method
        Headers = @{ Authorization = "Bearer $Token"; 'A2A-Version' = '1.0'; Accept = 'application/json' }
        MaximumRedirection = 0; SkipHttpErrorCheck = $true
        TimeoutSec = 60; ErrorAction = 'Stop'; Verbose = $false; Debug = $false
    }
    if ($Method -eq 'POST') { $options.Body = $Body; $options.ContentType = 'application/json' }
    $response = $null
    $observedStatus = $null
    try {
        # PS 7 emits a redirect response before MaximumRedirectExceeded. Capture
        # it incrementally: an assignment to the entire pipeline loses that
        # response when -ErrorAction Stop terminates the pipeline.
        Invoke-WebRequest @options | ForEach-Object {
            $response = $_
            $observedStatus = [int]$_.StatusCode
        }
        $status = [int]$response.StatusCode
        if ($status -lt 200 -or $status -ge 300) {
            return @{ Success = $false; HttpStatus = $status; Category = 'http-non-2xx' }
        }
        try { $json = ConvertFrom-DiagnosticJson $response.Content }
        catch { return @{ Success = $false; HttpStatus = $status; Category = 'invalid-json' } }
        return @{ Success = $true; HttpStatus = $status; Json = $json }
    } catch {
        $status = $observedStatus
        try {
            if ($null -eq $status -and $_.Exception.Response.StatusCode) { $status = [int]$_.Exception.Response.StatusCode }
        } catch {}
        $category = if ($null -eq $status) { 'transport-failure' } else { 'http-non-2xx' }
        return @{ Success = $false; HttpStatus = $status; Category = $category }
    }
}

function Test-A2ACard {
    param([System.Collections.IDictionary]$Card)
    if ($Card.name -isnot [string] -or [string]::IsNullOrWhiteSpace($Card.name)) { return 'invalid-card-shape' }
    $matched = $false
    if ($Card.Contains('protocolVersion')) {
        if ($Card.protocolVersion -isnot [string] -or $Card.protocolVersion -cne '1.0') { return 'card-version-mismatch' }
        $matched = $true
    }
    if ($Card.Contains('supportedInterfaces')) {
        if ($Card.supportedInterfaces -isnot [array] -or $Card.supportedInterfaces.Count -eq 0) { return 'invalid-card-shape' }
        foreach ($item in $Card.supportedInterfaces) {
            if ($item -isnot [System.Collections.IDictionary] -or $item.protocolVersion -isnot [string]) { return 'invalid-card-shape' }
            if ($item.protocolVersion -ceq '1.0') { $matched = $true }
        }
    }
    if (-not $matched) { return 'card-version-mismatch' }
    return $null
}

function Test-A2AParts {
    param($Parts)
    if ($Parts -isnot [array] -or $Parts.Count -eq 0) { return @{ Valid = $false; TextPresent = $false } }
    $textPresent = $false
    foreach ($part in $Parts) {
        if ($part -isnot [System.Collections.IDictionary]) { return @{ Valid = $false; TextPresent = $false } }
        $kinds = @('text', 'data', 'url', 'raw') | Where-Object { $part.Contains($_) }
        if (@($kinds).Count -ne 1) { return @{ Valid = $false; TextPresent = $false } }
        if ($part.Contains('text')) {
            if ($part.text -isnot [string]) { return @{ Valid = $false; TextPresent = $false } }
            if (-not [string]::IsNullOrWhiteSpace($part.text)) { $textPresent = $true }
        } elseif ($part.Contains('data')) {
            if ($part.data -isnot [System.Collections.IDictionary]) { return @{ Valid = $false; TextPresent = $false } }
        } else {
            $key = $kinds[0]
            if ($part[$key] -isnot [string] -or [string]::IsNullOrWhiteSpace($part[$key]) -or
                $part.mediaType -isnot [string] -or [string]::IsNullOrWhiteSpace($part.mediaType)) {
                return @{ Valid = $false; TextPresent = $false }
            }
        }
    }
    return @{ Valid = $true; TextPresent = $textPresent }
}

function Test-A2ARpcResponse {
    param([System.Collections.IDictionary]$Response, [string]$RequestId)
    if ($Response.jsonrpc -isnot [string] -or $Response.jsonrpc -cne '2.0' -or
        $Response.id -isnot [string] -or $Response.id -cne $RequestId) { return 'rpc-envelope-mismatch' }
    if ($Response.Contains('error')) { return 'rpc-error' }
    if ($Response.result -isnot [System.Collections.IDictionary]) { return 'invalid-result-shape' }
    $result = $Response.result
    if ($result.Contains('message') -eq $result.Contains('task')) { return 'invalid-result-shape' }
    if ($result.Contains('message')) {
        $message = $result.message
        if ($message -isnot [System.Collections.IDictionary] -or
            $message.messageId -isnot [string] -or [string]::IsNullOrWhiteSpace($message.messageId) -or
            $message.role -isnot [string] -or $message.role -cne 'ROLE_AGENT') { return 'invalid-message-shape' }
        $parts = Test-A2AParts $message.parts
        if (-not $parts.Valid) { return 'invalid-parts-shape' }
        if (-not $parts.TextPresent) { return 'missing-text-output' }
    } else {
        $task = $result.task
        if ($task -isnot [System.Collections.IDictionary] -or
            $task.id -isnot [string] -or [string]::IsNullOrWhiteSpace($task.id) -or
            $task.contextId -isnot [string] -or [string]::IsNullOrWhiteSpace($task.contextId) -or
            $task.status -isnot [System.Collections.IDictionary] -or $task.status.state -isnot [string]) {
            return 'invalid-task-shape'
        }
        if ($task.status.state -cne 'TASK_STATE_COMPLETED') { return 'task-not-completed' }
        if ($task.artifacts -isnot [array] -or $task.artifacts.Count -eq 0) { return 'missing-text-output' }
        $textPresent = $false
        foreach ($artifact in $task.artifacts) {
            if ($artifact -isnot [System.Collections.IDictionary] -or
                $artifact.artifactId -isnot [string] -or [string]::IsNullOrWhiteSpace($artifact.artifactId)) { return 'invalid-artifact-shape' }
            $parts = Test-A2AParts $artifact.parts
            if (-not $parts.Valid) { return 'invalid-parts-shape' }
            if ($parts.TextPresent) { $textPresent = $true }
        }
        if (-not $textPresent) { return 'missing-text-output' }
    }
    return $null
}

function Test-EndpointAccessibility {
    <# Url is the A2A base, not the card URL. Returns only sanitized metadata.
       Direct helper calls can target local fixtures; Run-Diagnostics validates
       the public-cloud HTTPS target before calling this transport boundary. #>
    param([string]$Url, [string]$Token)
    $http = Invoke-A2AHttp -Url "$Url/agentCard/v1.0" -Token $Token -Method GET
    $category = if ($http.Success) { Test-A2ACard $http.Json } else { $http.Category }
    $success = $http.Success -and -not $category
    return @{
        Success = [bool]$success; Accessible = [bool]$success
        StatusCode = $http.HttpStatus; Category = $category
        Response = @{ ProtocolVersion = '1.0'; CardValid = [bool]$success }
    }
}

function Test-A2AMessageExchange {
    param([string]$Url, [string]$Token, [string]$Prompt = 'Reply with exactly: A2A diagnostic OK')
    if ([string]::IsNullOrWhiteSpace($Prompt)) {
        return @{
            Success = $false; StatusCode = $null; Category = 'invalid-arguments'
            Response = @{ Text = 'REDACTED'; TextPresent = $false; ProtocolVersion = '1.0' }
        }
    }
    $id = [Guid]::NewGuid().ToString()
    $request = @{
        jsonrpc = '2.0'; id = $id; method = 'SendMessage'
        params = @{
            message = @{ messageId = [Guid]::NewGuid().ToString(); role = 'ROLE_USER'; parts = @(@{ text = $Prompt }) }
            configuration = @{ acceptedOutputModes = @('text/plain'); returnImmediately = $false }
        }
    }
    $http = Invoke-A2AHttp -Url $Url -Token $Token -Method POST -Body ($request | ConvertTo-Json -Depth 20 -Compress)
    $category = if ($http.Success) { Test-A2ARpcResponse -Response $http.Json -RequestId $id } else { $http.Category }
    $success = $http.Success -and -not $category
    return @{
        Success = [bool]$success; StatusCode = $http.HttpStatus; Category = $category
        Response = @{ Text = 'REDACTED'; TextPresent = [bool]$success; ProtocolVersion = '1.0' }
    }
}

function Run-Diagnostics {
    [CmdletBinding()]
    param(
        [string]$AccountName, [string]$ProjectId, [string]$SubAgentId,
        [string]$ServerUrl, [switch]$Interactive, [switch]$SendMessage,
        [string]$Prompt = 'Reply with exactly: A2A diagnostic OK',
        [string]$EvidencePath, [string[]]$RemainingArguments
    )
    $evidence = [ordered]@{
        Timestamp = [DateTimeOffset]::UtcNow.ToString('o')
        Environment = @{ OS = [Environment]::OSVersion.Platform.ToString(); PowerShell = $PSVersionTable.PSVersion.ToString(); AzureCli = 'unavailable' }
        Protocol = @{ Version = '1.0'; Header = 'A2A-Version: 1.0' }
        IdentityContext = @{ Source = 'azure-cli current login'; Type = 'unknown'; DeployedCallerAssessed = $false }
        Endpoint = '[redacted Foundry target]'
        RBAC = @{ Status = 'not assessed'; Scope = 'target project/agent endpoint permission'; Verified = $false }
        Phases = @()
        Request = @{ Method = 'GET'; Path = '/agentCard/v1.0'; SendMessage = [bool]$SendMessage }
        Reply = @{ Text = 'REDACTED'; TextPresent = $false }
        Outcome = 'failure'; ExitCode = 1; FailureCategory = $null
    }
    $phase = 'arguments'
    try {
        if ($RemainingArguments.Count -gt 0) { throw 'invalid-arguments' }
        if ($Interactive) {
            if ($ServerUrl -or $AccountName -or $ProjectId -or $SubAgentId) { throw 'invalid-arguments' }
            $AccountName = Read-Host 'Foundry account NAME'
            $ProjectId = Read-Host 'Project NAME (not ID)'
            $SubAgentId = Read-Host 'Agent NAME (not ID)'
        }
        if ($ServerUrl) {
            if ($AccountName -or $ProjectId -or $SubAgentId) { throw 'invalid-arguments' }
        } else {
            if ([string]::IsNullOrWhiteSpace($AccountName) -or [string]::IsNullOrWhiteSpace($ProjectId) -or
                [string]::IsNullOrWhiteSpace($SubAgentId)) { throw 'invalid-arguments' }
            $ServerUrl = "https://$AccountName.services.ai.azure.com/api/projects/$ProjectId/agents/$SubAgentId/endpoint/protocols/a2a"
        }
        $target = Test-A2AServerURL $ServerUrl
        if (-not $target.Valid -or [string]::IsNullOrWhiteSpace($Prompt)) { throw 'invalid-arguments' }
        $phase = 'dns'
        if (-not (Test-DNSResolution $target.Hostname)) { throw 'dns-failure' }
        $evidence.Phases += @{ Phase = $phase; HttpStatus = $null; Status = 'pass' }
        $phase = 'azure-cli-context'
        $context = Invoke-AzureCli -Arguments @('account', 'show', '-o', 'json')
        if ($context.ExitCode -ne 0) { throw $context.Category }
        $account = ConvertFrom-DiagnosticJson $context.Output
        if ($account.user -isnot [System.Collections.IDictionary] -or $account.user.type -isnot [string]) { throw 'invalid-cli-context' }
        switch -CaseSensitive ($account.user.type) {
            'user' { $evidence.IdentityContext.Type = 'user' }
            'servicePrincipal' { $evidence.IdentityContext.Type = 'service principal' }
            default { throw 'unsupported-cli-identity' }
        }
        $version = Invoke-AzureCli -Arguments @('version', '-o', 'json')
        if ($version.ExitCode -ne 0) { throw $version.Category }
        $versions = ConvertFrom-DiagnosticJson $version.Output
        if ($versions.'azure-cli' -isnot [string] -or $versions.'azure-cli' -cnotmatch '\A[0-9]+\.[0-9]+\.[0-9]+\z') { throw 'invalid-cli-version' }
        $evidence.Environment.AzureCli = $versions.'azure-cli'
        $evidence.Phases += @{ Phase = $phase; HttpStatus = $null; Status = 'pass' }
        $phase = 'token'
        $token = Get-AzureToken
        if (-not $token.Success) { throw $token.Category }
        $evidence.Phases += @{ Phase = $phase; HttpStatus = $null; Status = 'pass' }
        $phase = 'agent-card'
        $card = Test-EndpointAccessibility -Url $ServerUrl -Token $token.Token
        $evidence.Phases += @{ Phase = $phase; HttpStatus = $card.StatusCode; Status = 'failure' }
        if (-not $card.Success) { throw $card.Category }
        $evidence.Phases[-1].Status = 'pass'
        $evidence.Outcome = 'card-only-pass'
        if ($SendMessage) {
            $phase = 'send-message'
            $evidence.Request = @{
                Method = 'POST'; RpcMethod = 'SendMessage'; JsonRpc = '2.0'; SendMessage = $true
                Shape = 'params.message{messageId,role,parts:[{text}]};params.configuration{acceptedOutputModes,returnImmediately}'
                Prompt = if ($Prompt -ceq 'Reply with exactly: A2A diagnostic OK') { $Prompt } else { '[redacted custom prompt]' }
            }
            $rpc = Test-A2AMessageExchange -Url $ServerUrl -Token $token.Token -Prompt $Prompt
            $evidence.Phases += @{ Phase = $phase; HttpStatus = $rpc.StatusCode; Status = 'failure' }
            if (-not $rpc.Success) { throw $rpc.Category }
            $evidence.Phases[-1].Status = 'pass'
            $evidence.Reply.TextPresent = $true
            $evidence.Outcome = 'exchange-pass'
        }
        $evidence.ExitCode = 0
    } catch {
        $evidence.Outcome = 'failure'
        $evidence.ExitCode = if ($phase -eq 'arguments') { 2 } else { 1 }
        # Never serialize an exception: even local errors can contain credentials.
        $category = $_.Exception.Message
        $allowed = '\A(?:invalid-arguments|dns-failure|cli-(?:failure|unavailable|AADSTS[0-9]{5,10})|invalid-(?:json|token-json|cli-context|cli-version|card-shape|result-shape|message-shape|parts-shape|task-shape|artifact-shape)|unsupported-cli-identity|http-non-2xx|transport-failure|card-version-mismatch|rpc-envelope-mismatch|rpc-error|task-not-completed|missing-text-output)\z'
        if ($category -cnotmatch $allowed) { $category = 'unexpected-local-failure' }
        $evidence.FailureCategory = $category
        if ($evidence.Phases.Count -eq 0 -or $evidence.Phases[-1].Phase -ne $phase) {
            $evidence.Phases += @{ Phase = $phase; HttpStatus = $null; Status = 'failure' }
        }
        $evidence.Phases[-1].Category = $category
    }
    if ($EvidencePath) {
        try {
            $evidence | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $EvidencePath -Encoding utf8 -ErrorAction Stop
        } catch {
            $evidence.Outcome = 'failure'; $evidence.ExitCode = 1; $evidence.FailureCategory = 'evidence-write-failure'
            $evidence.Phases += @{ Phase = 'evidence'; HttpStatus = $null; Status = 'failure'; Category = 'evidence-write-failure' }
        }
    }
    return $evidence
}

if ($MyInvocation.InvocationName -ne '.') {
    $result = Run-Diagnostics @PSBoundParameters
    Write-Host ("A2A diagnostic: {0}; exit {1}" -f $result.Outcome, $result.ExitCode)
    Write-Host 'Identity context: Azure CLI current login, not the deployed caller. RBAC: not assessed (target project/agent endpoint permission).'
    foreach ($item in $result.Phases) {
        $http = if ($null -ne $item.HttpStatus) { " HTTP $($item.HttpStatus)" } else { '' }
        $category = if ($item.Category) { " $($item.Category)" } else { '' }
        Write-Host ("{0}: {1}{2}{3}" -f $item.Phase, $item.Status, $http, $category)
    }
    exit $result.ExitCode
}
