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

## Key Current Guidance

- A2A base endpoint format:
   https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a
- Agent card endpoint (v1.0):
   https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a/agentCard/v1.0
- Token audience for Foundry A2A data-plane calls:
   https://ai.azure.com
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
- Endpoint accessibility is tested with a fresh token for https://ai.azure.com.

When opening support:

- Include exact error text and timestamp.
- Include account, project, and agent identifiers.
- Include output from a2a_diagnostic.ps1.
- Include role-assignment output for the caller identity.
- Include what has already been tested.

## Reference Links

- Enable incoming A2A endpoint:
   https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint
- Foundry authentication and identity patterns:
   https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint
- Foundry RBAC concepts:
   https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint

Version: 1.1
Last Updated: 2026-07-14