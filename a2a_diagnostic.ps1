# Foundry A2A Diagnostic Script
# Helps gather configuration info and test A2A connectivity

param(
    [Parameter(Mandatory=$false)]
    [string]$AccountName,
    
    [Parameter(Mandatory=$false)]
    [string]$ProjectId,
    
    [Parameter(Mandatory=$false)]
    [string]$SubAgentId,
    
    [Parameter(Mandatory=$false)]
    [string]$MainAgentId = "main-agent",
    
    [Parameter(Mandatory=$false)]
    [switch]$Interactive
)

function Write-Section {
    param([string]$Title)
    Write-Host "`n" -ForegroundColor White
    Write-Host "=" * 80 -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "=" * 80 -ForegroundColor Cyan
}

function Write-Subsection {
    param([string]$Title)
    Write-Host "`n$Title" -ForegroundColor Yellow
    Write-Host "-" * 40 -ForegroundColor Yellow
}

function Test-URLValidity {
    param([string]$Url, [string]$Context)
    
    $result = @{
        Valid = $false
        Errors = @()
        Warnings = @()
    }
    
    if ([string]::IsNullOrWhiteSpace($Url)) {
        $result.Errors += "URL is empty"
        return $result
    }
    
    # Check for trailing slash
    if ($Url.EndsWith('/')) {
        $result.Warnings += "URL has trailing slash (can cause path matching issues)"
    }
    
    # Check URL format
    if (-not ($Url -match '^https?://')) {
        $result.Errors += "URL missing http/https scheme"
        return $result
    }
    
    # Parse URL
    try {
        $uri = [System.Uri]$Url
        $result.Valid = $true
    } catch {
        $result.Errors += "Invalid URL format: $_"
    }
    
    return $result
}

function Test-A2AServerURL {
    param([string]$Url)
    
    # Expected format: https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a
    $pattern = '^https://([^.]+)\.services\.ai\.azure\.com/api/projects/([^/]+)/agents/([^/]+)/endpoint/protocols/a2a/?$'
    
    if ($Url -match $pattern) {
        return @{
            Valid = $true
            Account = $Matches[1]
            Project = $Matches[2]
            Agent = $Matches[3]
        }
    }
    
    return @{
        Valid = $false
        Error = "URL does not match A2A endpoint pattern"
    }
}

function Get-AzureToken {
    param([string]$Resource = "https://cognitiveservices.azure.com/")
    
    try {
        $token = az account get-access-token --resource $Resource --query accessToken -o tsv 2>$null
        if ($token) {
            return @{
                Success = $true
                Token = $token
            }
        } else {
            return @{
                Success = $false
                Error = "Failed to acquire token"
            }
        }
    } catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
        }
    }
}

function Test-EndpointAccessibility {
    param(
        [string]$Url,
        [string]$Token
    )
    
    $result = @{
        Accessible = $false
        StatusCode = $null
        Response = $null
        Error = $null
    }
    
    try {
        $headers = @{
            Authorization = "Bearer $Token"
            "Content-Type" = "application/json"
        }
        
        $response = Invoke-WebRequest -Uri $Url -Headers $headers -Method GET -ErrorAction Stop
        
        $result.Accessible = $true
        $result.StatusCode = $response.StatusCode
        
        if ($response.Content) {
            $result.Response = $response.Content | ConvertFrom-Json
        }
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.Value
        $result.StatusCode = $statusCode
        $result.Accessible = $false
        $result.Error = $_.Exception.Message
        
        if ($statusCode -eq 404) {
            $result.Error = "404 Not Found - Endpoint may not be deployed or accessible"
        } elseif ($statusCode -eq 401) {
            $result.Error = "401 Unauthorized - Authentication token invalid or expired"
        } elseif ($statusCode -eq 403) {
            $result.Error = "403 Forbidden - Check RBAC permissions"
        }
    }
    
    return $result
}

function Get-RBACAssignments {
    param([string]$ProjectScope)
    
    try {
        $assignments = az role assignment list --scope $ProjectScope --output json 2>$null | ConvertFrom-Json
        return @{
            Success = $true
            Assignments = $assignments
        }
    } catch {
        return @{
            Success = $false
            Error = $_.Exception.Message
        }
    }
}

function Test-DNSResolution {
    param([string]$Hostname)
    
    try {
        $result = [System.Net.Dns]::GetHostAddresses($Hostname)
        if ($result) {
            return @{
                Resolved = $true
                IPs = $result | ForEach-Object { $_.IPAddressToString }
            }
        }
    } catch {
        # DNS resolution failed
    }
    
    return @{
        Resolved = $false
        Error = "Cannot resolve hostname"
    }
}

function Get-InteractiveInput {
    Write-Section "FOUNDRY A2A DIAGNOSTIC - CONFIGURATION INPUT"
    
    $AccountName = Read-Host "Enter your Foundry account name (e.g., myaccount from myaccount.services.ai.azure.com)"
    $ProjectId = Read-Host "Enter your project ID"
    $SubAgentId = Read-Host "Enter the sub-agent ID (agent with A2A endpoint)"
    $MainAgentId = Read-Host "Enter the main agent ID (agent using A2A tool) [default: main-agent]"
    
    if ([string]::IsNullOrWhiteSpace($MainAgentId)) {
        $MainAgentId = "main-agent"
    }
    
    return @{
        AccountName = $AccountName
        ProjectId = $ProjectId
        SubAgentId = $SubAgentId
        MainAgentId = $MainAgentId
    }
}

function Run-Diagnostics {
    param(
        [string]$AccountName,
        [string]$ProjectId,
        [string]$SubAgentId,
        [string]$MainAgentId
    )
    
    # Verify inputs
    if ([string]::IsNullOrWhiteSpace($AccountName) -or 
        [string]::IsNullOrWhiteSpace($ProjectId) -or 
        [string]::IsNullOrWhiteSpace($SubAgentId)) {
        
        Write-Host "Error: Missing required parameters" -ForegroundColor Red
        Write-Host "Usage: .\a2a_diagnostic.ps1 -AccountName <account> -ProjectId <project> -SubAgentId <agent>" -ForegroundColor Yellow
        return
    }
    
    # Construct URLs
    $baseUrl = "https://$AccountName.services.ai.azure.com/api/projects/$ProjectId/agents"
    $a2aEndpointUrl = "$baseUrl/$SubAgentId/endpoint/protocols/a2a"
    $agentCardUrl = "$baseUrl/$SubAgentId/agentCard/v1.0"
    
    Write-Section "FOUNDRY A2A DIAGNOSTIC REPORT"
    
    # 1. Configuration Display
    Write-Subsection "1. CONFIGURATION"
    Write-Host "Account Name: $AccountName"
    Write-Host "Project ID: $ProjectId"
    Write-Host "Sub-Agent ID: $SubAgentId"
    Write-Host "Main Agent ID: $MainAgentId"
    Write-Host "A2A Endpoint URL: $a2aEndpointUrl"
    Write-Host "Agent Card URL: $agentCardUrl"
    
    # 2. URL Validation
    Write-Subsection "2. URL VALIDATION"
    
    $urlTest = Test-A2AServerURL -Url $a2aEndpointUrl
    if ($urlTest.Valid) {
        Write-Host "✓ A2A Endpoint URL format is valid" -ForegroundColor Green
        Write-Host "  - Account: $($urlTest.Account)"
        Write-Host "  - Project: $($urlTest.Project)"
        Write-Host "  - Agent: $($urlTest.Agent)"
    } else {
        Write-Host "✗ A2A Endpoint URL format is invalid" -ForegroundColor Red
        Write-Host "  Expected: https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a"
        Write-Host "  Actual: $a2aEndpointUrl"
    }
    
    # 3. DNS Resolution
    Write-Subsection "3. DNS RESOLUTION"
    
    $hostname = "$AccountName.services.ai.azure.com"
    $dnsTest = Test-DNSResolution -Hostname $hostname
    
    if ($dnsTest.Resolved) {
        Write-Host "✓ DNS resolution successful for $hostname" -ForegroundColor Green
        Write-Host "  IPs: $($dnsTest.IPs -join ', ')"
    } else {
        Write-Host "✗ DNS resolution failed for $hostname" -ForegroundColor Red
        Write-Host "  This could indicate network/firewall issues"
    }
    
    # 4. Authentication & Token
    Write-Subsection "4. AUTHENTICATION & TOKEN"
    
    $tokenResult = Get-AzureToken
    if ($tokenResult.Success) {
        Write-Host "✓ Successfully acquired Azure authentication token" -ForegroundColor Green
        Write-Host "  Token acquired for resource: https://cognitiveservices.azure.com/"
    } else {
        Write-Host "✗ Failed to acquire token" -ForegroundColor Red
        Write-Host "  Error: $($tokenResult.Error)"
        Write-Host "  Fix: Ensure you're logged in with 'az login'"
        return
    }
    
    $token = $tokenResult.Token
    
    # 5. Endpoint Accessibility
    Write-Subsection "5. ENDPOINT ACCESSIBILITY TEST"
    
    $endpointTest = Test-EndpointAccessibility -Url $a2aEndpointUrl -Token $token
    
    if ($endpointTest.Accessible) {
        Write-Host "✓ A2A Endpoint is accessible" -ForegroundColor Green
        Write-Host "  Status Code: $($endpointTest.StatusCode)"
        if ($endpointTest.Response) {
            Write-Host "  Response Preview:"
            Write-Host "  $(($endpointTest.Response | ConvertTo-Json -Depth 2 -Compress).Substring(0, [Math]::Min(100, ($endpointTest.Response | ConvertTo-Json -Depth 2 -Compress).Length)))..."
        }
    } else {
        Write-Host "✗ A2A Endpoint is not accessible" -ForegroundColor Red
        Write-Host "  Status Code: $($endpointTest.StatusCode)"
        Write-Host "  Error: $($endpointTest.Error)"
        Write-Host "  "
        
        if ($endpointTest.StatusCode -eq 404) {
            Write-Host "  Possible causes:" -ForegroundColor Yellow
            Write-Host "    - Endpoint not deployed on sub-agent"
            Write-Host "    - A2A protocol not enabled on agent"
            Write-Host "    - URL format incorrect"
        } elseif ($endpointTest.StatusCode -eq 401) {
            Write-Host "  Possible causes:" -ForegroundColor Yellow
            Write-Host "    - Authentication token expired"
            Write-Host "    - Wrong resource scope for token"
            Write-Host "    - Service principal lacks permissions"
        } elseif ($endpointTest.StatusCode -eq 403) {
            Write-Host "  Possible causes:" -ForegroundColor Yellow
            Write-Host "    - RBAC role not assigned to managed identity"
            Write-Host "    - Missing 'Cognitive Services User' role"
        }
    }
    
    # 6. RBAC Check
    Write-Subsection "6. RBAC ROLE ASSIGNMENTS"
    
    $projectScope = "/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.CognitiveServices/accounts/$AccountName"
    Write-Host "Note: To check RBAC assignments, run:" -ForegroundColor Cyan
    Write-Host "  az role assignment list --scope <project-scope> --output table"
    Write-Host ""
    Write-Host "Look for these roles:" -ForegroundColor Cyan
    Write-Host "  ✓ Cognitive Services User"
    Write-Host "  ✓ Contributor"
    Write-Host "  ✓ Owner"
    
    # 7. Recommendations
    Write-Subsection "7. DIAGNOSTIC SUMMARY & RECOMMENDATIONS"
    
    $issues = @()
    
    if (-not $urlTest.Valid) {
        $issues += "A2A Endpoint URL format is incorrect - fix URL format"
    }
    
    if (-not $dnsTest.Resolved) {
        $issues += "DNS resolution failed - check network/firewall connectivity"
    }
    
    if (-not $endpointTest.Accessible) {
        if ($endpointTest.StatusCode -eq 404) {
            $issues += "Endpoint returns 404 - verify A2A is enabled on sub-agent"
        } elseif ($endpointTest.StatusCode -eq 401) {
            $issues += "Authentication failed (401) - verify token and permissions"
        } elseif ($endpointTest.StatusCode -eq 403) {
            $issues += "Access denied (403) - verify RBAC role assignments"
        }
    }
    
    if ($issues.Count -eq 0) {
        Write-Host "✅ All diagnostic checks passed!" -ForegroundColor Green
        Write-Host ""
        Write-Host "Configuration appears to be correct. If you're still experiencing issues:"
        Write-Host "  1. Check detailed error messages in the portal"
        Write-Host "  2. Review Application Insights logs"
        Write-Host "  3. Open an Azure Support ticket with these diagnostic results"
    } else {
        Write-Host "⚠️  Issues found:" -ForegroundColor Red
        foreach ($issue in $issues) {
            Write-Host "  • $issue" -ForegroundColor Red
        }
        Write-Host ""
        Write-Host "Next steps:"
        Write-Host "  1. Review the QUICK_REFERENCE.md for specific error fixes"
        Write-Host "  2. Run the suggested fix commands"
        Write-Host "  3. Re-run this diagnostic to verify fixes"
    }
    
    Write-Host "`n" -ForegroundColor White
    Write-Host "=" * 80 -ForegroundColor Cyan
    Write-Host "For detailed troubleshooting guidance, see: A2A_TROUBLESHOOTING_GUIDE.md" -ForegroundColor Cyan
    Write-Host "=" * 80 -ForegroundColor Cyan
    Write-Host ""
}

# Main execution
if ($Interactive -or [string]::IsNullOrWhiteSpace($AccountName)) {
    $input = Get-InteractiveInput
    Run-Diagnostics -AccountName $input.AccountName -ProjectId $input.ProjectId -SubAgentId $input.SubAgentId -MainAgentId $input.MainAgentId
} else {
    Run-Diagnostics -AccountName $AccountName -ProjectId $ProjectId -SubAgentId $SubAgentId -MainAgentId $MainAgentId
}
