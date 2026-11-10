"""Structural quality scorer for tq-forge artifacts (Python stdlib only).

Three artifact kinds:
  skill     a SKILL.md (or a directory holding one)        4 dimensions
  agent     a tq-forge 5-file agent directory (AGENT.md)   6 dimensions
  subagent  a Claude Code subagent file (.claude/agents/*.md)  5 dimensions

Each dimension scores 1-10. The headline `score` is 0-100:

    score = round(mean(dimensions) * 10 - lint penalties)

`average` (0-10) is `score / 10` before rounding and is kept for the >= 7 gate
that /tq-forge-promote and CI use. With no lint findings it equals the mean of
the dimensions, exactly as in tq-forge 1.0.

Usage: score.py <target> <json:true|false> [model-override]
"""

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import frontmatter  # noqa: E402
import model_lint  # noqa: E402
import models  # noqa: E402

VAGUE = r"\b(do the thing|various|some|things|stuff|whatever)\b"
REAL_PATHS = r"~/[\.\w/-]+|/home/\w+|\$HOME|\$TQ_FORGE_HOME|\$CLAUDE_PLUGIN_ROOT"
AGENT_FILES = ("AGENT.md", "system-prompt.md", "tools.json",
               "trigger-conditions.md", "example-tasks.md")
TRIGGER = r"\buse\s+(?:this\s+agent\s+)?(?:when|proactively|after|before|for|immediately)\b"
SECTIONS_BY_COUNT = {3: 9, 2: 7, 1: 5, 0: 3}


def score_skill(text):
    dims = {}

    match = re.search(r"##\s*When to use\s*\n(.+?)\n##", text, re.S | re.I)
    if match:
        body = match.group(1).strip()
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

    match = re.search(r"##\s*Procedure\s*\n(.+?)\n##", text, re.S | re.I)
    if match:
        body = match.group(1)
        steps = re.findall(r"^\s*\d+\.\s", body, re.M)
        if len(steps) >= 3 and body.count("```") >= 2:
            dims["actionability"] = 9
        elif len(steps) >= 2:
            dims["actionability"] = 7
        else:
            dims["actionability"] = 5
    else:
        dims["actionability"] = 3

    present = sum(bool(re.search(rf"##\s*{name}", text, re.I))
                  for name in ("Pitfalls", "Verification", "Tags"))
    dims["completeness"] = SECTIONS_BY_COUNT[present]

    vague = re.findall(VAGUE, text, re.I)
    real_paths = re.findall(REAL_PATHS, text)
    if not vague and len(real_paths) >= 3:
        dims["specificity"] = 9
    elif len(vague) <= 1 and len(real_paths) >= 1:
        dims["specificity"] = 7
    else:
        dims["specificity"] = 4

    return dims


def score_agent(agent_dir):
    missing = [name for name in AGENT_FILES if not (agent_dir / name).exists()]
    if missing:
        return {"_missing": missing}

    dims = {}
    prompt = (agent_dir / "system-prompt.md").read_text(errors="replace")
    prompt_words = len(prompt.split())

    persona = re.search(r"##\s*Persona\s*\n(.+?)(\n##|\Z)", prompt, re.S | re.I)
    dims["clarity"] = 9 if persona and len(persona.group(1).split()) > 50 else 5

    has_output = bool(re.search(r"##\s*Output format", prompt, re.I)) and "```" in prompt
    dims["actionability"] = 9 if has_output else 4

    has_never = bool(re.search(r"##\s*NEVER", prompt, re.I))
    has_context = "{{CONTEXT}}" in prompt or bool(re.search(r"##\s*Domain context", prompt, re.I))
    if 500 <= prompt_words <= 1500 and has_never and has_context:
        dims["completeness"] = 9
    elif has_never and has_context:
        dims["completeness"] = 7
    else:
        dims["completeness"] = 5

    field_count = len(re.findall(r"^\s*-\s*\w+:", prompt, re.M))
    dims["specificity"] = 9 if field_count >= 5 else 7 if field_count >= 2 else 4

    rigid = prompt.count("```yaml") >= 1 or prompt.count("```") >= 4
    dims["consistency"] = 9 if rigid else 5

    try:
        tools = json.loads((agent_dir / "tools.json").read_text())
        dims["handoff_clarity"] = 9 if len(tools.get("hand_off_to", [])) >= 1 else 4
    except Exception:
        dims["handoff_clarity"] = 3

    return dims


def _section(body, title_pattern):
    match = re.search(rf"^#{{1,3}}\s*(?:{title_pattern})[^\n]*\n(.+?)(?=^#{{1,3}}\s|\Z)",
                      body, re.S | re.M | re.I)
    return match.group(1) if match else None


def score_subagent(fields, body):
    """Score a Claude Code subagent file from its frontmatter and prompt body."""
    dims = {}

    description = str(fields.get("description", ""))
    described = len(description.split())
    if described >= 12 and re.search(TRIGGER, description, re.I):
        dims["clarity"] = 9
    elif described >= 8:
        dims["clarity"] = 7
    else:
        dims["clarity"] = 4

    workflow = _section(body, r"Workflow|Operating loop|Procedure|How you work|Process")
    steps = re.findall(r"^\s*(?:\d+\.|-)\s", workflow or "", re.M)
    if len(steps) >= 3:
        dims["actionability"] = 9
    elif workflow:
        dims["actionability"] = 7
    else:
        dims["actionability"] = 4

    present = sum(_section(body, pattern) is not None for pattern in (
        r"Output format|Report format|Final report|Communicating clearly",
        r"Boundaries|Constraints|Scope|NEVER|Limits",
        r"Self-review|Verification|Review loop|Checks",
    ))
    dims["completeness"] = SECTIONS_BY_COUNT[present]

    restricted = bool(frontmatter.as_list(fields.get("tools"))
                      or frontmatter.as_list(fields.get("disallowedTools")))
    pinned = bool(fields.get("model")) and bool(fields.get("effort"))
    vague = re.findall(VAGUE, body, re.I)
    if restricted and pinned and len(vague) <= 1:
        dims["specificity"] = 9
    elif restricted or pinned:
        dims["specificity"] = 7
    else:
        dims["specificity"] = 4

    report = _section(body, r"Output format|Report format|Final report")
    dims["consistency"] = 9 if report and "```" in report else 5

    return dims


def detect(target):
    """Return (kind, path) for a scoreable target, or (None, target)."""
    if target.is_file() and target.name == "SKILL.md":
        return "skill", target
    if target.is_dir() and (target / "SKILL.md").exists():
        return "skill", target / "SKILL.md"
    if target.is_dir() and (target / "AGENT.md").exists():
        return "agent", target
    if target.is_file() and target.suffix == ".md":
        fields, _, has_frontmatter = frontmatter.read(target.read_text(errors="replace"))
        if has_frontmatter and fields.get("name") and fields.get("description"):
            return "subagent", target
    return None, target


def evaluate(target, model_override=None):
    """Score one artifact and return the report payload."""
    kind, path = detect(target)
    if kind is None:
        raise ValueError(f"don't recognize target shape at {target}")

    declared = None
    if kind == "agent":
        dims = score_agent(path)
        prompt_file = path / "system-prompt.md"
        lint_text = prompt_file.read_text(errors="replace") if prompt_file.exists() else ""
    else:
        text = path.read_text(errors="replace")
        fields, body, _ = frontmatter.read(text)
        declared = fields.get("model")
        dims = score_skill(text) if kind == "skill" else score_subagent(fields, body)
        lint_text = text

    lint_model, lint_note = models.lint_target(model_override or declared)
    findings = model_lint.lint(lint_text, lint_model)
    penalty = model_lint.total_penalty(findings)

    scored = {name: value for name, value in dims.items() if not name.startswith("_")}
    mean = sum(scored.values()) / len(scored) if scored else 0.0
    average = max(0.0, round(mean - penalty / 10, 2))
    verdict = "excellent" if average >= 8 else "good" if average >= 6 else "needs_work"

    return {
        "target": str(target),
        "kind": kind,
        "score": int(average * 10 + 0.5),  # round half up, not banker's rounding
        "scale": 100,
        "average": average,
        "dimensions": dims,
        "penalty": penalty,
        "findings": findings,
        "lint_model": lint_model,
        "lint_note": lint_note,
        "emoji": "\U0001F7E2" if average >= 8 else "\U0001F7E1" if average >= 6 else "\U0001F534",
        "verdict": verdict,
    }


def render(payload, name):
    lines = [f"{payload['emoji']} {payload['kind']} {name}: {payload['score']}/100 "
             f"({payload['average']:.1f}/10, {payload['verdict']})"]
    for dim, value in payload["dimensions"].items():
        if dim.startswith("_"):
            lines.append(f"   missing files: {', '.join(value)}")
            continue
        bar = "█" * int(value) + "░" * (10 - int(value))
        lines.append(f"   {dim:<18} {value:>2}  {bar}")
    for finding in payload["findings"]:
        lines.append(f"   ⚠ {finding['id']} {finding['name']} (-{finding['penalty']}, "
                     f"line {finding['line']}): {finding['message']}")
        lines.append(f"     fix: {finding['fix']}")
    if payload["findings"]:
        lines.append(f"   lint target: {payload['lint_model'] or 'none'} ({payload['lint_note']})")
    return "\n".join(lines)


def main(argv):
    if len(argv) < 3:
        print("usage: score.py <target> <json:true|false> [model]", file=sys.stderr)
        return 2
    target = pathlib.Path(argv[1])
    json_out = argv[2].lower() == "true"
    model_override = argv[3] if len(argv) > 3 and argv[3] else None
    try:
        payload = evaluate(target, model_override)
    except ValueError as error:
        print(f"quality-score: {error}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2) if json_out else render(payload, target.name))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
