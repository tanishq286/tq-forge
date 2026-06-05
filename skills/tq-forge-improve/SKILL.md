---
name: tq-forge-improve
description: |
  Re-score a forged skill or agent, identify weak dimensions, rewrite only
  those sections, then verify the score improved to >=7. One targeted pass;
  if still <7 after the rewrite, flags it for manual review. Use when asked for
  "/tq-forge-improve", "improve a skill", "fix a weak skill", or "this skill
  scored low".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# /tq-forge-improve — targeted rewrite of low-scoring sections

## When to use

A forged skill or agent scored <7 and you want to fix it without rewriting the
whole artifact. Give it a slug (e.g. `notion-daily-summary`) or an absolute
path; the skill identifies which dimensions are pulling the score down,
rewrites only those sections, then verifies.

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
S="$CLAUDE_PLUGIN_ROOT/scripts"
source "$S/common.sh" && tq_ensure_home
```

1. **Assess the artifact.**
   ```bash
   bash "$S/improve-loop.sh" assess "<slug>"
   ```
   This prints per-dimension scores, highlights weak dims (<7), and gives a
   coaching hint for each. Capture which sections need work.

2. **Read the current content.** Read the SKILL.md (or AGENT.md +
   system-prompt.md) at the path `assess` printed. Understand what each weak
   section currently says.

3. **Rewrite only the weak sections:**

   | Dimension | Section to rewrite |
   |-----------|--------------------|
   | `clarity` | `## When to use` — <=3 sentences, concrete trigger |
   | `actionability` | `## Procedure` — add copy-pasteable commands |
   | `completeness` | Add missing section(s): Pitfalls / Verification / Tags |
   | `specificity` | Replace vague language with real paths / tool names |
   | `consistency` | Define the output-format schema once, up top (agents) |
   | `handoff_clarity` | `hand_off_to` in `tools.json` — add a `when:` per entry |

   Use `Edit` for targeted swaps; use `Write` only if the file is malformed.
   Preserve every section you are NOT rewriting, verbatim.

4. **Verify the improvement.**
   ```bash
   bash "$S/improve-loop.sh" verify "<slug>"
   ```
   This re-scores, prints before/after, and updates `skill-log.json`.

5. **Branch on the result.**
   - **avg >=7**: print `✅ <slug> now scores X/10. Ready to promote.` Suggest
     `/tq-forge-promote <slug>` if it's still in the sandbox.
   - **avg <7**: print the remaining weak dims and flag it:
     ```bash
     bash "$S/forge-checkpoint.sh" review "<slug>" "<weak-dim>" "<score>"
     ```

## Pitfalls

- Only rewrite weak sections. Editing a strong section risks dropping its score
  while raising the weak one. Target precisely.
- `assess` auto-detects sandbox and production paths. If the slug exists in
  both, it prefers the sandbox copy — improve there, then re-promote.
- Agents have 6 scoring dimensions vs 4 for skills; `handoff_clarity` and
  `consistency` apply only to agents.
- Adding copy-pasteable bash commands often raises `actionability` 2-3 points on
  its own — try that before broader rewrites.

## Verification

- `improve-loop.sh verify <slug>` reports `passed: true` in `--json` mode.
- `skill-log.json` shows the updated `score` and a `last_tested` timestamp.
- The before score < 7 and the after score >= 7 (delta printed).

## Tags

`tq-forge` `improve` `quality` `rewrite` `single-slug`
