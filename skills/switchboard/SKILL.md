---
name: switchboard
description: Turn a tq-forge mod on or off, or switch the input router's reader between haiku and sonnet. Use when asked for "/switchboard", "turn off the input router", "disable the screenshot shrinker", or "use sonnet for reading".
allowed-tools:
  - Bash
---

# /switchboard

## When to use

Run this when the user wants to change how a mod behaves without editing files: switch one mod off because it gets in the way, switch it back on, or make the input router hand large files to Sonnet instead of Haiku. Changes are stored in `~/.claude/tq-forge-mods.json` and take effect on the next hook call, with no restart.

## Procedure

1. Show the current state first:

```bash
M="$HOME/.claude/hooks/tq-forge/mods.py"; [ -f "$M" ] || M=".claude/hooks/tq-forge/mods.py"
python3 "$M" status
```

2. Apply the one change the user asked for. The mods are `input-router`, `effort-optimizer`, `subagent-model-selector`, `cache-clock`, `handoff` and `efficient-browser-use`:

```bash
python3 "$M" toggle input-router sonnet
python3 "$M" toggle efficient-browser-use off
```

3. Run `status` again and show the user the new state.

## Pitfalls

- `haiku` and `sonnet` are accepted only for `input-router`. Every other mod takes `on` or `off`.
- Turning `efficient-browser-use` off restores full-size screenshots, which cost about four times as many image tokens. Do that when small text in a screenshot must be read.
- Turning `subagent-model-selector` off means every subagent without its own model runs on the session model again.
- Do not edit `settings.json` to disable a mod. The toggle leaves the hook in place and makes it do nothing, which is easier to undo.

## Verification

- `status` shows the mod with the new value.
- `~/.claude/tq-forge-mods.json` holds the change.

## Tags

switchboard, mods, toggle, settings
