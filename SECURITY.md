# Security Policy

`tq-forge` is designed from the ground up for safe, transparent, and deterministic operation in developer environments.

## Architecture & Trust Model

- **Zero Outbound Telemetry**: tq-forge sends no analytics or telemetry. The scorers, generators, optimizer, `auto-improve`, the hooks and `postinstall` make no network call at all.
- **`learn` and `scout` fetch what you point them at**: GET requests to the URL you pass, or to YouTube, the GitHub API (through `gh api --method GET` when `gh` is installed), Reddit, Hacker News and DEV.to for a topic. Only `http` and `https` URLs are fetched, the request carries the topic and nothing about your machine, and `--offline` skips it. Fetched text is treated as data: lines matching prompt-injection or unsafe-shell patterns are removed, the skill body is a fixed template, and source text is fenced in `reference.md`. A pattern list cannot catch everything, so nothing is installed without `--apply`.
- **One other optional network call**: `tq-forge sync-models` makes a GET request to `https://api.anthropic.com/v1/models` (only when `ANTHROPIC_API_KEY` is set; the key is sent to Anthropic and nowhere else) or to `https://openrouter.ai/api/v1/models`. The request carries nothing about your project and redirects are not followed. `--offline` skips it. A model id reported only by OpenRouter is shown and not acted on unless you pass `--trust-source`.
- **Token-Free Scoring**: Artifact quality scoring and linting are performed entirely via local static analysis using Python standard library heuristics.
- **Execution Sandboxing**: Newly generated skills and subagents are scaffolded into an isolated sandbox (`$TQ_FORGE_HOME/sandbox/`) and never touch active configurations or production repositories until explicitly promoted.
- **Hook Policy Enforcement**: Scaffolding includes proactive guardrails for Claude Code lifecycle hooks:
  - `PreToolUse`: blocks dangerous root deletions (`rm -rf /`) and force git pushes (`git push --force`) with `exit 2`.
  - `PostToolUse`: validates file syntax on write before continuation.
  - `Stop`: prevents premature session termination if merge conflict markers or unfinished placeholders are detected.

## What the context optimizer writes

`tq-forge optimize`, `tq-forge auto-improve`, `tq-forge shield` and `tq-forge sync-models` rewrite existing project files. (`tq-forge scaffold` only adds files, except that `scaffold mcp --scope project` merges new servers into an existing `.mcp.json`.)

- **Dry run by default.** Without `--apply` they print a plan and a before/after estimate and write nothing.
- **Scope.** With `--apply` they write only inside the `--root` you pass: `.mcp.json`, `CLAUDE.md`, `.claude/settings.json`, `.claude/rules/`, `.claude/agents/`, and the skill folders under `.claude/skills/`.
- **Backup.** Every file that is changed is first copied to `.tq-forge-backup/`, and the files the optimizer creates are listed in its `manifest.json`. `tq-forge restore` puts the originals back and deletes the created files. A created file you edited since is kept and listed, because its SHA-256 no longer matches what was written; `--discard-edits` deletes it too. Paths are compared after `os.path.realpath`, so nothing outside `--root` is restored or deleted without `--outside`.
- **Symlinks and encodings.** A file that is a symlink, sits under a symlinked folder, or is not valid UTF-8 is left unchanged and reported as a warning, so by default nothing is written outside `--root`.
- **Opt-in writes through symlinks.** `--follow-symlinks` edits the file a skill symlink points at, which can be outside `--root`. That file is first copied to `.tq-forge-backup/symlink-targets/`, and `restore --outside` copies it back. Plain `restore` never writes or deletes outside `--root`, whatever the backup's `manifest.json` says, and never copies onto a symlink. Both `--apply` and `restore` stop when `.tq-forge-backup/` is, or contains, a symlink. `--dedupe-plugins` removes symlinks (never their targets) and records each one so `restore` recreates it. A dry run never touches a link or its target.
- **Plugin files.** Files under `.claude/plugins/` are read to find duplicate skills and are never written. No command enables, disables or deletes a plugin.
- **Mods.** `mods install --apply` writes `.claude/hooks/tq-forge/`, five skills, two subagents and hook entries in `.claude/settings.json`, with the same backup; existing hooks and settings are kept. The hooks make no network call, exit 0 on any error, and write only under `~/.claude/` (`tq-forge-savings.json`, `tq-forge-cache-clock.json`, `tq-forge-mods.json`, owner-only payload files in `tq-forge-payloads/` and `tq-forge-ccr/` that are deleted after a week) and `<project>/.claude/HANDOFF.md`. `--allow-autonomy` adds permission rules for `WebSearch`, `WebFetch`, `gh api` and the learn/scout commands; `gh api` can write with your GitHub token, so the flag is never implied.
- **Session logs.** `auto-improve` reads the transcripts under `<root>/.claude/projects/` and the root's own folder under `~/.claude/projects/` to count which skills were invoked. It keeps skill names and counts in memory for that run, writes none of it to disk, and sends nothing.
- **Background hook.** `templates/hooks/auto-improve-session.sh` runs `auto-improve --apply` unattended, with the same backup and a log at `$TQ_FORGE_HOME/auto-improve.log`. It is a template: it runs only if you register it in your own `settings.json`. `TQ_FORGE_AUTO_IMPROVE=0` turns it off.
- **postinstall.** Installing the package runs `bin/postinstall.js`, which reads `~/.claude` to print an estimate, writes nothing, and makes no network call. `npm install --ignore-scripts` or `TQ_FORGE_SKIP_POSTINSTALL=1` skips it.
- **Hostile `.mcp.json`.** A server whose name or keys contain characters other than letters, digits, `_`, `.` and `-` is not moved, so a crafted name cannot add fields such as `permissionMode` to a generated subagent.
- **No silent loss.** `--apply` stops without writing when the preview is missing any line or MCP server the project had before.
- **Secrets.** MCP server blocks are moved as written, including `${VAR}` references. The optimizer does not expand environment variables. Because the backup holds a copy of `.mcp.json`, add `.tq-forge-backup/` to `.gitignore` if that file contains literal credentials.
- **Deny rules.** `shield` adds `permissions.deny` entries for build output (`--deny-env` adds `.env` files, `--strict` adds `node_modules` and lockfiles). It adds to the existing list and never removes an entry.
- **Model and effort.** `shield` sets `effortLevel`, `modelSettings` and `CLAUDE_CODE_SUBAGENT_MODEL`, which changes how every session and subagent runs. `--effort keep` and `--subagent-model keep` leave them alone.

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
- Report it through GitHub Private Vulnerability Reporting:
  **https://github.com/tanishq286/tq-forge/security/advisories/new**

Please include:
1. Description of the vulnerability and attack vector.
2. Steps to reproduce or proof-of-concept configuration.
3. Impact assessment and potential mitigations.

You will receive an initial response within 48 hours and regular updates until resolution.
