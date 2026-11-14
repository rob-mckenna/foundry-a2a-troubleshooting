# A2A Quick Reference

Checked 2026-11-13. Scope: Foundry (new), public-cloud Foundry targets.

No agent to test? Run `pwsh -NoProfile -File .\demo.ps1 -Local` for a free synthetic
demo, or follow [SANDBOX_GUIDE.md](SANDBOX_GUIDE.md) to create an opt-in Azure sandbox.

## Start with the failing operation

| Failure | First check | Do not infer |
| --- | --- | --- |
| Card-target mismatch | Compare the connection target and resolved card destination | That the calling agent must share the target project |
| Card GET fails | Request `/agentCard/v1.0` with a fresh Entra token | That GET on the base URL should return the card |
| A2A message fails | Inspect HTTP outcome AND JSON-RPC error/task state | That HTTP 200 means the task completed |
| Browser consent page fails | Identify the auth type and which URL/phase fails; redact codes and query values | That a consent 404 is the same failure as a target 404 |
| Alternating errors | Correlate operation, principal context, time, and error code | Token expiry or a confirmed platform outage |

## Configuration

```text
Base: https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT/agents/AGENT/endpoint/protocols/a2a
Card: BASE/agentCard/v1.0
Direct token resource: https://ai.azure.com
Direct SDK token scope: https://ai.azure.com/.default
```

- PROJECT and AGENT are names.
- Foundry tool connection: **omit card_path**; discovery is automatic.
- Direct SDK: use `agentCard/v1.0` relative to the base.
- Select v1.0 explicitly. Incoming unversioned requests default to preview v0.3.
- A trailing slash alone is not established evidence of a platform failure.
- Incoming enablement uses REST/SDK, not a portal A2A enablement tab.

## HTTP and protocol outcomes

| Observed outcome | Investigation |
| --- | --- |
| 400 | Request shape/version selectors; inspect sanitized problem/error code |
| 401 | Token validity, target audience, supported authorization scheme |
| 403 | Actual token principal's endpoint permission; public-network restrictions can also deny access |
| 404 | Requested route, target names, incoming A2A configuration; separate consent URLs |
| 405 | Wrong method/route; GET card discovery is not JSON-RPC message invocation |
| 429 | Throttling; bounded retries may be appropriate using Retry-After |
| 5xx | Capture time/correlation information; do not claim a root cause from status alone |
| No HTTP response | DNS, TLS, proxy, connection timeout, private-network reachability |
| HTTP 200 plus JSON-RPC `error` | Protocol operation failed |
| Task not `TASK_STATE_COMPLETED` | Not a completed exchange; inspect failed/interrupted/pending state |

Do not repeatedly retry invalid configuration or 401/403/404 without resolving the
cause. Message retries may duplicate work; consider operation/idempotency semantics
before retrying. The diagnostic deliberately sends at most one message.

## Identity checks

- Identify the actual token principal; do not substitute the target's managed identity.
- Grant Foundry Agent Consumer or equivalent endpoint permission on the **target
  project or agent**. Prefer the narrowest suitable scope.
- App-only new-model agent calls use the calling agent's identity.
- `UserEntraToken` is a delegated compatibility path. `AgentOnBehalfOfUser` is
  preview and requires the source AgentBlueprint scheme and matching incoming audience.
- Different subscriptions alone are not a documented A2A failure; authorization,
  tenant policy, and network reachability determine access.
- A CLI user test does not verify the deployed agent's identity or consent flow.

## Safe direct discovery

```powershell
pwsh -NoProfile -File .\a2a_diagnostic.ps1 `
  -AccountName ACCOUNT -ProjectId PROJECT -SubAgentId AGENT
```

For the opt-in message exchange, static checks, and offline tests, see
[README.md](README.md). For support, use [SUPPORT_GUIDE.md](SUPPORT_GUIDE.md).

## Sources

- [Incoming A2A](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint)
- [Outgoing A2A tool](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/agent-to-agent)
- [Authentication](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-to-agent-authentication)
- [RBAC](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry)
