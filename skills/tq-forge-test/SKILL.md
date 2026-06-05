---
name: tq-forge-test
description: |
  Re-run dry-test + quality-score on an existing forged skill or agent without
  rewriting it. Useful after a manual edit, or to verify a flagged
  "needs_manual_review" item now passes. Use when asked for "/tq-forge-test",
  "re-test the skill", "score it again", or "is this still passing".
allowed-tools:
  - Bash
  - Read
---

# /tq-forge-test — re-validate without rewriting

## When to use

You manually edited a sandbox or production artifact and want to confirm it
still passes. Or `forge-queue.json` has a slug in `needs_manual_review` and you
want to know if today's edit cleared the bar. This skill never rewrites the
artifact — only the score.

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
S="$CLAUDE_PLUGIN_ROOT/scripts"
source "$S/common.sh" && tq_ensure_home
```

1. **Resolve the target.** Accept a slug or a full path. With a slug,
   auto-detect across sandbox + production:
   ```bash
   bash "$S/quality-score.sh" --auto-detect "<slug>"
   ```
   If missing everywhere, list the sandbox + production dirs and abort:
   ```bash
   ls "$SANDBOX_SKILLS" "$SANDBOX_AGENTS" "$CLAUDE_SKILLS_DIR" 2>/dev/null
   ```

2. **Run the structural dry-test** (resolve the path first via `tq_resolve`):
   ```bash
   P="$(tq_resolve "<slug>")"; bash "$S/dry-test.sh" --json "$P"
   ```
   Capture verdict (`pass`/`warn`/`fail`), checks_passed, and `issues`.

3. **Run quality-score.**
   ```bash
   bash "$S/quality-score.sh" --json "$P"
   ```
   Capture avg and per-dimension breakdown.

4. **Print a combined report.** Two-line header, then the per-dimension bars,
   then any dry-test `issues` as bullets:
   ```
   <emoji> <slug> (<kind>) — quality X/10 · dry-test Y/10 (<verdict>)
   ```

5. **Update skill-log.json** with the new score (mutate only the matching entry):
   ```bash
   python3 -c "import json,datetime,pathlib,os;p=pathlib.Path(os.environ['TQ_FORGE_HOME'])/'skill-log.json';d=json.loads(p.read_text() or '[]');[e.update({'score':<new>,'last_tested':datetime.datetime.now(datetime.timezone.utc).isoformat()}) for e in d if e.get('slug')=='<slug>'];p.write_text(json.dumps(d,indent=2))"
   ```

6. **If the slug was in `needs_manual_review` and avg >= 7, remove it:**
   ```bash
   python3 -c "import json,pathlib,os;p=pathlib.Path(os.environ['TQ_FORGE_HOME'])/'forge-queue.json';q=json.loads(p.read_text());q['needs_manual_review']=[x for x in q.get('needs_manual_review',[]) if x.get('slug')!='<slug>'];p.write_text(json.dumps(q,indent=2))"
   ```
   Print: "✅ Cleared from needs_manual_review."

7. **Suggest the next action.** avg >= 7 -> suggest `/tq-forge-promote`. avg < 7
   -> point at the lowest dimension and suggest `/tq-forge-improve <slug>`.

## Pitfalls

- Check both copies if a slug exists in sandbox and production — the production
  copy is what users actually invoke. Test both.
- A skill that scored 9 last week but 6 now usually means an edit deleted a
  section. Run `git diff` (if the dir is tracked) to spot what changed.
- `quality-score.sh` is heuristic. 7-9 is the normal pass band; a perfect 10 is
  rare. Don't chase 10 by padding word count.

## Verification

- Both subcommands exit 0 on success and non-zero on parse error — surface the
  exit code.
- `skill-log.json` has an updated `last_tested` for the slug.
- If the artifact was on `needs_manual_review` and now passes, that list is
  shorter by one.

## Tags

`tq-forge` `test` `re-score` `read-only`
