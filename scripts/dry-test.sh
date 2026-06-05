#!/usr/bin/env bash
# dry-test.sh — structural validation of a forged agent or skill.
#
# This is NOT a live LLM run. It's a static check that the artifact is shaped
# correctly and would behave coherently if invoked. For live behavior testing,
# the user runs the skill manually after promote.
#
# Usage:
#   dry-test.sh <path>
#   dry-test.sh --json <path>

set -uo pipefail

JSON_OUT=false
[[ "${1:-}" == "--json" ]] && { JSON_OUT=true; shift; }
TARGET="${1:-}"
[[ -z "$TARGET" ]] && { echo "usage: dry-test.sh [--json] <path>" >&2; exit 2; }

python3 - "$TARGET" "$JSON_OUT" <<'PYEOF'
import sys, json, re, pathlib
target = pathlib.Path(sys.argv[1])
json_out = sys.argv[2].lower() == "true"

issues = []
warnings = []
checks_passed = 0
checks_total = 0

def check(label, ok, hint=""):
    global checks_passed, checks_total
    checks_total += 1
    if ok:
        checks_passed += 1
    else:
        issues.append(f"{label}: {hint}" if hint else label)

if not target.exists():
    print(json.dumps({"verdict": "fail", "reason": "not found", "target": str(target)}))
    sys.exit(1)

if target.is_dir() and (target / "AGENT.md").exists():
    kind = "agent"
elif target.is_dir() and (target / "SKILL.md").exists():
    kind = "skill"; target = target / "SKILL.md"
elif target.is_file() and target.name == "SKILL.md":
    kind = "skill"
else:
    print(json.dumps({"verdict": "fail", "reason": "unrecognized shape"}))
    sys.exit(1)

if kind == "skill":
    text = target.read_text(errors="replace")
    m = re.match(r"^---\n(.+?)\n---\n", text, re.S)
    check("frontmatter present", bool(m), "missing --- ... --- block")
    if m:
        fm = m.group(1)
        check("name field", "name:" in fm)
        check("description field", "description:" in fm)
        check("allowed-tools", "allowed-tools:" in fm)
    check("when-to-use section", "## When to use" in text)
    check("procedure section", re.search(r"##\s*Procedure", text, re.I) is not None)
    check("pitfalls section", re.search(r"##\s*Pitfalls", text, re.I) is not None)
    check("verification section", re.search(r"##\s*Verification", text, re.I) is not None)
    word_count = len(re.sub(r"```.*?```", "", text, flags=re.S).split())
    check("word count 200-1500", 200 <= word_count <= 1500, f"got {word_count}")

elif kind == "agent":
    files = ["AGENT.md", "system-prompt.md", "tools.json",
             "trigger-conditions.md", "example-tasks.md"]
    for f in files:
        check(f"{f} present", (target / f).exists())
    try:
        tj = json.loads((target / "tools.json").read_text())
        check("tools.json valid JSON", True)
        check("tools.json has tools list", isinstance(tj.get("tools"), list))
        check("tools.json has hand_off_to", "hand_off_to" in tj)
    except Exception as e:
        check("tools.json valid JSON", False, str(e))
    try:
        sp = (target / "system-prompt.md").read_text()
        wc = len(sp.split())
        check("system-prompt 500-1500 words", 500 <= wc <= 1500, f"got {wc}")
        check("NEVER block present", "## NEVER" in sp)
        check("output format defined", re.search(r"##\s*Output format", sp, re.I) is not None)
        has_ctx = ("{{CONTEXT}}" in sp) or bool(re.search(r"##\s*Domain context", sp, re.I))
        check("domain context injected", has_ctx,
              "no {{CONTEXT}} token or '## Domain context' section")
    except Exception as e:
        check("system-prompt readable", False, str(e))
    try:
        et = (target / "example-tasks.md").read_text()
        n = len(re.findall(r"^##\s*Task\s*\d+", et, re.M))
        check("example-tasks has >=3 entries", n >= 3, f"got {n}")
    except Exception:
        check("example-tasks readable", False)

pct = (checks_passed / checks_total * 100) if checks_total else 0
verdict = "pass" if pct >= 85 else "warn" if pct >= 60 else "fail"
score = round(pct / 10, 2)

payload = {
    "kind": kind, "target": str(target),
    "checks_passed": checks_passed, "checks_total": checks_total,
    "score": score, "verdict": verdict, "issues": issues, "warnings": warnings,
}

if json_out:
    print(json.dumps(payload, indent=2))
else:
    emoji = {"pass": "✅", "warn": "⚠️", "fail": "\U0001F534"}[verdict]
    print(f"{emoji} {kind} dry-test: {checks_passed}/{checks_total} ({score}/10) — {verdict}")
    for issue in issues:
        print(f"   ❌ {issue}")
PYEOF
