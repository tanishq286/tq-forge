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

## What the context optimizer writes

`tq-forge optimize` and `tq-forge shield` rewrite existing project files. (`tq-forge scaffold` only adds files, except that `scaffold mcp --scope project` merges new servers into an existing `.mcp.json`.)

- **Dry run by default.** Without `--apply` they print a plan and a before/after estimate and write nothing.
- **Scope.** With `--apply` they write only inside the `--root` you pass: `.mcp.json`, `CLAUDE.md`, `.claude/settings.json`, `.claude/rules/`, `.claude/agents/`, and the skill folders under `.claude/skills/`.
- **Backup.** Every file that is changed is first copied to `.tq-forge-backup/`, and the files the optimizer creates are listed in its `manifest.json`. `tq-forge restore` puts the originals back and deletes the created files, including any edits made to those created files afterwards.
- **Symlinks and encodings.** A file that is a symlink, sits under a symlinked folder, or is not valid UTF-8 is left unchanged and reported as a warning, so nothing is written outside `--root`.
- **Hostile `.mcp.json`.** A server whose name or keys contain characters other than letters, digits, `_`, `.` and `-` is not moved, so a crafted name cannot add fields such as `permissionMode` to a generated subagent.
- **No silent loss.** `--apply` stops without writing when the preview is missing any line or MCP server the project had before.
- **Secrets.** MCP server blocks are moved as written, including `${VAR}` references. The optimizer does not expand environment variables. Because the backup holds a copy of `.mcp.json`, add `.tq-forge-backup/` to `.gitignore` if that file contains literal credentials.
- **Deny rules.** `shield` adds `permissions.deny` entries for `.env` files and build output (`--strict` adds `node_modules` and lockfiles). It adds to the existing list and never removes an entry.

Review the plan before you run `--apply`.

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
