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

<br/>

<img src="assets/demo.gif" alt="tq-forge demo: the deterministic scorer passing a 9.0 and a 7.8, then blocking a 3.2 at the promote gate" width="760"/>

</div>

---

## Overview

Claude Code enables developers to define reusable **skills** (`.claude/skills/<name>/SKILL.md`) and specialized **subagents** (`.claude/agents/<name>.md`). However, creating them manually involves fragile YAML frontmatter, strict token constraints, subtle permission modes, and zero static quality feedback.

**`tq-forge` is an autonomous maintainer factory and static quality engine.** From a single English intent, it determines the right abstraction, generates fully conformant artifacts into a sandbox, validates them with a **token-free deterministic quality scorer (0–100)**, and ensures nothing reaches production until it meets rigorous thresholds.

```
You:  /tq-forge an isolated security auditor for checking pull request diffs

      → classified: isolated subagent
      → template: security-auditor (claude-opus-5-5, effort: high)
      → isolation: worktree, permissionMode: plan, memory: project
      → written to ~/.tq-forge/sandbox/project/.claude/agents/security-auditor.md
      🟢 subagent security-auditor.md: 90/100 (9.0/10, excellent)
         clarity            9  █████████░
         actionability      9  █████████░
         completeness       9  █████████░
         specificity        9  █████████░
         consistency        9  █████████░
      → Next: /tq-forge-promote security-auditor
```

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
- Configurable `permissionMode` (`plan`, `acceptEdits`), `allowed-tools`, and `memory: project` for context retention across turns.

### 3. Lifecycle Hooks Generation (`.claude/hooks/`)
- Deterministic hooks for `PreToolUse`, `PostToolUse`, `SessionStart`, and `Stop`.
- Strict exit code semantics:
  - **`exit 0` (Allow)**: Normal execution continues.
  - **`exit 2` (Block)**: Rejects execution and prints feedback on `stderr` directly into Claude's context.
- Guardrails:
  - Blocks dangerous shell operations (`rm -rf /`, `git push --force`).
  - Automatically syntax-checks changed files (`.json`, `.sh`, `.py`, `.js`) on edit or write.
  - Injects repository status on session startup.
  - Enforces loop-safe stop prevention when merge conflicts or unfilled placeholders remain.

### 4. MCP Server Scaffolding (`.mcp.json`)
- **Project-scoped MCP servers**: In `.mcp.json` with `http` or `stdio` transports, argument passing, and clean `${VAR}` environment variable expansion.
- **Subagent-scoped MCP servers**: Isolates heavy toolkits (e.g. SQLite, GitHub, Kubernetes) into dedicated subagents so tool definitions do not consume the main conversation context.

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

Executes 225+ assertions testing license compliance, schema rules, frontmatter limits, hook exit-code behavior, dynamic scaffolding, and quality benchmarks.

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

- **OpenSSF Criticality & Security**: Monitored via automated Scorecard runs in `.github/workflows/scorecard.yml`.
- **Zero Network Calls in Tooling**: Scorer, dry-test, and scaffolding utilities run purely offline with zero external dependencies.
- **Full Security Policy**: See [SECURITY.md](SECURITY.md).
- **Responsible Disclosure**: [Report vulnerabilities privately](https://github.com/tanishq286/tq-forge/security/advisories/new).

---

## License

[MIT](LICENSE) © 2026 Tanishq Agarwal
