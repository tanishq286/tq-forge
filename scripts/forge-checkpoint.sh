#!/usr/bin/env bash
# forge-checkpoint.sh — manage the deferred forge-work queue.
#
# Usage:
#   forge-checkpoint.sh status                 -> pretty queue summary
#   forge-checkpoint.sh queue <intent...>      -> push an intent to the queue
#   forge-checkpoint.sh review <slug> <dim> <score>  -> push to needs_manual_review
#   forge-checkpoint.sh pop                    -> print + remove queue item #1
#   forge-checkpoint.sh raw                    -> dump queue JSON
#
# All writes are atomic (write .tmp, mv into place).

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$HERE/common.sh"
tq_ensure_home

CMD="${1:-status}"; shift || true

python3 - "$FORGE_QUEUE" "$CMD" "$@" <<'PYEOF'
import sys, json, datetime, pathlib
qp  = pathlib.Path(sys.argv[1])
cmd = sys.argv[2] if len(sys.argv) > 2 else "status"
args = sys.argv[3:]

q = json.loads(qp.read_text() or '{"queue":[],"needs_manual_review":[]}')
q.setdefault("queue", []); q.setdefault("needs_manual_review", [])
now = datetime.datetime.now(datetime.timezone.utc).isoformat()

def save():
    tmp = qp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(q, indent=2))
    tmp.replace(qp)

if cmd == "status":
    print(f"📥 queue: {len(q['queue'])} pending  ·  🩹 needs_manual_review: {len(q['needs_manual_review'])}")
    for i, it in enumerate(q["queue"], 1):
        intent = it if isinstance(it, str) else it.get("intent", "?")
        print(f"   {i}. {intent}")
    for it in q["needs_manual_review"]:
        print(f"   - {it.get('slug','?')}  weak:{it.get('weak_dimension','?')} ({it.get('score','?')}/10)")
elif cmd == "queue":
    if not args: sys.exit("usage: queue <intent>")
    q["queue"].append({"intent": " ".join(args), "at": now})
    save(); print(f"📥 queued: {' '.join(args)}")
elif cmd == "review":
    if len(args) < 3: sys.exit("usage: review <slug> <dim> <score>")
    q["needs_manual_review"].append({"slug": args[0], "weak_dimension": args[1],
                                     "score": args[2], "at": now})
    save(); print(f"🩹 flagged for review: {args[0]}")
elif cmd == "pop":
    if not q["queue"]:
        print(""); sys.exit(0)
    it = q["queue"].pop(0)
    save()
    print(it if isinstance(it, str) else it.get("intent", ""))
elif cmd == "raw":
    print(json.dumps(q, indent=2))
else:
    print(f"unknown subcommand: {cmd}", file=sys.stderr); sys.exit(2)
PYEOF
