---
name: tq-forge-agent
description: |
  Force-agent mode — bypass /tq-forge's auto-classification and scaffold a
  5-file agent in the sandbox. Picks a base template (researcher, coder,
  business-analyst, ops-manager, scraper, reviewer, sales-agent, custom) and
  injects your domain context from $TQ_FORGE_HOME/context.md. Use when asked
  for "/tq-forge-agent", "make an agent that...", or "scaffold an agent".
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
---

# /tq-forge-agent — force-agent scaffold

## When to use

You want a multi-turn, persona-driven agent with a rigid output format — not a
one-shot procedural skill. The agent lives as a 5-file directory under
`$TQ_FORGE_HOME/sandbox/forged-agents/<slug>/`: `AGENT.md`, `system-prompt.md`,
`tools.json`, `trigger-conditions.md`, `example-tasks.md`. `/tq-forge-promote`
is the only path that moves it into production.

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
S="$CLAUDE_PLUGIN_ROOT/scripts"; T="$CLAUDE_PLUGIN_ROOT/templates/agent-templates"
source "$S/common.sh" && tq_ensure_home
```

1. **Check the halt flag.** If `$TQ_FORGE_HOME/halt.flag` exists, queue and exit:
   ```bash
   test -f "$TQ_FORGE_HOME/halt.flag" && bash "$S/forge-checkpoint.sh" queue "<intent>" && exit 0
   ```

2. **Pick the agent kind** via AskUserQuestion (default to the closest match by
   the intent's verbs — search -> researcher, build -> coder, monitor ->
   ops-manager): `researcher`, `coder`, `business-analyst`, `ops-manager`,
   `scraper`, `reviewer`, `sales-agent`, `custom`.

3. **Pick a slug.** Lowercase, hyphenated, <=32 chars. Confirm if ambiguous.

4. **Check for collisions.**
   ```bash
   for d in "$SANDBOX_AGENTS/<slug>" "$CLAUDE_SKILLS_DIR/agents/<slug>"; do
     test -e "$d" && echo "EXISTS: $d"
   done
   ```

5. **Read the template + your context.**
   ```bash
   cat "$T/<kind>.md"
   cat "$TQ_FORGE_HOME/context.md"
   ```

6. **Create the directory + 5 files.**
   ```bash
   mkdir -p "$SANDBOX_AGENTS/<slug>"
   ```
   Write each file, basing persona/output-format/NEVER on the template:
   - `AGENT.md` — kind, slug, one-paragraph mission, default_tools,
     `dry_test_score_target`, `hand_off_to` list.
   - `system-prompt.md` — 500-1500 words. Sections: `## Persona`,
     `## Operating principles`, `## Output format` (fenced block), `## NEVER`,
     and `## Domain context` with the full `context.md` substituted in wherever
     the template had `{{CONTEXT}}`.
   - `tools.json` — `{"tools": [...], "hand_off_to": [...]}` from the template's
     `default_tools`.
   - `trigger-conditions.md` — 3-6 intent patterns that should route here.
   - `example-tasks.md` — at least 3 `## Task N` entries showing input ->
     expected output shape, drawn from your domain context.

7. **Score it.**
   ```bash
   bash "$S/quality-score.sh" "$SANDBOX_AGENTS/<slug>"
   bash "$S/dry-test.sh" "$SANDBOX_AGENTS/<slug>"
   ```

8. **If quality score < 7**, rewrite the lowest-scoring dimension once (usually
   `system-prompt.md` length or output-format rigidity), re-score. If still <7:
   ```bash
   bash "$S/forge-checkpoint.sh" review "<slug>" "<weak-dim>" "<score>"
   ```

9. **Append to skill-log.json.**
   ```bash
   python3 -c "import json,datetime,pathlib,os;p=pathlib.Path(os.environ['TQ_FORGE_HOME'])/'skill-log.json';d=json.loads(p.read_text() or '[]');d.append({'slug':'<slug>','kind':'agent','score':<S>,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'intent':'<intent>','status':'sandbox'});p.write_text(json.dumps(d,indent=2))"
   ```

10. **Print summary.** slug, kind, score, sandbox path, and `/tq-forge-promote <slug>`.

## Pitfalls

- An agent missing any of the 5 files fails dry-test. Don't ship 4-of-5 — write
  the missing file (even a stub) and re-run.
- If `system-prompt.md` has neither the `{{CONTEXT}}` substitution nor a
  `## Domain context` section, scoring drops `completeness`. Always inject
  `context.md`.
- `tools.json` must be valid JSON with `tools` and `hand_off_to` keys. A
  trailing comma breaks dry-test.
- If `context.md` is still the placeholder, the agent will be generic. Tell the
  user to fill in `$TQ_FORGE_HOME/context.md` first.

## Verification

- `$SANDBOX_AGENTS/<slug>/` contains all 5 files.
- `dry-test.sh` returns verdict `pass` (>=85% checks).
- `quality-score.sh` reports avg >=7.
- `skill-log.json` has a new entry with `kind: agent, status: sandbox`.

## Tags

`tq-forge` `force-agent` `sandbox` `agent-factory`
