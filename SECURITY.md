# Security Policy

`tq-forge` is designed from the ground up for safe, transparent, and deterministic operation in developer environments.

## Architecture & Trust Model

- **Zero Outbound Telemetry**: The CLI, scorers, generators, and hooks make zero outbound network calls and send no analytics or telemetry.
- **Token-Free Scoring**: Artifact quality scoring and linting are performed entirely via local static analysis using Python standard library heuristics.
- **Execution Sandboxing**: Newly generated skills and subagents are scaffolded into an isolated sandbox (`$TQ_FORGE_HOME/sandbox/`) and never touch active configurations or production repositories until explicitly promoted.
- **Hook Policy Enforcement**: Scaffolding includes proactive guardrails for Claude Code lifecycle hooks:
  - `PreToolUse`: blocks dangerous root deletions (`rm -rf /`) and force git pushes (`git push --force`) with `exit 2`.
  - `PostToolUse`: validates file syntax on write before continuation.
  - `Stop`: prevents premature session termination if merge conflict markers or unfinished placeholders are detected.

## Supported Versions

| Version | Supported | Status |
| :--- | :---: | :--- |
| `1.1.x` | Yes | Current stable release |
| `1.0.x` | Yes | Legacy maintenance |
| `< 1.0` | No | Unsupported |

## Reporting a Vulnerability

If you discover a security vulnerability or security bug in `tq-forge`, please report it responsibly:

- **Do NOT open a public GitHub issue.**
- Submit a private advisory via GitHub:
  **https://github.com/tanishq286/tq-forge/security/advisories/new**
- Alternatively, contact the maintainer directly at `tanishqagarwal2864@gmail.com` with the subject line `[SECURITY] tq-forge Vulnerability Report`.

Please include:
1. Description of the vulnerability and attack vector.
2. Steps to reproduce or proof-of-concept configuration.
3. Impact assessment and potential mitigations.

You will receive an initial response within 48 hours and regular updates until resolution.
