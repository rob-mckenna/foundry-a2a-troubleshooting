#requires -Version 7.0
<#
.SYNOPSIS
Runs a free local demo or an explicitly cost-approved Azure sandbox.
.EXAMPLE
pwsh -NoProfile -File .\demo.ps1 -Local
.EXAMPLE
pwsh -NoProfile -File .\demo.ps1 -Local -Scenario throttled
.EXAMPLE
pwsh -NoProfile -File .\demo.ps1 -Azure -SubscriptionId SUB -Location REGION -Model MODEL -ModelVersion VERSION -AcceptCost
.EXAMPLE
pwsh -NoProfile -File .\demo.ps1 -Cleanup -ConfirmDelete
#>
[CmdletBinding(DefaultParameterSetName = 'Local')]
param(
    [Parameter(ParameterSetName = 'Local')]
    [switch]$Local,
    [Parameter(ParameterSetName = 'Local')]
    [ValidateSet('all', 'success', 'unauthorized', 'forbidden', 'not-found',
        'wrong-method', 'throttled', 'server-error', 'redirect', 'malformed-json',
        'rpc-error', 'failed-task')]
    [string]$Scenario = 'all',
    [Parameter(Mandatory, ParameterSetName = 'Azure')]
    [switch]$Azure,
    [Parameter(ParameterSetName = 'Azure')]
    [ValidateSet('Create', 'Probe', 'Diagnose')]
    [string]$AzureAction = 'Create',
    [Parameter(ParameterSetName = 'Azure')]
    [string]$SubscriptionId,
    [Parameter(ParameterSetName = 'Azure')]
    [string]$Location,
    [Parameter(ParameterSetName = 'Azure')]
    [string]$Model,
    [Parameter(ParameterSetName = 'Azure')]
    [string]$ModelVersion,
    [Parameter(ParameterSetName = 'Azure')]
    [ValidateSet('GlobalStandard', 'Standard')]
    [string]$Sku = 'GlobalStandard',
    [Parameter(ParameterSetName = 'Azure')]
    [ValidateRange(1, 10)]
    [int]$Capacity = 1,
    [Parameter(ParameterSetName = 'Azure')]
    [string]$DiagnosticsFile,
    [Parameter(ParameterSetName = 'Azure')]
    [ValidateSet('all', 'model', 'target-responses', 'caller-no-tools', 'direct-a2a', 'caller-a2a')]
    [string]$Control = 'all',
    [Parameter(ParameterSetName = 'Azure')]
    [switch]$ProvisionOnly,
    [Parameter(ParameterSetName = 'Azure')]
    [switch]$AcceptCost,
    [Parameter(Mandatory, ParameterSetName = 'Cleanup')]
    [switch]$Cleanup,
    [Parameter(ParameterSetName = 'Cleanup')]
    [switch]$ConfirmDelete,
    [Parameter(ParameterSetName = 'Azure')]
    [Parameter(ParameterSetName = 'Cleanup')]
    [string]$StateFile = (Join-Path $PSScriptRoot 'private-evidence\sandbox-state.json'),
    [Parameter(ParameterSetName = 'Local')]
    [Parameter(ParameterSetName = 'Azure')]
    [string]$EvidenceFile
)

function Invoke-Demo {
    param(
        [string]$Mode, [string]$Scenario, [string]$AzureAction,
        [string]$SubscriptionId, [string]$Location, [string]$Model,
        [string]$ModelVersion, [string]$Sku, [int]$Capacity,
        [bool]$AcceptCost, [bool]$ConfirmDelete, [string]$StateFile,
        [string]$EvidenceFile, [string]$DiagnosticsFile, [bool]$ProvisionOnly,
        [string]$Control = 'all'
    )
    $PSNativeCommandUseErrorActionPreference = $false
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
    if (-not $python) {
        Write-Error 'Install Python 3.11+ and PowerShell 7+. The harness does not install tools or log you in.'
        return 2
    }
    $arguments = @()
    switch ($Mode) {
        'Local' {
            if (-not $EvidenceFile) {
                $EvidenceFile = Join-Path $PSScriptRoot 'private-evidence\local-demo.json'
            }
            $arguments = @((Join-Path $PSScriptRoot 'demo_local.py'),
                '--scenario', $Scenario, '--evidence-file', $EvidenceFile)
        }
        'Azure' {
            if (-not $AcceptCost) {
                Write-Error 'Azure mode requires -AcceptCost. It provisions resources and sends billable inference requests.'
                return 2
            }
            if (-not $EvidenceFile) {
                $EvidenceFile = Join-Path $PSScriptRoot 'private-evidence\azure-sandbox.json'
            }
            $arguments = @((Join-Path $PSScriptRoot 'sandbox_azure.py'),
                $AzureAction.ToLowerInvariant(), '--accept-cost',
                '--state-file', $StateFile, '--evidence-file', $EvidenceFile)
            if ($DiagnosticsFile) { $arguments += @('--diagnostics-file', $DiagnosticsFile) }
            if ($AzureAction -eq 'Diagnose') { $arguments += @('--control', $Control) }
            elseif ($Control -ne 'all') {
                Write-Error '-Control applies only to AzureAction Diagnose.'
                return 2
            }
            if ($AzureAction -eq 'Create') {
                if ($ProvisionOnly) { $arguments += '--provision-only' }
                if (-not $SubscriptionId -or -not $Location -or -not $Model -or -not $ModelVersion) {
                    Write-Error 'Azure Create requires -SubscriptionId, -Location, -Model, and -ModelVersion. No resources created.'
                    return 2
                }
                $arguments += @('--subscription', $SubscriptionId, '--location', $Location,
                    '--model', $Model, '--model-version', $ModelVersion,
                    '--sku', $Sku, '--capacity', "$Capacity")
            } elseif ($SubscriptionId -or $Location -or $Model -or $ModelVersion -or $ProvisionOnly) {
                Write-Error 'Azure Probe/Diagnose uses saved state. Do not supply deployment values or ProvisionOnly.'
                return 2
            }
        }
        'Cleanup' {
            if (-not $ConfirmDelete) {
                Write-Error 'Cleanup requires -ConfirmDelete. It deletes only the saved and ownership-verified sandbox resource group.'
                return 2
            }
            $arguments = @((Join-Path $PSScriptRoot 'sandbox_azure.py'),
                'cleanup', '--confirm-delete', '--state-file', $StateFile)
        }
        default {
            Write-Error 'Select Local, Azure, or Cleanup.'
            return 2
        }
    }
    & $python.Source @arguments | Out-Host
    return $LASTEXITCODE
}

if ($MyInvocation.InvocationName -ne '.') {
    $parameters = @{
        Mode = $PSCmdlet.ParameterSetName
        Scenario = $Scenario; AzureAction = $AzureAction
        SubscriptionId = $SubscriptionId; Location = $Location; Model = $Model
        ModelVersion = $ModelVersion; Sku = $Sku; Capacity = $Capacity
        AcceptCost = [bool]$AcceptCost; ConfirmDelete = [bool]$ConfirmDelete
        StateFile = $StateFile; EvidenceFile = $EvidenceFile; DiagnosticsFile = $DiagnosticsFile
        ProvisionOnly = [bool]$ProvisionOnly
        Control = $Control
    }
    exit (Invoke-Demo @parameters)
}
