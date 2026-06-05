---
name: tq-forge-skill
description: |
  Force-skill mode — bypass /tq-forge's auto-classification and scaffold a
  skill directly. Same sandbox + scoring + log path. Use when asked for
  "/tq-forge-skill", "make a skill that...", "scaffold a skill", or when
  /tq-forge classified something as an agent but you wanted a skill.
allowed-tools:
  - Bash
  - Read
  - Write
  - AskUserQuestion
---

# /tq-forge-skill — force-skill scaffold

## When to use

You know you want a skill (a one-shot procedure callable as `/<name>`), not an
agent. Either /tq-forge classified the intent ambiguously, or you're skipping
the classifier entirely.

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
S="${CLAUDE_PLUGIN_ROOT:-${TQ_FORGE_HOME:-$HOME/.tq-forge}/install}/scripts"
source "$S/common.sh" && tq_ensure_home
```

1. **Check the halt flag.** If `$TQ_FORGE_HOME/halt.flag` exists, queue the
   intent and exit:
   ```bash
   test -f "$TQ_FORGE_HOME/halt.flag" && bash "$S/forge-checkpoint.sh" queue "<intent>" && exit 0
   ```

2. **Pick a slug.** Lowercase, hyphenated, <=32 chars. Use an explicit slug if
   the user gave one; else derive it. Confirm if ambiguous.

3. **Check for collisions.**
   ```bash
   for d in "$CLAUDE_SKILLS_DIR/<slug>" "$SANDBOX_SKILLS/<slug>"; do
     test -e "$d" && echo "EXISTS: $d"
   done
   ```
   On a collision, ask: fork (`<slug>-v2`), edit the existing one, or abort.

4. **Create the directory.**
   ```bash
   mkdir -p "$SANDBOX_SKILLS/<slug>"
   ```

5. **Compose the SKILL.md** using `${CLAUDE_PLUGIN_ROOT:-${TQ_FORGE_HOME:-$HOME/.tq-forge}/install}/templates/SKILL.md.tmpl`
   as the shape: frontmatter (`name`, `description` with "Use when…",
   `allowed-tools`), `## When to use` (2-3 sentences), `## Procedure`
   (numbered, copy-pasteable commands), `## Pitfalls` (real ones),
   `## Verification`, `## Tags`. Target 200-800 words.

6. **Write it.** Use the Write tool. Path: `$SANDBOX_SKILLS/<slug>/SKILL.md`.

7. **Score it.**
   ```bash
   bash "$S/quality-score.sh" "$SANDBOX_SKILLS/<slug>"
   bash "$S/dry-test.sh" "$SANDBOX_SKILLS/<slug>"
   ```

8. **If quality score < 7**, identify the weakest dimension from the per-dim
   output, rewrite just that section, write again, re-score. ONE refine
   attempt. If still <7:
   ```bash
   bash "$S/forge-checkpoint.sh" review "<slug>" "<weak-dim>" "<score>"
   ```

9. **Append to skill-log.json.**
   ```bash
   python3 -c "import json,datetime,pathlib,os;p=pathlib.Path(os.environ['TQ_FORGE_HOME'])/'skill-log.json';d=json.loads(p.read_text() or '[]');d.append({'slug':'<slug>','kind':'skill','score':<S>,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'intent':'<intent>','status':'sandbox'});p.write_text(json.dumps(d,indent=2))"
   ```

10. **Print summary.** slug, score, sandbox path, exact promote command.

## Pitfalls

- The slug must be unique across BOTH sandbox AND production. Don't shadow a
  live skill — it breaks naming when promoted.
- Don't write SKILL.md anywhere outside the sandbox. `/tq-forge-promote` is the
  only path that writes into `$CLAUDE_SKILLS_DIR`.
- If `allowed-tools` lists a tool the host doesn't grant, the skill silently
  fails when invoked. Pick from tools you know are available.

## Verification

- `$SANDBOX_SKILLS/<slug>/SKILL.md` exists, >=200 words.
- Quality score printed, >=7 (or flagged for review).
- `skill-log.json` has a new entry with `kind: skill, status: sandbox`.

## Tags

`tq-forge` `force-skill` `sandbox`
