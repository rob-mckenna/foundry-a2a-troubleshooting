# Diagnostic sandbox deployment plan

Status: Deployed and verified; sandbox retained

## Scope and approval

Modify this existing repository with a standard-library Python/Azure CLI sandbox.
The user approved a small paid East US 2 smoke test using gpt-4.1-mini
2025-04-14, GlobalStandard capacity 1. The first sandbox was deleted with approval.
For issues #1-#5 the user now requests sequential live troubleshooting against a
new retained sandbox. Do not delete this environment without new explicit approval.
Subscription selection remains private runtime input, not a checked-in value.

Use separate retained-sandbox state/evidence paths. Enable private allowlisted
diagnostic journaling and provision-only creation before running controlled probes.
The existing Foundry Toolkit selection is empty; create the isolated project
already approved rather than adopting another resource. These are remote prompt
agents, not Python hosted agents; hosted-agent F5/debugpy setup is not applicable.

## Architecture

- One uniquely named, tagged resource group.
- One Foundry AIServices account with local authentication disabled.
- One project, one model deployment, and two prompt agents.
- Incoming v1.0 A2A on the target; RemoteA2A tool on the caller.
- Explicit caller instance identity and scoped endpoint permission.
- Separate direct-user and caller-agent probes; no delegated-user claim.

## Steps

- [x] Implement create/probe/ownership-checked cleanup and private recovery state.
- [x] Add offline negative-path tests and validate the existing local demo.
- [x] Validate configuration, model availability, quota, and authorization.
- [x] Provision and capture sanitized successful or failed live outcomes.
- [x] Delete only the newly created tagged group and verify deletion.
- [x] Update public documentation with measured scope and limitations.

## Safety and verification

Use explicit subscription selection without changing Azure CLI defaults.
Require explicit cost acceptance and separate deletion confirmation.
Never persist access tokens or publish identifiers, remote text, or raw errors.
Persist partial state before mutations; refuse foreign resource groups.
Retry bounded readiness reads only, not billable inference.
Keep local, mocked, direct-user, and true two-agent verification distinct.
The model is catalogued as legacy: this is compatibility evidence, not a
production model recommendation. Resource-group deletion does not establish
Entra directory-object cleanup.

## Preparation results

The user approved this architecture and live-test/cleanup scope.
Azure CLI is the deployment recipe: this small diagnostic intentionally needs
no application hosting, azd template, container, storage, or package install.
The latest complete offline run passed 59 Python tests and 134 PowerShell assertions.
Pylance syntax validation passed for the new harness and tests.
The live catalog lists the selected model/SKU, and available inference quota
exceeds capacity 1. The harness rechecks these prerequisites before provisioning.
The first run failed with HTTP 424. The subsequent retained-sandbox run verified
direct v1.0 messaging and a completed remote A2A call/output pair.

## Validation checklist

- [x] All validation checks pass for the approved Python/REST path.
  - [x] Core: CLI authentication, enabled subscription, registered provider,
    model/version/SKU, and available inference quota checked read-only.
  - [x] Build equivalent: 59 offline Python tests, 134 PowerShell assertions,
    Pylance syntax checks, and patch whitespace check passed.
  - [x] Docker build: not applicable (no container).
  - [x] Azure Policy: five applicable/inherited assignments are visible;
    enforcement remains authoritative during provisioning, without bypass.
    No claim of comprehensive static policy compliance is made.
  - [x] User approved validating the actual Python/REST path rather than
    introducing a separate Bicep implementation solely for validation.
  - [x] Effective subscription permissions include resource-group creation,
    account creation, and role-assignment creation.

## Role assignment verification

Static mapping verified:

- Bootstrap CLI principal: Foundry Owner at the dedicated account scope, for
  agent configuration and identity management; never subscription-wide.
- Project managed identity: Foundry User at that dedicated account for model use.
- Calling agent instance identity: Foundry Agent Consumer at the target project.
- No substitution of the project identity for a missing agent instance identity.

The script records role-assignment acceptance separately from runtime success.
The anonymous card probe must reject access, while authenticated discovery,
direct messaging, and an actual completed A2A tool item must all pass.

## Section 7: Validation Proof

Final issue #5 validation, 2026-11-14 UTC:

- Full Python suite: 59 passed. PowerShell diagnostic suite: 134 assertions passed.
- Pylance syntax checks passed for the harness and sandbox tests.
- Public wrapper live Probe: success, including anonymous rejection, authenticated
  card, direct v1.0 exchange, and completed paired remote A2A output.
- Calling agent version 3 restored the original tool definition after a temporary
  no-tool version 2 control. Target remains version 1.
- The user-approved capacity increase to 10 is retained.
- Historical 424s and 429s are preserved. The confirmed checker false-negative
  affected HTTP 200 output item parsing, not the HTTP 424 transport result.

Retained-sandbox revalidation, 2026-11-14 UTC:

- Full Python regression command below: 56 tests passed, including 27 sandbox
  tests and provision-only behavior. Pylance syntax and whitespace checks passed.
- Fresh read-only model preflight reconfirmed the selected version/SKU, available
  quota, enabled subscription, registered provider, and CLI user context.
- Resource shapes and scoped role mapping are unchanged from the verified prior
  provisioning. New features only add private metadata and optional probe deferral.
- Prior approval for the Python/REST validation recipe remains applicable.
- Existing deleted state is preserved; new state will use a distinct filename.

Recorded 2026-11-13:

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -p "test_*.py" -q` | 52 passed |
| `pwsh -NoProfile -File .\tests\test_diagnostic.ps1` | 134 assertions passed |
| Pylance file syntax checks | Harness and new test file passed |
| `git diff --check` | Passed |
| Azure CLI account/provider/model/usage reads | Enabled, Registered, selected model listed, quota available |
| ARM permissions read | Group/account/role-assignment writes allowed |
| Azure CLI inherited policy assignment list | Five assignments visible; no bypass |

These are preparation checks, not a successful live A2A exchange. Bicep
compilation, ARM template what-if, and Docker build are not applicable to the
user-approved imperative Python/REST implementation.

## First sandbox: historical execution and cleanup

- The public create wrapper provisioned the isolated group/account/project/model,
  both version-1 agents, connection, and role assignments.
- Authenticated v1.0 card discovery and direct Entra-authenticated messaging passed.
- Anonymous discovery returned HTTP 401 as expected.
- Calling-agent Responses requests returned HTTP 424 in two deliberate attempts.
  No successful A2A tool item was observed; the failure's cause is not established.
- Read-only verification matched each actual bootstrap/project/caller principal to
  its expected role and exact account/project scope.
- User-approved cleanup verified the saved group ID and ownership tags, deleted
  only that group, and confirmed absence. An independent subsequent read also
  returned HTTP 404. Private state remains with phase `deleted`.
- Entra directory-object cleanup is not verified.
- The user confirmed Microsoft-derived provenance; the original MIT notice stays.

Public evidence and limitations are in
[VALIDATION_EVIDENCE.md](../VALIDATION_EVIDENCE.md) and
[azure-sandbox.json](../evidence/azure-sandbox.json).

## Retained sandbox: current state

Issues #1-#5 track private diagnostics, retained provisioning, isolation, live fix,
and publication evidence. The latest successful result is recorded in
[azure-retained-results.json](../evidence/azure-retained-results.json).

The retained group is not deleted and no cleanup is scheduled. New explicit
approval is required before removal. Further probes remain billable. Private
state, correlation metadata, and original caller definition stay under the ignored
private-evidence directory and must not be published.
