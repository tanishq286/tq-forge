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
| `optimize-mcp` | Servers stay in `.mcp.json`. Per-server `"alwaysLoad": true` is removed and `ENABLE_TOOL_SEARCH=true` is set in `settings.json`, so tool schemas are deferred and every tool stays callable from the main thread and from subagents. `--isolate-mcp` moves each server into `.claude/agents/mcp-<name>.md` instead; the main thread then loses direct access to its tools | Schemas load when Claude searches for a tool |
| `optimize-skills` | Descriptions of 350 characters or fewer are never cut; longer ones are cut to whole sentences, keeping the "Use when" sentence (`--description-limit 160` is the aggressive setting). Reference sections of skill bodies over 120 lines move to `reference.md`. Files under `.claude/plugins/` are never written | When the skill is invoked |
| `optimize-skills` | `CLAUDE.md` sections (in files over 80 lines) that name paths existing in the repo move to `.claude/rules/<topic>.md` with `paths:` | When Claude reads a matching file |
| `optimize` (prose step) | A `CLAUDE.md` over 80 lines keeps its rules, tables, short lists, short commands and paragraphs that name a tool or command. Prose and long examples move to an on-demand skill, and each section that loses anything is copied there whole | When that skill is invoked |
| `shield` | Sets `claudeMdExcludes`, adds two "soaker" subagents that return summaries of 15 lines or fewer and a one-line (33-token) hygiene note in `CLAUDE.md`. It changes neither effort, nor the subagent model, nor permissions; `--effort`, `--subagent-model`, `--deny-env` and `--strict` are opt-in | — |

```bash
npx tq-forge measure                  # estimate the always-loaded context
npx tq-forge optimize                 # dry run: plan and before/after estimate
npx tq-forge optimize --apply         # write; originals go to .tq-forge-backup/
npx tq-forge shield --apply           # effort, subagent model and permissions are left as they are
npx tq-forge restore                  # undo
```

These opt-in flags reach further than the default, lossless pass:

| Flag | What it does |
| :--- | :--- |
| `optimize --follow-symlinks` | Also compacts skills that sit behind a symlink, and the shared `.agents/skills/` folder they usually point at. The real file is copied to `.tq-forge-backup/symlink-targets/` first, so `restore` still puts every byte back |
| `optimize --dedupe-plugins` | A skill that is symlinked into `.claude/skills/` and is also shipped by an enabled plugin loads twice. The link is removed (and recorded, so `restore` recreates it); the plugin copy and the link's target stay |
| `optimize --isolate-mcp` | Moves each MCP server into its own worker subagent. Largest saving, and the main conversation can no longer call those tools directly |
| `measure --plugins [--listing-budget N]` | Adds the skills of enabled plugins to the estimate. `--listing-budget` models Claude Code's own cap on the skill listing (1% of the context window, about 40,000 characters on a 1M-token model): every name stays, descriptions are dropped once the budget is spent |

`skillOverrides` in `settings.json` hides personal and project skills only. Claude Code does not apply it to plugin skills, so tq-forge never writes plugin skill names there; for an unused plugin the answer is `/plugin`, and `auto-improve` tells you which ones.

### Auto-improve

`tq-forge auto-improve` runs everything `optimize` does (lossless by default) and then uses two more signals: Claude Code's own session logs (which skills were ever invoked) and the 0–100 rubric. The first and third rows below describe `--aggressive`, which also isolates MCP servers; without it the lossless prose step and the 350-character limit apply.

| Signal | Change |
| :--- | :--- |
| `CLAUDE.md` over 300 tokens | Rule sections stay. Every other section moves, word for word, into an on-demand skill (`reference.md` plus a 140-character trigger), and a one-line pointer stays behind. Long rule bullets keep their first sentence; the full wording goes to `reference.md` |
| `--scope-rules`: rule file over 150 tokens with no `paths:` | Gets any-file globs, so it loads the first time Claude touches a file instead of on every turn. Opt-in, because a rule about how to answer should stay always loaded |
| Skill description over 140 characters | Cut to 140, keeping the "Use when" trigger (a trigger that is too long is cut, never dropped) |
| Skill still over 150 tokens a turn and never invoked | Listed by name only through `skillOverrides`. Skipped when there are no session logs to read, and for any skill you already have an override for |
| `--dedupe-plugins` | Symlinked skills a plugin also loads are unlinked. Plugin files themselves are never edited |
| Skill or subagent scoring under 85 | Mechanical fixes only: an outdated `model:` id replaced, a missing `effort` filled in. `--add-paths` also adds `paths:` for the file types a description names; it is opt-in because `paths:` stops a skill loading for every other file |

```bash
npx tq-forge auto-improve --root ~                      # dry run on your user setup
npx tq-forge auto-improve --root ~ --follow-symlinks --dedupe-plugins --scope-rules --apply
npx tq-forge restore --root ~                           # undo
```

It does not write missing sections for you, turn off a plugin, or (unless you pass `--extract-scripts`) turn the shell examples in a skill into script calls. It reports those as recommendations instead. On the maintainer's setup the rubric found 41 skills and subagents under 85 and the mechanical fixes raised none of them over it: what they lack is content, not formatting.

**Run it without being asked.** `templates/hooks/auto-improve-session.sh` is a `SessionStart` / `Stop` hook. It measures at most once a day, and starts `auto-improve --apply` in the background when the always-loaded context is over 4,000 tokens or after `sync-models` records a new model. It prints nothing, never waits, and always exits 0. Register it yourself in `settings.json`; nothing installs it for you. Installing the package also prints your current `~/.claude` estimate and the one-line command (a read-only `postinstall`, skipped in CI or with `TQ_FORGE_SKIP_POSTINSTALL=1`).

### Model sync

`config/models.json` is a registry of Claude model generations: the current model of each family (`claude-fable-5-2`, `claude-mythos-5-2`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`) with its role (`orchestrator`, `daily-driver`, `fast-worker`), capabilities, an effort guide, prices and prompting rules, plus a table of retired and deprecated ids and the recommended lead + subagent pair (today `claude-fable-5-2` + `claude-haiku-5-5`).

```bash
npx tq-forge sync-models                 # dry run
npx tq-forge sync-models --root ~ --apply
npx tq-forge sync-models --offline       # no network call
```

`sync-models` reads the live list of model ids from Anthropic's `/v1/models` when `ANTHROPIC_API_KEY` is set, otherwise from OpenRouter's public model list, and falls back to the registry itself when neither answers. Only Anthropic's own list is acted on: a newer id seen on OpenRouter is reported and nothing is rewritten unless you pass `--trust-source`. An id more than one major or five minor versions ahead is ignored either way. When a family has a newer version (`claude-fable-*`, `claude-mythos-*`, `claude-opus-*`, `claude-sonnet-*`, `claude-haiku-*`) it:

1. adds the model to the registry. Role, effort guide, capabilities and prompting rules carry over from the version it replaces. Prices come from the source when it reports them; otherwise they are copied and marked `inherited_from`, which means "check this".
2. rewrites pinned `model:` ids that are now behind, in `.claude/agents/**/*.md` and `.claude/settings.json` (`model`, `env.CLAUDE_CODE_SUBAGENT_MODEL`, `modelSettings`) under `--root`, and in the tq-forge templates. Aliases such as `opus` or `inherit` are left alone. A retired id the registry lists by name (`claude-2.1`) moves to its listed replacement; `claude-mythos-preview` has two possible successors, so it is reported and left for you.

The model-compatibility lint is keyed by family, so a model added this way is linted from the day it is added. `.github/workflows/model-sync.yml` runs the sync weekly (with `--trust-source`, since its output is a pull request), regenerates the compatibility matrix, runs `npm test`, and opens that pull request when something changed. A person still merges it: a new model can change behavior that no registry field describes.

### Model compatibility

`tq-forge score` subtracts points for instructions the target model rejects or handles badly. The checks are static and deterministic: no model is called.

| Rule | What it flags | Applies to |
| :--- | :--- | :--- |
| M001 | `thinking: {"type": "enabled", "budget_tokens": N}` or any fixed thinking budget. Use adaptive thinking and `output_config.effort`. | all models |
| M010 | `thinking: {"type": "disabled"}`. Lower `effort` instead. | Fable, Opus, Sonnet |
| M008 | `temperature`, `top_p`, `top_k`. Sonnet 5.5 and Haiku 5.5 still accept the default values. | all models |
| M004 | A request for raw reasoning or chain of thought in the reply, which can be declined as `reasoning_extraction`. | Fable, Opus, Sonnet |
| M011 | A long-horizon subagent with no completion instructions at an effort level where the model stops early (Fable at `low` or `medium`; Sonnet and Haiku at `low`). | Fable, Sonnet, Haiku |
| M012 | A retired (−10), deprecated (−6) or superseded (−3) Claude model id. | any target |

M002, M003, M005, M006, M007 and M009 cover token budgets shown to the model, think-less instructions, thinking incantations, history editing, forced `tool_choice` and prefill. A file that pins an outdated id such as `claude-sonnet-4-6` is linted against its family's current model; before 1.3.0 it got no model rules at all.

```bash
npx tq-forge score .claude/agents/my-agent.md   # findings with line numbers and fixes
npx tq-forge compat                             # every bundled skill and template under each model
```

[`docs/MODEL_COMPATIBILITY.md`](docs/MODEL_COMPATIBILITY.md) is the generated matrix: each bundled skill and subagent template with its score under Fable 5.2, Opus 5.5, Sonnet 5.5 and Haiku 5.5, the minimum model tier, the starting effort level and pass or fail. `npm test` fails when that file differs from the generator's output.

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

The table is the aggressive path (`--isolate-mcp`, 160-character descriptions). The default lossless pass takes the same fixture from 7,337 to 3,121 (−57.5%) with every MCP server still on the main thread. The test asserts a reduction of at least 40% on the bloated fixture, with and without counting MCP, and that every instruction line and every MCP server is still present afterwards.

### A real setup

> These numbers are from the 1.1.0 aggressive pass (`--isolate-mcp`, `--scope-rules`, 140-character descriptions). It cost direct access to the MCP tools and was reverted on that machine. The 1.2.0 lossless pass with `--dedupe-plugins` on the same setup measures 11,951 → 9,137 (45,524 → 42,710 with plugin skills counted): most of what is left is rules and routing tables that are meant to load on every turn.

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

## Mods

`tq-forge mods install` adds six hook handlers and four slash commands. Each one decides from what is happening in the session instead of a static global setting, and each can be switched off with `/switchboard`.

| Mod | Hook | What it does |
| :--- | :--- | :--- |
| `input-router` | `PreToolUse(Read)`, `PostToolUse(mcp__*)` | A data file over 2,000 tokens (source over 12,000) is handed to the `input-reader` subagent (`haiku`, or `sonnet` via `/switchboard`) or read in ranges. MCP output loses empty fields, base64 blobs and avatar URLs. What is still over the threshold is stored whole under a CCR id and shown short (JSON as a schema and its first rows, a log without repeats, a large source file as an outline); `tq-forge retrieve <id>` prints the original. Other large text is saved under `~/.claude/tq-forge-payloads/` and replaced by a preview |
| `effort-optimizer` | `UserPromptSubmit` | Classifies the prompt and recommends `/effort low`, `medium`, `high` or `xhigh` when the current effort does not fit. A hook cannot change effort, so this is a one-line recommendation; it never suggests `max` |
| `subagent-model-selector` | `PreToolUse(Agent)` | Easy jobs (read, summarize, search, run one test) go to `haiku`, normal jobs to `sonnet`, complex or high-risk jobs stay on the session model. An explicit model, a plugin agent, a pinned agent definition and the built-in agents are never overridden |
| `cache-clock` | `Stop`, status line | Records each reply and shows how long the prompt cache stays warm: 60 minutes on a Claude subscription, 5 with an API key |
| `handoff` | `Stop` | Past 250,000 tokens it writes a `HANDOFF.md` skeleton from the transcript and points to `/handoff` |
| `efficient-browser-use` | `PostToolUse(mcp__*)` | Halves screenshot dimensions: a 1280×720 capture goes from about 1,200 image tokens to about 300. Uses Pillow when it is installed and a standard-library PNG path otherwise |

```bash
npx tq-forge mods install --root ~           # dry run
npx tq-forge mods install --root ~ --apply   # existing hooks and settings are kept; restore undoes it
npx tq-forge mods status | savings
npx tq-forge mods toggle input-router sonnet
npx tq-forge keep-warm --ttl 55m
npx tq-forge retrieve 0123456789ab --lines 40:80   # or --search ERROR; the id comes from a [CCR-ID: ...] line
```

`--chain-statusline` appends the cache clock to a status line you already have. `--allow-autonomy` pre-approves `WebSearch`, `WebFetch`, `gh api` and the learn/scout commands; `gh api` can also write with your GitHub token, so the flag is never implied. `/savings` reads `~/.claude/tq-forge-savings.json`; its figures are estimates (characters ÷ 4, pixels ÷ 750, list prices).

## Learn and scout

```bash
npx tq-forge learn https://www.youtube.com/watch?v=<id>     # captions and chapters
npx tq-forge learn https://github.com/<owner>/<repo>        # CLAUDE.md, skill and agent names, latest release
npx tq-forge scout "claude code hooks" --sources github,social
```

The collector (`scripts/lib/intel_scout.py`) uses `yt-dlp` and `gh` when they are installed and plain HTTPS otherwise. What it fetches is untrusted: `scripts/lib/self_evolve.py` removes lines that look like prompt injection or unsafe shell, writes a skill whose body is a fixed template, and keeps the source text fenced as data in `reference.md`. The result goes to the sandbox. With `--apply` it is installed to `.claude/skills/learned-<slug>/` only when it scores 85 or more and holds at least three concrete steps. A pattern filter cannot catch everything, so read a learned skill before you rely on it.

---


## Benchmark Scorecard (Quantitative Quality Scorer)

Every bundled skill and subagent template is scored by the deterministic 0–100 engine (`scripts/quality-score.sh`) under the rules of each current Claude model. All 27 artifacts (18 skills, 9 subagent templates) pass the promotion gate of 70 under Fable 5.2, Opus 5.5, Sonnet 5.5 and Haiku 5.5, and `npm test` fails if one stops passing.

The current scores, with the minimum model tier and starting effort for each artifact, are generated into [`docs/MODEL_COMPATIBILITY.md`](docs/MODEL_COMPATIBILITY.md).

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

This installs all 18 skills into `~/.claude/skills/`, configures support engines in `~/.tq-forge/install/`, and verifies system dependencies.

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

Runs two suites: `scripts/test-runner.py` (971 assertions on manifests, frontmatter schemas, hook exit codes, scaffolding from one-line intents, the 0–100 scorer, the model registry, the model-compatibility lint, the cross-model matrix, the auto-improve session hook and `postinstall`) and `tests/` (200 tests: `test_optimize.py` on the context optimizer, lossless mode, restore safety, auto-improve and model sync; `test_mods.py` on every mod, the installer and the savings log; `test_learn.py` on the collectors with the network faked, the sanitizer, the synthesizer and the rubric; `test_model_compat.py` on the registry, the lint cases and the matrix; `test_ccr.py` on the reversible short forms; `test_manifests.py` on versions and documented counts).

---

## The 18 Claude Code Slash Commands

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
| `/tq-forge-learn <url-or-topic>` | Researches a video, repository, thread or topic and turns it into a small skill |
| `/savings` | Tokens and estimated dollars saved, mod by mod |
| `/switchboard` | Turns a mod on or off, or switches the input router between `haiku` and `sonnet` |
| `/handoff` | Writes `HANDOFF.md` so a fresh chat can continue with a small context |
| `/keep-warm` | Refreshes the prompt cache with one minimal turn and reports when it expires |

---

## Security & Supply Chain Integrity

- **OpenSSF Scorecard**: `.github/workflows/scorecard.yml` publishes the security Scorecard weekly. (The OpenSSF Criticality Score is a separate tool and is not computed here.)
- **Pinned actions**: every GitHub Action in `.github/workflows/` is pinned to a commit SHA.
- **Network calls, all optional**: `sync-models` makes one GET to Anthropic's `/v1/models` (when `ANTHROPIC_API_KEY` is set) or to OpenRouter's public model list. `learn` and `scout` make GET requests to the URL or public sources you ask about (YouTube, GitHub, Reddit, Hacker News, DEV.to). `--offline` skips them. Everything else, including the mods' hooks, makes no network call.
- **Full Security Policy**: See [SECURITY.md](SECURITY.md).
- **Responsible Disclosure**: [Report vulnerabilities privately](https://github.com/tanishq286/tq-forge/security/advisories/new).

---

## License

[MIT](LICENSE) © 2026 Tanishq Agarwal
