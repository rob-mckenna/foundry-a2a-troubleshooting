# Validation Evidence

Updated **2026-11-14 UTC**. The retained Azure sandbox passed direct v1.0 messaging
and a completed two-agent tool exchange. Earlier HTTP 424 and throttling failures
are preserved below; the final success does not establish their original root cause.
Local tests and live outcomes are reported separately.

## Local verification scope

| Item | Recorded context |
| --- | --- |
| Python | 3.11.9 |
| PowerShell | 7.7.0 |
| OS | Windows |
| A2A wire protocol | v1.0 JSON-RPC; `A2A-Version: 1.0` |
| SDK | None; PowerShell REST client and Python standard-library HTTP fixture |
| Authentication | Synthetic bearer value; not an Entra credential |
| Principal/tenant | None; no real identity was authenticated |
| Agent/deployment version | Local synthetic fixture; no Azure agent deployment |
| Azure CLI | Not used by the HTTP fixture; CLI behavior is mocked in regression tests |
| RBAC, consent, tenant policy | Not verified |
| Live Azure exchange | Not part of the local fixture; see the separate live run below |

The direct-client identity context is the current Azure CLI login. Success in
that context does not verify a deployed agent's tool access or delegated user consent.

## Executed checks

```text
python -m unittest discover -s tests -p test_validator.py -v
Ran 16 tests
OK

python -m unittest discover -s tests -p test_exchange.py -v
Ran 5 tests
OK

pwsh -NoProfile -File .\tests\test_diagnostic.ps1
134 passed; 0 failed; live Azure exchanges: 0
```

Python coverage comprises 16 static-validator tests and five HTTP integration
tests containing additional negative-case subtests. PowerShell coverage includes
card/JSON-RPC failures, native CLI exit handling, redaction, and subprocess exits.
The counts are test-run results, not percentages of platform reliability.

After adding the local demo and Azure orchestration tests, the complete offline
suite passed **59 Python tests**: 16 validator, five exchange, eight local-demo,
and 30 Azure orchestration tests. The PowerShell suite still passed **134**
assertions. Azure orchestration tests mock provisioning; their direct-probe bridge
also executes the production PowerShell helpers against the real loopback fixture.

Pylance syntax checks passed for the Python sources and tests. `git diff --check`
was used to check patch whitespace.

## Self-contained local demo verification

The public entry point was executed, not just its internal helpers:

```powershell
pwsh -NoProfile -File .\demo.ps1 -Local -EvidenceFile .\evidence\local-demo.json
```

All **11 scenarios** produced their expected results: one successful exchange,
six HTTP failures, a refused redirect, malformed JSON, a JSON-RPC error, and a
failed task. Every temporary server was stopped before exit.
See [local-demo.json](evidence/local-demo.json) for the sanitized recorded output.

Eight additional demo tests verify fixture authorization/version/request checks,
shutdown on failure, no fresh success evidence on failed assertions, CLI execution,
and cost/cleanup gates.

```text
python -m unittest discover -s tests -p test_demo_local.py -v
Ran 8 tests
OK
```

No sandbox is provisioned, no Entra principal authenticated, and no inference
charges incurred by these offline tests. The opt-in Azure sandbox was exercised
separately as described below and in [SANDBOX_GUIDE.md](SANDBOX_GUIDE.md).

## Retained sandbox: successful two-agent verification

At **2026-11-14 04:13 UTC**, the public Probe wrapper passed against a retained
sandbox. [Sanitized results](evidence/azure-retained-results.json) include the
control outcomes and verified configuration:

| Context | Recorded value |
| --- | --- |
| Runtime | Python 3.11.9, PowerShell 7.7.0, Azure CLI 2.92.0; no SDK |
| Deployment | East US 2; gpt-4.1-mini 2025-04-14, GlobalStandard capacity 10 |
| Observed rate limits | 10 requests and 10,000 tokens per 60 seconds |
| Agent versions | Target `1`; calling agent `3` |
| Direct identity | Current Azure CLI user; Entra audience `https://ai.azure.com` |
| Tool identity | Actual calling agent instance principal; `AgenticIdentityToken` |
| Target access | Foundry Agent Consumer at target project scope; actual identity verified |
| Tool configuration | GA `type: a2a`, `a2a_version: 1.0`; automatic Foundry card resolution |
| Lifecycle | Sandbox retained; no cleanup performed or scheduled |

Final observed sequence:

1. Anonymous v1.0 card: HTTP 401, expected rejection.
2. Authenticated v1.0 card: HTTP 200, valid card.
3. Direct `SendMessage` with `A2A-Version: 1.0`: HTTP 200, valid matching
   JSON-RPC envelope and completed text result.
4. Calling-agent Responses request: HTTP 200, response completed, one completed
   A2A call and one completed matching output. Call IDs/names matched, and the
   **remote tool output** matched the fixed synthetic diagnostic reply.
   Remote text and identifying values are omitted from public evidence.

Reproduce against that retained state (billable):

```powershell
pwsh -NoProfile -File .\demo.ps1 -Azure -AzureAction Probe -AcceptCost `
  -StateFile .\private-evidence\retained-sandbox-state.json `
  -EvidenceFile .\private-evidence\retained-verified-next.json `
  -DiagnosticsFile .\private-evidence\retained-diagnostics.jsonl
```

Other users create their own sandbox as described in
[SANDBOX_GUIDE.md](SANDBOX_GUIDE.md); private state is intentionally not distributed.

### What the investigation established

- Ordinary model Responses, target Responses, and isolated direct A2A passed.
- Caller controls at capacity 1 returned `rate_limit_exceeded`; the management
  API reported only 1 request and 1,000 tokens per minute. Capacity was increased
  to 10 with explicit approval. Some 429s and a 424 still occurred afterward.
- A caller version with A2A removed passed. The original A2A definition was then
  restored in version 3; the service returned completed tool items.
- The checker had incorrectly expected an `a2a_call` item. The actual response
  contained `a2a_preview_call` and `a2a_preview_call_output`. This caused a
  **false negative on HTTP 200**, not the earlier HTTP 424.
- The parser now checks matching completed pairs and the actual synthetic remote
  reply. Missing/duplicate/mismatched pairs, failure states, embedded errors, and
  incorrect replies are covered by regression tests.

The [official A2AToolCallOutput schema](https://learn.microsoft.com/python/api/azure-ai-agentserver-responses/azure.ai.agentserver.responses.models.a2atoolcalloutput?view=azure-python)
documents the legacy-named output discriminator. Its name is not proof of the
wire version: the GA tool was configured for v1.0, while only the direct HTTP
exchange's version header was inspected. Internal service-to-service HTTP headers
were not captured.

The capacity change and caller-version recreation both preceded success. Their
individual effects on the earlier transient failures were not conclusively
isolated. Do not claim that the parser fix, quota, RBAC, or a platform defect
explains every historical 424. No delegated consent or platform-wide reliability
claim is established. The selected legacy model is compatibility evidence only.

## First sandbox: historical direct success and two-agent failure

The public [Azure evidence](evidence/azure-sandbox.json) records two deliberate
attempts. Both used the sandbox created by the public entry point:

```powershell
pwsh -NoProfile -File .\demo.ps1 -Azure `
  -SubscriptionId SUBSCRIPTION_UUID -Location eastus2 `
  -Model gpt-4.1-mini -ModelVersion 2025-04-14 `
  -Sku GlobalStandard -Capacity 1 -AcceptCost
```

| Context | Recorded value |
| --- | --- |
| Runtime | Windows; Python 3.11.9; PowerShell 7.7.0; Azure CLI 2.92.0 |
| SDK | None; standard-library HTTPS and the production PowerShell helpers |
| Model/deployment | gpt-4.1-mini, 2025-04-14, GlobalStandard capacity 1, East US 2 |
| Model lifecycle | Catalogued Legacy; inference deprecation listed as 2027-04-14 |
| Target/calling agent versions | Both version `1`, read from creation responses |
| Agent API / connection management API | `v1` / `2025-04-01-preview` |
| Direct client | Current CLI **user**; real Entra token for `https://ai.azure.com` |
| Calling agent | Actual instance principal resolved; app-only `AgenticIdentityToken` connection |
| Permission check | Actual principal/role/scope triples matched for bootstrap, project identity, and caller |
| User delegation/consent | Not tested |

Observed in both attempts:

1. Anonymous GET of `/agentCard/v1.0`: **HTTP 401**, expected rejection.
2. Authenticated GET: **HTTP 200**, valid v1.0 card.
3. POST to the A2A base with `A2A-Version: 1.0`: **HTTP 200**, valid JSON-RPC
   `SendMessage` response with matching request ID and completed text output.
   The production helper validated the result; arbitrary model text is omitted.
4. POST to `/openai/v1/responses` using the calling agent: **HTTP 424**.
   No completed A2A tool item was observed, so the overall two-agent result is **FAIL**.

The direct request uses the same fixed synthetic prompt and v1.0 request shape
shown below for the local exchange. The Azure reply is deliberately not substituted
with the fixture's reply in this report.

Before the explicit second attempt, read-only checks confirmed both agents were
enabled, the connection target/audience/authentication matched, and role assignments
matched the **actual** caller instance identity rather than a substituted project
identity. The second probe capped calling-agent tool calls at one. Those checks
did not establish the cause of the 424. Error-marker metadata was inconclusive;
do not label this an RBAC, consent, quota, or product defect without further evidence.

Cleanup was explicitly approved and run through the public wrapper:

```powershell
pwsh -NoProfile -File .\demo.ps1 -Cleanup -ConfirmDelete
```

The saved group ID and ownership tags matched before deletion, and a subsequent
management-plane read confirmed the resource group was absent. Private state is
retained with phase `deleted`. Entra directory-object deletion was **not verified**.
The run used billable model inference; no statement about a final invoiced amount
is made. The selected legacy model is not a production recommendation.

## One actual local v1.0 exchange

The HTTP fixture binds only to loopback on an ephemeral port and is stopped after
the tests. The tests call the production discovery and message helpers. They do
not replace the HTTP client or construct a fictitious success transcript.

Observed sequence:

1. GET `/a2a/agentCard/v1.0`: HTTP 200, v1.0 card.
2. POST `/a2a`: HTTP 200, JSON-RPC `SendMessage`, matching request ID.
3. Request and discovery carry `A2A-Version: 1.0` and the expected synthetic bearer
   header. The credential value is not retained.
4. Response contains `result.message`, `ROLE_AGENT`, and nonempty text.

Sanitized request:

```json
{
  "jsonrpc": "2.0",
  "id": "[generated]",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "[generated]",
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

Sanitized fixture response:

```json
{
  "jsonrpc": "2.0",
  "id": "[matched request]",
  "result": {
    "message": {
      "messageId": "[synthetic]",
      "role": "ROLE_AGENT",
      "parts": [{"text": "A2A diagnostic OK"}]
    }
  }
}
```

The visible reply is explicitly authored public fixture text, **not model output
from Foundry**. Real remote reply text is omitted by the live diagnostic's evidence
allowlist.

## Reproduced failure cases

| Injected case | Observed diagnostic outcome | Evidence source |
| --- | --- | --- |
| HTTP 401, 403, 404, 405, 429, 500 | FAIL with the original HTTP status | Actual loopback HTTP responses |
| JSON-RPC error with HTTP 200 | FAIL, `rpc-error`; remote message omitted | Actual loopback HTTP response |
| Failed/canceled/rejected task | FAIL, `task-not-completed` | Actual loopback HTTP response |
| Auth-required/input-required/working task | FAIL, not completed | Actual loopback HTTP response |
| Completed task with text artifact | PASS | Actual loopback HTTP response |
| HTTP 302 with Location | FAIL; no credential-bearing redirect followed | Actual loopback HTTP response |
| Other 3xx redirects or unknown HTTP failure | FAIL | PowerShell mocks |
| Malformed JSON/invalid response shapes | FAIL | PowerShell mocks |
| DNS/transport/token/native CLI failure | FAIL; safe phase/category, no secret output | PowerShell mocks |
| Wrong target/card/version/identity/audience | Static FAIL | Python regression tests |
| Invalid CLI arguments/unreadable JSON | Nonzero process exit | CLI regression tests |
| Remote error, token, custom prompt/reply sentinel | Absent from diagnostic output/evidence | Redaction assertions |

Injected failures are expected negative-test results, not incidents observed in Azure.
Machine-readable HTTP evidence is in [local-results.json](evidence/local-results.json).

## Reproduce and refresh local evidence

From the repository root, with Python and PowerShell 7+ installed:

```powershell
$env:A2A_EVIDENCE_PATH = Join-Path (Get-Location) "evidence\local-results.json"
python -m unittest discover -s tests -p "test_*.py" -v
if ($LASTEXITCODE -ne 0) { throw "Python regression tests failed" }
pwsh -NoProfile -File .\tests\test_diagnostic.ps1
if ($LASTEXITCODE -ne 0) { throw "PowerShell regression tests failed" }
Remove-Item Env:\A2A_EVIDENCE_PATH
```

Review refreshed versions, timestamps, and test outcomes before publishing.
The checked-in JSON represents the recorded run; refresh it only intentionally.

## Reproduce direct Azure verification against an existing target

Provide an existing enabled target and ensure the current CLI login has endpoint
access. Run the following yourself, replacing the target names:

```powershell
pwsh -NoProfile -File .\a2a_diagnostic.ps1 `
  -ServerUrl "https://ACCOUNT.services.ai.azure.com/api/projects/PROJECT/agents/AGENT/endpoint/protocols/a2a" `
  -SendMessage -EvidencePath .\private-evidence\live.json
```

One inference request can incur charges. This command does not deploy an agent,
change RBAC, or test a browser consent flow. Review the sanitized output and
privately record the target agent's deployment version and actual principal
context. Only report a **direct Azure v1.0 exchange** as verified when those checks pass.

An article can cite the later verified two-agent result and the historical
failures, with their exact contexts. It must distinguish the confirmed checker
false-negative from the earlier HTTP 424s, whose root cause remains unconfirmed.
