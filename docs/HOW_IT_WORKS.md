# How tq-forge works

A deeper look at the architecture, the scoring model, and the file layout — for
anyone who wants to understand or extend the tool.

## The one-sentence model

> Describe a workflow → tq-forge classifies it (skill vs agent), scaffolds it
> into a **sandbox**, **scores** it on structural quality, and only lets you
> **promote** it into your live skills dir once a re-score passes at ≥7/10.

Nothing you forge is ever live until you explicitly promote it, and promotion
always re-scores first — so a stale score can't sneak a weak artifact into
production.

## The pipeline

```
  /tq-forge "intent"
        │
        ▼
   classify ──▶ skill | agent
        │
        ▼  scaffold
   $TQ_FORGE_HOME/sandbox/forged-{skills,agents}/<slug>/
        │
        ▼  quality-score.sh + dry-test.sh   (static, token-free)
   score ≥ 7 ? ──no──▶ /tq-forge-improve   (rewrite ONLY weak sections, 1 pass)
        │ yes
        ▼  /tq-forge-promote   (re-score, then copy)
   $CLAUDE_SKILLS_DIR/<slug>/   ← live
```

## Two install modes, one set of skills

The skills are **dual-mode**. Each SKILL.md resolves its support scripts like
this:

```bash
S="${CLAUDE_PLUGIN_ROOT:-${TQ_FORGE_HOME:-$HOME/.tq-forge}/install}/scripts"
```

- **Plugin install** (`/plugin marketplace add`): Claude Code sets
  `CLAUDE_PLUGIN_ROOT`, so scripts resolve from the plugin directory.
- **npm install** (`npx tq-forge install`): the CLI copies scripts + templates
  into `~/.tq-forge/install/`, and the fallback resolves there.

Same SKILL.md, both ways — no separate builds.

## State layout

Everything mutable lives under `$TQ_FORGE_HOME` (default `~/.tq-forge`), never
inside the plugin/package (which may be read-only or reinstalled):

```
~/.tq-forge/
├── context.md            # your domain context, injected into agents via {{CONTEXT}}
├── skill-log.json        # inventory: every artifact's slug, kind, score, status
├── forge-queue.json      # { queue: [...], needs_manual_review: [...] }
├── halt.flag             # touch to pause forge work; remove to resume
├── install/              # scripts + templates (npm mode only)
└── sandbox/
    ├── forged-skills/<slug>/SKILL.md
    └── forged-agents/<slug>/{AGENT.md, system-prompt.md, tools.json,
                              trigger-conditions.md, example-tasks.md}
```

All JSON writes are **read-modify-write with atomic replace** (write `.tmp`,
`mv` into place) so a crash mid-write can't corrupt your inventory.

## The scoring model

`scripts/quality-score.sh` is pure Python stdlib — **no LLM calls**, so it's free
and deterministic. It reads the artifact and applies heuristics per dimension.

### Skills (4 dimensions)

| Dimension | What earns a 9 |
|---|---|
| `clarity` | "When to use" is 30–200 words across ≤4 sentences |
| `actionability` | "Procedure" has ≥3 numbered steps and ≥2 code blocks |
| `completeness` | Pitfalls **and** Verification **and** Tags all present |
| `specificity` | No vague phrases ("do the thing", "stuff") + ≥3 real paths/tools |

### Agents (6 dimensions)

The four above (computed from `system-prompt.md`) plus:

| Dimension | What earns a 9 |
|---|---|
| `consistency` | Output format is a fenced/`yaml` schema (rigid, not prose) |
| `handoff_clarity` | `tools.json` lists `hand_off_to` targets |

The average is the score. **8–9 is the normal pass band**; a perfect 10 is rare
by design — don't pad word count to chase it.

### What the scorer is *not*

It's a **structural floor, not a correctness judge**. It catches missing
sections, vagueness, and malformed agents. It cannot tell you whether your
procedure actually *works* — that's on you to verify after promoting. Treat ≥7
as "well-formed enough to ship," not "proven correct."

## dry-test

`scripts/dry-test.sh` is a separate structural gate that checks things the score
doesn't: valid YAML frontmatter, all 5 agent files present, valid `tools.json`,
and word-count bounds. Promotion requires both `score ≥ 7` **and**
`dry-test = pass`.

## The improve loop

`/tq-forge-improve` runs `improve-loop.sh assess` to find the weak dimensions,
rewrites **only** those sections (leaving strong sections byte-for-byte intact),
then `improve-loop.sh verify` re-scores and records the before/after delta in
`skill-log.json`. One targeted pass — if it still fails, it's flagged for manual
review rather than looped forever.

## Pause / resume

`halt.flag` is a dead-simple budget/attention guard: while it exists, `/tq-forge`
and friends **queue** the requested intent instead of running it.
`/tq-forge-resume` clears the flag and drains the queue. No daemon, no tracker —
just a file you can `touch` and `rm`.

## Extending it

- **New agent archetype** → add `templates/agent-templates/<kind>.md` (yaml block,
  Persona, Output format, NEVER, `{{CONTEXT}}`) and list it in `/tq-forge-agent`.
- **Smarter scoring** → edit the heuristics in `quality-score.sh` /
  `dry-test.sh`. Keep them stdlib-only and token-free.

See [CONTRIBUTING.md](../CONTRIBUTING.md).
