# A2A Quick Reference Card

## Error 1: "Agent card path must target the same host, project, and agent as the server URL"

### 99% of the time, this is caused by:

| Check | What to do |
|-------|-----------|
| **Account name typo** | `https://my-accout.services.ai...` ❌ vs `https://my-account.services.ai...` ✅ |
| **Project ID mismatch** | Server on `projects/projectA` but tool on `projects/projectB` |
| **Agent ID mismatch** | Server on `agents/subagent-1` but tool references different agent |
| **Trailing slashes** | `https://account.../endpoint/protocols/a2a/` ❌ (remove the slash) |
| **Card path wrong** | `agentCard/v2.0` ❌ should be `agentCard/v1.0` ✅ |
| **Card path shape mismatch** | Use `agentCard/v1.0` (SDK path) or `/agentCard/v1.0` (connection metadata) |

### Quick Fix Checklist:
```
☐ Copy exact account name from both URLs and verify character-by-character match
☐ Copy exact project ID from both URLs and verify character-by-character match
☐ Copy exact agent ID from both URLs and verify character-by-character match
☐ Remove any trailing slashes from URLs
☐ Verify card path is exactly: agentCard/v1.0
☐ Use relative path for SDK clients; use leading slash for connection metadata
```

---

## Error 2: Page Not Found (404) on Consent

### 95% of the time, this is caused by:

| Check | What to do |
|-------|-----------|
| **Missing RBAC** | Calling identity lacks `Foundry Agent Consumer` (or higher) on target project |
| **Wrong identity** | Using agent identity when should use project managed identity (or vice versa) |
| **Token expired** | Authentication token used during consent flow is expired |
| **Endpoint not deployed** | A2A endpoint on sub-agent isn't fully initialized |
| **Network blocked** | Corporate firewall blocking `*.services.ai.azure.com` |
| **Subscription isolated** | Main and sub agents in different, non-linked subscriptions |

### Quick Fix Checklist:
```
☐ Run: az role assignment list --scope <sub-agent-project-scope>
☐ Verify 'Foundry Agent Consumer' (or higher) appears for the caller identity
☐ If using Project Managed Identity, ensure it's enabled on the sub-agent
☐ If using Agent Identity, ensure the agent has an identity assigned
☐ Test endpoint: curl -H "Authorization: Bearer $token" https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a
☐ Expect 200 OK with agent card JSON response
☐ If 404, endpoint not accessible - check agent deployment status
```

---

## Configuration Verification Flowchart

```
Are you getting "card path must target the same" error?
├─ YES → Go to Error 1 fixes above
└─ NO → Continue

Are you getting 404 on consent page?
├─ YES → Go to Error 2 fixes above
└─ NO → Continue

Are errors alternating randomly?
├─ YES → Likely token/auth issue - add retry logic and check RBAC
└─ NO → Continue

Still stuck? → Collect:
   • Exact error message + timestamp
   • Both agent IDs and project IDs
   • Current configuration (redact sensitive data)
   • Output of: az role assignment list --scope {project}
   → Open Azure Support ticket
```

---

## URL Format Reference

### Correct Format:
```
https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT-ID/agents/AGENT-ID/endpoint/protocols/a2a
                    ↑ must match                                                                                   ↑ no trailing slash
```

### Common Mistakes:
```
❌ https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT-ID/agents/AGENT-ID/endpoint/protocols/a2a/
   (trailing slash)

❌ https://my-account-wrong.services.ai.azure.com/api/projects/PROJECT-ID/agents/AGENT-ID/endpoint/protocols/a2a
   (typo in account)

❌ https://ACCOUNT.services.ai.azure.com/api/projects/WRONG-PROJECT/agents/AGENT-ID/endpoint/protocols/a2a
   (wrong project)

❌ https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT-ID/agents/WRONG-AGENT/endpoint/protocols/a2a
   (wrong agent)

✅ https://my-account.services.ai.azure.com/api/projects/abc-123/agents/my-sub-agent/endpoint/protocols/a2a
   (correct format)
```

---

## Common Fixes by Symptom

### "Randomly alternating between both errors"
**Likely cause**: Auth tokens expiring mid-flow
**Fix**:
1. Add exponential backoff retry logic (3-5 retries with 1s-5s delays)
2. Ensure token is fresh before making A2A call
3. Request token for `https://ai.azure.com`

### "Always gets 404, never gets to consent"
**Likely cause**: Endpoint not deployed or network blocked
**Fix**:
1. Verify endpoint is deployed: Check Foundry portal → Agent → A2A tab
2. Test manually: `curl -v -H "Authorization: Bearer $token" <server-url>`
3. Check firewall: Ensure `*.services.ai.azure.com` is not blocked
4. Check DNS: `nslookup {account}.services.ai.azure.com`

### "Gets to consent but then 404"
**Likely cause**: Token scope wrong or consent redirect URL incorrect
**Fix**:
1. Ensure token has correct resource scope
2. Check that redirect URL matches registered endpoint URL exactly
3. Verify no query parameters are being added to redirect URL

---

## Quick Test Commands

### Bash
```bash
# Get token
TOKEN=$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

# Test endpoint
curl -v -H "Authorization: Bearer $TOKEN" \
  https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT/agents/AGENT/endpoint/protocols/a2a

# Expected response: 200 OK with agent card JSON
```

### PowerShell
```powershell
# Get token
$token = (az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv)

# Test endpoint
$headers = @{
    Authorization = "Bearer $token"
}

Invoke-WebRequest `
  -Uri "https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT/agents/AGENT/endpoint/protocols/a2a" `
  -Headers $headers `
  -Verbose

# Check RBAC
az role assignment list `
  --scope "/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}" `
  --output table

# Look for caller role assignment: Foundry Agent Consumer (or higher)
```

---

## Support Resources

- **Official Docs**: https://learn.microsoft.com/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint
- **Authentication Docs**: https://learn.microsoft.com/azure/foundry/agents/concepts/authentication
- **RBAC Reference**: https://learn.microsoft.com/azure/foundry/agents/concepts/rbac
- **Troubleshooting Guide**: See `A2A_TROUBLESHOOTING_GUIDE.md` in this folder

---

## When to Escalate

Open an Azure Support ticket if:
- ✓ You've verified all URL components match exactly
- ✓ You've confirmed RBAC roles are assigned
- ✓ You've tested endpoint accessibility and got 200 OK
- ✓ You've checked firewalls and DNS resolution
- ✓ Errors still persist after trying the above steps

**When opening ticket, include:**
- Both agent IDs (main agent and sub-agent)
- Exact error message + timestamp
- Output of: `az role assignment list --scope {project-scope}`
- Testing results from curl/Invoke-WebRequest
- Application Insights logs (if available)
