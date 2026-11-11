# Changelog

All notable changes to `tq-forge` are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — 2026-11-11

Major release introducing the context optimizer, auto-improve, model sync, Claude Fable 5.2 orchestrators, lifecycle hooks, MCP scaffolding, isolated subagents, and an automated benchmark test suite.

### Added
- **Auto-improve** (`tq-forge auto-improve [--root <dir>] [--apply]`, `scripts/lib/auto_improve.py`): runs every `optimize` step, then uses Claude Code's session logs (`scripts/lib/telemetry.py`, skill names only, read locally) and the 0–100 rubric.
  - A `CLAUDE.md` over 300 tokens keeps its rule sections; every other section moves word for word into an on-demand skill (`reference.md` plus a 140-character trigger).
  - Rule files over 150 tokens with no `paths:` get source-file globs (`--keep-rules` to skip).
  - Skill descriptions are cut to 140 characters; a skill still over 150 tokens a turn that was never invoked is listed by name only through `skillOverrides`.
  - Skills and subagents under 85 get mechanical fixes only (`paths:` when the description names file types, outdated `model:` ids, a missing `effort`). `--extract-scripts` is opt-in. Missing sections are reported, not invented.
  - `templates/hooks/auto-improve-session.sh`: a `SessionStart` / `Stop` hook that measures at most once a day and starts a background pass over 4,000 tokens or after a model sync. Silent, non-blocking, always exits 0, never installed for you.
  - Read-only `postinstall` (`bin/postinstall.js`) that prints the current `~/.claude` estimate and the one-line command. Skipped in CI or with `TQ_FORGE_SKIP_POSTINSTALL=1`.
- **Model sync** (`tq-forge sync-models [--apply]`, `scripts/lib/model_sync.py`, `config/models.json`): a registry of Claude model generations (`claude-fable-5-2`, `claude-mythos-5-2`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`) with role, effort, prices, prompting rules and the recommended lead + subagent pair.
  - Reads live ids from Anthropic's `/v1/models` (with `ANTHROPIC_API_KEY`) or OpenRouter's public list, with an offline fallback; recognises future `claude-{fable,mythos,opus,sonnet,haiku}-*` releases by pattern.
  - On a newer model: updates the registry and rewrites pinned ids in `.claude/agents/**/*.md`, `.claude/settings.json` (`model`, `env.CLAUDE_CODE_SUBAGENT_MODEL`, `modelSettings`) and the templates. Prices that the source does not report are marked `inherited_from`.
  - The model-compat lint is now keyed by family, so a newly added model is linted immediately.
  - `.github/workflows/model-sync.yml` (weekly + `workflow_dispatch`) runs the sync and `npm test` and opens a pull request when something changed.
- **Optimizer reach** (`scripts/lib/optimize.py`, `scripts/lib/context_cost.py`, `scripts/lib/linkdedupe.py`):
  - `--follow-symlinks` compacts skills behind symlinks and in `.agents/skills/`, backing the real file up under `.tq-forge-backup/symlink-targets/`.
  - `--dedupe-plugins` unlinks a symlinked skill that an enabled plugin also loads; `restore` recreates the link.
  - `--compact-plugins`, `measure --plugins` and `--listing-budget` scan `.claude/plugins/`, measure plugin skill listings and compact them with a backup.
  - `skillOverrides` is written for personal skills only: Claude Code does not apply it to plugin skills.
  - Subagents in nested `.claude/agents/` folders are now counted, as Claude Code loads them.
- **Real-world benchmark**: on the maintainer's `~` the estimate went from 13,075 to 1,910 tokens (−85.4%; 11,233 → 1,910 without the MCP server). With 412 plugin skills counted under a 40,000-character listing budget it is 19,829 → 11,228 (−43.4%). See the README for how to read those numbers.

### Changed
- `shield` writes a one-line, 33-token hygiene note into `CLAUDE.md` instead of a 320-token rule file, no longer denies `.env` reads unless `--deny-env` is passed, and now sets `effortLevel: medium` (plus `modelSettings`) and `CLAUDE_CODE_SUBAGENT_MODEL` by default (`--effort keep` / `--subagent-model keep` to opt out; an existing subagent model is kept).
- A "Use when" trigger that is too long for the description limit is cut instead of dropped.
- `restore` removes the folders an apply created, not only the files, and touches files outside `--root` only with `--outside`. Backup and restore now live in `scripts/lib/backup.py`.
- CI runs ShellCheck on `templates/hooks/*.sh` as well as `scripts/*.sh`.
- `SECURITY.md` points to GitHub Private Vulnerability Reporting only.

### Also added in 1.1.0
- **Context optimizer** (`tq-forge measure | optimize | optimize-mcp | optimize-skills | shield | restore`, backed by `scripts/optimize.sh` and `scripts/lib/optimize.py`):
  - Moves each server in `.mcp.json` into a `.claude/agents/mcp-<name>.md` Haiku worker with inline `mcpServers:`.
  - Cuts skill descriptions to 160 characters (keeping the "Use when" sentence when it fits, and moving the full text into the body) and moves reference sections of long skills into `reference.md`.
  - Moves `CLAUDE.md` sections that name existing paths into `.claude/rules/<topic>.md` with `paths:` frontmatter.
  - `shield` adds `claudeMdExcludes` and `permissions.deny` entries, the `context-soaker` and `test-soaker` subagents, and a context-hygiene note.
  - Dry run by default; `--apply` backs up every changed file to `.tq-forge-backup/` and `restore` undoes it.
  - Leaves symlinked (unless `--follow-symlinks`) or non-UTF-8 files unchanged, keeps servers with unsafe or colliding names in `.mcp.json`, and refuses `--apply` when the preview is missing a line or server.
  - `scripts/lib/context_cost.py` estimates always-loaded context as characters ÷ 4. On the synthetic bloated fixture in `tests/test_optimize.py` the estimate drops from 7,337 to 470 tokens (−93.6%); on the lean control project nothing changes. These are fixture results, not a promise for every project.
- **CLI subcommands** `scaffold`, `score`, and `validate` in `bin/cli.js`, passing arguments to the bundled scripts as an argument array (no shell string).
- **Test suite** `tests/test_optimize.py` (62 tests on the optimizer, auto-improve and model sync), run by `npm test` after `scripts/test-runner.py` (264 assertions).
- **Hardened workflows**: every GitHub Action pinned to a commit SHA, `contents: read` permissions on CI, and shellcheck run from the runner image instead of an unpinned third-party action.
- **Claude Fable 5.2 Architecture & Persistence**:
  - Support for `claude-fable-5-2` as the default orchestrator and strategic advisor model profile with `effort: high`.
  - Dedicated subagent templates: `fable-5-2-orchestrator` (delegation, planning, and self-review) and `fable-5-2-advisor` (defensive foresight, trade-off analysis, second opinion).
  - Model-profile prompt snippets including `# Finishing work` persistence blocks, `# Progress updates`, and `# Communicating clearly`.
  - Model registry (`templates/models.json`) and token-free static model-compatibility linter (`scripts/lib/model_lint.py`).
- **Claude Code Lifecycle Hooks**:
  - Scaffolder for `.claude/hooks/` and `.claude/settings.json` (`scaffold.sh hooks --events PreToolUse,PostToolUse,SessionStart,Stop`).
  - Standardized JSON stdin validation and exit-code policy enforcement:
    - `exit 0`: allow action or pass session state into context.
    - `exit 2`: block tool execution or prevent premature stop with stderr reason displayed to the model.
  - Built-in safety handlers: destructive command blocking (`rm -rf /`, `git push --force`), file syntax check on write (`json`, `sh`, `py`, `js`), repository context injection on session start, and loop-safe stop prevention for unmerged conflicts and unfilled placeholders.
- **MCP Server Scaffolding**:
  - Scaffolding of project-scoped MCP configs in `.mcp.json` (`scaffold.sh mcp --scope project`) supporting `http` and `stdio` transports, `${VAR}` token expansion, and sanitized secret handling.
  - Subagent-scoped isolated MCP agents (`scaffold.sh mcp --scope subagent`) embedding `mcpServers:` directly in `.claude/agents/<name>.md`.
- **Isolated Subagent Scaffolding**:
  - First-class support for isolated worktree agents (`scaffold.sh agent --isolated` or `--isolation worktree`).
  - Scaffolding options for `permissionMode` (`plan`, `acceptEdits`), `memory: project`, and `tools`/`allowed-tools`.
  - Production templates: `code-reviewer` (`isolation: worktree`, `permissionMode: plan`), `security-auditor` (`isolation: worktree`, `permissionMode: plan`), and `test-runner` (`isolation: worktree`, `permissionMode: acceptEdits`).
- **Automated Test Suite & Quantitative Scorer Benchmarks**:
  - Added comprehensive test suite (`scripts/test-runner.py`) wired into `npm test` and `.github/workflows/ci.yml`.
  - Validates skill and subagent frontmatter: `name`, `description` <= 1536 characters, `allowed-tools`, `paths`, and schema constraints.
  - Evaluates deterministic 0–100 quality scores across all bundled skills and templates.
  - End-to-end integration tests verifying dynamic scaffolding and real exit code execution for all lifecycle hooks.
- **Security & Community Standards**:
  - Added OpenSSF Scorecard supply-chain security workflow (`.github/workflows/scorecard.yml`).
  - Re-enabled and modernized `.github/workflows/launch-digest.yml` with weekly scheduling and manual dispatch.
  - Verified standard OSI-approved MIT License (Copyright (c) 2026 Tanishq Agarwal).

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
- **Auto-publish workflow** (`.github/workflows/publish.yml`) and npm installer CLI (`bin/cli.js`).
- **Deferred-work queue** + manual `halt.flag` pause/resume.
- CI that shellchecks scripts and asserts every bundled skill scores >=7 and passes dry-test.

### Configuration
- `TQ_FORGE_HOME` (default `~/.tq-forge`) — state home.
- `CLAUDE_SKILLS_DIR` (default `~/.claude/skills`) — promote target.

[1.1.0]: https://github.com/tanishq286/tq-forge/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/tanishq286/tq-forge/releases/tag/v1.0.0
