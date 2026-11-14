#requires -Version 7.0
param([string]$ChildScenario)
$ErrorActionPreference = 'Stop'
$diagnosticPath = Join-Path (Split-Path $PSScriptRoot -Parent) 'a2a_diagnostic.ps1'
$script:secret = 'SENTINEL_SECRET_MUST_NOT_LEAK'
$script:endpoint = 'https://example.services.ai.azure.com/api/projects/project-name/agents/agent-name/endpoint/protocols/a2a'

# Dot-sourcing must not prompt, invoke az/HTTP/DNS, print a summary, or exit.
function az { throw 'Dot-source called Azure CLI' }
function Invoke-WebRequest { throw 'Dot-source called HTTP' }
$loaded = @(. $diagnosticPath *>&1)
if ($loaded.Count -ne 0) { throw 'Dot-source produced output' }
$script:realCli = ${function:Invoke-AzureCli}
$script:passed = 0
$script:failed = 0

function Assert {
    param([bool]$Condition, [string]$Label)
    if (-not $Condition) { throw $Label }
}

function Reset-Mocks {
    $script:dnsOk = $true
    $script:cliFailure = ''
    $script:cliShape = ''
    $script:identityType = 'user'
    $script:card = @{ name = 'Diagnostic agent'; protocolVersion = '1.0' }
    $script:cardStatus = 200
    $script:rpcStatus = 200
    $script:cardContent = $null
    $script:rpcContent = $null
    $script:httpThrow = ''
    $script:throwStatus = $null
    $script:rpcMode = 'message'
    $script:taskState = 'TASK_STATE_COMPLETED'
    $script:mutate = $null
    $script:requests = [System.Collections.Generic.List[object]]::new()
    $script:cliCalls = [System.Collections.Generic.List[object]]::new()
}

function Test-DNSResolution {
    param([string]$Hostname)
    return $script:dnsOk
}

function Invoke-AzureCli {
    param([string[]]$Arguments)
    $script:cliCalls.Add($Arguments)
    $kind = if ($Arguments[0] -eq 'version') { 'version' } elseif ($Arguments[1] -eq 'show') { 'context' } else { 'token' }
    if ($script:cliFailure -eq $kind) { return @{ ExitCode = 9; Output = $script:secret; Category = 'cli-failure' } }
    if ($script:cliShape -eq $kind) { return @{ ExitCode = 0; Output = $script:secret } }
    $output = switch ($kind) {
        context { @{ user = @{ type = $script:identityType; name = $script:secret }; id = $script:secret } | ConvertTo-Json -Depth 5 }
        version { @{ 'azure-cli' = '2.80.0'; extensions = @{ sentinel = $script:secret } } | ConvertTo-Json }
        token { @{ accessToken = $script:secret } | ConvertTo-Json }
    }
    return @{ ExitCode = 0; Output = $output }
}

function Invoke-WebRequest {
    [CmdletBinding()]
    param($Uri, $Method, $Headers, $MaximumRedirection, $SkipHttpErrorCheck, $TimeoutSec, $Body, $ContentType)
    Assert ($MaximumRedirection -eq 0) 'Redirects were not disabled'
    Assert ($Headers.Authorization -ceq "Bearer $script:secret") 'Missing bearer token'
    Assert ($Headers.'A2A-Version' -ceq '1.0') 'Missing explicit v1 negotiation'
    Assert ($SkipHttpErrorCheck -eq $true) 'HTTP error handling not explicit'
    $script:requests.Add(@{ Uri = $Uri; Method = $Method; Body = $Body })
    if ($script:httpThrow) {
        if ($script:httpThrow -eq 'redirect') {
            # Reproduce PS 7's output-then-terminating-error semantics, rather
            # than an HttpResponseException (which carries Response.StatusCode).
            Write-Output @{ StatusCode = 302; Content = $script:secret }
            $errorRecord = [System.Management.Automation.ErrorRecord]::new(
                [InvalidOperationException]::new($script:secret),
                'MaximumRedirectExceeded',
                [System.Management.Automation.ErrorCategory]::InvalidOperation,
                [System.Net.Http.HttpRequestMessage]::new()
            )
            $PSCmdlet.WriteError($errorRecord)
            return
        }
        $exception = [Exception]::new($script:secret)
        if ($null -ne $script:throwStatus) {
            Add-Member -InputObject $exception -MemberType NoteProperty -Name Response -Value @{ StatusCode = $script:throwStatus }
        }
        throw $exception
    }
    if ($Method -eq 'GET') {
        Assert ($Uri -ceq "$script:endpoint/agentCard/v1.0") 'GET incorrectly used base endpoint'
        $content = if ($null -ne $script:cardContent) { $script:cardContent } else { $script:card | ConvertTo-Json -Depth 20 -Compress }
        return @{ StatusCode = $script:cardStatus; Content = $content }
    }
    Assert ($Method -eq 'POST' -and $Uri -ceq $script:endpoint) 'RPC used incorrect endpoint/method'
    Assert ($ContentType -ceq 'application/json') 'Missing JSON ContentType'
    $request = ConvertFrom-Json $Body -AsHashtable
    Assert ($request.jsonrpc -ceq '2.0' -and $request.method -ceq 'SendMessage') 'Wrong JSON-RPC version or method'
    Assert ($request.id -match '^[0-9a-f-]{36}$') 'Missing request ID'
    Assert ($request.params.message.messageId -match '^[0-9a-f-]{36}$') 'Missing message ID'
    Assert ($request.params.message.role -ceq 'ROLE_USER') 'Wrong user role'
    Assert ($request.params.message.parts -is [array] -and $request.params.message.parts.Count -eq 1) 'Wrong request parts'
    Assert ($request.params.configuration.acceptedOutputModes -is [array]) 'Missing output modes'
    Assert ($request.params.configuration.acceptedOutputModes[0] -ceq 'text/plain') 'Wrong output modes'
    Assert ($request.params.configuration.returnImmediately -ceq $false) 'Request should wait for terminal response'
    $response = @{
        jsonrpc = '2.0'; id = $request.id
        result = @{
            message = @{ messageId = 'reply-id'; role = 'ROLE_AGENT'; parts = @(@{ text = $script:secret }) }
        }
    }
    switch ($script:rpcMode) {
        task {
            $response.result = @{
                task = @{
                    id = 'task-id'; contextId = 'context-id'; status = @{ state = $script:taskState }
                    artifacts = @(@{ artifactId = 'artifact-id'; parts = @(@{ text = $script:secret }) })
                }
            }
        }
        error { $response.Remove('result'); $response.error = @{ code = -32603; message = $script:secret; data = $script:secret } }
        old { $response.result = @{ id = 'old-task'; status = @{ state = 'completed' }; artifacts = @() } }
    }
    if ($script:mutate) { & $script:mutate $response }
    $content = if ($null -ne $script:rpcContent) { $script:rpcContent } else { $response | ConvertTo-Json -Depth 30 -Compress }
    return @{ StatusCode = $script:rpcStatus; Content = $content }
}

function Invoke-Probe {
    param([switch]$SendMessage, [string]$EvidencePath, [string]$Prompt = 'Reply with exactly: A2A diagnostic OK')
    $result = Run-Diagnostics -ServerUrl $script:endpoint -SendMessage:$SendMessage -EvidencePath $EvidencePath -Prompt $Prompt
    Assert (($result | ConvertTo-Json -Depth 30) -notmatch $script:secret) 'Sentinel leaked into evidence'
    return $result
}

function Case {
    param([string]$Name, [scriptblock]$Body)
    Reset-Mocks
    try {
        & $Body
        $script:passed++
        Write-Host "PASS $Name"
    } catch {
        $script:failed++
        # Assertion names are local; never print remote/native exception messages.
        Write-Host "FAIL $Name"
    }
}

if ($ChildScenario) {
    Reset-Mocks
    if ($ChildScenario -eq 'runtime') { $script:cardStatus = 500 }
    elseif ($ChildScenario -ne 'pass') { exit 2 }
    $result = Invoke-Probe
    Write-Host ($result | ConvertTo-Json -Depth 20 -Compress)
    exit $result.ExitCode
}

Case 'dot-source loads silently with no services' { Assert ($loaded.Count -eq 0) 'Unexpected output' }
Case 'card-only pass is not exchange/RBAC success' {
    $r = Invoke-Probe
    Assert ($r.ExitCode -eq 0 -and $r.Outcome -eq 'card-only-pass') 'Card outcome'
    Assert ($script:requests.Count -eq 1 -and -not $r.Reply.TextPresent) 'Default should not send'
    Assert (-not $r.RBAC.Verified -and -not $r.IdentityContext.DeployedCallerAssessed) 'Incorrect RBAC/caller claim'
    Assert ($r.IdentityContext.Source -ceq 'azure-cli current login') 'Wrong identity source'
    $tokenArgs = $script:cliCalls[2]
    Assert ($tokenArgs[3] -ceq 'https://ai.azure.com') 'Wrong token audience'
}
Case 'backwards name parameters build correct card endpoint' {
    $r = Run-Diagnostics -AccountName example -ProjectId project-name -SubAgentId agent-name
    Assert ($r.ExitCode -eq 0) 'Name parameter outcome'
}
Case 'service principal is CLI context not deployed caller' {
    $script:identityType = 'servicePrincipal'
    $r = Invoke-Probe
    Assert ($r.ExitCode -eq 0 -and $r.IdentityContext.Type -ceq 'service principal') 'Incorrect SP identity'
}
Case 'supportedInterfaces v1 card' {
    $script:card = @{ name = 'agent'; supportedInterfaces = @(@{ protocolVersion = '1.0'; url = $script:endpoint; protocolBinding = 'JSONRPC' }) }
    Assert ((Invoke-Probe).ExitCode -eq 0) 'v1 interface card'
}
Case 'message exchange uses v1 wrapper and synthetic prompt' {
    $r = Invoke-Probe -SendMessage
    Assert ($r.ExitCode -eq 0 -and $r.Outcome -eq 'exchange-pass' -and $r.Reply.TextPresent) 'Exchange outcome'
    Assert ($r.Reply.Text -ceq 'REDACTED') 'Reply not redacted'
    $request = ConvertFrom-Json $script:requests[1].Body -AsHashtable
    Assert ($request.params.message.parts[0].text -ceq 'Reply with exactly: A2A diagnostic OK') 'Unsafe default prompt'
}
Case 'completed task with text artifacts passes' {
    $script:rpcMode = 'task'
    Assert ((Invoke-Probe -SendMessage).ExitCode -eq 0) 'Completed task outcome'
}
Case 'public card helper returns sanitized response and status' {
    $r = Test-EndpointAccessibility -Url $script:endpoint -Token $script:secret
    Assert ($r.Success -and $r.Accessible -and $r.StatusCode -eq 200 -and $r.Response.CardValid) 'Helper contract'
    Assert (($r | ConvertTo-Json -Depth 20) -notmatch $script:secret) 'Card helper leaked'
}
Case 'public exchange helper redacts response' {
    $r = Test-A2AMessageExchange -Url $script:endpoint -Token $script:secret
    Assert ($r.Success -and $r.StatusCode -eq 200 -and $r.Response.TextPresent) 'Exchange helper contract'
    Assert (($r | ConvertTo-Json -Depth 20) -notmatch $script:secret) 'Exchange helper leaked'
}
Case 'public exchange helper rejects blank prompt before HTTP' {
    $r = Test-A2AMessageExchange -Url $script:endpoint -Token $script:secret -Prompt ''
    Assert (-not $r.Success -and $script:requests.Count -eq 0) 'Blank helper prompt accepted'
}
foreach ($status in @(401, 403, 404, 405, 429, 500, 599, 301, 302, 307, 308)) {
    Case "card HTTP $status fails (original false-green regression)" {
        $script:cardStatus = $status
        $r = Invoke-Probe
        Assert ($r.ExitCode -eq 1 -and $r.Outcome -eq 'failure' -and $r.FailureCategory -ceq 'http-non-2xx') 'False success'
        Assert ($r.Phases[-1].HttpStatus -eq $status) 'HTTP status missing'
    }
    Case "RPC HTTP $status fails" {
        $script:rpcStatus = $status
        Assert ((Invoke-Probe -SendMessage).ExitCode -eq 1) 'RPC false success'
    }
}
Case 'transport exception does not leak secret' {
    $script:httpThrow = 'transport'
    $r = Invoke-Probe
    Assert ($r.ExitCode -eq 1 -and $r.FailureCategory -ceq 'transport-failure') 'Transport outcome'
}
Case 'thrown HTTP exception records only safe status' {
    $script:httpThrow = 'http'; $script:throwStatus = 403
    $r = Invoke-Probe
    Assert ($r.ExitCode -eq 1 -and $r.Phases[-1].HttpStatus -eq 403) 'Exception status'
}
foreach ($helper in @('Test-EndpointAccessibility', 'Test-A2AMessageExchange')) {
    Case "PS7 emitted redirect response retains HTTP302 in $helper" {
        $script:httpThrow = 'redirect'
        $r = & $helper -Url $script:endpoint -Token $script:secret
        Assert (-not $r.Success -and $r.StatusCode -eq 302 -and $r.Category -ceq 'http-non-2xx') 'Redirect status lost'
        Assert ($script:requests.Count -eq 1) 'Redirect followed'
        Assert (($r | ConvertTo-Json -Depth 20) -notmatch $script:secret) 'Redirect leaked'
    }
}
Case 'DNS failure stops before CLI and HTTP' {
    $script:dnsOk = $false
    $r = Invoke-Probe
    Assert ($r.ExitCode -eq 1 -and $script:requests.Count -eq 0 -and $script:cliCalls.Count -eq 0) 'DNS not fail-fast'
}
foreach ($content in @('{', 'null', '[]', '"sentinel"', 'true', '')) {
    Case "malformed or non-object card JSON [$content]" {
        $script:cardContent = $content
        Assert ((Invoke-Probe).ExitCode -eq 1) 'Card JSON false success'
    }
    Case "malformed or non-object RPC JSON [$content]" {
        $script:rpcContent = $content
        Assert ((Invoke-Probe -SendMessage).ExitCode -eq 1) 'RPC JSON false success'
    }
}
foreach ($badCard in @(
    @{ name = 'a'; protocolVersion = '0.3' },
    @{ name = 'a' },
    @{ protocolVersion = '1.0' },
    @{ name = 'a'; supportedInterfaces = @(@{ protocolVersion = '0.3' }) },
    @{ name = 'a'; protocolVersion = '1.0'; supportedInterfaces = '1.0' },
    @{ name = 'a'; supportedInterfaces = @('1.0') },
    @{ name = 'a'; protocolVersion = '0.3'; supportedInterfaces = @(@{ protocolVersion = '1.0' }) }
)) {
    Case "invalid/mismatched card $($badCard | ConvertTo-Json -Compress -Depth 5)" {
        $script:card = $badCard
        Assert ((Invoke-Probe).ExitCode -eq 1) 'Invalid card false success'
    }
}
foreach ($url in @(
    '', 'http://example.services.ai.azure.com/api/projects/p/agents/a/endpoint/protocols/a2a',
    "$script:endpoint/", "$script:endpoint/agentCard/v1.0", "$script:endpoint?api-version=1", "$script:endpoint#fragment",
    "$script:endpoint?", "$script:endpoint#", "$script:endpoint/../a2a",
    ($script:endpoint -replace 'example.services', 'example.services.evil'),
    ($script:endpoint -replace 'https://', 'https://secret@'),
    ($script:endpoint -replace '.com/api', '.com:443/api'),
    ($script:endpoint -replace '.com/api', '.com:8443/api'),
    ($script:endpoint -replace 'project-name', '%2e%2e'),
    ($script:endpoint -replace 'agent-name', 'a%2Fb'),
    ($script:endpoint -replace 'agent-name', '..'),
    ($script:endpoint -replace 'agent-name', "agent`nname"),
    "$script:endpoint$script:secret"
)) {
    Case 'invalid URL is rejected before services' {
        $r = Run-Diagnostics -ServerUrl $url
        Assert ($r.ExitCode -eq 2 -and $script:requests.Count -eq 0 -and $script:cliCalls.Count -eq 0) 'Invalid URL not rejected'
        Assert (($r | ConvertTo-Json -Depth 20) -notmatch $script:secret) 'URL leaked'
    }
}
Case 'conflicting URL and names rejected' {
    $r = Run-Diagnostics -ServerUrl $script:endpoint -AccountName example
    Assert ($r.ExitCode -eq 2) 'Conflicting target accepted'
}
Case 'unknown remaining arguments rejected' {
    Assert ((Run-Diagnostics -ServerUrl $script:endpoint -RemainingArguments '-Unknown').ExitCode -eq 2) 'Unknown argument accepted'
}
Case 'empty prompt rejected' { Assert ((Invoke-Probe -SendMessage -Prompt ' ').ExitCode -eq 2) 'Blank prompt accepted' }
foreach ($kind in @('context', 'version', 'token')) {
    Case "CLI $kind native failure rejects even nonempty output" {
        $script:cliFailure = $kind
        $r = Invoke-Probe
        Assert ($r.ExitCode -eq 1 -and $script:requests.Count -eq 0) 'CLI failed but continued'
    }
    Case "CLI $kind malformed JSON fails" {
        $script:cliShape = $kind
        Assert ((Invoke-Probe).ExitCode -eq 1) 'Bad CLI JSON accepted'
    }
}
Case 'unknown CLI identity not mislabeled user' {
    $script:identityType = $script:secret
    Assert ((Invoke-Probe).ExitCode -eq 1) 'Unknown CLI context accepted'
}
Case 'native CLI wrapper checks real process exit, redacts stdout/stderr' {
    $native = & $script:realCli -Executable (Join-Path $PSHOME 'pwsh.exe') -Arguments @(
        '-NoProfile', '-Command', "[Console]::Out.WriteLine('$script:secret'); [Console]::Error.WriteLine('$script:secret'); exit 9"
    )
    Assert ($native.ExitCode -eq 9) 'Native exit not retained'
    Assert (($native | ConvertTo-Json) -notmatch $script:secret) 'Native failure leaked'
}
Case 'missing native CLI is safe' {
    $native = & $script:realCli -Executable 'not-a-real-a2a-cli'
    Assert ($native.ExitCode -ne 0 -and -not $native.Output) 'Missing CLI accepted'
}
Case 'RPC HTTP200 error fails without printing remote error' {
    $script:rpcMode = 'error'
    $r = Invoke-Probe -SendMessage
    Assert ($r.ExitCode -eq 1 -and $r.FailureCategory -ceq 'rpc-error') 'RPC error false success'
}
Case 'old v0.3 result shape rejected' {
    $script:rpcMode = 'old'
    Assert ((Invoke-Probe -SendMessage).ExitCode -eq 1) 'Old result accepted'
}
foreach ($state in @('TASK_STATE_FAILED', 'TASK_STATE_CANCELED', 'TASK_STATE_REJECTED', 'TASK_STATE_AUTH_REQUIRED',
    'TASK_STATE_INPUT_REQUIRED', 'TASK_STATE_SUBMITTED', 'TASK_STATE_WORKING', 'TASK_STATE_UNSPECIFIED', 'completed', '')) {
    Case "nonterminal/interrupted task $state fails" {
        $script:rpcMode = 'task'; $script:taskState = $state
        Assert ((Invoke-Probe -SendMessage).ExitCode -eq 1) 'Noncompleted task false success'
    }
}
$messageMutations = @(
    { param($r) $r.id = 'wrong' },
    { param($r) $r.jsonrpc = '1.0' },
    { param($r) $r.jsonrpc = @('2.0') },
    { param($r) $r.Remove('id') },
    { param($r) $r.result = $null },
    { param($r) $r.result = @{} },
    { param($r) $r.result.task = @{} },
    { param($r) $r.result.message = 'bad' },
    { param($r) $r.result.message.Remove('messageId') },
    { param($r) $r.result.message.role = 'ROLE_USER' },
    { param($r) $r.result.message.role = @('ROLE_AGENT') },
    { param($r) $r.result.message.parts = @() },
    { param($r) $r.result.message.parts = @{ text = 'not array' } },
    { param($r) $r.result.message.parts = @(@{ text = '' }) },
    { param($r) $r.result.message.parts = @(@{ text = 7 }) },
    { param($r) $r.result.message.parts = @('bad') },
    { param($r) $r.result.message.parts = @(@{ text = 'ok'; data = @{} }) },
    { param($r) $r.result.message.parts = @(@{ kind = 'text'; text = '' }) },
    { param($r) $r.result.message.parts = @(@{ text = 'ok' }, @{ unexpected = 'bad' }) }
)
foreach ($mutation in $messageMutations) {
    Case "invalid message/envelope shape $mutation" {
        $script:mutate = $mutation
        Assert ((Invoke-Probe -SendMessage).ExitCode -eq 1) 'Invalid message shape accepted'
    }
}
$taskMutations = @(
    { param($r) $r.result.task.Remove('id') },
    { param($r) $r.result.task.Remove('contextId') },
    { param($r) $r.result.task.status = 'bad' },
    { param($r) $r.result.task.status.Remove('state') },
    { param($r) $r.result.task.artifacts = @() },
    { param($r) $r.result.task.artifacts = @(@{ artifactId = 'a'; parts = @(@{ text = ' ' }) }) },
    { param($r) $r.result.task.artifacts = @(@{ parts = @(@{ text = 'ok' }) }) },
    { param($r) $r.result.task.artifacts = @('bad') },
    { param($r) $r.result.task.artifacts = @(@{ artifactId = 'a'; parts = @(@{ data = @{} }) }) },
    { param($r) $r.result.task.artifacts = @(@{ artifactId = 'a'; parts = @(@{ text = 'ok' }, @{ text = $null }) }) }
)
foreach ($mutation in $taskMutations) {
    Case "invalid completed-task output $mutation" {
        $script:rpcMode = 'task'; $script:mutate = $mutation
        Assert ((Invoke-Probe -SendMessage).ExitCode -eq 1) 'Invalid task shape accepted'
    }
}
Case 'evidence file success only contains allowlist, never secret/custom prompt/reply' {
    $path = Join-Path $PSScriptRoot '.diagnostic-test-evidence.json'
    try {
        $r = Invoke-Probe -SendMessage -EvidencePath $path -Prompt $script:secret
        Assert ($r.ExitCode -eq 0) 'Evidence exchange failed'
        $text = Get-Content -LiteralPath $path -Raw
        Assert ($text -notmatch $script:secret -and $text -match 'REDACTED') 'Evidence leaked'
        $file = ConvertFrom-Json $text -AsHashtable
        Assert ($file.Endpoint -ceq '[redacted Foundry target]' -and $file.Reply.TextPresent) 'Evidence missing safe fields'
        Assert ($file.Request.Prompt -ceq '[redacted custom prompt]') 'Custom prompt exposed'
    } finally { Remove-Item -LiteralPath $path -ErrorAction SilentlyContinue }
}
Case 'HTTP failure evidence redacts remote body and credentials' {
    $path = Join-Path $PSScriptRoot '.diagnostic-test-evidence.json'
    try {
        $script:cardStatus = 500; $script:cardContent = $script:secret
        $r = Invoke-Probe -EvidencePath $path
        Assert ($r.ExitCode -eq 1) 'HTTP evidence outcome'
        Assert ((Get-Content -LiteralPath $path -Raw) -notmatch $script:secret) 'Failure evidence leaked'
    } finally { Remove-Item -LiteralPath $path -ErrorAction SilentlyContinue }
}
Case 'evidence write failure is nonzero and sanitized' {
    $r = Invoke-Probe -EvidencePath (Join-Path $PSScriptRoot "$script:secret\missing\file.json")
    Assert ($r.ExitCode -eq 1 -and $r.FailureCategory -ceq 'evidence-write-failure') 'Evidence write failure ignored'
}
foreach ($scenario in @('runtime', 'pass')) {
    Case "subprocess mocked $scenario retains exit status and redaction" {
        $text = & (Join-Path $PSHOME 'pwsh.exe') -NoProfile -File $PSCommandPath -ChildScenario $scenario 2>&1
        $code = $LASTEXITCODE
        $expected = if ($scenario -eq 'runtime') { 1 } else { 0 }
        Assert ($code -eq $expected) 'Wrong subprocess exit'
        Assert (($text -join "`n") -notmatch $script:secret) 'Subprocess output leaked'
    }
}
Case 'executable missing arguments exits 2 without prompting or services' {
    $text = & (Join-Path $PSHOME 'pwsh.exe') -NoProfile -File $diagnosticPath 2>&1
    Assert ($LASTEXITCODE -eq 2) 'Executable invalid args exit'
    Assert (($text -join "`n") -notmatch $script:secret) 'Executable leaked'
}
Case 'executable invalid URL exits 2 and redacts user input' {
    $text = & (Join-Path $PSHOME 'pwsh.exe') -NoProfile -File $diagnosticPath -ServerUrl "https://$script:secret.evil" 2>&1
    Assert ($LASTEXITCODE -eq 2) 'Executable invalid URL exit'
    Assert (($text -join "`n") -notmatch $script:secret) 'Executable URL leaked'
}

Write-Host "$script:passed passed; $script:failed failed; live Azure exchanges: 0"
if ($script:failed -gt 0) { exit 1 }
exit 0
