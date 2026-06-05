---
name: tq-forge-resume
description: |
  Resume forge work after a pause: clear the halt flag (with confirmation) and
  drain any queued intents. Use when asked for "/tq-forge-resume", "resume
  forge", "process the forge queue", or "unpause the forge".
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
---

# /tq-forge-resume — pick up where you left off

## When to use

Either:
1. You paused forge work with `$TQ_FORGE_HOME/halt.flag` and want to clear it.
2. Intents piled up in the queue while forge was paused and you want to drain
   them now.

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
S="${CLAUDE_PLUGIN_ROOT:-${TQ_FORGE_HOME:-$HOME/.tq-forge}/install}/scripts"
source "$S/common.sh" && tq_ensure_home
```

1. **Inspect current state.**
   ```bash
   bash "$S/forge-checkpoint.sh" status
   test -f "$TQ_FORGE_HOME/halt.flag" && echo "⏸  halt set: $(cat "$TQ_FORGE_HOME/halt.flag")" || echo "▶  no halt"
   ```

2. **If the halt flag is set**, ask the user via AskUserQuestion: "Clear the
   halt flag and resume?" Options: "Clear and resume", "Keep paused".
   - On "Clear and resume":
     ```bash
     rm -f "$TQ_FORGE_HOME/halt.flag"
     echo "▶  Resumed."
     ```

3. **Drain the queue.** If `queue` is non-empty, list each intent and ask
   "Process the queue now?" via AskUserQuestion. On yes, loop:
   ```bash
   while INTENT="$(bash "$S/forge-checkpoint.sh" pop)"; [ -n "$INTENT" ]; do
     test -f "$TQ_FORGE_HOME/halt.flag" && echo "⏸  halt re-set — stopping." && break
     echo "Processing: $INTENT"   # then follow the /tq-forge procedure for each
   done
   ```
   For each popped intent, run the full `/tq-forge` flow (classify -> scaffold ->
   score -> log).

4. **On completion**, print what was processed and the remaining queue depth:
   ```bash
   bash "$S/forge-checkpoint.sh" status
   ```

5. **If nothing is pending**, print `🎉 Nothing queued — forge is up to date.`

## Pitfalls

- Don't clear the halt flag silently. Always confirm — the flag exists precisely
  to make a deliberate pause deliberate to undo.
- If a previous session left a partial sandbox artifact (truncated SKILL.md),
  delete it and re-forge fresh rather than trying to patch it.
- Re-check the halt flag inside the drain loop. A long batch can trip a new
  pause; honor it.

## Verification

- `forge-checkpoint.sh status` shows `0 pending` after a full drain.
- `$TQ_FORGE_HOME/halt.flag` no longer exists if the user chose to resume.
- Each processed intent produced a new entry in `skill-log.json`.

## Tags

`tq-forge` `resume` `queue`
