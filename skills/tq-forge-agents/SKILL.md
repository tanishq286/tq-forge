---
name: tq-forge-agents
description: |
  List every forged agent across the sandbox and production with kind, current
  quality score, hand_off_to wiring, and a one-line capability summary.
  Read-only. Use when asked for "/tq-forge-agents", "show agents", "list my
  agents", or "what does this agent do".
allowed-tools:
  - Bash
  - Read
---

# /tq-forge-agents — agent registry view

## When to use

You want a snapshot of every forged agent — sandbox + promoted — with its kind
(researcher / coder / etc.), current quality score, the agents it can hand off
to, and a one-line capability summary from `AGENT.md`. This is the agent-only
counterpart of `/tq-forge-list`, which mixes skills + agents.

## Procedure

```bash
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
source "$CLAUDE_PLUGIN_ROOT/scripts/common.sh" && tq_ensure_home
```

1. **Enumerate agent directories.**
   ```bash
   find "$SANDBOX_AGENTS" "$CLAUDE_SKILLS_DIR/agents" -maxdepth 2 -name AGENT.md 2>/dev/null
   ```

2. **For each agent, read metadata** — yaml + json in one pass:
   ```bash
   python3 - <<'PY'
   import json, re, pathlib, os
   roots = [pathlib.Path(os.environ['SANDBOX_AGENTS']),
            pathlib.Path(os.environ['CLAUDE_SKILLS_DIR'])/'agents']
   for r in roots:
       if not r.exists(): continue
       for d in sorted(p for p in r.iterdir() if p.is_dir()):
           agm, tj = d/'AGENT.md', d/'tools.json'
           if not agm.exists(): continue
           text = agm.read_text(errors='replace')
           kind = (re.search(r'kind:\s*(\S+)', text) or [None,'?'])[1]
           tools = hand = []
           if tj.exists():
               try:
                   j = json.loads(tj.read_text())
                   tools, hand = j.get('tools',[]), j.get('hand_off_to',[])
               except Exception: pass
           loc = 'sandbox' if str(d).startswith(os.environ['SANDBOX_AGENTS']) else 'promoted'
           names = [h if isinstance(h,str) else h.get('name','?') for h in hand]
           print(f"{d.name}\t{kind}\t{loc}\t{len(tools)}\t{','.join(names) or '-'}")
   PY
   ```

3. **Pull current scores** for each agent slug from `skill-log.json`:
   ```bash
   python3 -c "import json,pathlib,os;d=json.loads((pathlib.Path(os.environ['TQ_FORGE_HOME'])/'skill-log.json').read_text() or '[]');print(json.dumps({e['slug']:e.get('score') for e in d if e.get('kind')=='agent'}))"
   ```

4. **Render the table.**
   ```
   AGENT               KIND        LOC       SCORE  TOOLS  HAND-OFF
   market-research     researcher  promoted  🟢 8.7    3    business-analyst, reviewer
   inbox-triage        ops-manager sandbox   🟡 6.5    3    coder
   ```
   Color: 🟢 >= 8, 🟡 >= 6, 🔴 < 6. Show "—" if score missing.

5. **Print a totals footer.**
   ```
   <N> agents · <S> sandbox · <P> promoted · avg score <X.X>/10
   ```

6. **Suggest follow-ups** only when applicable: sandbox agents >=7 ->
   `/tq-forge-promote`; promoted agents <7 -> `/tq-forge-improve`; none found ->
   `/tq-forge-agent <intent>`.

## Pitfalls

- An agent with missing or malformed `AGENT.md` yaml trips the parser. Skip it
  with a warning rather than aborting the listing.
- `hand_off_to` may be a list of strings or objects (`[{"name":...,"when":...}]`).
  Show the `name` field if it's an object.
- This view reads only forged agents under the two known roots — it won't show
  unrelated subagents the host may have.

## Verification

- The table has one row per `AGENT.md` found under the two roots.
- Total count matches `find ... -name AGENT.md | wc -l`.

## Tags

`tq-forge` `agents` `registry` `read-only`
