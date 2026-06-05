---
name: tq-forge-list
description: |
  List every forged skill and agent (sandbox + promoted) with quality scores
  color-coded green/yellow/red. Reads $TQ_FORGE_HOME/sandbox and skill-log.json.
  Use when asked for "/tq-forge-list", "show forged skills", "what's in the
  sandbox", or "which skills have I forged".
allowed-tools:
  - Bash
  - Read
---

# /tq-forge-list — inventory of forged items

## When to use

You want a quick overview of everything /tq-forge has built — what's still in
the sandbox awaiting promote, what's already live, and which scored low enough
to need a refresh.

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
S="${CLAUDE_PLUGIN_ROOT:-${TQ_FORGE_HOME:-$HOME/.tq-forge}/install}/scripts"
source "$S/common.sh" && tq_ensure_home
```

1. **Read the skill log.**
   ```bash
   cat "$TQ_FORGE_HOME/skill-log.json"
   ```
   Each entry has `{slug, kind, score, at, intent, status}`. `status` is one of
   `sandbox`, `promoted`, `needs_manual_review`.

2. **Walk the sandbox.**
   ```bash
   ls -1 "$SANDBOX_SKILLS" 2>/dev/null
   ls -1 "$SANDBOX_AGENTS" 2>/dev/null
   ```
   A directory in the sandbox but not in skill-log.json is an orphan — include
   it with score `?` and a flag.

3. **Walk promoted items.**
   ```bash
   ls -1 "$CLAUDE_SKILLS_DIR/agents" 2>/dev/null
   ```
   Plus any slug from skill-log.json with `status: promoted`.

4. **Render two tables — Skills first, Agents second:**
   ```
   📚 SKILLS (sandbox: <N>, promoted: <M>)
   Slug                    Score   Status     Forged
   notion-daily-summary    🟢 8.5  promoted   2d ago
   inventory-snapshot      🟡 6.8  sandbox    1h ago

   🤖 AGENTS (sandbox: <N>, promoted: <M>)
   Slug                Kind        Score   Status
   market-research     researcher  🟢 8.9  promoted
   ```

5. **Color code by score:** 🟢 >= 8.0, 🟡 6.0-7.9, 🔴 < 6.0.

6. **Footer line** with quick commands:
   ```
   Promote: /tq-forge-promote <slug>   Improve: /tq-forge-improve <slug>   Test: /tq-forge-test <slug>
   ```

## Pitfalls

- Entries with `score: null` are pending a score. Show them but flag with `?`.
- The orphan check (sandbox dir with no log entry) catches manually-created
  scaffolds. Treat as `?`, suggest `/tq-forge-test` to score them.
- Don't list pre-existing skills from `$CLAUDE_SKILLS_DIR` that tq-forge didn't
  create — only show items present in skill-log.json or the sandbox.

## Verification

- The two header counts (sandbox + promoted) equal `ls | wc -l` of the
  corresponding directories.

## Tags

`tq-forge` `inventory` `read-only`
