---
name: savings
description: Show how many tokens and dollars each tq-forge mod has saved. Use when asked for "/savings", "what did the mods save", "token savings", or "is the input router worth it".
allowed-tools:
  - Bash
---

# /savings

## When to use

Run this when the user wants to see what the tq-forge mods have done so far: tokens kept out of the conversation by the input router and the screenshot shrinker, subagent runs that were routed to a cheaper model, effort recommendations, and warm versus cold cache turns. It reads one local file and changes nothing.

## Procedure

1. Print the dashboard:

```bash
M="$HOME/.claude/hooks/tq-forge/mods.py"; [ -f "$M" ] || M=".claude/hooks/tq-forge/mods.py"
python3 "$M" savings
```

2. Show the table to the user as it is. Do not round the numbers or add rows.
3. Say which figures are estimates: tokens are characters divided by four, image tokens are pixels divided by 750, and dollars use list prices.
4. If a mod shows zero events, say it has not fired yet. That is different from saving nothing.

## Pitfalls

- The Effort Optimizer row counts recommendations. A hook cannot change effort, so it saves tokens only when the user follows one.
- The Context Optimizer row is what `optimize --apply` runs took off every turn. It is a per-turn figure, not a running total, so it is left out of the Total line. `restore` does not reset it.
- The Input Router figure for a routed file assumes the file was handed to the reader subagent. If it was read in ranges instead, the real saving is smaller.

## Verification

- The command exits 0 and prints seven rows plus a total.
- The raw data is in `~/.claude/tq-forge-savings.json` if the user wants to check an event.

## Tags

savings, tokens, mods, dashboard
