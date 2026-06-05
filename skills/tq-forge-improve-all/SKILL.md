---
name: tq-forge-improve-all
description: |
  Scan every forged skill and agent for scores below 7, then improve each one
  in priority order (lowest first). Runs assess -> rewrite -> verify per
  artifact, stopping if the halt flag appears or the user interrupts. Use when
  asked for "/tq-forge-improve-all", "improve everything", "fix all weak
  skills", or "bulk improve".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# /tq-forge-improve-all — batch improve every sub-7 artifact

## When to use

You want a single sweep that finds every forged skill and agent scoring below 7
and fixes them in one session. Good after an initial forge spree, or after
`/tq-forge-scan` surfaces several weak entries. Each artifact gets one improve
attempt; if it still fails, it's flagged for manual review and the loop moves on.

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
S="$CLAUDE_PLUGIN_ROOT/scripts"
source "$S/common.sh" && tq_ensure_home
```

1. **Enumerate artifacts below threshold.** From the log plus any un-logged
   sandbox dirs:
   ```bash
   python3 - <<'PY'
   import json, pathlib, os
   home = pathlib.Path(os.environ['TQ_FORGE_HOME'])
   log = json.loads((home/'skill-log.json').read_text() or '[]')
   weak = [e for e in log if isinstance(e.get('score'),(int,float)) and e['score'] < 7]
   weak.sort(key=lambda e: e['score'])
   for e in weak:
       print(f"{e['slug']}\t{e['score']}\t{e.get('status','?')}")
   PY
   ```

2. **Print the improvement queue** so the user can abort if it's longer than
   expected:
   ```
   🔧 Improvement queue — <N> artifacts below 7/10
    1. notion-daily-summary    5.8/10  (weak: actionability, specificity)
    2. inventory-snapshot      6.2/10  (weak: completeness)
   ```

3. **For each artifact in order:**
   a. Check the halt flag before each item:
      ```bash
      test -f "$TQ_FORGE_HOME/halt.flag" && echo "⏸  halt.flag set — stopping batch." && exit 0
      ```
   b. Run the `/tq-forge-improve` logic inline:
      ```bash
      bash "$S/improve-loop.sh" assess "<slug>"
      ```
      Read the artifact, rewrite only the weak sections, then:
      ```bash
      bash "$S/improve-loop.sh" verify "<slug>"
      ```
   c. Print a one-line status: `✅ notion-daily-summary: 5.8 -> 8.1` or
      `⚠️ inventory-snapshot: 6.2 -> 6.5 — still weak, flagged for review`.

4. **Print the final summary.**
   ```
   📊 Improve-all complete
   Improved:   <N>  (now >=7)
   Still weak: <M>  (flagged in forge-queue.json)
   Skipped:    <K>  (halt.flag hit mid-run)
   ```

5. **If any remain in `needs_manual_review`**, print: "Run /tq-forge-queue to
   see what needs a human touch."

## Pitfalls

- An artifact scoring 6.9 on one run can score 7.1 on the next with no edit
  (scorer variance). Accept >=7.0 as passing; don't re-run needlessly.
- If an agent's `tools.json` is malformed, skip that agent with a warning rather
  than aborting the whole batch.
- Promoted artifacts under `$CLAUDE_SKILLS_DIR` are editable here — the path is
  already writable. Don't treat "promoted" as read-only.

## Verification

- `skill-log.json` `score` fields are updated for every processed artifact.
- The printed "Improved + Still weak + Skipped = N" matches the step-2 queue.
- Running the skill again immediately prints "0 artifacts below 7" if all passed.

## Tags

`tq-forge` `improve` `batch` `quality` `bulk`
