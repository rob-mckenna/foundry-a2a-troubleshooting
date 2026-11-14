# Foundry A2A Troubleshooting Guide

Documentation verified 2026-11-13. This guide covers Foundry (new) public-cloud
targets. It distinguishes documented requirements from diagnostic hypotheses.

## 1. Establish the target and API surface

Use the target's project and agent **names**:

```text
https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT/agents/AGENT/endpoint/protocols/a2a
```

The target must support the responses protocol. Incoming enablement requires
`agent_card` plus `agent_endpoint.protocol_configuration.responses` and `.a2a`.
Microsoft documents configuring them through REST/SDK. It is not yet an incoming
enablement portal feature. Follow the official [enablement instructions](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint#enable-incoming-a2a);
this toolkit does not deploy agents or change their configuration.

The GA v1.0 incoming endpoint supports JSON-RPC and text, not streaming/SSE,
HTTP+JSON, gRPC, or files. v0.3 remains preview. An external A2A server can support
different transports and authentication; do not apply these Foundry restrictions
to the entire protocol.

## 2. Configure discovery correctly

### A Foundry agent calling another Foundry agent

Create a `RemoteA2A` connection targeting the A2A base URL. Set the audience to
`https://ai.azure.com`. **Do not specify an agent-card path** for a Foundry target.
Foundry resolves discovery automatically; a separate
`send_credentials_for_agent_card` override is not needed for this target case.
Use the GA `a2a` tool and v1.0 selection.

For example, the current Python SDK pattern is:

```python
from azure.ai.projects.models import A2AProtocolVersion, A2ATool

connection = project.connections.get("my-a2a-connection")
tool = A2ATool(
    a2a_version=A2AProtocolVersion.V1_0,
    project_connection_id=connection.id,
)
```

Here `project` is an authenticated `AIProjectClient` for the calling project.
Consult the [complete official SDK example and version prerequisites](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/agent-to-agent).
This fragment is not a standalone deployment script.

### A direct SDK or protocol client

Fetch the authenticated card at `BASE/agentCard/v1.0`. For the Python A2A SDK,
pass `agentCard/v1.0` as the custom relative discovery path. A generic URL resolver
may interpret a leading slash as the host root, not the A2A base path.

The card destination must resolve to the same target, not another host, project,
or agent. The static validator checks both destination and documented path shape.
It normalizes a single trailing base slash; it does not diagnose that slash as a
confirmed platform defect.

Incoming requests without version selection default to preview v0.3. Select v1.0
through SDK card negotiation, `A2A-Version: 1.0`, or `?a2a-version=1.0`.
Header and query selectors must agree. The scripts use the header; query-free base
URL validation is their input convention, not a Foundry protocol limitation.

## 3. Identify the principal and required access

All incoming Foundry A2A URLs, including the card, require Microsoft Entra ID.
Key-based and anonymous incoming access are not supported.

| Caller | Relevant identity context |
| --- | --- |
| This toolkit's direct CLI diagnostic | Current Azure CLI user/service principal |
| App-only new-model agent | Its `instance_identity`; assigned at creation |
| Legacy Agent Application | Shared project identity before publishing; distinct application identity afterward |
| Delegated call | User/actor context determined by the selected auth pattern |

For direct token acquisition use resource `https://ai.azure.com`, or SDK scope
`https://ai.azure.com/.default`. The diagnostic covers the ordinary Azure RBAC
endpoint flow; it does not obtain a blueprint-audience delegated token.

Grant the **actual calling principal** Foundry Agent Consumer or another role
granting endpoint access. Use its Entra object/principal ID, not application/client
ID. Prefer target-agent scope when access to every target-project agent is unnecessary:

```text
/subscriptions/SUB/resourceGroups/RG/providers/Microsoft.CognitiveServices/accounts/ACCOUNT/projects/PROJECT
/subscriptions/SUB/resourceGroups/RG/providers/Microsoft.CognitiveServices/accounts/ACCOUNT/projects/PROJECT/agents/AGENT
```

Check effective access at the intended scope, including inherited/group permissions
and applicable restrictions. A role listing at account scope alone can miss
project/agent assignments. The scripts do not automatically verify RBAC.

Use agent identity for app-only Foundry calls. `UserEntraToken` preserves user
context for existing compatibility integrations. `AgentOnBehalfOfUser` is preview
and requires the source AgentBlueprint endpoint scheme and an incoming token
targeting that blueprint. OAuth sign-in/consent is a separate surface.

Do not switch identities as a generic workaround: it changes who is authorized.
Do not require "linked subscriptions" or an identity on the target as a substitute
for access by the caller.

Sources: [incoming identities](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint#grant-access-to-the-a2a-endpoint),
[A2A authentication](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-to-agent-authentication),
[user delegation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/configure-user-delegation),
[RBAC](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry).

## 4. Reproduce discovery and a v1.0 message

First run the static validator, then discovery:

```powershell
python .\a2a_validator.py --interactive
pwsh -NoProfile -File .\a2a_diagnostic.ps1 `
  -AccountName ACCOUNT -ProjectId PROJECT -SubAgentId AGENT
```

Opt in to exactly one synthetic message (can incur inference charges):

```powershell
pwsh -NoProfile -File .\a2a_diagnostic.ps1 `
  -ServerUrl "https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT/agents/AGENT/endpoint/protocols/a2a" `
  -SendMessage -EvidencePath .\private-evidence\live.json
```

The wire request uses the v1.0 JSON-RPC binding:

```json
{
  "jsonrpc": "2.0",
  "id": "diagnostic-request-id",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "unique-message-id",
      "role": "ROLE_USER",
      "parts": [{"text": "Reply with exactly: A2A diagnostic OK"}]
    },
    "configuration": {
      "acceptedOutputModes": ["text/plain"],
      "returnImmediately": false
    }
  }
}
```

Send it as POST to the base URL with bearer authentication,
`Content-Type: application/json`, and `A2A-Version: 1.0`. IDs are fresh for each
diagnostic. The response must match the request ID and contain **either**
`result.message` or `result.task`. A completed exchange requires an agent text
message or a completed task with text output. HTTP 200 plus JSON-RPC `error`, a
failed/interrupted task, or an empty/unexpected response is not success.

The script omits arbitrary reply text from shared evidence. Card-only success is
reported separately from message completion. Neither proves a deployed caller's
tool connection, identity, end-user delegation, or browser consent flow.

Reference: [A2A v1.0 JSON-RPC binding](https://a2a-protocol.org/v1.0.0/specification/#941-sendmessage).
See [recorded validation evidence](VALIDATION_EVIDENCE.md) for what was actually run.

## 5. Interpret failures without guessing the cause

Record the failing operation, timestamp, HTTP/protocol code, and principal context.
Use the [quick-reference table](QUICK_REFERENCE.md) to decide the next check.

- A card-target mismatch is a configuration/resolution issue, not proof of an outage.
- A consent-page 404 needs its own auth-flow investigation; don't treat it as
  equivalent to a 404 from the target card or JSON-RPC endpoint.
- Intermittent errors need correlated evidence. Token expiry, throttling, deployment
  state, and service failures are hypotheses, not automatically established causes.
- Retry only appropriate transient failures, bounded by a timeout and Retry-After
  when supplied. Repeated message calls can duplicate work. Do not retry invalid
  configuration or permanent authorization failures blindly.

## 6. Network and telemetry

DNS resolving does not prove the caller can reach the target. Check public-network
settings, private endpoint/DNS configuration, proxy/TLS behavior, and where the
request originates. A public IP can be wrong for an isolated target; a private IP
can be unreachable outside its network. Azure service-to-service access is not
universally allowed by default. See [network isolation](https://learn.microsoft.com/en-us/azure/foundry/how-to/configure-private-link).

Application/agent traces, where configured, help correlate data-plane invocations.
Azure Activity Log is useful for management/configuration changes, not a guaranteed
record of every failed A2A request.

A2A tasks/contexts are retained for 60 days since their latest write. Don't rely
on indefinite server-side retention for a later incident investigation.

## 7. Share only reviewed evidence

Never publish bearer tokens, OAuth codes, full consent-link queries, raw CLI identity
details, customer identifiers/prompts, or arbitrary remote responses. Avoid `curl -v`
on authenticated requests. The diagnostic intentionally summarizes, rather than
dumps, remote data.

Use [SUPPORT_GUIDE.md](SUPPORT_GUIDE.md) for escalation. Do not delay support until
you obtain a successful endpoint response; inability to reach it can be the issue.
