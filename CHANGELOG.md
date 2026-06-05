# Changelog

All notable changes to tq-forge are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- **npm installer** — `npx tq-forge install` copies the skills into
  `~/.claude/skills/` and support scripts into `~/.tq-forge/install/`, seeds the
  state home, and checks dependencies. Also `uninstall` and `doctor` subcommands.
- Skills are now **dual-mode**: they resolve their scripts from
  `$CLAUDE_PLUGIN_ROOT` when loaded as a Claude Code plugin, or from
  `~/.tq-forge/install` when installed via npm — same SKILL.md either way.
- CI now syntax-checks the CLI, runs `npm pack`, and smoke-tests an isolated
  install.

## [1.0.0] — 2026-06-04

First public release.

### Added
- **13 slash-command skills**: `tq-forge`, `tq-forge-skill`, `tq-forge-agent`,
  `tq-forge-promote`, `tq-forge-improve`, `tq-forge-improve-all`,
  `tq-forge-test`, `tq-forge-list`, `tq-forge-agents`, `tq-forge-status`,
  `tq-forge-scan`, `tq-forge-queue`, `tq-forge-resume`.
- **Token-free quality scorer** (`scripts/quality-score.sh`) — static Python
  stdlib, no LLM calls. Scores skills on 4 dimensions, agents on 6.
- **Structural dry-test** (`scripts/dry-test.sh`) — frontmatter, file presence,
  valid `tools.json`, word-count bounds.
- **Sandbox → promote workflow**: nothing reaches your live skills dir until
  `/tq-forge-promote` re-scores and passes it (>=7/10).
- **8 agent archetypes**: researcher, coder, business-analyst, ops-manager,
  scraper, reviewer, sales-agent, custom — each with a rigid output format and a
  `{{CONTEXT}}` slot for your domain.
- **Deferred-work queue** + manual `halt.flag` pause/resume.
- CI that shellchecks the scripts and asserts every bundled skill scores >=7 and
  passes dry-test.

### Configuration
- `TQ_FORGE_HOME` (default `~/.tq-forge`) — state home.
- `CLAUDE_SKILLS_DIR` (default `~/.claude/skills`) — promote target.

[1.0.0]: https://github.com/tanishq286/tq-forge/releases/tag/v1.0.0
