# Changelog

All notable changes to `tq-forge` are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.1] — 2026-11-14

Two fixes for skills that set an output language, from community feedback on the Dev.to launch. Thanks to laogedev2 and Halfcycle.

### Added
- **Lint rule M013** `output-language-not-in-description` (−5): a skill body that tells Claude to answer in a language (`respond in Chinese`, `output in Japanese`, `write in Spanish`, `translate into Hindi`, `output language: French`, `must be in German`) while the frontmatter `description` never names it. Claude routes a skill on `name` and `description` alone, so the constraint can be missed. English is the default and is never reported; negated mentions, input languages (`documents written in Japanese`) and sample prompts inside code fences are ignored. It checks skills and applies to every target model. A native spelling in the description (`日本語`, `中文`) counts.

### Changed
- **`/savings` keeps output languages through description compaction.** When a description has to be cut, any language it names that the cut would drop comes back as a closing `Languages: ...` clause, and the rest is shortened to make room. The `Use when` sentence is still reserved first, so its leading verbs and nouns survive, and the full original description stays in `## Full description`.
- **`/savings` never moves an output-language rule out of the file Claude reads it from.** A skill section that sets the language stays in `SKILL.md` instead of going to `reference.md`; a `CLAUDE.md` section that sets it stays in `CLAUDE.md` instead of becoming a path-scoped rule; a paragraph that sets it is not offloaded as prose.
- `/savings` warns, with the skill name and the rule id, when a skill body sets a language that its description does not name.

### Tests
- 18 M013 cases in the scorer assertions and the unit tests, a check that the 18 bundled skills trigger no M013, and a retention suite for descriptions, skill sections, `CLAUDE.md` rules and prose offload. The lossless benchmark is unchanged at 7337 → 3121 estimated tokens (−57.5%).

## [1.3.0] — 2026-11-13

Model compatibility for the Claude 5.2 / 5.5 lineup: a fuller registry, a stricter lint, and a generated cross-model matrix.

### Added
- **Registry schema 2** (`config/models.json`). Each model (`claude-fable-5-2`, `claude-mythos-5-2`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`) now carries:
  - `capabilities`: context window, output cap, thinking mode, sampling policy, forced `tool_choice`, prefill, refusal categories.
  - `effort_guide`: the API default, the `routine`, `agentic` and `hardest` levels, and the levels at which the model stops a long task early. Fable 5.2 is `medium` / `high` / `xhigh`.
  - `deprecations`: 13 rules for retired and deprecated ids. An older version that is not listed counts as `superseded`.
- **Lint rule M011** `missing-completion-instructions`: a long-horizon subagent with no `# Finishing work` block at an effort level where the model stops early (Fable at `low` or `medium`; Sonnet and Haiku at `low`). −6.
- **Lint rule M012** `stale-model-id`: a retired (−10), deprecated (−6) or superseded (−3) Claude model id, in frontmatter or body.
- **`tq-forge compat [--write|--check|--json]`** (`scripts/lib/compat_matrix.py`) scores every bundled skill and subagent template under each model's rules and writes [`docs/MODEL_COMPATIBILITY.md`](docs/MODEL_COMPATIBILITY.md): score per model, dry-test, minimum model tier, starting effort, pass or fail. 27 of 27 pass.
- 59 lint fixture cases (`scripts/lib/lint_cases.py`) and `tests/test_model_compat.py`. `npm test` now runs 971 scorer assertions (was 320) and 200 unit tests (was 165).

### Changed
- **A stale pinned id no longer switches the model rules off.** A file with `model: claude-sonnet-4-6` is linted against the current Sonnet and gets M012. Before, it got no model rules and scored as clean.
- **M001** also catches `budgetTokens` and `thinking_budget`; its fix names adaptive thinking and `output_config.effort`.
- **M004** also catches reasoning headers ("begin every response with a Reasoning section"), scratchpad blocks and "print the raw chain-of-thought". Its message names the `reasoning_extraction` refusal.
- **M008** also catches `topP`, and no longer flags the two default values Sonnet 5.5 and Haiku 5.5 accept (`temperature: 1`, `top_p: 0.99`).
- **Completion instructions in every subagent template.** `code-reviewer`, `security-auditor`, `test-runner`, `omni-scout`, `input-reader` and both MCP worker templates gain a `# Finishing work` block. `scaffold agent` adds the `keep-working` block when the chosen model and effort need one.
- **`sync-models`** moves an id the registry lists as retired by name (`claude-2.1`) to its replacement, and carries capabilities and the effort guide over to a new model. `claude-mythos-preview` is reported, not rewritten.
- The weekly model-sync workflow regenerates the matrix; CI runs `compat --check`.
- README: the hand-written scorecard (13 skills, outdated scores) is replaced by a link to the generated matrix.

### Fixed
- **The weekly model sync could not open its pull request after a real release.** Nine tests named today's model ids, so the job's own `npm test` failed once the registry changed. They are now relative to the registry; a simulated release of three models passes both suites.
- `optimize` wrote MCP workers with a hardcoded `claude-haiku-5-5`, so after a sync the next `auto-improve` pass rewrote them. It now uses the registry's worker model.
- A registry synced by an older tq-forge (schema 1) in `~/.tq-forge/` no longer shadows the bundled schema 2 registry.

### Notes
- The matrix and the lint are static: no model is called. The minimum tier is an estimate from the tools a file uses and the length of its procedure.
- `/tq-forge-agent` now shows `--model fable` (an alias) in its example, so the skill does not go stale on the next release.

## [1.2.1] — 2026-11-13

The input-router shows large output in a short form you can undo.

### Added
- **Reversible short forms in `input-router`** (`scripts/lib/ccr_engine.py`). MCP output that is still over the threshold after cleaning is stored whole under a 12-character CCR id and shown short: JSON as a schema, its first 15 rows and a row count; a log without colour codes, blank lines or repeated lines. A Read of a source file over 12,000 tokens is still routed, and the note now carries an outline of the file's definitions with their line numbers. Text that is neither JSON nor a log, and JSON that stays large, is parked behind a preview as before. `"ccr": false` under `input-router` in `~/.claude/tq-forge-mods.json` turns it off.
- **`tq-forge retrieve <ccr_id> [--lines A:B] [--search KW]`** prints the full text behind a CCR id, a line range of it, or the lines containing a keyword. An id must match `^[a-f0-9]{12}$`; anything else exits 2 before a path is built. An unknown id exits 1.

### Changed
- `mods install` copies `ccr_engine.py` next to `mods.py` in `.claude/hooks/tq-forge/`. Without it the router parks and previews, so an older install keeps working. The installed copy's `[CCR-ID: ...]` line names the command that works on that machine (`node <path>/bin/cli.js retrieve` for a checkout or a global install, `npx tq-forge retrieve` otherwise), the same way the bundled skills do.

### Notes
- The CCR store is `~/.claude/tq-forge-ccr/`: owner-only files, deleted after a week, never sent anywhere.

## [1.2.0] — 2026-11-12

Lossless by default, eight signal-driven mods, and `learn` / `scout`.

### Changed
- **`optimize` and `auto-improve` no longer trade capability for context unless asked.**
  - MCP servers stay in `.mcp.json`. The MCP step removes per-server `"alwaysLoad": true` and sets `ENABLE_TOOL_SEARCH=true` in `settings.json` `env` (an existing value is left alone), so tool schemas are deferred and every tool stays callable from the main thread and from subagents. Moving servers into worker subagents is now `--isolate-mcp`.
  - Skill descriptions of 350 characters or fewer are never cut (`--description-limit 160` is the old behaviour). Reference sections move to `reference.md` for skill bodies over 120 lines.
  - Files under `.claude/plugins/` are never written. `--compact-plugins` is removed.
  - New `prose` step (`scripts/lib/offload.py`): a `CLAUDE.md` over 80 lines keeps its rules, tables, short lists, short commands and tool-naming trigger paragraphs; only prose and long examples move to an on-demand skill, and each section that loses anything is copied there whole. `auto-improve --aggressive` keeps the 1.1.0 behaviour.
- **`shield` changes neither effort, nor the subagent model, nor permissions.** `effortLevel: medium` and `CLAUDE_CODE_SUBAGENT_MODEL` are no longer set (`--effort` and `--subagent-model` are opt-in), and build folders (`dist/`, `build/`, `.next/`, `coverage/`) are no longer in `permissions.deny`; they stay in `claudeMdExcludes`.
- **Scorer rubric recalibrated** (`scripts/lib/score.py`): each dimension accepts the headings real skills use (Workflow, Red flags, Checklist, numbered or `Step N` headings, worked examples) and credits a trigger written in the description, so a clear, concise skill reaches 85 without a Tags section or a duplicated "When to use".
- Settings and `.mcp.json` are written with non-ASCII text intact instead of `\u` escapes.

### Added
- **Mods** (`tq-forge mods install|status|toggle|savings`, `scripts/lib/mods.py`, `config/mods.json`): hook handlers that decide from what is happening instead of a static global setting. `mods install` is a dry run unless `--apply`, keeps existing hooks and settings, and is undone by `restore`.
  - `input-router`: a data file over 2,000 tokens (source over 12,000) is handed to the `input-reader` subagent or read in ranges; MCP output is cleaned of empty fields, base64 and avatar URLs, and what is still over the threshold is saved to a file and replaced by a preview. Reads inside a subagent are never routed.
  - `effort-optimizer`: classifies each prompt and recommends `/effort low|medium|high|xhigh` when the current effort does not fit. A hook cannot change effort, so it recommends; it never suggests `max`.
  - `subagent-model-selector`: easy jobs go to `haiku`, normal to `sonnet`, complex stay on the session model. An explicit model, a plugin agent, a pinned agent definition and the built-in agents are left alone.
  - `cache-clock`: records each reply; the status line and `tq-forge keep-warm [--ttl 55m|4m] [--wait]` show when the prompt cache goes cold (60 minutes on a subscription, 5 with an API key). `--chain-statusline` appends it to a status line you already have.
  - `handoff`: past 250,000 tokens it writes a `HANDOFF.md` skeleton from the transcript (requests, files read and changed, skills, URLs) and points to `/handoff`.
  - `efficient-browser-use`: halves screenshot dimensions (Pillow when present, a stdlib PNG path otherwise).
  - Skills `/savings`, `/switchboard`, `/handoff`, `/keep-warm`; savings are logged to `~/.claude/tq-forge-savings.json`.
- **`tq-forge learn <url-or-query>` and `tq-forge scout <topic> [--sources youtube,github,social,web]`** (`scripts/lib/intel_scout.py`, `scripts/lib/self_evolve.py`, `omni-scout` agent, `/tq-forge-learn`): collects a video's captions and chapters, a repository's Claude setup, Reddit / Hacker News / DEV.to posts or one page; removes lines that look like prompt injection or unsafe shell; writes a skill whose body is a fixed template and whose source text sits fenced in `reference.md`. Sandbox only unless `--apply`, and then only when it scores 85 or more with at least three concrete steps. `mods install --allow-autonomy` pre-approves the learn/scout commands, `WebSearch`, `WebFetch` and `gh api`; it is never added without the flag.

### Fixed
- **`restore` no longer deletes a file an apply created if you edited it since.** The manifest records a SHA-256 of what was written; a changed file is kept and listed (`--discard-edits` deletes it).
- **`restore` compares real paths** (`os.path.realpath`), so a path that only looks like it is inside `--root` is never written or deleted.
- `CODE_OF_CONDUCT.md` points to GitHub Private Vulnerability Reporting instead of a personal email address.

### Notes
- On the maintainer's `~` the lossless pass with `--dedupe-plugins` measures 45,524 → 42,710 estimated tokens with plugin skills counted (11,951 → 9,137 without). The 1.1.0 figure of −85% came from isolating the MCP server and scoping rules, which is what `--isolate-mcp` and `--aggressive` still do.
- Token and dollar figures in `/savings` are estimates: characters ÷ 4, pixels ÷ 750, list prices.

## [1.1.0] — 2026-11-11

Major release introducing the context optimizer, auto-improve, model sync, Claude Fable 5.2 orchestrators, lifecycle hooks, MCP scaffolding, isolated subagents, and an automated benchmark test suite.

### Added
- **Auto-improve** (`tq-forge auto-improve [--root <dir>] [--apply]`, `scripts/lib/auto_improve.py`): runs every `optimize` step, then uses Claude Code's session logs (`scripts/lib/telemetry.py`, skill names only, read locally) and the 0–100 rubric.
  - A `CLAUDE.md` over 300 tokens keeps its rule sections; every other section moves word for word into an on-demand skill (`reference.md` plus a 140-character trigger).
  - With `--scope-rules`, rule files over 150 tokens with no `paths:` get any-file globs, so they load on the first file touched. Opt-in; without it they are reported.
  - Skill descriptions are cut to 140 characters; a skill still over 150 tokens a turn that was never invoked is listed by name only through `skillOverrides`. Usage-based steps are skipped when no session log is found, and an existing override is never replaced.
  - Skills and subagents under 85 get mechanical fixes only (outdated `model:` ids, a missing `effort`). `--add-paths` and `--extract-scripts` are opt-in. Missing sections are reported, not invented.
  - `templates/hooks/auto-improve-session.sh`: a `SessionStart` / `Stop` hook that measures at most once a day and starts a background pass over 4,000 tokens or after a model sync. Silent, non-blocking, always exits 0, never installed for you.
  - Read-only `postinstall` (`bin/postinstall.js`) that prints the current `~/.claude` estimate and the one-line command. Skipped in CI or with `TQ_FORGE_SKIP_POSTINSTALL=1`.
- **Model sync** (`tq-forge sync-models [--apply]`, `scripts/lib/model_sync.py`, `config/models.json`): a registry of Claude model generations (`claude-fable-5-2`, `claude-mythos-5-2`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`) with role, effort, prices, prompting rules and the recommended lead + subagent pair.
  - Reads live ids from Anthropic's `/v1/models` (with `ANTHROPIC_API_KEY`) or OpenRouter's public list, with an offline fallback; recognises future `claude-{fable,mythos,opus,sonnet,haiku}-*` releases by pattern. Only Anthropic's list is acted on unless `--trust-source` is passed; implausible version jumps are ignored; redirects are not followed, so the API key cannot be forwarded to another host.
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
- `restore` removes the folders an apply created, not only the files, and touches files outside `--root` only with `--outside`. Neither apply nor restore works through a symlink in the backup folder, restore never copies onto a symlink, and the backup manifest is written before the first change so a failed apply can still be restored. Backup and restore now live in `scripts/lib/backup.py`.
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
- **Test suite** `tests/test_optimize.py` (76 tests on the optimizer, auto-improve and model sync), run by `npm test` after `scripts/test-runner.py` (264 assertions).
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
