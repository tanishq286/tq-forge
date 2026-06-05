#!/usr/bin/env bash
# quality-score.sh — score a forged skill or agent on structural quality.
#
# Skills (4 dims, 1-10 each, average):
#   clarity        — when-to-use is concrete and <=3 sentences
#   actionability  — procedure has numbered steps with copy-pasteable commands
#   completeness   — pitfalls + verification + tags sections present
#   specificity    — references real paths/tools/files (not "do the thing")
#
# Agents (6 dims, 1-10 each, average):
#   above 4 +
#   consistency    — output format defined and rigid (yaml/code-block schema)
#   handoff_clarity — hand_off_to listed with named agents + conditions
#
# Usage:
#   quality-score.sh <path>                 -> pretty score
#   quality-score.sh --json <path>          -> machine-readable
#   quality-score.sh --auto-detect <slug>   -> finds it in sandbox or production

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh disable=SC1091
source "$HERE/common.sh"

JSON_OUT=false
AUTO_DETECT=false
TARGET=""

while (( $# )); do
    case "${1:-}" in
        --json) JSON_OUT=true; shift ;;
        --auto-detect) AUTO_DETECT=true; shift ;;
        *) TARGET="$1"; shift ;;
    esac
done

if [[ -z "$TARGET" ]]; then
    echo "usage: quality-score.sh [--json] [--auto-detect] <path-or-slug>" >&2
    exit 2
fi

if $AUTO_DETECT; then
    if RESOLVED="$(tq_resolve "$TARGET")"; then TARGET="$RESOLVED"; fi
fi

if [[ ! -d "$TARGET" && ! -f "$TARGET" ]]; then
    echo "quality-score: not found: $TARGET" >&2
    exit 1
fi

python3 - "$TARGET" "$JSON_OUT" <<'PYEOF'
import sys, json, re, pathlib

target = pathlib.Path(sys.argv[1])
json_out = sys.argv[2].lower() == "true"

def score_skill(skill_path):
    text = skill_path.read_text(errors="replace")
    dims = {}

    m = re.search(r"##\s*When to use\s*\n(.+?)\n##", text, re.S | re.I)
    if m:
        body = m.group(1).strip()
        sentences = [s for s in re.split(r"[.!?]\s", body) if s.strip()]
        words = len(body.split())
        if 30 <= words <= 200 and 1 <= len(sentences) <= 4:
            dims["clarity"] = 9
        elif words < 30:
            dims["clarity"] = 5
        else:
            dims["clarity"] = 7
    else:
        dims["clarity"] = 3

    m = re.search(r"##\s*Procedure\s*\n(.+?)\n##", text, re.S | re.I)
    if m:
        body = m.group(1)
        steps = re.findall(r"^\s*\d+\.\s", body, re.M)
        code_blocks = body.count("```")
        if len(steps) >= 3 and code_blocks >= 2:
            dims["actionability"] = 9
        elif len(steps) >= 2:
            dims["actionability"] = 7
        else:
            dims["actionability"] = 5
    else:
        dims["actionability"] = 3

    has_pitfalls = bool(re.search(r"##\s*Pitfalls", text, re.I))
    has_verif    = bool(re.search(r"##\s*Verification", text, re.I))
    has_tags     = bool(re.search(r"##\s*Tags", text, re.I))
    n = sum([has_pitfalls, has_verif, has_tags])
    dims["completeness"] = {3: 9, 2: 7, 1: 5, 0: 3}[n]

    vague = re.findall(r"\b(do the thing|various|some|things|stuff|whatever)\b", text, re.I)
    real_paths = re.findall(r"~/[\.\w/-]+|/home/\w+|\$HOME|\$TQ_FORGE_HOME|\$CLAUDE_PLUGIN_ROOT", text)
    if len(vague) == 0 and len(real_paths) >= 3:
        dims["specificity"] = 9
    elif len(vague) <= 1 and len(real_paths) >= 1:
        dims["specificity"] = 7
    else:
        dims["specificity"] = 4

    avg = sum(dims.values()) / len(dims)
    return avg, dims

def score_agent(agent_dir):
    files = ["AGENT.md", "system-prompt.md", "tools.json",
             "trigger-conditions.md", "example-tasks.md"]
    missing = [f for f in files if not (agent_dir / f).exists()]
    if missing:
        return 0.0, {"_missing": missing}

    dims = {}
    sp = (agent_dir / "system-prompt.md").read_text(errors="replace")
    sp_words = len(sp.split())

    persona = re.search(r"##\s*Persona\s*\n(.+?)(\n##|\Z)", sp, re.S | re.I)
    dims["clarity"] = 9 if persona and len(persona.group(1).split()) > 50 else 5

    has_output = bool(re.search(r"##\s*Output format", sp, re.I)) and "```" in sp
    dims["actionability"] = 9 if has_output else 4

    has_never = bool(re.search(r"##\s*NEVER", sp, re.I))
    # Generic context check: token, or a Domain context section, or non-trivial injected context.
    has_ctx = ("{{CONTEXT}}" in sp) or bool(re.search(r"##\s*Domain context", sp, re.I))
    if 500 <= sp_words <= 1500 and has_never and has_ctx:
        dims["completeness"] = 9
    elif has_never and has_ctx:
        dims["completeness"] = 7
    else:
        dims["completeness"] = 5

    real_field_count = len(re.findall(r"^\s*-\s*\w+:", sp, re.M))
    dims["specificity"] = 9 if real_field_count >= 5 else 7 if real_field_count >= 2 else 4

    yaml_blocks = sp.count("```yaml")
    code_blocks = sp.count("```")
    dims["consistency"] = 9 if (yaml_blocks >= 1 or code_blocks >= 4) else 5

    try:
        tj = json.loads((agent_dir / "tools.json").read_text())
        ho = tj.get("hand_off_to", [])
        dims["handoff_clarity"] = 9 if len(ho) >= 1 else 4
    except Exception:
        dims["handoff_clarity"] = 3

    avg = sum(dims.values()) / len(dims)
    return avg, dims

if target.is_file() and target.name == "SKILL.md":
    skill_path = target
elif target.is_dir() and (target / "SKILL.md").exists():
    skill_path = target / "SKILL.md"
elif target.is_dir() and (target / "AGENT.md").exists():
    avg, dims = score_agent(target); kind = "agent"; skill_path = None
else:
    print(f"quality-score: don't recognize target shape at {target}", file=sys.stderr)
    sys.exit(1)

if skill_path:
    avg, dims = score_skill(skill_path); kind = "skill"

emoji = "\U0001F7E2" if avg >= 8 else "\U0001F7E1" if avg >= 6 else "\U0001F534"
payload = {
    "target": str(target), "kind": kind, "average": round(avg, 2),
    "dimensions": dims, "emoji": emoji,
    "verdict": "excellent" if avg >= 8 else "good" if avg >= 6 else "needs_work",
}

if json_out:
    print(json.dumps(payload, indent=2))
else:
    print(f"{emoji} {kind} {target.name}: {avg:.1f}/10 ({payload['verdict']})")
    for d, v in dims.items():
        bar = "█" * int(v) + "░" * (10 - int(v))
        print(f"   {d:<18} {v:>2}  {bar}")
PYEOF
