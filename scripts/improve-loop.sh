#!/usr/bin/env bash
# improve-loop.sh — score an artifact, identify weak dimensions, verify after rewrite.
#
# Phase 1 (assess):  score the artifact, print weak dimensions + coaching hints
# Phase 2 (verify):  re-score after a rewrite, compare before/after, update skill-log
#
# Usage:
#   improve-loop.sh assess  <slug-or-path>
#   improve-loop.sh verify  <slug-or-path>
#   improve-loop.sh --json assess <slug-or-path>

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh disable=SC1091
source "$HERE/common.sh"
tq_ensure_home

JSON_OUT=false
PHASE=""
TARGET=""

while (( $# )); do
    case "${1:-}" in
        --json) JSON_OUT=true; shift ;;
        assess|verify) PHASE="$1"; shift ;;
        *) TARGET="$1"; shift ;;
    esac
done

[[ -z "$PHASE"  ]] && { echo "usage: improve-loop.sh [--json] assess|verify <slug-or-path>" >&2; exit 2; }
[[ -z "$TARGET" ]] && { echo "usage: improve-loop.sh [--json] assess|verify <slug-or-path>" >&2; exit 2; }

RESOLVED="$(tq_resolve "$TARGET")" || { echo "improve-loop: not found: $TARGET" >&2; exit 1; }

python3 - "$PHASE" "$RESOLVED" "$TARGET" "$SKILL_LOG" "$JSON_OUT" "$HERE/quality-score.sh" <<'PYEOF'
import sys, json, pathlib, datetime, subprocess

phase    = sys.argv[1]
resolved = pathlib.Path(sys.argv[2])
slug     = pathlib.Path(sys.argv[3]).name
log_path = pathlib.Path(sys.argv[4])
json_out = sys.argv[5].lower() == "true"
qscore   = sys.argv[6]

score_raw = subprocess.check_output([qscore, '--json', str(resolved)],
                                    stderr=subprocess.DEVNULL).decode()
score_data = json.loads(score_raw)
avg  = score_data.get('average', 0)
dims = score_data.get('dimensions', {})

HINTS = {
    'clarity':         'Shorten "When to use" to <=3 concrete sentences; name the exact trigger.',
    'actionability':   'Add copy-pasteable bash/python commands to every Procedure step.',
    'completeness':    'Ensure all sections exist: When to use, Procedure, Pitfalls, Verification, Tags.',
    'specificity':     'Replace vague phrases ("do the thing", "the file") with real paths/tool names.',
    'consistency':     'Define output format once at the top of Procedure; repeat the schema in Verification.',
    'handoff_clarity': 'List hand_off_to names explicitly with a "when:" condition for each.',
}

weak = {k: v for k, v in dims.items() if v < 7}

if phase == 'assess':
    if json_out:
        print(json.dumps({
            'slug': slug, 'path': str(resolved), 'average': avg, 'dimensions': dims,
            'weak': weak, 'hints': {k: HINTS.get(k, '') for k in weak},
            'needs_improvement': avg < 7,
        }))
    else:
        status = '\U0001F534 needs improvement' if avg < 7 else ('\U0001F7E1 borderline' if avg < 8 else '\U0001F7E2 strong')
        print(f"\n🔍 {slug}  —  avg {avg:.1f}/10  {status}")
        print(f"   path: {resolved}\n")
        for dim, score in sorted(dims.items(), key=lambda x: x[1]):
            bar = '▓' * int(score) + '░' * (10 - int(score))
            flag = ' <- weak' if score < 7 else ''
            print(f"   {dim:<20} {bar}  {score:.0f}/10{flag}")
        if weak:
            print("\n📋 Sections to rewrite:")
            for dim in weak:
                print(f"   [{dim}]  {HINTS.get(dim, '')}")
        else:
            print("\n✅ All dimensions >=7 — no improvement needed.")

elif phase == 'verify':
    prev_score = None
    log = []
    if log_path.exists():
        try:
            log = json.loads(log_path.read_text() or '[]')
            for entry in reversed(log):
                if entry.get('slug') == slug:
                    prev_score = entry.get('score'); break
        except Exception:
            log = []

    updated = False
    for entry in log:
        if entry.get('slug') == slug:
            entry['score'] = avg
            entry['last_tested'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            updated = True; break
    if not updated:
        log.append({'slug': slug, 'score': avg,
                    'last_tested': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'path': str(resolved)})
    log_path.write_text(json.dumps(log, indent=2))

    delta = round(avg - prev_score, 1) if prev_score is not None else None

    if json_out:
        print(json.dumps({
            'slug': slug, 'path': str(resolved), 'new_score': avg,
            'prev_score': prev_score, 'delta': delta, 'dimensions': dims,
            'passed': avg >= 7,
        }))
    else:
        delta_str = (f'+{delta}' if delta and delta > 0 else str(delta)) if delta is not None else 'N/A'
        status = '✅ PASSED' if avg >= 7 else '❌ STILL BELOW 7'
        print(f"\n🔄 {slug}  —  verify result  {status}")
        print(f"   new avg:  {avg:.1f}/10")
        if prev_score is not None:
            print(f"   prev avg: {prev_score:.1f}/10   Δ = {delta_str}")
        for dim, score in sorted(dims.items(), key=lambda x: x[1]):
            print(f"   {dim:<20} {score:.0f}/10")
        print()
        print("   skill-log updated. Ready to promote or continue." if avg >= 7
              else "   ⚠️  Score still <7. Queue for manual review or try another rewrite pass.")
PYEOF
