# Public Troubleshooting Package

This repository contains public, unofficial guidance and synthetic test cases.
It contains no approved customer-specific incident evidence.

## Share these resources

1. [README.md](README.md): scope, capabilities, prerequisites, and commands.
2. [QUICK_REFERENCE.md](QUICK_REFERENCE.md): first action by failing operation.
3. [A2A_TROUBLESHOOTING_GUIDE.md](A2A_TROUBLESHOOTING_GUIDE.md): detailed configuration
   and reproducible v1.0 request.
4. [SUPPORT_GUIDE.md](SUPPORT_GUIDE.md): public escalation checklist.
5. [a2a_validator.py](a2a_validator.py): static checks.
6. [a2a_diagnostic.ps1](a2a_diagnostic.ps1): live discovery and opt-in message test.
7. [tests](tests): offline regression and synthetic exchange tests.
8. [VALIDATION_EVIDENCE.md](VALIDATION_EVIDENCE.md): recorded evidence and limitations.
9. [SANDBOX_GUIDE.md](SANDBOX_GUIDE.md) and [demo.ps1](demo.ps1): create a local test
   target without Azure, or opt into a dedicated two-agent Azure sandbox.

No existing target? Start with `pwsh -NoProfile -File .\demo.ps1 -Local`.

## First action

- **Configuration/card-target error:** validate a real JSON configuration with
  `python a2a_validator.py --config config.json`. Foundry connections omit card paths;
  direct SDK clients use the relative path `agentCard/v1.0`.
- **Card or invocation failure:** run PowerShell discovery, then explicitly opt in
  to one message if needed. Do not expect GET on the base URL to return the card.
- **Consent failure:** record its distinct auth type and operation; do not publish
  the full consent URL or infer that endpoint RBAC is its confirmed cause.
- **Intermittent failure:** correlate operations and identity context before choosing
  a retry strategy. Repeated messages may duplicate work.

Follow the commands and prerequisites in [README.md](README.md).

## Before public sharing

Review licensing/provenance and all outputs. Remove customer identifiers, tokens,
OAuth codes, identity details, raw remote text, and sensitive screenshots.
The guides are public; generated private evidence is not automatically approved
for publication. State whether a result came from a local fixture, direct Azure
CLI client, or deployed agent. These are different verification scopes.

Last documentation verification: **2026-11-13**.
