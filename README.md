# Microsoft Foundry A2A Troubleshooting Toolkit

Unofficial troubleshooting samples for **Foundry (new), Azure public cloud**.
These samples are not a Microsoft support commitment or a general A2A conformance
suite. Documentation checked against public Microsoft Learn on **2026-11-13**.

Separate three operations before diagnosing a failure:

1. **Discovery:** retrieve the target's authenticated agent card.
2. **Invocation:** send a version-selected A2A message.
3. **Consent/delegation:** establish the identity context required by a tool.

A successful discovery request does not prove invocation, a consent flow, or a
deployed agent's permissions.

## Try it without an existing agent

Install Python 3.11+ and PowerShell 7+, then run:

```powershell
pwsh -NoProfile -File .\demo.ps1 -Local
```

This creates a temporary local server, performs a v1.0 message exchange, demonstrates
ten failure scenarios, writes reviewed-format evidence, and stops the server.
It requires no Azure subscription, login, model, Docker, or third-party Python packages.
Expected failures are clearly labeled; exit zero means all requested expectations
were verified, not that each simulated request succeeded.

For a real two-agent test, the opt-in Azure sandbox creates its own dedicated
resource group, Foundry resource/project, model deployment, target agent, and calling
agent. No existing endpoint is needed. **Live direct v1.0 messaging and a completed
two-agent exchange were verified on 2026-11-14 UTC.** Earlier HTTP 424 and throttling
failures are preserved in the [recorded evidence](VALIDATION_EVIDENCE.md), alongside
the checker fix and the successful retained-sandbox run. This is a measured
configuration, not a platform-wide reliability claim.

```powershell
# Paid, explicit opt-in. Replace values; availability and permissions vary.
pwsh -NoProfile -File .\demo.ps1 -Azure `
  -SubscriptionId SUBSCRIPTION_UUID -Location REGION `
  -Model MODEL_NAME -ModelVersion MODEL_VERSION -AcceptCost

# Re-test the saved sandbox (billable requests; no new sandbox).
pwsh -NoProfile -File .\demo.ps1 -Azure -AzureAction Probe -AcceptCost

# Explicitly delete only the ownership-verified sandbox.
pwsh -NoProfile -File .\demo.ps1 -Cleanup -ConfirmDelete
```

Read [SANDBOX_GUIDE.md](SANDBOX_GUIDE.md) for costs, prerequisites, cleanup, and
verification boundaries. The harness never installs tools, signs you in, or
silently substitutes a model/region.

The verified gpt-4.1-mini configuration used `-Capacity 10`; capacity 1 reported
only 1 request/minute and 1,000 tokens/minute and produced throttling during the
investigation. Capacity is model-specific: check actual limits, not just available
quota. Use `-ProvisionOnly` to defer inference, then `-AzureAction Diagnose` for
individual controls. Resources remain deployed until explicitly cleaned up.

## Current documented capabilities

| Surface | Support |
| --- | --- |
| `a2a` tool and incoming A2A v1.0 | Generally available |
| `a2a_preview` and incoming v0.3 | Preview; not recommended for new production integrations |
| Incoming v1.0 transport | JSON-RPC only; no HTTP+JSON or gRPC |
| Incoming modalities | Text only |
| Incoming streaming/SSE | Not supported |
| Incoming agent requirement | Responses protocol |
| Incoming authentication, including card discovery | Microsoft Entra ID; no anonymous or key-based access |
| A2A task/context retention | 60 days since the latest write |
| `AgentOnBehalfOfUser` | Preview; requires the source's AgentBlueprint endpoint scheme |

These incoming limitations describe **Foundry targets**, not every external A2A
server or the full A2A specification. The outbound tool supports external targets
with other authentication methods; this toolkit's validator deliberately covers
Foundry targets only. Protocol GA does not make every SDK or delegated feature GA.

## Configure the correct surface

Target base URL (use project and agent **names**, not an arbitrary resource UUID):

```text
https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT/agents/AGENT/endpoint/protocols/a2a
```

- **Foundry-to-Foundry connection:** set its target to that base URL and audience
  to `https://ai.azure.com`. **Omit the card path**; Foundry resolves it automatically.
  Use the GA `a2a` tool with v1.0 selected.
- **Direct A2A SDK client:** configure the custom relative path `agentCard/v1.0`.
  The authenticated discovery URL is the base URL plus `/agentCard/v1.0`.
- **Direct protocol request:** set `A2A-Version: 1.0` or `a2a-version=1.0`.
  Conflicting selectors are invalid. Without explicit selection, Foundry defaults
  to preview v0.3. This toolkit uses the header and rejects queries on configuration
  base URLs; that is a tool input rule, not a platform prohibition.
- **Incoming enablement:** configure `agent_card` and
  `agent_endpoint.protocol_configuration` with `responses` and `a2a` through REST
  or SDK. Incoming enablement is not yet configurable in the portal. Creating an
  outgoing tool connection in the portal is a different operation.

See the [detailed guide](A2A_TROUBLESHOOTING_GUIDE.md) for identities and role scope.

## Tools and prerequisites

| File | What it verifies |
| --- | --- |
| [a2a_validator.py](a2a_validator.py) | Static target, discovery-mode, version, audience, and identity-label consistency |
| [a2a_diagnostic.ps1](a2a_diagnostic.ps1) | Authenticated v1.0 card discovery; optional one-message exchange using the Azure CLI login |
| [demo.ps1](demo.ps1) | One-command local demo and opt-in Azure sandbox entry point |
| [demo_local.py](demo_local.py) | Shared local fixture and bounded demo scenarios |
| [sandbox_azure.py](sandbox_azure.py) | Dedicated Azure sandbox creation, probe, and ownership-checked cleanup |
| [QUICK_REFERENCE.md](QUICK_REFERENCE.md) | First action by failing operation |
| [A2A_TROUBLESHOOTING_GUIDE.md](A2A_TROUBLESHOOTING_GUIDE.md) | Detailed setup, troubleshooting, and reproducible request |
| [SUPPORT_GUIDE.md](SUPPORT_GUIDE.md) | Sanitized escalation checklist |
| [CUSTOMER_PACKAGE.md](CUSTOMER_PACKAGE.md) | Public package handoff |
| [VALIDATION_EVIDENCE.md](VALIDATION_EVIDENCE.md) | Recorded local results and explicit Azure verification status |
| [SANDBOX_GUIDE.md](SANDBOX_GUIDE.md) | Self-contained demo walkthrough and safety boundaries |

Python validation/tests use the standard library only (tested on Python 3.11).
The live diagnostic requires PowerShell 7+, Azure CLI, a current CLI login, and an
existing enabled target. Sign in yourself with `az login` if necessary.

### Static validation

```powershell
# Print a sample, not a validation of your environment.
python .\a2a_validator.py --example

# Enter real target configuration; no credentials are requested.
python .\a2a_validator.py --interactive

# Or validate your own JSON object.
python .\a2a_validator.py --config .\config.json
```

Use `mode: "foundry_connection"` without `card_path`, or `mode: "direct_client"`
with `card_path: "agentCard/v1.0"`. Both `server_url` and `tool_url` refer to the
**target**; they do not require the calling agent to belong to the target project.
Use explicit `protocol_version`, `audience`, and `auth_type` fields.

Accepted identity labels include `AgenticIdentityToken`, `ProjectManagedIdentity`,
`UserEntraToken`, and `AgentOnBehalfOfUser`. `ServicePrincipal` is a direct-client
description, not a RemoteA2A connection authType. These labels alone do not prove
consent, tenant policy, endpoint authorization, or permissions.

### Live discovery and optional message exchange

```powershell
# Discovery only; no inference message.
pwsh -NoProfile -File .\a2a_diagnostic.ps1 `
  -AccountName ACCOUNT -ProjectId PROJECT -SubAgentId AGENT

# Explicit opt-in: one synthetic message; can incur inference charges.
pwsh -NoProfile -File .\a2a_diagnostic.ps1 `
  -ServerUrl "https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT/agents/AGENT/endpoint/protocols/a2a" `
  -SendMessage -EvidencePath .\private-evidence\live.json
```

The diagnostic uses the **current Azure CLI login**. It does not impersonate a
deployed agent, run that agent's tool connection, or automatically verify RBAC.
Evidence excludes credentials, identifying target values, and arbitrary remote
reply text. Review generated evidence before publication.

Exit codes: `0` requested checks passed, `1` validation/runtime failure, `2` invalid
CLI input or unreadable configuration. The Python `--example` operation returns
`0` but does not perform checks. Warnings must still be reviewed.

### Offline regression tests

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
pwsh -NoProfile -File .\tests\test_diagnostic.ps1
```

Tests use synthetic configuration, mocked failures, and a loopback fixture. They
do not establish Azure availability or validate real Entra credentials.

## Publication and support boundaries

No unsupported cause-frequency statistics or systemic reliability claims are made.
Record exact operations and sanitized evidence before attributing a product defect.
Do not publish tokens, OAuth codes, full consent URLs, tenant/principal IDs, customer
prompts, or arbitrary responses. Do not capture authenticated requests with `curl -v`.

The existing Microsoft MIT attribution in [LICENSE](LICENSE) is retained for the
Microsoft-derived material. This does not make the toolkit an official Microsoft
product or support commitment. An ignore rule is not a secrecy boundary.
All guides listed above are intended as public documentation.

## Authoritative references

- [Enable incoming A2A, protocol versions, identities, and limitations](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint)
- [Connect with the A2A tool](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/agent-to-agent)
- [A2A authentication](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-to-agent-authentication)
- [Configure user delegation](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/configure-user-delegation)
- [Foundry RBAC](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry)
- [Network isolation](https://learn.microsoft.com/en-us/azure/foundry/how-to/configure-private-link)
- [A2A v1.0 specification](https://a2a-protocol.org/v1.0.0/specification/)
