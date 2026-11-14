# Self-contained A2A Demo

You do not need an existing agent to try this toolkit. Choose the free local
demonstration or explicitly opt into an isolated Azure sandbox.

## Free local demonstration

Prerequisites: Python 3.11+ and PowerShell 7+ on PATH. No pip packages, Azure login,
subscription, Docker, or model download is needed.

```powershell
pwsh -NoProfile -File .\demo.ps1 -Local
```

The demo creates a loopback HTTP server on an ephemeral port, calls the same
PowerShell discovery/message helpers used by the live diagnostic, captures
sanitized evidence, and stops the server before returning. It does not start a
long-lived background service.

Default scenarios:

- Successful v1.0 discovery and text message.
- HTTP 401, 403, 404, 405, 429, and 500.
- Redirect refused, malformed card JSON, JSON-RPC error at HTTP 200, failed task.

Choose a single scenario:

```powershell
pwsh -NoProfile -File .\demo.ps1 -Local -Scenario throttled
pwsh -NoProfile -File .\demo.ps1 -Local -Scenario success `
  -EvidenceFile .\private-evidence\my-local-result.json
```

Exit `0` means each scenario's expected outcome was verified. A displayed expected
`FAIL` is the point of the negative scenario, not a failing demo run. Nonzero exit
means prerequisites, assertions, or evidence output failed.

The fixture validates its synthetic authorization header, explicit v1 selection,
route, and message shape. Its bearer value is **not an Entra token**. Local scenarios
do not establish Azure availability, permissions, quotas, consent, or a product
defect. Fixture reply text is deliberately public synthetic text.

## Optional Azure two-agent sandbox

The automation and its negative paths are offline-tested. See the separate
[recorded verification status](VALIDATION_EVIDENCE.md) before making any claim
of a successful live deployment or agent-to-agent exchange.

The first sandbox reproduced a calling-agent HTTP 424 and was deleted with approval.
A subsequent **retained sandbox passed direct v1.0 and two-agent verification**
on 2026-11-14 UTC. It remains deployed for investigation. Historical 424s do not
have a confirmed root cause; a separate checker false-negative was identified and
fixed when the service returned completed legacy-named A2A output items.

Prerequisites:

- Python 3.11+, PowerShell 7+, and Azure CLI on PATH.
- Your own completed `az login`, with an enabled selected subscription.
- Permission to create a resource group, Foundry resources/projects/model deployments,
  agents/connections, and scoped role assignments. Resource Contributor alone does
  not grant permission to create role assignments.
- The Cognitive Services resource provider registered in the subscription.
- A supported model/version/SKU in the chosen region and adequate quota/capacity.
- Tenant policy allowing the required agent identity creation and app-only access.

Create and test using the recorded configuration (replace the subscription UUID):

```powershell
pwsh -NoProfile -File .\demo.ps1 -Azure `
  -SubscriptionId SUBSCRIPTION_UUID `
  -Location eastus2 `
  -Model gpt-4.1-mini -ModelVersion 2025-04-14 `
  -Sku GlobalStandard -Capacity 10 `
  -AcceptCost
```

There is no universal guaranteed region/model default. Choose current supported
values for your subscription. The harness does not change your global Azure CLI
subscription, install extensions, register providers, log in, or silently choose
a different region/model. A deployment rejection is a failure, not a passed check.

For the recorded gpt-4.1-mini 2025-04-14 GlobalStandard test, the successful run
used capacity **10**. The management API reported 10 requests and 10,000 tokens
per minute, compared with only 1 request and 1,000 tokens at capacity 1.
The latter produced `rate_limit_exceeded` during caller tests. These are observed
model-specific limits, not a universal conversion or guaranteed minimum. The
harness keeps its conservative default and never increases capacity automatically.
The selected model is catalogued as Legacy; this example reproduces a compatibility
test rather than recommending a model for new production deployments.

### What the sandbox creates

- A uniquely named dedicated resource group with toolkit/run ownership tags.
- A Foundry AIServices resource and project, with Entra authentication.
- One explicitly selected model deployment.
- A target prompt agent with incoming A2A enabled and a diagnostic text skill.
- A calling prompt agent with a GA v1.0 A2A tool and an app-only identity connection.
- Scoped role assignments needed by the bootstrap principal and calling agent.

The target's declared skill is only to respond to a synthetic diagnostic prompt.
This is not a hosted container, workflow, general assistant deployment, or browser
OAuth/consent sample. No customer data is needed.

### What counts as verification

The intended sequence is:

1. Check runtime, subscription, provider, and selected model deployment inputs.
2. Provision the dedicated sandbox.
3. Resolve the calling agent's actual identity; do not substitute the project identity.
4. Configure scoped target access and the A2A connection.
5. Verify anonymous card access is rejected and retrieve the authenticated v1.0 card.
6. Send one direct v1.0 message using the CLI principal.
7. Invoke the calling agent and verify an actual successful A2A tool call, not just
   a text answer that could have been generated without calling the target.
8. Save separate direct-client and agent-to-agent results in sanitized evidence.

Both probes must pass for a complete sandbox test. A failed or interrupted task,
malformed response, or absent successful A2A tool call is not success.
For this synthetic sandbox, the remote tool output must match the requested
`A2A diagnostic OK` reply. The checker requires exactly matched completed
`a2a_preview_call` / `a2a_preview_call_output` pairs, not just the final model text.
These are the observed and documented Responses item names even with GA
`type: a2a`, `a2a_version: 1.0` tool configuration. They are not a reason to switch
the configured tool to `a2a_preview` or claim a v0.3 wire exchange.
The harness is not a proof of user delegation, OAuth consent, production readiness,
cross-tenant access, or network-isolated configuration.

For a retained troubleshooting environment, add `-ProvisionOnly` to Azure Create.
It creates the resources and checks authenticated card readiness, but does not send
the inference probes. Evidence records provisioning separately from exchange
verification. Later use Azure Probe with the same `-StateFile`. The environment
persists after success or failure; there is no automatic cleanup.

### Costs and persistence

`-AcceptCost` is required for creation and probing. Model deployment and inference
can incur charges; calling-agent execution can include additional model calls.
Capacity units depend on the model/SKU and are not a universal token-rate measure.
This example is pay-as-you-go, not a provisioned-throughput purchase.

Azure resources remain until explicitly cleaned up. Do not assume process exit
removes them. Budget alerts are not spending caps. Avoid repeated probes as a
substitute for diagnosing permanent failures.

The harness polls bounded, non-inference readiness reads. It never automatically
replays a billable message after a failure. A successful role-assignment write is
not proof that access has propagated; a failed probe can require diagnosis and an
explicit later retry.

Private state defaults to `private-evidence\sandbox-state.json`; sanitized Azure
results default to `private-evidence\azure-sandbox.json`. State contains resource
identifiers for recovery/cleanup and must not be published. Preserve it after a
partial failure so the created sandbox can be identified.

Retest without creating a new sandbox:

```powershell
pwsh -NoProfile -File .\demo.ps1 -Azure -AzureAction Probe -AcceptCost
```

### Private troubleshooting metadata

Add `-DiagnosticsFile .\private-evidence\azure-diagnostics.jsonl` to Azure Create,
Probe, or Diagnose to append private timestamps, structured error codes, and selected
request/correlation IDs from the Python Azure transport. Public evidence remains
separate. Numeric retry/rate-limit headers and the structured rate-limit source
are also retained when present. The existing direct A2A PowerShell helpers report sanitized outcomes;
they do not currently expose server correlation headers to this journal.

The diagnostic path must resolve inside this repository's ignored
`private-evidence` directory and differ from state/evidence paths. The journal
never stores tokens, authorization/cookie headers, URLs, prompts, or arbitrary
remote message text. JSON error codes and correlation IDs remain private support
metadata: do not copy the journal into an issue or public evidence. A failed
journal write is an explicit failure, not a silently successful diagnostic run.

Azure Create and Probe never automatically delete the sandbox. Keep the same
state file for live investigation, use a distinct evidence filename per attempt,
and run Cleanup only after an explicit decision to remove the environment.

### Isolate a live failure

Run independent controls against the retained state:

```powershell
pwsh -NoProfile -File .\demo.ps1 -Azure -AzureAction Diagnose -AcceptCost `
  -StateFile .\private-evidence\retained-sandbox-state.json `
  -EvidenceFile .\private-evidence\controls-01.json `
  -DiagnosticsFile .\private-evidence\retained-diagnostics.jsonl
```

`-Control` selects `model`, `target-responses`, `caller-no-tools`, `direct-a2a`,
`caller-a2a`, or `all` (default). Each selected control executes once; failures
are recorded and the remaining controls still run. There are no automatic
inference retries. Each control can incur model usage charges.

The no-tool controls set `tools: []` and `tool_choice: none`, and reject observed
tool output. These request-level settings are not proof that the service skipped
tool preparation. During the recorded investigation an actual no-tool caller
version was also tested, then the original tool definition was restored.
Caller A2A requires tool execution. A successful text control is not
evidence of a remote tool call. Use the separate outcomes to locate the failing
boundary rather than inferring its cause from HTTP 424 alone.

If a particular permission, region, API behavior, or quota fails, capture the safe
phase/category and resolve it. No silent fallback establishes success.

## Scoped cleanup

```powershell
pwsh -NoProfile -File .\demo.ps1 -Cleanup -ConfirmDelete
```

Cleanup requires the saved state and matching resource-group ownership tags.
It must refuse foreign or inconsistent targets; it never accepts an arbitrary
resource group to delete. If state is missing, do not point cleanup at unrelated
resources: inspect the tagged sandbox manually through an authorized Azure session.

State is retained with phase `deleted` only after a management-plane read confirms
the group is absent. Failed or timed-out deletion retains recoverable state.
Creation refuses an existing state file; use a different explicit `-StateFile`
for a new sandbox rather than overwriting evidence from a previous run.

Delete only the sandbox group you intentionally created. Group deletion removes
its Azure resources and associated role assignments; do not assume it proves
deletion of every Entra directory object. Review identity lifecycle separately
under your tenant policy if required.

## Reproducible evidence and tests

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
pwsh -NoProfile -File .\tests\test_diagnostic.ps1
```

The tests are offline. They verify local HTTP behavior and mock the Azure orchestration
boundaries; they cannot establish that a region has quota or a new Azure API works
in your tenant.

The recorded complete offline run passed **59 Python tests** (including 30 Azure
orchestration tests) and **134 PowerShell assertions**. Azure orchestration tests
cover cost/deletion gates, collision/ownership checks, partial-state recovery,
model/quota validation, CLI error redaction, actual local HTTP probes through the
production helpers, and rejection of text-only answers without a completed A2A call.

See [VALIDATION_EVIDENCE.md](VALIDATION_EVIDENCE.md) and
[local-demo.json](evidence/local-demo.json) for recorded local results. Review all
generated evidence before sharing. Tokens, full consent URLs, actual principals,
customer payloads, and arbitrary remote reply text must not be published.

Authoritative setup references:
[incoming A2A](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/enable-agent-to-agent-endpoint),
[A2A tool](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/agent-to-agent),
[RBAC](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry).
