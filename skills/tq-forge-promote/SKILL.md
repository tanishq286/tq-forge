---
name: tq-forge-promote
description: |
  Promote a sandboxed forged skill or agent from $TQ_FORGE_HOME/sandbox/ into
  production at $CLAUDE_SKILLS_DIR, re-scoring first and refusing anything below
  7/10 or failing dry-test. Use when asked for "/tq-forge-promote", "ship the
  skill", "install the agent", or "move from sandbox to production".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - AskUserQuestion
---

# /tq-forge-promote — sandbox -> production

## When to use

A skill or agent in `$TQ_FORGE_HOME/sandbox/forged-{skills,agents}/<slug>/` has
passed scoring (>=7) and is ready to ship. This is the only path that writes
into `$CLAUDE_SKILLS_DIR` (default `~/.claude/skills`).

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
S="${CLAUDE_PLUGIN_ROOT:-${TQ_FORGE_HOME:-$HOME/.tq-forge}/install}/scripts"
source "$S/common.sh" && tq_ensure_home
```

1. **Check the halt flag.** If `$TQ_FORGE_HOME/halt.flag` exists, queue and exit:
   ```bash
   test -f "$TQ_FORGE_HOME/halt.flag" && bash "$S/forge-checkpoint.sh" queue "promote <slug>" && exit 0
   ```

2. **Resolve the slug.**
   ```bash
   for d in "$SANDBOX_SKILLS/<slug>" "$SANDBOX_AGENTS/<slug>"; do
     test -e "$d" && echo "FOUND: $d"
   done
   ```
   If neither exists, abort and list what's available:
   ```bash
   ls "$SANDBOX_SKILLS" "$SANDBOX_AGENTS"
   ```

3. **Re-score before promoting.** Never trust a stale score:
   ```bash
   bash "$S/quality-score.sh" --auto-detect "<slug>"
   bash "$S/dry-test.sh" "$SANDBOX_SKILLS/<slug>"   # or $SANDBOX_AGENTS
   ```
   If avg < 7 OR dry-test verdict != `pass`, refuse: "Score is X/10 — run
   /tq-forge-improve <slug> first."

4. **Copy into production.**
   ```bash
   # Skill
   mkdir -p "$CLAUDE_SKILLS_DIR"
   cp -r "$SANDBOX_SKILLS/<slug>" "$CLAUDE_SKILLS_DIR/<slug>"

   # Agent
   mkdir -p "$CLAUDE_SKILLS_DIR/agents"
   cp -r "$SANDBOX_AGENTS/<slug>" "$CLAUDE_SKILLS_DIR/agents/<slug>"
   ```

5. **Update skill-log.json status.**
   ```bash
   python3 -c "import json,pathlib,os;p=pathlib.Path(os.environ['TQ_FORGE_HOME'])/'skill-log.json';d=json.loads(p.read_text() or '[]');[e.update({'status':'promoted'}) for e in d if e.get('slug')=='<slug>'];p.write_text(json.dumps(d,indent=2))"
   ```

6. **Print summary.** slug, kind, final score, production path, and the
   reminder: "Restart Claude Code (or reload skills) to pick it up."

## Pitfalls

- Use `cp -r`, not `mv` — keep the sandbox copy as a rollback. Only delete the
  sandbox dir after the user confirms production works.
- A slug already present at `$CLAUDE_SKILLS_DIR/<slug>/` means a name collision
  with another skill set — refuse and ask the user to rename.
- Skills are loaded at session start; a freshly promoted skill won't be callable
  until the session reloads. Say so explicitly.

## Verification

- `$CLAUDE_SKILLS_DIR/<slug>/SKILL.md` (or `agents/<slug>/AGENT.md`) exists.
- `skill-log.json` shows `status: promoted` for the slug.
- Re-running quality-score on the production path still reports >=7.

## Tags

`tq-forge` `promote` `production`
