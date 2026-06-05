---
name: tq-forge-queue
description: |
  Show queued forge work — intents deferred while the halt flag was set, plus
  items flagged "needs_manual_review" because their score stayed below 7 after a
  refine attempt. Lets you remove, reorder, or run the next item. Use when asked
  for "/tq-forge-queue", "what's queued", "show pending forges", or "process the
  queue".
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
---

# /tq-forge-queue — view + manage deferred forge work

## When to use

`/tq-forge` and `/tq-forge-skill` queue the requested intent (instead of running
it) when `$TQ_FORGE_HOME/halt.flag` is set, and flag artifacts as
`needs_manual_review` when scoring stays <7. This skill is the cockpit for both:
inspect what's pending, drop entries you don't want, and run the next one when
you're ready.

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
S="${CLAUDE_PLUGIN_ROOT:-${TQ_FORGE_HOME:-$HOME/.tq-forge}/install}/scripts"
source "$S/common.sh" && tq_ensure_home
```

1. **Render both lists.**
   ```bash
   bash "$S/forge-checkpoint.sh" status
   ```
   Two arrays matter: `queue` (intents waiting to run) and `needs_manual_review`
   (slugs scored <7).

2. **Ask the user what to do next** via AskUserQuestion:
   - **Run next** — pop item #1 and process it via the `/tq-forge` procedure.
   - **Run all** — loop through every queued intent. Stop if the halt flag
     re-appears.
   - **Drop one** — prompt for the index, remove it.
   - **Clear queue** — drop all `queue` entries (keeps `needs_manual_review`).
   - **Open review** — for a `needs_manual_review` slug, print its sandbox path
     so the user can edit by hand, then `/tq-forge-test` it.

3. **Run next** pops atomically:
   ```bash
   INTENT="$(bash "$S/forge-checkpoint.sh" pop)"
   test -n "$INTENT" && echo "Processing: $INTENT"   # then follow /tq-forge
   ```

4. **Run all** loops, checking the halt flag each iteration:
   ```bash
   while INTENT="$(bash "$S/forge-checkpoint.sh" pop)"; [ -n "$INTENT" ]; do
     test -f "$TQ_FORGE_HOME/halt.flag" && echo "⏸  halt set — stopping." && break
     echo "Processing: $INTENT"   # follow /tq-forge for each
   done
   ```

5. **Drop / clear** mutate the queue file safely (read-modify-write):
   ```bash
   python3 -c "import json,pathlib,os;p=pathlib.Path(os.environ['TQ_FORGE_HOME'])/'forge-queue.json';q=json.loads(p.read_text());q['queue'].pop(<idx>);p.write_text(json.dumps(q,indent=2))"
   ```

## Pitfalls

- `forge-queue.json` is the source of truth for deferred work. Don't overwrite
  it blank — always read-modify-write.
- Older entries may be bare strings; newer ones are `{intent, at}` dicts. Handle
  both shapes when displaying.
- "Run all" without checking the halt flag re-arms the problem the queue solved.
  Check it every iteration.

## Verification

- After running an item, the queue length decreased by exactly one (`pop`
  removes it).
- `forge-queue.json` is still valid JSON:
  `python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$TQ_FORGE_HOME/forge-queue.json"`.

## Tags

`tq-forge` `queue` `pending` `manage`
