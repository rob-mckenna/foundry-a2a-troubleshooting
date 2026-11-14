# A2A Support and Escalation Guide

Public guidance, checked 2026-11-13. No customer-specific details are included.

## Capture the failing surface

Distinguish static configuration, card discovery, message invocation, deployed
tool invocation, and browser consent. A CLI exchange is not proof of the deployed
caller's effective identity or user delegation.

For each observed failure record:

- UTC timestamp and reproducible operation.
- HTTP status, JSON-RPC/problem code, and task state when available.
- Version selector, tool type, runtime/SDK versions, and agent deployment version
  if known. Explicitly mark missing values as unverified.
- Caller context: direct CLI user/service principal, deployed agent identity, or
  delegated user/actor. Do not publish identifying principal/tenant values.
- Whether discovery succeeded independently of invocation.
- Network context: public access, selected-IP restrictions, or private endpoint;
  originating environment and expected DNS behavior.
- Sanitized correlation information and steps already attempted.

The scripts' evidence is allowlisted and intentionally excludes arbitrary response
text. Review it before sharing. Provide required account/project/agent/principal
identifiers privately through authorized support channels, not in a public article.

## Establish authorization separately

Verify effective endpoint permission for the principal actually represented by the
request, at target project/agent scope. Foundry Agent Consumer is the documented
least-privilege endpoint role. Do not infer access from an unrelated principal's
role or an account-scope list alone. Document whether inherited/group permissions
and restrictions were considered.

For current/legacy publishing identity differences and delegated flows, follow
[incoming authentication](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint#configure-authentication-for-incoming-requests)
and [delegation configuration](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/configure-user-delegation).

## Reproduce without leaking data

```powershell
pwsh -NoProfile -File .\a2a_diagnostic.ps1 `
  -AccountName ACCOUNT -ProjectId PROJECT -SubAgentId AGENT `
  -SendMessage -EvidencePath .\private-evidence\live.json
```

`-SendMessage` explicitly permits one synthetic inference request. Omit it for
discovery only. The token comes from the current Azure CLI login. No RBAC,
deployment, or identity configuration is changed.

Do not publish raw authenticated curl verbose output, tokens, OAuth redirect codes,
customer payloads, or raw remote exception bodies. An ignored file may still be
tracked or shared; ignore rules are not a confidentiality boundary.

## Escalation

Open Azure Support when the documented configuration cannot be made to work or
evidence indicates unexplained behavior. You do not need a 200 response to qualify
for escalation. Provide private identifiers only in the secured support request.

Use configured agent/application traces for invocation details; use Azure Activity
Log for management changes. State what telemetry was actually enabled and captured.
Do not infer a service-wide defect or cause frequency from a single reproduction.

See [README.md](README.md), [QUICK_REFERENCE.md](QUICK_REFERENCE.md), and
[VALIDATION_EVIDENCE.md](VALIDATION_EVIDENCE.md).
