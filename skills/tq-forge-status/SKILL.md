---
name: tq-forge-status
description: |
  Show the forge state at a glance: how many skills/agents are forged, what's in
  the queue, what needs manual review, and whether the halt flag is set. Use
  when asked for "/tq-forge-status", "forge status", "what's queued", or
  "where's the forge at".
allowed-tools:
  - Bash
  - Read
---

# /tq-forge-status — forge state snapshot

## When to use

A quick "where am I" check. Three questions in one place: what have I forged,
what's queued, and is forge currently paused?

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
S="$CLAUDE_PLUGIN_ROOT/scripts"
source "$S/common.sh" && tq_ensure_home
```

1. **Inventory counts.**
   ```bash
   python3 -c "import json,pathlib,os;d=json.loads((pathlib.Path(os.environ['TQ_FORGE_HOME'])/'skill-log.json').read_text() or '[]');import collections;c=collections.Counter(e.get('status','?') for e in d);print('total',len(d),dict(c))"
   ```

2. **Queue depth.**
   ```bash
   bash "$S/forge-checkpoint.sh" status
   ```

3. **Halt status.**
   ```bash
   test -f "$TQ_FORGE_HOME/halt.flag" && echo "⏸  HALT ACTIVE — $(cat "$TQ_FORGE_HOME/halt.flag")" || echo "▶  no halt"
   ```

4. **Last forged item.**
   ```bash
   python3 -c "import json,pathlib,os;d=json.loads((pathlib.Path(os.environ['TQ_FORGE_HOME'])/'skill-log.json').read_text() or '[]');e=d[-1] if d else None;print('last:',e['slug'],e.get('kind'),'score',e.get('score'),e.get('at')) if e else print('last: (none yet)')"
   ```

5. **Render a single combined panel:**
   ```
   ═══════════════════════════════════════════════════
    tq-forge — Status
   ═══════════════════════════════════════════════════
    Forged:   <T> total   (<S> sandbox · <P> promoted · <R> needs review)
    Queue:    <Q> pending intents
    Halt:     <yes/no>
   ───────────────────────────────────────────────────
    Last forged:  <slug>  <kind>  score=<S>  <ago>
   ═══════════════════════════════════════════════════
   ```

6. **Suggest the next action** by state:
   - Queue >= 1 + no halt -> `/tq-forge-resume` to drain it
   - Halt active -> "Remove $TQ_FORGE_HOME/halt.flag to resume."
   - Items in needs_manual_review -> `/tq-forge-queue`
   - All clear -> suggest `/tq-forge "<intent>"` to forge new work

## Pitfalls

- The "last forged" line reads `skill-log.json`. If you've never run /tq-forge,
  it's an empty array — show "(none yet)" rather than erroring.
- All subcommands should exit 0. If one fails, print the failing one and
  continue — a partial status beats no status.

## Verification

- The status panel renders without a Python traceback.
- The counts shown match `skill-log.json` and `forge-queue.json`.

## Tags

`tq-forge` `status` `read-only`
