---
name: handoff
description: Write a HANDOFF.md that lets a fresh chat continue this work with a small context. Use when asked for "/handoff", when the session is long or slow, or when the handoff mod reports that the chat passed 250,000 tokens.
allowed-tools:
  - Bash
  - Read
  - Edit
---

# /handoff

## When to use

Run this when a session has grown large enough that every turn is expensive, or when the user wants to stop and pick the work up later. The mod builds the factual part from the transcript (what was asked, which files were read and changed, which skills and URLs were used); you add the part only you know, which is the state of the work.

## Procedure

1. Build the skeleton from the transcript:

```bash
M="$HOME/.claude/hooks/tq-forge/mods.py"; [ -f "$M" ] || M=".claude/hooks/tq-forge/mods.py"
python3 "$M" handoff --cwd "$PWD"
```

2. Read `.claude/HANDOFF.md`. Check the Goal and the file lists against what actually happened, and fix anything wrong.
3. Replace the placeholder under "State of the work" with: what is finished and verified, what is not finished, each decision and the reason for it, and the next three steps in order.
4. Add anything a new chat could not rediscover from the files: a failing command and its error, a constraint the user gave, a path that looks wrong but is right.
5. Tell the user the file is ready and that they can start a new chat with: "Read .claude/HANDOFF.md and continue."

## Pitfalls

- Write what is true now, not what was planned. A step that was not verified is not finished.
- Do not paste file contents into the handoff. Point to the file and the line.
- The skeleton lists every file that was read. Remove the ones that turned out not to matter.

## Verification

- `.claude/HANDOFF.md` has no placeholder text left.
- Someone who reads only that file could name the next step.

## Tags

handoff, context, session, mods
