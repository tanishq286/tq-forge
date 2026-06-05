---
name: tq-forge
description: |
  Autonomous skill + agent factory for Claude Code. Given a one-line intent,
  decides whether to scaffold a new skill or a 5-file agent, writes it to the
  sandbox at $TQ_FORGE_HOME/sandbox/, scores it for structural quality, and
  queues it for /tq-forge-promote. Use when asked for "/tq-forge", "forge a
  skill", "build me an agent for X", or "make a skill that Y".
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
---

# /tq-forge — autonomous skill + agent forge

## When to use

A workflow keeps coming up that you'd want to one-shot in the future, or you
need a specialized agent (researcher, coder, business-analyst, ops-manager,
scraper, reviewer, sales-agent) tuned to your own domain context. /tq-forge
takes the intent in plain English, decides which kind to build, writes it to
the sandbox, scores it, and prints the next command. Nothing goes live until
you run `/tq-forge-promote <slug>`.

## Procedure

Scripts live at `$CLAUDE_PLUGIN_ROOT/scripts`. State lives at
`${TQ_FORGE_HOME:-$HOME/.tq-forge}`. Initialize both up front:

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
S="$CLAUDE_PLUGIN_ROOT/scripts"
source "$S/common.sh" && tq_ensure_home
```

1. **Check the halt flag.** If `$TQ_FORGE_HOME/halt.flag` exists, the user has
   paused forge work. Queue the intent and exit cleanly:
   ```bash
   test -f "$TQ_FORGE_HOME/halt.flag" && \
     bash "$S/forge-checkpoint.sh" queue "<intent>" && \
     echo "⏸  Forge paused (halt.flag set). Queued. Remove the flag to resume." && exit 0
   ```

2. **Classify intent.** Decide:
   - **agent** if intent uses persona language ("an agent that…", "a researcher
     for…", "ops manager that watches X") or names a known kind: researcher,
     coder, business-analyst, ops-manager, scraper, reviewer, sales-agent.
   - **skill** if intent describes a procedure ("a command for daily summaries",
     "scaffold a skill that does X", "automate Y").
   - **ambiguous** -> AskUserQuestion: "Skill (one-shot procedure) or Agent
     (persona with system prompt + handoff rules)?"

3. **Scan for duplicates.** Don't forge something that already exists:
   ```bash
   ls "$CLAUDE_SKILLS_DIR" "$SANDBOX_SKILLS" "$SANDBOX_AGENTS" 2>/dev/null
   grep -liE "<keyword from intent>" "$CLAUDE_SKILLS_DIR"/*/SKILL.md 2>/dev/null
   ```
   If a near-match exists, print the path and ask: fork, edit, or abort. Never
   silently overwrite.

4. **Pick a slug.** Lowercase, hyphenated, <=32 chars. "Notion daily summary"
   -> `notion-daily-summary`. Confirm via AskUserQuestion only if ambiguous.

5. **Hand off to the right builder.**
   - **skill** -> follow the `/tq-forge-skill` procedure (writes
     `$SANDBOX_SKILLS/<slug>/SKILL.md`).
   - **agent** -> follow the `/tq-forge-agent` procedure (writes the 5-file
     agent under `$SANDBOX_AGENTS/<slug>/`, injecting `$TQ_FORGE_HOME/context.md`
     wherever `{{CONTEXT}}` appears).

6. **Score the output.**
   ```bash
   bash "$S/quality-score.sh" "$SANDBOX_SKILLS/<slug>"   # or $SANDBOX_AGENTS
   bash "$S/dry-test.sh" "$SANDBOX_SKILLS/<slug>"
   ```
   Score must be >=7. If lower, refine the weakest dimension once and re-score.
   If still <7, flag it:
   ```bash
   bash "$S/forge-checkpoint.sh" review "<slug>" "<weak-dim>" "<score>"
   ```

7. **Log it.** Append to `$TQ_FORGE_HOME/skill-log.json`:
   ```bash
   python3 -c "import json,datetime,pathlib,os;p=pathlib.Path(os.environ['TQ_FORGE_HOME'])/'skill-log.json';d=json.loads(p.read_text() or '[]');d.append({'slug':'<slug>','kind':'<skill|agent>','score':<S>,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'intent':'<intent>','status':'sandbox'});p.write_text(json.dumps(d,indent=2))"
   ```

8. **Print summary.** slug, kind, sandbox path, score, and the exact next
   command: `/tq-forge-promote <slug>`.

## Pitfalls

- The sandbox is mandatory. Even a trivial skill goes through promote — that's
  the only path that writes into `$CLAUDE_SKILLS_DIR`.
- Don't forge a duplicate. The duplicate scan in step 3 is not optional.
- Slug collisions: if `<slug>` already exists in the sandbox, append `-v2`
  rather than overwriting.
- Agents need `$TQ_FORGE_HOME/context.md` filled in. With the placeholder
  still in place, agents will be generic — tell the user to edit it.

## Verification

- `ls "$SANDBOX_SKILLS/<slug>"` (or `$SANDBOX_AGENTS`) shows the new files.
- `skill-log.json` includes the new entry with `status: sandbox`.
- The printed score is >=7, or it was flagged for manual review with a reason.

## Tags

`tq-forge` `meta` `factory` `sandbox-only`
