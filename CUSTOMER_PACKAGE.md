# Customer Troubleshooting Package

This folder contains only the files customers need to troubleshoot their Foundry A2A issues.

## What's Included (Share These Files)

```
README.md                          Main guide - start here
├── QUICK_REFERENCE.md            Error lookup + quick fixes ⭐
├── A2A_TROUBLESHOOTING_GUIDE.md   Detailed troubleshooting steps
├── a2a_diagnostic.ps1            PowerShell diagnostic tool
└── a2a_validator.py              Python configuration validator
```

## Installation

1. Download or clone this repository
2. Read **README.md** first
3. Use the resources based on your error:
   - Error #1? → Open **QUICK_REFERENCE.md** → Error 1 section
   - Error #2? → Open **QUICK_REFERENCE.md** → Error 2 section

## Quick Start

**For Windows:**
```powershell
.\a2a_diagnostic.ps1 -Interactive
```

**For Linux/Mac with Python:**
```bash
python3 a2a_validator.py --interactive
```

## Customer Handoff (First Action by Symptom)

Use this section in customer communications to route quickly to the right first step.

### Symptom: "Agent card path must target the same host, project, and agent as the server URL"
1. Open **QUICK_REFERENCE.md** and go to **Error 1**.
2. Verify account, project, and agent values match exactly.
3. Verify card path is `agentCard/v1.0` (or `/agentCard/v1.0` when using connection metadata).
4. Run:

```powershell
.\a2a_diagnostic.ps1 -Interactive
```

### Symptom: "Page Not Found" (404) during consent or tool call
1. Open **QUICK_REFERENCE.md** and go to **Error 2**.
2. Confirm caller identity has **Foundry Agent Consumer** (or higher) on the target project.
3. Test endpoint with a fresh token for `https://ai.azure.com`:

```bash
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)
curl -H "Authorization: Bearer $TOKEN" \
   https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a
```

### Symptom: Intermittent/alternating failures
1. Re-run diagnostics to validate token freshness and endpoint accessibility.
2. Add retry with exponential backoff in caller logic.
3. Review **A2A_TROUBLESHOOTING_GUIDE.md** for detailed remediation.

### Symptom: Need support escalation package
Collect and share:
1. Exact error text and timestamp.
2. Output from `a2a_diagnostic.ps1`.
3. Account/project/agent identifiers.
4. Caller role-assignment evidence on target project.
5. Steps already attempted.

## Support

If this package doesn't resolve your issue:
1. Collect the output from the diagnostic script
2. Review the detailed guide in **A2A_TROUBLESHOOTING_GUIDE.md**
3. Contact Azure Support with the diagnostic output

---

**Note:** This is a customer-facing troubleshooting package. Internal support documentation is not included.
