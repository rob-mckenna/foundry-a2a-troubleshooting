# Foundry A2A Troubleshooting Guide

## Issue Summary
Customer reports two intermittent errors with Agent-to-Agent (A2A) communication:
1. **"Agent card path must target the same host, project, and agent as the server URL"**
2. **Page Not Found error on consent**

Using Entra authentication with either agent identity or project managed identity.

---

## Root Cause Analysis

### Error #1: "Agent card path must target the same host, project, and agent as the server URL"

**Most Common Cause:** Mismatch between the tool configuration URL and the card path.

**Likely Issues:**
- **Card path misconfiguration**: The card path is set to `agentCard/v1.0` but the actual tool URL or server URL doesn't match this structure
- **URL encoding/formatting**: URLs might have trailing slashes, protocol differences, or other formatting issues
- **Project/Account mismatch**: The account or project in different parts of the configuration don't align

**Solution Steps:**
1. **Verify exact URL formats:**
   ```
   Server URL (on sub-agent): https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a
   Tool URL (on main agent): Must reference the EXACT same host and path structure
   Card path: agentCard/v1.0 (this should be a relative path to your agent card)
   ```

2. **Check for URL consistency:**
   - Ensure `{account}` is identical in both agents' configurations
   - Ensure `{project}` is identical in both agents' configurations
   - Ensure `{agent}` points to the correct sub-agent
   - No extra slashes, query parameters, or URL encoding differences

3. **Validate card path location:**
   - The card path `agentCard/v1.0` must exist in your deployed agent
   - Verify the agent card is actually at that location
   - Consider whether this should be a full URL instead of relative path

### Error #2: Page Not Found (404) on Consent

**Most Common Cause:** Authentication/Authorization token issues or endpoint not being properly registered.

**Likely Issues:**
- **Missing or invalid authentication headers**: The consent redirect doesn't have proper authentication
- **RBAC/Permissions insufficient**: The managed identity or agent identity lacks proper permissions
- **Endpoint not fully deployed**: The A2A endpoint on the sub-agent isn't ready to serve requests
- **Session/Token expiration**: The consent flow happens after token expiration

**Solution Steps:**
1. **Verify RBAC permissions:**
   - If using **Project Managed Identity**: Ensure it has `Cognitive Services User` role on the sub-agent's project
   - If using **Agent Identity**: Ensure the agent identity has `Cognitive Services User` role
   - Check if you have `Contributor` or `Owner` role on both projects

2. **Check endpoint status:**
   - Verify the sub-agent's A2A endpoint is deployed and accessible
   - Try accessing `https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a` directly with proper auth headers
   - Confirm no firewall/network rules are blocking the endpoint

3. **Review authentication flow:**
   - For Entra auth, ensure the consent flow is using the correct tenant ID
   - Verify the tool is configured with the correct authentication method
   - Check if the main agent has permissions to call the sub-agent's endpoint

---

## Troubleshooting Checklist

### Configuration Validation
- [ ] **Account name** matches exactly in both agents
- [ ] **Project ID** matches exactly in both agents  
- [ ] **Agent ID** for sub-agent is correctly referenced
- [ ] **Card path** (`agentCard/v1.0`) actually exists on the sub-agent
- [ ] **No trailing slashes** in any URLs
- [ ] **No extra query parameters** or encoding issues
- [ ] **Endpoint URL format** matches documentation exactly

### Authentication & Authorization
- [ ] **Managed Identity** has been enabled on the sub-agent
- [ ] **RBAC role assigned**: `Cognitive Services User` on the sub-agent's project
- [ ] **Both agents** in the same or trusted Azure subscriptions
- [ ] **Service Principal permissions** verified with `az role assignment list` command
- [ ] **Token not expired** - test with fresh authentication

### Endpoint & Network
- [ ] **A2A endpoint enabled** on the sub-agent (can verify via Foundry portal)
- [ ] **Endpoint is accessible** (test with curl/Postman with auth header)
- [ ] **No firewalls** blocking `*.services.ai.azure.com` access
- [ ] **Service tags** configured if using network security groups
- [ ] **DNS resolution** working for `{account}.services.ai.azure.com`

### Tool Configuration in Main Agent
- [ ] **Tool type** set to "Agent to Agent"
- [ ] **Server URL** points to sub-agent's A2A endpoint
- [ ] **Card path** is relative path to agent card
- [ ] **Authentication method** is "Entra" or correct identity
- [ ] **No spaces** or special characters in configuration

---

## Step-by-Step Debugging

### Step 1: Verify URLs Match Exactly

```powershell
# Compare the exact URLs
$accountName = "your-account"
$projectId = "your-project"
$subAgentId = "your-sub-agent"

$serverUrl = "https://$accountName.services.ai.azure.com/api/projects/$projectId/agents/$subAgentId/endpoint/protocols/a2a"
Write-Host "Server URL: $serverUrl"

# This is what your tool should point to
Write-Host "Tool should reference: $serverUrl"
Write-Host "Card path should be: agentCard/v1.0"
```

### Step 2: Test Endpoint Accessibility

```bash
# Get an auth token
$token = az account get-access-token --query accessToken -o tsv

# Test if endpoint responds
curl -H "Authorization: Bearer $token" \
  https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/endpoint/protocols/a2a

# Expected: Should return agent card info, not 404
```

### Step 3: Check RBAC Assignment

```bash
# Check who has access to the sub-agent's project
az role assignment list --scope /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{account}

# Ensure the managed identity appears with a proper role (Contributor or Cognitive Services User)
```

### Step 4: Validate Agent Card Structure

```bash
# Fetch the agent card to verify it exists at the expected path
$agentCard = Invoke-RestMethod `
  -Uri "https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}/agentCard/v1.0" `
  -Headers @{ Authorization = "Bearer $token" }

$agentCard | ConvertTo-Json
```

---

## Known Issues & Workarounds

### Issue: Alternating Between Two Errors
If errors alternate between the two types, this suggests:
- **Cause**: The endpoint is intermittently available or auth tokens are flaky
- **Workaround**: 
  - Increase token refresh frequency
  - Add retry logic with exponential backoff in the tool call
  - Check for concurrent request limits

### Issue: Page Not Found on Consent
If the consent page 404s:
- **Cause**: Authentication token or endpoint not ready
- **Workaround**:
  - Manually verify endpoint with authenticated request first
  - Ensure service principal has explicit `Cognitive Services User` role
  - Try using project managed identity instead of agent identity (or vice versa)

### Issue: Card Path Validation Error
If card path error persists despite correct URLs:
- **Cause**: Server URL and card path not on same host/project/agent
- **Workaround**:
  - Use **absolute URL** instead of relative path for card path
  - Verify URL format matches: `https://{account}.services.ai.azure.com/api/projects/{project}/agents/{agent}`
  - Check no URL parameters are being added during serialization

---

## Network Configuration Considerations

### If Behind Corporate Firewall

1. **Allow service endpoints:**
   ```
   *.services.ai.azure.com (HTTPS port 443)
   *.api.cognitive.microsoft.com (HTTPS port 443)
   *.cognitiveservices.azure.com (HTTPS port 443)
   ```

2. **Check NSG rules (if applicable):**
   - Service-to-service communication within Azure should be allowed by default
   - If using Private Endpoints, ensure proper routing is configured
   - Verify no DLP policies blocking the traffic

3. **Verify DNS resolution:**
   ```bash
   nslookup {account}.services.ai.azure.com
   # Should resolve to an Azure IP address
   ```

---

## Recommended Action Plan

### For Immediate Resolution:
1. **Verify URL consistency** - ensure no typos or formatting issues
2. **Check RBAC** - confirm managed identity has proper roles
3. **Test endpoint accessibility** - validate endpoint is responding with 200 OK
4. **Review logs** - check Azure Activity Log and Application Insights for detailed errors

### If Still Not Working:
1. Open an Azure Support ticket with:
   - Exact error messages (timestamps)
   - Both agent names and IDs
   - Current configuration screenshots (with sensitive data redacted)
   - Activity Log entries showing failures

2. Enable diagnostics:
   - Enable Application Insights tracing on both agents
   - Capture request/response logs for failed A2A calls
   - Record error details with full stack traces

---

## Additional Resources

- **A2A Documentation**: https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint
- **Foundry Authentication**: https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/authentication
- **RBAC Roles**: https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/rbac
