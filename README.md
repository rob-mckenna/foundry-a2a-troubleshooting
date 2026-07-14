# Foundry Agent-to-Agent (A2A) Troubleshooting Guide

Welcome! This kit helps you resolve issues with Agent-to-Agent communication in Microsoft Foundry.

## Are You Experiencing A2A Issues?

This toolkit will help if you're seeing:
1. **"Agent card path must target the same host, project, and agent as the server URL"**
2. **Page Not Found (404) when trying to consent to an A2A tool call**
3. **Errors that appear randomly or intermittently**

You're in the right place. Follow the resources below to resolve your issue.

---

## Resources in This Toolkit

### 1. **QUICK_REFERENCE.md** ⭐ START HERE
**Best for:** Quick diagnosis and immediate fixes
- Error-specific solution tables
- 99% most common causes
- Quick fix checklists
- Configuration verification flowchart
- URL format reference

**When to use:**
- You just started getting an error
- Need a fast solution without deep technical details
- Want to rule out obvious configuration issues

### 2. **A2A_TROUBLESHOOTING_GUIDE.md**
**Best for:** Deep-dive troubleshooting and comprehensive understanding
- Detailed root cause analysis
- Step-by-step debugging procedures
- Full troubleshooting checklist
- Network configuration considerations
- Known issues and workarounds

**When to use:**
- Quick fixes from QUICK_REFERENCE.md didn't resolve the issue
- You want to understand what's happening with your configuration
- You need detailed step-by-step debugging procedures

### 3. **a2a_diagnostic.ps1** 🔧
**Best for:** Automated configuration validation and testing
- PowerShell script that validates entire setup
- Tests URL format compliance
- Validates DNS resolution
- Tests endpoint accessibility
- Checks authentication
- Provides diagnostic summary

**How to use:**
```powershell
# Interactive mode (prompted for configuration)
.\a2a_diagnostic.ps1 -Interactive

# Scripted mode
.\a2a_diagnostic.ps1 -AccountName "myaccount" -ProjectId "myproject" -SubAgentId "subagent"
```

**What it checks:**
- ✓ URL format validity
- ✓ DNS resolution
- ✓ Authentication token acquisition
- ✓ Endpoint accessibility (200 OK response)
- ✓ Response content validation

### 4. **a2a_validator.py**
**Best for:** Detailed configuration validation with Python
- Configuration format validation
- URL component extraction and verification
- RBAC requirement validation
- Cross-configuration consistency checks

**How to use:**
```bash
# Interactive mode
python a2a_validator.py --interactive

# Example validation
python a2a_validator.py
```

---

## How to Use This Toolkit

**Start here based on your situation:**

### I see Error #1: "card path must target the same..."
1. Open **QUICK_REFERENCE.md** and go to **Error 1** section
2. Follow the quick fix checklist (should take < 5 minutes)
3. If not resolved, run **a2a_diagnostic.ps1** to validate URL format
4. Still stuck? Go to **A2A_TROUBLESHOOTING_GUIDE.md** → Error #1 for detailed steps

### I see Error #2: "Page Not Found" (404)
1. Open **QUICK_REFERENCE.md** and go to **Error 2** section
2. Verify your RBAC permissions are set correctly
3. Run **a2a_diagnostic.ps1** to test endpoint accessibility
4. Still stuck? Go to **A2A_TROUBLESHOOTING_GUIDE.md** → Error #2 for detailed steps

### Errors keep happening randomly
1. Check **QUICK_REFERENCE.md** → "Common Fixes by Symptom"
2. Review RBAC assignments and token handling
3. If needed, add retry logic to your A2A tool calls
4. See **A2A_TROUBLESHOOTING_GUIDE.md** for network considerations

### I want to validate my entire setup
1. Run **a2a_diagnostic.ps1** with your configuration
2. Review the diagnostic report
3. Follow any recommended fixes
4. Re-run the script to verify fixes worked

---

## Common Configuration Errors

### Error: "Account mismatch"
```
❌ Main agent service URL: https://my-account.services.ai.azure.com/api/projects/proj-a/agents/main/...
❌ Sub-agent A2A URL: https://my-acount.services.ai.azure.com/api/projects/proj-a/agents/sub/...
                                 ^ typo: "acount"

✅ Fix: Ensure exact account name match in both URLs
```

### Error: "Project mismatch"
```
❌ Tool URL references: projects/project-123
❌ Server URL on sub-agent: projects/project-456

✅ Fix: Ensure both agents are in the SAME project
```

### Error: "Card path inconsistency"
```
❌ Server URL: .../endpoint/protocols/a2a
❌ Card path: "agentCard/v2.0" (doesn't match server path)

✅ Fix: Ensure card path matches expected version (usually v1.0)
```

### Error: "RBAC missing"
```
❌ Managed identity has no roles assigned
❌ Result: 403 Forbidden or 404 Not Found

✅ Fix: Assign "Cognitive Services User" role to managed identity
Command: az role assignment create --role "Cognitive Services User" ...
```

---

## Testing & Validation Procedures

### Manual Endpoint Test (Bash)
```bash
# Get tokeIssues at a Glance

| Issue | Most Common Cause | Quick Fix |
|-------|-------------------|-----------|
| "Card path must target the same..." | Typo in account/project/agent name in URL | Check QUICK_REFERENCE.md Error #1 |
| 404 Page Not Found | Missing RBAC role "Cognitive Services User" | Verify role is assigned to your managed identity |
| Random/intermittent errors | Auth token expiring during tool call | Ensure token is fresh, add retry logic |
| DNS errors | Network/firewall blocking `*.services.ai.azure.com` | Check with your network admin |

See **QUICK_REFERENCE.md** for detailed solutions.
## File Manifest

```
foundry-a2a-troublshooting/
├── README.md                          (this file)
├── QUICK_REFERENCE.md                 (error lookup and quick fixes)
├── A2A_TROUBLESHOOTING_GUIDE.md        (comprehensive deep-dive)
├── a2a_diagnostic.ps1                 (automated PowerShell diagnostics)
└── a2a_validator.py                   (Python configuration validator)
```

---

## Next Steps

### For Immediate Help:
1. 📖 Read **QUICK_REFERENCE.md**
2. 🔧 Run **a2a_diagnostic.ps1** with customer's config
3. ✅ Follow quick fix checklist

### For Deep Troubleshooting:
1. 📖 Read **A2A_TROUBLESHOOTING_GUIDE.md**
2. 🧪 Run step-by-step debugging procedures
3. 📋 Complete full troubleshooting checklist
4. 🎯 Address specific root cause

### If Escalating to Support:
1. 📦 Collect diagnostic package (all outputs above)
2. 📝 Document what has been tried
3. 🎟️ Open Azure Support ticket with collected evidence
4. 📧 Share QUICK_REFERENCE.md and this README with customer

---

## Support & Escalation

**For questions about this toolkit:**
- See specific resource files for detailed guidance
- Refer to Microsoft Foundry official documentation
- Check Azure Support portal for account-specific issues

**Microsoft Documentation:**
- [Enable Agent-to-Agent Endpoint](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint)
- [Foundry Authentication](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/authentication)
- [RBAC for Foundry](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/rbac)

---

## What's in This Toolkit

- **QUICK_REFERENCE.md** - Error lookup and quick solutions (read this first!)
- **A2A_TROUBLESHOOTING_GUIDE.md** - Detailed troubleshooting steps and diagnostics
- **a2a_diagnostic.ps1** - Automated PowerShell script to test your setup
- **a2a_validator.py** - Python script for detailed configuration validation
- **README.md** - This file

## Getting Help

Need help understanding this toolkit?
- Each file has clear instructions on how to use it
- Look for ⭐ markers indicating which file to start with
- Follow the step-by-step sections in order

**Version:** 1.0  
**Last Updated:** July 2024
2. **Review documentation:**
   - [Enable Agent-to-Agent Endpoint](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint) - Official setup guide
   - [Foundry Authentication](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/authentication) - How authentication works
   - [RBAC for Foundry](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/rbac) - Role requirements

3. **Contact Azure Support** with:
   - The full diagnostic output from a2a_diagnostic.ps1
   - Your exact error message and when it occurred
   - What you've already tried from this guide
   - Your configuration details (redact sensitive data