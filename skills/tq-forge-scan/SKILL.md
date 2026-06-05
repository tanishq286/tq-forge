---
name: tq-forge-scan
description: |
  Scan every installed skill and detect coverage gaps — workflows you keep
  doing by hand that don't have a skill yet. Builds a coverage map from skill
  descriptions and recommends forge candidates. Use when asked for
  "/tq-forge-scan", "find skill gaps", "what's missing", or "scan for forge
  candidates".
allowed-tools:
  - Bash
  - Read
---

# /tq-forge-scan — gap detection across the skill library

## When to use

You suspect there's a workflow you've re-done by hand several times that should
have been forged already. Or you want a coverage report before a forge spree.

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
source "$CLAUDE_PLUGIN_ROOT/scripts/common.sh" && tq_ensure_home
```

1. **Enumerate every installed skill.**
   ```bash
   ls "$CLAUDE_SKILLS_DIR" 2>/dev/null
   find "$HOME/.claude/plugins" -maxdepth 4 -name SKILL.md 2>/dev/null | head -100
   ls "$SANDBOX_SKILLS" "$SANDBOX_AGENTS" 2>/dev/null
   ```

2. **Read each skill's `description:` frontmatter** to build a coverage map:
   ```bash
   for d in "$CLAUDE_SKILLS_DIR"/*/; do
     name=$(basename "$d")
     desc=$(awk '/^description:/{flag=1;next} /^[a-z-]+:/{flag=0} flag' "$d/SKILL.md" 2>/dev/null | head -3)
     echo "$name | $desc"
   done
   ```
   Group what's covered into categories (browser, design, security, deployment,
   research, ops, data, communication, etc.).

3. **Gather candidate gaps.** Ask the user what repetitive workflows they've
   been doing by hand lately, or skim recent session history if available. Each
   recurring manual task with no matching skill is a candidate.

4. **For each candidate, classify:**
   - **Already covered** — a skill exists with a matching description. Drop.
   - **Partially covered** — exists but the description is mismatched. Suggest
     `/tq-forge-improve <existing>`.
   - **Real gap** — no skill matches. Suggest `/tq-forge "<intent>"`.

5. **Render a gap report:**
   ```
   🔍 tq-forge-scan — coverage report
    Installed:  <N> skills, <M> agents
    Forgeable:  <K> sandbox + <P> promoted
    ───────────────────────────────────────────
    🟢 Covered:        browser-test, ship, design-audit, ...
    🟡 Partial:        notion-summary (description vague)
    🔴 Gap candidates:
       1. weekly-metrics-digest
       2. invoice-reconcile
   ```

## Pitfalls

- The scan is heuristic — it matches descriptions textually, so a skill with a
  poorly-written `description:` can look like a gap even when it covers the case.
  When unsure, ask before recommending a forge.
- Plugin-provided skills (under `~/.claude/plugins`) are usually not yours to
  edit — list them as covered/reference, not as improve candidates.

## Verification

- The "Installed" count is in the same ballpark as
  `find "$CLAUDE_SKILLS_DIR" -name SKILL.md | wc -l` plus plugin skills.
- Each gap candidate is a workflow with no matching installed skill description.

## Tags

`tq-forge` `scan` `gap-detection` `read-only`
