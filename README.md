<div align="center">

# 🔨 tq-forge

**An autonomous skill + agent factory for [Claude Code](https://claude.com/claude-code).**

Forge production-grade slash-command skills and autonomous subagents from a one-line intent —
scored deterministically, sandboxed safely, and promoted into production without leaving your terminal.

[![npm](https://img.shields.io/npm/v/tq-forge?color=cb3837&logo=npm)](https://www.npmjs.com/package/tq-forge)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/tanishq286/tq-forge/actions/workflows/ci.yml/badge.svg)](https://github.com/tanishq286/tq-forge/actions/workflows/ci.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/tanishq286/tq-forge/badge)](https://scorecard.dev/viewer/?site=github.com/tanishq286/tq-forge)
[![Claude Fable 5.2 Ready](https://img.shields.io/badge/Claude%20Fable%205.2-Ready-8A2BE2.svg)](https://claude.com/claude-code)
[![Context optimizer](https://img.shields.io/badge/context%20optimizer-%E2%89%A540%25%20on%20benchmark%20fixture-brightgreen.svg)](#context-optimizer)

<br/>

<img src="assets/demo.gif" alt="tq-forge demo: the deterministic scorer passing a 9.0 and a 7.8, then blocking a 3.2 at the promote gate" width="760"/>

</div>

---

## Overview

Claude Code enables developers to define reusable **skills** (`.claude/skills/<name>/SKILL.md`) and specialized **subagents** (`.claude/agents/<name>.md`). However, creating them manually involves fragile YAML frontmatter, strict token constraints, subtle permission modes, and zero static quality feedback.

**`tq-forge` is an autonomous maintainer factory and static quality engine.** From a single English intent, it determines the right abstraction, generates fully conformant artifacts into a sandbox, validates them with a **token-free deterministic quality scorer (0–100)**, and ensures nothing reaches production until it meets rigorous thresholds.

```console
$ npx tq-forge scaffold agent --template security-auditor --out .
wrote .claude/agents/security-auditor.md
next: quality-score.sh .claude/agents/security-auditor.md

$ npx tq-forge score .claude/agents/security-auditor.md
🟢 subagent security-auditor.md: 90/100 (9.0/10, excellent)
   clarity             9  █████████░
   actionability       9  █████████░
   completeness        9  █████████░
   specificity         9  █████████░
   consistency         9  █████████░
```

The same engine also shrinks what Claude Code loads on every turn. See [Context optimizer](#context-optimizer).

---

## Architecture: How `tq-forge` Works

```
                ┌────────────────────────────────────────┐
                │          One-Line Natural Intent       │
                └───────────────────┬────────────────────┘
                                    │
                       Classification & Scaffolding
                                    │
          ┌─────────────────────────┴─────────────────────────┐
          ▼                                                   ▼
┌──────────────────────┐                           ┌──────────────────────┐
│  Procedural Skills   │                           │ Autonomous Subagents │
│ (.claude/skills/)    │                           │ (.claude/agents/)    │
│ • YAML Frontmatter   │                           │ • Claude Fable 5.2   │
│ • desc <= 1536 chars │                           │ • effort: high       │
│ • allowed-tools      │                           │ • # Finishing work   │
│ • 4 Core Sections    │                           │ • isolation:worktree │
└──────────┬───────────┘                           └──────────┬───────────┘
           │                                                  │
           └────────────────────────┬─────────────────────────┘
                                    ▼
                ┌────────────────────────────────────────┐
                │       Deterministic Quality Scorer     │
                │        (Token-free static analysis)    │
                │     Scores 0–100 across 5 dimensions   │
                └───────────────────┬────────────────────┘
                                    ▼
                          Is Score >= 70/100?
                         /                  \
                     [No]                    [Yes]
                      ▼                        ▼
           ┌──────────────────────┐  ┌──────────────────────┐
           │ Staged in Sandbox    │  │ /tq-forge-promote    │
           │ /tq-forge-improve    │  │ Deployed Live to     │
           │ (targeted rewrite)   │  │ .claude/ directory   │
           └──────────────────────┘  └──────────────────────┘
```

### 1. Claude Fable 5.2 Orchestrators & Advisors
- **`claude-fable-5-2` Orchestrator**: High-effort (`effort: high`) orchestrator for multi-stage reasoning, parallel subagent delegation, and autonomous verification loops.
- **`claude-fable-5-2` Strategic Advisor**: Operates in read-only plan mode to perform architectural tradeoff analysis, dependency migration reviews, and failure-mode checks before risky operations.
- **`# Finishing work` Persistence**: Integrated prompt persistence blocks preventing premature agent halt on transient errors or recoverable tool failures.

### 2. Isolated Subagents
- Supports `isolation: worktree` so subagents operate inside temporary, pristine git worktrees without polluting the main working tree.
- Configurable `permissionMode` (`plan`, `acceptEdits`), `tools`, and `memory: project` for notes that persist across sessions. (Subagent files use `tools`; `allowed-tools` is the skill field, and `validate` warns when it appears in a subagent.)
- A worktree starts from the repository's default branch, so uncommitted changes are not visible in it. Give the subagent a commit or branch to work on, or set `worktree.baseRef` to `head`.

### 3. Lifecycle Hooks Generation (`.claude/hooks/`)
- Deterministic hooks for `PreToolUse`, `PostToolUse`, `SessionStart`, and `Stop`.
- Strict exit code semantics:
  - **`exit 0`**: continue.
  - **`exit 2`**: what it does depends on the event, as Claude Code defines it:

    | Event | Exit 2 blocks? | Who sees stderr |
    | :--- | :---: | :--- |
    | `PreToolUse` | Yes, the tool call | Claude |
    | `PostToolUse` | No, the tool already ran | Claude |
    | `Stop` | Yes, Claude keeps working | Claude |
    | `SessionStart` | No | Only you |
- Guardrails:
  - Blocks dangerous shell operations (`rm -rf /`, `git push --force`).
  - Automatically syntax-checks changed files (`.json`, `.sh`, `.py`, `.js`) on edit or write.
  - Injects repository status on session startup.
  - Enforces loop-safe stop prevention when merge conflicts or unfilled placeholders remain.

### 4. MCP Server Scaffolding (`.mcp.json`)
- **Project-scoped MCP servers**: In `.mcp.json` with `http` or `stdio` transports, argument passing, and clean `${VAR}` environment variable expansion.
- **Subagent-scoped MCP servers**: Isolates heavy toolkits (e.g. SQLite, GitHub, Kubernetes) into dedicated subagents so tool definitions do not consume the main conversation context.

---

## Context optimizer

Claude Code loads some text into the main conversation before your first prompt and resends it every turn: `CLAUDE.md`, rules without a `paths:` scope, every skill's description, every subagent's description, and each MCP server's tool names and instructions. `tq-forge optimize` moves that text to places that load on demand. It deletes nothing.

| Step | What it changes | When the moved text loads afterwards |
| :--- | :--- | :--- |
| `optimize-mcp` | Each server in `.mcp.json` moves into `.claude/agents/mcp-<name>.md` (inline `mcpServers:`, `claude-haiku-5-5`) | When Claude delegates to that worker |
| `optimize-skills` | Descriptions over 160 characters are cut to whole sentences, keeping the "Use when" sentence when it fits in 160 characters (a single longer sentence is cut with "…"); the full text moves into the skill body. Reference sections of skills over 150 lines move to `reference.md` | When the skill is invoked |
| `optimize-skills` | `CLAUDE.md` sections (in files over 80 lines) that name paths existing in the repo move to `.claude/rules/<topic>.md` with `paths:` | When Claude reads a matching file |
| `shield` | Sets `effortLevel: medium` (also per model in `modelSettings`), `CLAUDE_CODE_SUBAGENT_MODEL` to the registry's worker model, `claudeMdExcludes`, and `permissions.deny` for build output. Adds two "soaker" subagents that return summaries of 15 lines or fewer and a one-line (33-token) hygiene note in `CLAUDE.md`. `.env` files stay readable unless you pass `--deny-env` | — |

```bash
npx tq-forge measure                  # estimate the always-loaded context
npx tq-forge optimize                 # dry run: plan and before/after estimate
npx tq-forge optimize --apply         # write; originals go to .tq-forge-backup/
npx tq-forge shield --apply           # --effort keep / --subagent-model keep leave those settings alone
npx tq-forge restore                  # undo
```

Three opt-in flags reach further than the project's own files:

| Flag | What it does |
| :--- | :--- |
| `optimize --follow-symlinks` | Also compacts skills that sit behind a symlink, and the shared `.agents/skills/` folder they usually point at. The real file is copied to `.tq-forge-backup/symlink-targets/` first, so `restore` still puts every byte back |
| `optimize --dedupe-plugins` | A skill that is symlinked into `.claude/skills/` and is also shipped by an enabled plugin loads twice. The link is removed (and recorded, so `restore` recreates it); the plugin copy and the link's target stay |
| `optimize --compact-plugins` | Compacts the descriptions of plugin skills under `.claude/plugins/`, with a backup. A plugin update replaces those files, so run it again afterwards |
| `measure --plugins [--listing-budget N]` | Adds the skills of enabled plugins to the estimate. `--listing-budget` models Claude Code's own cap on the skill listing (1% of the context window, about 40,000 characters on a 1M-token model): every name stays, descriptions are dropped once the budget is spent |

`skillOverrides` in `settings.json` hides personal and project skills only. Claude Code does not apply it to plugin skills, so tq-forge never writes plugin skill names there; for an unused plugin the answer is `/plugin`, and `auto-improve` tells you which ones.

### Auto-improve

`tq-forge auto-improve` runs everything `optimize` does and then uses two more signals: Claude Code's own session logs (which skills were ever invoked) and the 0–100 rubric.

| Signal | Change |
| :--- | :--- |
| `CLAUDE.md` over 300 tokens | Rule sections stay. Every other section moves, word for word, into an on-demand skill (`reference.md` plus a 140-character trigger), and a one-line pointer stays behind. Long rule bullets keep their first sentence; the full wording goes to `reference.md` |
| `--scope-rules`: rule file over 150 tokens with no `paths:` | Gets any-file globs, so it loads the first time Claude touches a file instead of on every turn. Opt-in, because a rule about how to answer should stay always loaded |
| Skill description over 140 characters | Cut to 140, keeping the "Use when" trigger (a trigger that is too long is cut, never dropped) |
| Skill still over 150 tokens a turn and never invoked | Listed by name only through `skillOverrides`. Skipped when there are no session logs to read, and for any skill you already have an override for |
| `--dedupe-plugins` | Symlinked skills a plugin also loads are unlinked; their plugin twins and idle plugin skills over 150 tokens are compacted |
| Skill or subagent scoring under 85 | Mechanical fixes only: an outdated `model:` id replaced, a missing `effort` filled in. `--add-paths` also adds `paths:` for the file types a description names; it is opt-in because `paths:` stops a skill loading for every other file |

```bash
npx tq-forge auto-improve --root ~                      # dry run on your user setup
npx tq-forge auto-improve --root ~ --follow-symlinks --dedupe-plugins --scope-rules --apply
npx tq-forge restore --root ~                           # undo
```

It does not write missing sections for you, turn off a plugin, or (unless you pass `--extract-scripts`) turn the shell examples in a skill into script calls. It reports those as recommendations instead. On the maintainer's setup the rubric found 41 skills and subagents under 85 and the mechanical fixes raised none of them over it: what they lack is content, not formatting.

**Run it without being asked.** `templates/hooks/auto-improve-session.sh` is a `SessionStart` / `Stop` hook. It measures at most once a day, and starts `auto-improve --apply` in the background when the always-loaded context is over 4,000 tokens or after `sync-models` records a new model. It prints nothing, never waits, and always exits 0. Register it yourself in `settings.json`; nothing installs it for you. Installing the package also prints your current `~/.claude` estimate and the one-line command (a read-only `postinstall`, skipped in CI or with `TQ_FORGE_SKIP_POSTINSTALL=1`).

### Model sync

`config/models.json` is a registry of Claude model generations: the current model of each family with its role (`orchestrator`, `daily-driver`, `fast-worker`), starting effort, prices and prompting rules, plus the recommended lead + subagent pair (today `claude-fable-5-2` + `claude-haiku-5-5`).

```bash
npx tq-forge sync-models                 # dry run
npx tq-forge sync-models --root ~ --apply
npx tq-forge sync-models --offline       # no network call
```

`sync-models` reads the live list of model ids from Anthropic's `/v1/models` when `ANTHROPIC_API_KEY` is set, otherwise from OpenRouter's public model list, and falls back to the registry itself when neither answers. Only Anthropic's own list is acted on: a newer id seen on OpenRouter is reported and nothing is rewritten unless you pass `--trust-source`. An id more than one major or five minor versions ahead is ignored either way. When a family has a newer version (`claude-fable-*`, `claude-mythos-*`, `claude-opus-*`, `claude-sonnet-*`, `claude-haiku-*`) it:

1. adds the model to the registry. Role, effort and prompting rules carry over from the version it replaces. Prices come from the source when it reports them; otherwise they are copied and marked `inherited_from`, which means "check this".
2. rewrites pinned `model:` ids that are now behind, in `.claude/agents/**/*.md` and `.claude/settings.json` (`model`, `env.CLAUDE_CODE_SUBAGENT_MODEL`, `modelSettings`) under `--root`, and in the tq-forge templates. Aliases such as `opus` or `inherit` are left alone.

The model-compatibility lint is keyed by family, so a model added this way is linted from the day it is added. `.github/workflows/model-sync.yml` runs the sync weekly (with `--trust-source`, since its output is a pull request), runs `npm test`, and opens that pull request when something changed. A person still merges it: a new model can change behavior that no registry field describes.

### Benchmark

`npm test` builds two projects and asserts the result. Tokens are **estimated as characters ÷ 4**; run `/context` in Claude Code for real counts.

| Always-loaded context (est. tokens) | Before | After |
| :--- | ---: | ---: |
| `CLAUDE.md` (200 lines, five path-specific sections) | 3,709 | 50 |
| Skill listings (six skills, ~680-character descriptions) | 1,038 | 255 |
| MCP tool names and instructions (five servers, 30 tools each) | 2,590 | 0 |
| Subagent listings (five new `mcp-*` workers) | 0 | 165 |
| **Total, bloated fixture** | **7,337** | **470 (−93.6%)** |
| **Total, lean control project** | — | **no change (0%)** |

The test asserts a reduction of at least 40% on the bloated fixture, with and without counting MCP, and that every instruction line and every MCP server is still present afterwards.

### A real setup

The same estimator on the maintainer's own `~` (a ruflo / claude-flow `CLAUDE.md`, ten always-loaded rule files, 49 personal skills of which 25 were symlinks duplicated by a plugin, and the claude-flow MCP server with 393 tools), after `shield --apply` and `auto-improve --root ~ --follow-symlinks --dedupe-plugins --scope-rules --apply`:

| Always-loaded context (est. tokens) | Before | After |
| :--- | ---: | ---: |
| `CLAUDE.md` (project and user) | 2,467 | 411 |
| Rules with no `paths:` | 4,853 | 0 |
| Personal skill listings | 3,478 | 913 |
| Subagent listings | 435 | 586 |
| claude-flow MCP tool names | 1,842 | 0 |
| **Total** | **13,075** | **1,910 (−85.4%)** |
| Total without the MCP server | 11,233 | 1,910 (−83.0%) |

Read these three ways before quoting them:

- **The rules did not go away.** With `--scope-rules` the 4,853 tokens of rules load the first time Claude touches a file. A session that works on files pays for them as before; a session that never opens one does not. Without that flag the total is 6,763 (−48.3%).
- **Plugins bound the skill saving.** That machine also has 412 plugin skills. Counted under Claude Code's 40,000-character listing budget, the total goes from 19,829 to 11,228 (−43.4%), because the budget that the shorter personal descriptions free up is spent on plugin descriptions that were being dropped before. The durable savings there are `CLAUDE.md`, the rules and the MCP tool names.
- **It is one machine.** `tq-forge restore --root ~` put all 121 changed files back byte for byte when this was tested.

### What this does and does not show

- The numbers are for a deliberately bloated synthetic project. A lean project gets nothing; yours will land in between.
- It measures the fixed context sent each turn. It does not measure your total token use or your usage limits, which also depend on the conversation, tool output, and the model's replies.
- MCP savings are counted only when you pass `--mcp-inventory` with each server's tool names and instructions, because those come from the server and not from `.mcp.json`. Claude Code's MCP tool search already defers full tool schemas by default, so isolation removes names and instructions, not schemas.
- These are trade-offs, not free wins. A shorter description gives Claude less to match a skill on. A path-scoped rule is absent until a matching file is read. An isolated MCP server is reached through a Haiku worker that returns a summary. Review the dry run before `--apply`.
- `--extract-scripts` (moving long shell blocks into `scripts/`), `shield --strict` and `shield --deny-env` are opt-in because they can change behavior. `shield` does set a default effort and subagent model; `--effort keep` and `--subagent-model keep` turn that off, and an existing `CLAUDE_CODE_SUBAGENT_MODEL` is never overwritten.
- Symlinked files and folders (for example `CLAUDE.md -> AGENTS.md`, or skills linked from `~/.agents/skills`) and files that are not valid UTF-8 are left unchanged and listed as warnings, unless you pass `--follow-symlinks`. A server whose name is unsafe in agent frontmatter, or whose worker file name is already taken, stays in `.mcp.json`.
- `--apply` refuses to write when the preview is missing any line or MCP server that the project had before.
- `restore` puts back the files that existed before and deletes the files the optimizer created, including edits you made to those created files afterwards. A file outside `--root` (the target of a followed symlink) is restored only with `restore --outside`, so a backup folder that came with a cloned project cannot write elsewhere on your machine. For the same reason tq-forge refuses to run with a backup folder that is or contains a symlink, and `restore` never copies onto one.

---

## Benchmark Scorecard (Quantitative Quality Scorer)

Every bundled skill and subagent archetype is validated against our deterministic 0–100 quality scoring engine (`scripts/quality-score.sh`):

| Artifact | Kind | Target Model | Score (0–100) | Structural Breakdown | Status |
| :--- | :---: | :---: | :---: | :--- | :---: |
| **`tq-forge`** | Skill | `claude-fable-5-2` | **90/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 9 | ✅ PASS |
| **`tq-forge-agent`** | Skill | `claude-fable-5-2` | **90/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 9 | ✅ PASS |
| **`tq-forge-improve-all`**| Skill | `claude-fable-5-2` | **90/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 9 | ✅ PASS |
| **`tq-forge-queue`** | Skill | `claude-fable-5-2` | **90/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 9 | ✅ PASS |
| **`tq-forge-resume`** | Skill | `claude-fable-5-2` | **90/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 9 | ✅ PASS |
| **`tq-forge-list`** | Skill | `claude-fable-5-2` | **90/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 9 | ✅ PASS |
| **`tq-forge-test`** | Skill | `claude-fable-5-2` | **85/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 7 | ✅ PASS |
| **`tq-forge-agents`** | Skill | `claude-fable-5-2` | **85/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 7 | ✅ PASS |
| **`tq-forge-improve`** | Skill | `claude-fable-5-2` | **85/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 7 | ✅ PASS |
| **`tq-forge-promote`** | Skill | `claude-fable-5-2` | **80/100** | Clarity: 5, Action: 9, Complete: 9, Specific: 9 | ✅ PASS |
| **`tq-forge-scan`** | Skill | `claude-fable-5-2` | **80/100** | Clarity: 5, Action: 9, Complete: 9, Specific: 9 | ✅ PASS |
| **`tq-forge-skill`** | Skill | `claude-fable-5-2` | **80/100** | Clarity: 5, Action: 9, Complete: 9, Specific: 9 | ✅ PASS |
| **`tq-forge-status`** | Skill | `claude-fable-5-2` | **80/100** | Clarity: 5, Action: 9, Complete: 9, Specific: 9 | ✅ PASS |
| **`fable-5-2-orchestrator`** | Subagent | `claude-fable-5-2` | **90/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 9, Consistency: 9 | ✅ PASS |
| **`fable-5-2-advisor`** | Subagent | `claude-fable-5-2` | **90/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 9, Consistency: 9 | ✅ PASS |
| **`code-reviewer`** | Subagent | `claude-opus-5-5` | **90/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 9, Consistency: 9 | ✅ PASS |
| **`security-auditor`** | Subagent | `claude-opus-5-5` | **90/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 9, Consistency: 9 | ✅ PASS |
| **`test-runner`** | Subagent | `claude-sonnet-5-5` | **90/100** | Clarity: 9, Action: 9, Complete: 9, Specific: 9, Consistency: 9 | ✅ PASS |

---

## Comparison

| Feature | Hand-Writing | Standard Prompting | **`tq-forge`** |
| :--- | :---: | :---: | :---: |
| **Spec-Compliant Frontmatter** | Error-prone | Variable | **100% Deterministic** |
| **Claude Fable 5.2 Persistence Blocks** | Manual | Often omitted | **Included (`# Finishing work`)** |
| **Isolated Git Worktree Scaffolding** | Manual setup | Rare | **One command (`--isolated`)** |
| **Lifecycle Hooks & Stdin Validation** | Complex | Shell-heavy | **Preconfigured (`exit 0` / `exit 2`)** |
| **MCP Server Isolation** | Manual JSON | Untrusted envs | **Structured (`.mcp.json` / agents)** |
| **Structural Quality Scoring** | None | Non-deterministic | **Token-Free 0–100 Engine** |
| **Cost Per Score** | Free | API Tokens | **0 Tokens (Pure Python Stdlib)** |
| **Automated Promotion Gate** | None | None | **Mandatory >= 70/100 check** |

---

## Installation

### Via npm (Recommended)

```bash
npx tq-forge install
```

This installs all 13 skills into `~/.claude/skills/`, configures support engines in `~/.tq-forge/install/`, and verifies system dependencies.

```bash
npx tq-forge doctor      # Verify installation and dependencies
npx tq-forge uninstall   # Remove installed skills (preserves your sandbox data)
```

### Via Claude Code Plugin Marketplace

```
/plugin marketplace add tanishq286/tq-forge
/plugin install tq-forge@tq-forge
```

---

## CLI & Scaffolding Usage

### 1. Scaffolding Skills

```bash
# Scaffold a skill from a one-line intent
bash scripts/scaffold.sh skill "deploy static documentation to cloudflare pages"

# Run structural dry-test validation
bash scripts/dry-test.sh ~/.tq-forge/sandbox/forged-skills/deploy-static-documentation/

# Run quantitative quality score
bash scripts/quality-score.sh ~/.tq-forge/sandbox/forged-skills/deploy-static-documentation/
```

### 2. Scaffolding Subagents

```bash
# Scaffold built-in Claude Fable 5.2 orchestrator
bash scripts/scaffold.sh agent --template fable-5-2-orchestrator

# Scaffold built-in Claude Fable 5.2 strategic advisor
bash scripts/scaffold.sh agent --template fable-5-2-advisor

# Scaffold a custom isolated subagent in a git worktree
bash scripts/scaffold.sh agent "audit pull request diffs for injection flaws" \
  --isolated \
  --model claude-fable-5-2 \
  --effort high \
  --allowed-tools "Read, Grep, Glob, Bash"
```

### 3. Scaffolding Lifecycle Hooks

```bash
# Scaffold all 4 lifecycle hooks with JSON stdin validation and exit-code enforcement
bash scripts/scaffold.sh hooks --events PreToolUse,PostToolUse,SessionStart,Stop
```

### 4. Scaffolding MCP Servers

```bash
# Scaffold a project-level MCP server into .mcp.json
bash scripts/scaffold.sh mcp --name cloud-db --url https://api.example.com/mcp --token-env DB_TOKEN --scope project

# Scaffold an isolated MCP subagent
bash scripts/scaffold.sh mcp --name sqlite-db --command python3 --arg -m --arg sqlite_mcp --scope subagent
```

### 5. Running the Automated Test Suite

```bash
npm test
```

Runs two suites: `scripts/test-runner.py` (264 assertions on manifests, frontmatter schemas, hook exit codes, scaffolding from one-line intents, the 0–100 scorer, the model registry, the auto-improve session hook and `postinstall`) and `tests/test_optimize.py` (76 tests on the context optimizer, auto-improve and model sync: the before/after benchmark, dry-run and restore safety, symlink and plugin handling, model-id parsing and upgrades with the network faked, and hostile inputs such as colliding server names and non-UTF-8 files).

---

## The 13 Claude Code Slash Commands

| Command | Description |
| :--- | :--- |
| `/tq-forge <intent>` | Intelligently classifies intent → scaffolds skill or subagent → scores → queues |
| `/tq-forge-skill <intent>` | Direct skill mode: scaffolds `.claude/skills/<name>/SKILL.md` |
| `/tq-forge-agent <intent>` | Direct agent mode: scaffolds persona-driven agent with domain context |
| `/tq-forge-promote <slug>` | Strict quality gate: re-scores and promotes sandbox artifact to production |
| `/tq-forge-improve <slug>` | Surgical optimizer: rewrites only the dimensions scoring below target |
| `/tq-forge-improve-all` | Batch optimizer: raises all staged sandbox artifacts above 70/100 |
| `/tq-forge-test <slug>` | Static quality evaluator: runs 0–100 scoring breakdown without modifying files |
| `/tq-forge-list` | Real-time catalog of all skills and subagents with quality metrics |
| `/tq-forge-agents` | Subagent registry: archetypes, models, effort levels, and tool bindings |
| `/tq-forge-status` | Factory status: queue depth, halt flag state, and active sandbox items |
| `/tq-forge-scan` | Gap detector: analyzes recent activity to identify workflows ready for automation |
| `/tq-forge-queue` | Queue manager: inspects and triages deferred scaffolding jobs |
| `/tq-forge-resume` | Clears safety halt flags and drains deferred queue |

---

## Security & Supply Chain Integrity

- **OpenSSF Scorecard**: `.github/workflows/scorecard.yml` publishes the security Scorecard weekly. (The OpenSSF Criticality Score is a separate tool and is not computed here.)
- **Pinned actions**: every GitHub Action in `.github/workflows/` is pinned to a commit SHA.
- **Two network calls, both optional**: `sync-models` makes one GET to Anthropic's `/v1/models` (when `ANTHROPIC_API_KEY` is set) or to OpenRouter's public model list, and `--offline` skips it. Everything else (scorer, dry-test, scaffolding, optimizer, auto-improve, the hook, `postinstall`) runs offline with zero dependencies and sends nothing.
- **Full Security Policy**: See [SECURITY.md](SECURITY.md).
- **Responsible Disclosure**: [Report vulnerabilities privately](https://github.com/tanishq286/tq-forge/security/advisories/new).

---

## License

[MIT](LICENSE) © 2026 Tanishq Agarwal
