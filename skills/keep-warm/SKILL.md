---
name: keep-warm
description: Refresh the prompt cache for this session with one minimal turn, and report when it expires next. Use when asked for "/keep-warm", "keep the cache warm", or just before stepping away from a long session.
allowed-tools:
  - Bash
---

# /keep-warm

## When to use

Run this when the user is about to pause a long session and wants the next turn to read the conversation from the prompt cache instead of paying to write it again. Sending this command is itself the refresh: any turn in the session resets the cache clock, so the reply should be as small as possible.

## Procedure

1. Read the cache clock:

```bash
M="$HOME/.claude/hooks/tq-forge/mods.py"; [ -f "$M" ] || M=".claude/hooks/tq-forge/mods.py"
python3 "$M" keep-warm
```

2. Reply in one line with what it printed: how long the cache stays warm from now.
3. Stop. Do not summarize the session, read files, or call other tools; every extra token here is cost with no benefit.

## Pitfalls

- A refresh is not free. It reads the whole conversation from the cache once, so it pays off only if the user comes back before the next expiry.
- The cache lasts about an hour on a Claude subscription and about five minutes with an API key. On the five-minute clock, keeping a session warm through a long break costs more than letting it go cold.
- `tq-forge keep-warm --wait` in another terminal rings the bell when a refresh is due. It cannot send the turn for you; only a message in this session refreshes this session's cache.

## Verification

- The command prints the minutes left, and the status line (if it shows the cache clock) resets after this turn.

## Tags

cache, keep-warm, cost, mods
