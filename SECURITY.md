# Security

tq-forge is designed to be safe to install and read end to end. This document
states exactly what it does and does not do, so you can verify before you trust.

## What it does

- **Generates files** in a sandbox (`~/.tq-forge/sandbox/`) and, on explicit
  promote, copies them into your Claude Code skills dir (`~/.claude/skills/`).
- **Reads** your installed skills' frontmatter (for the gap scan) and its own
  state files under `~/.tq-forge/`.
- **Runs** small `bash` + `python3` (standard library) scripts to score and
  validate artifacts.

## What it does NOT do

- ❌ **No network calls.** The installer and all runtime scripts are local. The
  scorer (`quality-score.sh`), validator (`dry-test.sh`), and the npm CLI make
  zero outbound requests. (`npx` itself downloads the package from npm — that's
  the npm client, not our code.)
- ❌ **No telemetry.** Nothing is collected, logged remotely, or phoned home.
- ❌ **No LLM/API calls in the tooling.** Scoring is static and deterministic.
- ❌ **No `bypass-permissions` requirement.** The skills use ordinary Bash/Read/
  Write tools you already grant Claude Code.
- ❌ **No modification of shared system files.** Everything stays under your home
  directory (`~/.tq-forge/` and `~/.claude/skills/`).

## Scope of writes

| Path | Written by | When |
|---|---|---|
| `~/.tq-forge/**` | scripts + CLI | install, forge, score |
| `~/.claude/skills/<slug>/` | `/tq-forge-promote`, `npx tq-forge install` | explicit promote/install |

`/tq-forge-promote` refuses to overwrite a skill slug that already exists, and
keeps the sandbox copy as a rollback (it copies, never moves).

## Auditing it yourself

Everything is plain text. To review before installing:

```bash
git clone https://github.com/tanishq286/tq-forge
cd tq-forge
less scripts/*.sh        # the only executable logic
less bin/cli.js          # the installer (pure Node stdlib)
```

The scripts are kept shellcheck-clean (enforced in CI) and dependency-free.

## Reporting a vulnerability

If you find a security issue, please **do not open a public issue**. Instead,
use GitHub's private vulnerability reporting:

**https://github.com/tanishq286/tq-forge/security/advisories/new**

You'll get an acknowledgement and a fix timeline. Thank you for disclosing
responsibly.

## Supported versions

The latest released version on the `main` branch / npm `latest` tag is supported.
