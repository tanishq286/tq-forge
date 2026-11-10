#!/usr/bin/env bash
# quality-score.sh — score a forged skill, agent, or subagent on structural quality.
#
# Headline score is 0-100:  round(mean(dimensions) * 10 - lint penalties).
# `average` (0-10) is the same number / 10 and feeds the >= 7 promote gate.
#
# Skills (4 dims, 1-10 each):
#   clarity        — when-to-use is concrete and <=4 sentences
#   actionability  — procedure has numbered steps with copy-pasteable commands
#   completeness   — pitfalls + verification + tags sections present
#   specificity    — references real paths/tools/files (not "do the thing")
#
# 5-file agents (6 dims): the 4 above + consistency + handoff_clarity.
#
# Claude Code subagents (.claude/agents/<name>.md, 5 dims):
#   clarity, actionability, completeness, specificity, consistency
#
# Model-compat lint (scripts/lib/model_lint.py) subtracts points for
# instructions the target model rejects or handles badly. The target is the
# artifact's `model:` frontmatter, --model, or the default profile.
#
# Usage:
#   quality-score.sh <path>                 -> pretty score
#   quality-score.sh --json <path>          -> machine-readable
#   quality-score.sh --model <id> <path>    -> lint against this model
#   quality-score.sh --auto-detect <slug>   -> finds it in sandbox or production

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh disable=SC1091
source "$HERE/common.sh"

JSON_OUT=false
AUTO_DETECT=false
TARGET=""
MODEL=""

while (( $# )); do
    case "${1:-}" in
        --json) JSON_OUT=true; shift ;;
        --auto-detect) AUTO_DETECT=true; shift ;;
        --model)
            [[ $# -ge 2 ]] || { echo "quality-score: --model needs a value" >&2; exit 2; }
            MODEL="$2"; shift 2 ;;
        *) TARGET="$1"; shift ;;
    esac
done

if [[ -z "$TARGET" ]]; then
    echo "usage: quality-score.sh [--json] [--model <id>] [--auto-detect] <path-or-slug>" >&2
    exit 2
fi

if $AUTO_DETECT; then
    if RESOLVED="$(tq_resolve "$TARGET")"; then TARGET="$RESOLVED"; fi
fi

if [[ ! -d "$TARGET" && ! -f "$TARGET" ]]; then
    echo "quality-score: not found: $TARGET" >&2
    exit 1
fi

PYTHONDONTWRITEBYTECODE=1 exec python3 "$HERE/lib/score.py" "$TARGET" "$JSON_OUT" "$MODEL"
