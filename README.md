# Foundry Agent-to-Agent (A2A) Troubleshooting Guide

This toolkit helps resolve common A2A issues in Microsoft Foundry, including:

1. "Agent card path must target the same host, project, and agent as the server URL"
2. Page Not Found (404) during tool consent or invocation
3. Intermittent or alternating A2A failures

## Start Here

1. Open QUICK_REFERENCE.md for rapid checks.
2. Run a2a_diagnostic.ps1 to validate endpoint, token, and connectivity.
3. Use A2A_TROUBLESHOOTING_GUIDE.md for deep troubleshooting.

## What's in This Toolkit

- QUICK_REFERENCE.md: Fast diagnosis and quick fixes.
- A2A_TROUBLESHOOTING_GUIDE.md: Detailed root-cause and remediation steps.
- SUPPORT_GUIDE.md: Full support-ready reference and escalation checklist.
- a2a_diagnostic.ps1: Automated PowerShell diagnostics.
- a2a_validator.py: Python-based strict configuration validator.

## Why These Scripts Exist

The two scripts are complementary. They answer different troubleshooting questions:

- a2a_validator.py answers: "Is my configuration logically correct?"
- a2a_diagnostic.ps1 answers: "Does it actually work end-to-end in my environment right now?"

Use both to reduce false starts and speed up escalation.

### a2a_validator.py (Configuration Validator)

What it does:

- Validates URL shape for A2A endpoint values.
- Checks strict consistency between server URL and tool URL target values.
- Validates agent card path patterns.
- Validates auth-type and identity-type inputs.
- Prints structured results as Errors, Warnings, and Information.

When to use it:

- First pass before changing identities, roles, or network settings.
- During configuration edits to catch typos/mismatches quickly.
- In environments where live endpoint calls are temporarily blocked.

What success looks like:

- No Errors.
- Warnings are understood and intentional.

### a2a_diagnostic.ps1 (Live Runtime Diagnostic)

What it does:

- Validates endpoint URL structure.
- Resolves DNS for the Foundry account hostname.
- Acquires a token for <https://ai.azure.com>.
- Calls the A2A endpoint and reports HTTP outcome.
- Classifies common runtime failures (401/403/404/network/TLS).

When to use it:

- After validator checks pass.
- When errors are intermittent or environment-specific.
- Before opening a support case (to capture runtime evidence).

What success looks like:

- Token acquisition succeeds.
- Endpoint call succeeds with expected response.

## Recommended Run Order

1. Run a2a_validator.py first (fast static checks).
2. Run a2a_diagnostic.ps1 second (live auth/network/endpoint checks).
3. Use QUICK_REFERENCE.md and A2A_TROUBLESHOOTING_GUIDE.md to remediate findings.

## How to Interpret Script Results

If a2a_validator.py reports Errors:

- Fix configuration issues first (URL mismatch, card path mismatch, auth-type mismatch).
- Re-run validator until Errors are cleared.

If a2a_diagnostic.ps1 reports 401:

- Verify token audience is <https://ai.azure.com>.
- Re-authenticate and retry.

If a2a_diagnostic.ps1 reports 403:

- Verify caller identity role assignment on the target Foundry project.
- Confirm Foundry Agent Consumer (or higher).

If a2a_diagnostic.ps1 reports 404:

- Verify A2A is enabled on the target agent.
- Re-check host/project/agent alignment and card path.

If a2a_diagnostic.ps1 reports network/TLS/DNS failure:

- Verify DNS resolution.
- Verify outbound HTTPS path to *.services.ai.azure.com.
- Check corporate proxy/firewall/TLS inspection behavior.

## Key Current Guidance

- A2A base endpoint format:
   <https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a>
- Agent card endpoint (v1.0):
   <https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a/agentCard/v1.0>
- Token audience for Foundry A2A data-plane calls:
   <https://ai.azure.com>
- For service-identity calls, the caller should have Foundry Agent Consumer (or higher) on the target Foundry project.

## Quick Usage

PowerShell:

```powershell
# Interactive mode
.\a2a_diagnostic.ps1 -Interactive

# Scripted mode
.\a2a_diagnostic.ps1 -AccountName "myaccount" -ProjectId "myproject" -SubAgentId "subagent"
```

Python:

```bash
# Interactive mode
python a2a_validator.py --interactive

# Example run
python a2a_validator.py
```

## Escalation Readiness

Escalate only after all of the following:

- URL host/project/agent alignment is verified.
- Agent card path is verified against the A2A endpoint path.
- Caller role assignment is verified on the target project.
- Endpoint accessibility is tested with a fresh token for <https://ai.azure.com>.

When opening support:

- Include exact error text and timestamp.
- Include account, project, and agent identifiers.
- Include output from a2a_diagnostic.ps1.
- Include role-assignment output for the caller identity.
- Include what has already been tested.

## Reference Links

- Enable incoming A2A endpoint:
   <https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint>
- Foundry authentication and identity patterns:
   <https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint>
- Foundry RBAC concepts:
   <https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint>

Version: 1.2
Last Updated: 2026-07-14
