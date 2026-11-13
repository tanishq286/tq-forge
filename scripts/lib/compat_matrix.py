"""Cross-model compatibility matrix for the bundled skills and templates (Python stdlib only).

Scores every bundled skill and subagent template under the lint rules of each
current Claude model, runs the dry-test, and renders the result as Markdown.
Static analysis only: no model is called and no network request is made.

For each artifact the matrix reports:

  score       0-100 under each model's rules (structure minus lint penalties)
  dry-test    structural checks passed / total
  min tier    the least capable model tier the artifact is expected to run well on
  effort      the effort level to start at on that tier
  status      PASS when every score is >= 70 and the dry-test passes

The minimum tier is an estimate from what the artifact is allowed to do, not a
measured result. A subagent that pins a model uses that model's tier. A skill
counts one point each for: writing files, using the web, asking the user a
question, and a procedure of eight or more steps. 0 points is haiku, 1-2 is
sonnet, 3 or more is opus; a skill that starts subagents is fable.

Usage: compat_matrix.py [--write] [--check] [--json] [--out FILE]
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import drytest  # noqa: E402
import frontmatter  # noqa: E402
import model_lint  # noqa: E402
import models  # noqa: E402
import score  # noqa: E402

PACKAGE = pathlib.Path(__file__).resolve().parents[2]
DOC = pathlib.Path("docs") / "MODEL_COMPATIBILITY.md"
COLUMNS = ("fable", "opus", "sonnet", "haiku")  # most to least capable
PASS_SCORE = 70
SWEEP_EFFORTS = ("low", "medium", "high")
WEB_TOOLS = frozenset({"WebSearch", "WebFetch"})
ASK_TOOL = "AskUserQuestion"
LONG_PROCEDURE_STEPS = 8
OPUS_DEMAND = 3
CLEAN = "clean"


def column_models(registry):
    """[(family, model id)] for the matrix columns, from the registry's current models."""
    return [(family, models.family_current(family, registry)) for family in COLUMNS
            if models.family_current(family, registry)]


def label(model_id):
    family, (major, minor) = models.parse_id(model_id)
    return f"{family.title()} {major}" + (f".{minor}" if minor else "")


# ------------------------------------------------------------- artifacts

def skill_files(package):
    return sorted((package / "skills").glob("*/SKILL.md"))


def subagent_files(package):
    return sorted(path for path in (package / "templates" / "agents").glob("*.md")
                  if not path.name.startswith("_"))


def base_agent_files(package):
    return sorted(path for path in (package / "templates" / "agent-templates").glob("*.md")
                  if not path.name.startswith("_"))


def _dry_test(path, kind):
    checks = drytest.Checks()
    (drytest.check_skill if kind == "skill" else drytest.check_subagent)(path, checks)
    percent = checks.passed / checks.total * 100 if checks.total else 0
    needed = 100 if kind in drytest.STRICT_KINDS else drytest.PASS_PERCENT
    return {"passed": checks.passed, "total": checks.total, "ok": percent >= needed}


def skill_demand(fields, body):
    """Signals for how much a skill asks of the model. Returns (points, delegates)."""
    tools = set(frontmatter.as_list(fields.get("allowed-tools") or fields.get("tools")))
    points = sum((
        bool(tools & model_lint.WRITE_TOOLS),
        bool(tools & WEB_TOOLS),
        ASK_TOOL in tools,
        len(model_lint._NUMBERED_STEP.findall(body)) >= LONG_PROCEDURE_STEPS,
    ))
    return points, bool(tools & model_lint.DELEGATE_TOOLS)


def recommend(kind, fields, body, registry):
    """Return (minimum tier, starting effort, why) for one artifact."""
    pinned = models.parse_id(fields.get("model")) if fields.get("model") else None
    if kind == "subagent" and pinned:
        tier = model_lint.family(fields["model"]) or pinned[0]
        return tier, str(fields.get("effort") or _guide(registry, tier)["agentic"]), "pinned in the template"
    points, delegates = skill_demand(fields, body)
    if delegates:
        tier = "fable"
    elif points >= OPUS_DEMAND:
        tier = "opus"
    elif points:
        tier = "sonnet"
    else:
        tier = "haiku"
    guide = _guide(registry, tier)
    effort = str(fields.get("effort") or (guide["agentic"] if points or delegates else guide["routine"]))
    return tier, effort, f"{points} demand point(s)" + (", delegates" if delegates else "")


def _guide(registry, family):
    return registry["models"][models.family_current(family, registry)]["effort_guide"]


def evaluate_artifact(path, registry):
    """One matrix row: scores under every model, dry-test, recommendation and status."""
    kind = score.detect(path)[0]
    fields, body, _ = frontmatter.read(path.read_text(errors="replace"))
    scores, findings = {}, {}
    for family, model_id in column_models(registry):
        report = score.evaluate(path, model_id)
        scores[family] = report["score"]
        findings[family] = [finding["id"] for finding in report["findings"]]
    sweep = sorted({f"{finding['id']} on {family} at {effort}"
                    for family, model_id in column_models(registry) for effort in SWEEP_EFFORTS
                    for finding in score.evaluate(path, model_id, effort)["findings"]})
    dry = _dry_test(path, kind)
    tier, effort, why = recommend(kind, fields, body, registry)
    return {
        "name": path.parent.name if kind == "skill" else path.stem,
        "kind": kind,
        "pinned": fields.get("model"),
        "scores": scores,
        "findings": findings,
        "effort_sweep": sweep,
        "dry_test": dry,
        "min_tier": tier,
        "effort": effort,
        "why": why,
        "pass": dry["ok"] and min(scores.values()) >= PASS_SCORE,
    }


def lint_only(path, registry):
    """Lint a base agent template, which is a prompt skeleton with no frontmatter to score."""
    text = path.read_text(errors="replace")
    return {"name": path.stem,
            "findings": {family: [finding["id"] for finding in model_lint.lint(text, model_id, kind="agent")]
                         for family, model_id in column_models(registry)}}


def build(package=PACKAGE):
    registry = models.generations()
    return {
        "registry_updated": registry.get("updated"),
        "mythos": models.family_current("mythos", registry),
        "models": [{"family": family, "id": model_id, **registry["models"][model_id]}
                   for family, model_id in column_models(registry)],
        "skills": [evaluate_artifact(path, registry) for path in skill_files(package)],
        "subagents": [evaluate_artifact(path, registry) for path in subagent_files(package)],
        "base_agents": [lint_only(path, registry) for path in base_agent_files(package)],
        "deprecations": registry.get("deprecations") or [],
    }


# --------------------------------------------------------------- render

def _table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(" --- " for _ in header) + "|"]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def _artifact_rows(artifacts, families, pinned=False):
    rows = []
    for item in artifacts:
        row = [f"`{item['name']}`"]
        if pinned:
            row.append(f"`{item['pinned']}`" if item["pinned"] else "none")
        row.extend(item["scores"][family] for family in families)
        row.extend([f"{item['dry_test']['passed']}/{item['dry_test']['total']}", item["min_tier"].title(),
                    f"`{item['effort']}`", "PASS" if item["pass"] else "**FAIL**"])
        rows.append(row)
    return rows


def _rule_rows(report):
    rows = []
    for rule in model_lint.RULES:
        applies = [("yes" if rule["models"] is model_lint.ANY_TARGET or model["family"] in rule["models"] else "no")
                   for model in report["models"]]
        penalty = "3-10" if rule["id"] == "M012" else rule["penalty"]
        rows.append([rule["id"], f"`{rule['name']}`", *applies, penalty])
    return rows


def _model_rows(report):
    rows = []
    for model in report["models"]:
        guide, caps = model["effort_guide"], model["capabilities"]
        early = ", ".join(f"`{level}`" for level in guide["stops_early_at"]) or "none documented"
        rows.append([label(model["id"]), f"`{model['id']}`", model["role"], f"`{guide['api_default']}`",
                     f"`{guide['routine']}`", f"`{guide['agentic']}`", f"`{guide['hardest']}`", early,
                     caps["thinking"], caps["sampling"]])
    return rows


def _mythos_note(report):
    mythos = report.get("mythos")
    if not mythos:
        return "Each column is the current model of its family."
    return (f"Each column is the current model of its family. {label(mythos)} (`{mythos}`, verified "
            "organizations only) shares the Fable column: same rules, same effort guide.")


def _deprecation_rows(report):
    rows = []
    for rule in report["deprecations"]:
        if "id" in rule:
            name = f"`{rule['id']}`"
            target = f"`{rule['replacement']}`" + (f" ({rule['note']})" if rule.get("note") else "")
        else:
            major, minor = rule["version"]
            name = f"{rule['family'].title()} {major}" + (f".{minor}" if minor else "") + " (every id)"
            target = f"current {rule['family'].title()}"
        rows.append([name, rule["status"], rule.get("date") or "to be announced", target])
    return rows


def _summary(report):
    artifacts = report["skills"] + report["subagents"]
    if not artifacts:
        return "No bundled skills or subagent templates were found next to this script."
    passed = sum(item["pass"] for item in artifacts)
    lowest = min(min(item["scores"].values()) for item in artifacts)
    sweep = sorted({entry for item in artifacts for entry in item["effort_sweep"]})
    sweep_text = ("Linted again at `low`, `medium` and `high` effort under every model, no artifact loses a point."
                  if not sweep else "Effort sweep findings: " + "; ".join(sweep) + ".")
    return (f"**{passed} of {len(artifacts)} artifacts pass** ({len(report['skills'])} skills, "
            f"{len(report['subagents'])} subagent templates). The lowest score under any model is "
            f"{lowest}/100; the gate is {PASS_SCORE}. {sweep_text}")


def render(report):
    families = [model["family"] for model in report["models"]]
    heads = [label(model["id"]) for model in report["models"]]
    tail = ["Dry-test", "Min tier", "Effort", "Status"]
    base_rows = [[f"`{item['name']}`", *[", ".join(item["findings"][family]) or CLEAN for family in families]]
                 for item in report["base_agents"]]
    parts = [
        "# Model compatibility matrix",
        "<!-- Generated by `tq-forge compat --write`. Do not edit by hand: `npm test` fails when this file "
        "differs from the generator's output. -->",
        "How every bundled skill and subagent template scores under the rules of each current Claude model. "
        f"Model data is from `config/models.json` (updated {report['registry_updated']}). The scores come from "
        "static checks: no model was called, so this shows that a file avoids what a model rejects or handles "
        "badly, not how well the model performs the task.",
        _summary(report),
        "## Models",
        _table(["Model", "ID", "Role", "API default effort", "Routine", "Agentic", "Hardest", "Stops early at",
                "Thinking", "Sampling parameters"], _model_rows(report)),
        _mythos_note(report),
        "`Routine` is the level for chat and short, well-specified tasks. `Agentic` is the starting level for "
        "multistep coding and tool use. `Hardest` is worth its cost only where a gain was measured on your own "
        "tasks. `Stops early at` lists the levels at which the model is documented to end a long task before "
        "it is done; a long-horizon agent needs explicit completion instructions there (rule M011).",
        "## Bundled skills",
        _table(["Skill", *heads, *tail], _artifact_rows(report["skills"], families)),
        "## Subagent templates",
        _table(["Template", "Pinned model", *heads, *tail], _artifact_rows(report["subagents"], families, True)),
        "## Base agent templates",
        "The eight templates behind `/tq-forge-agent` are prompt skeletons, scored only after an agent is "
        "forged from them. Here they are linted as written.",
        _table(["Template", *heads], base_rows),
        "## Rules by model",
        _table(["Rule", "Name", *heads, "Penalty"], _rule_rows(report)),
        "Run `tq-forge score <path>` to see the message and the fix for each finding. A file can opt out of a "
        "rule with `<!-- tq-forge-lint-ignore: M002 -->`.",
        "## Deprecated and retired model ids",
        _table(["Model", "Status", "Date (Claude API)", "Move to"], _deprecation_rows(report)),
        "An older version that is not listed is `superseded`: still served, but behind the registry. Rule M012 "
        "subtracts 10 points for a retired id, 6 for a deprecated one and 3 for a superseded one. "
        "`tq-forge sync-models --apply` rewrites pinned `model:` fields.",
        "## How to read the recommendations",
        "- **Score**: structural dimensions (1-10 each, averaged, times 10) minus the lint penalties of that "
        f"model. {PASS_SCORE} is the promotion gate.\n"
        "- **Min tier**: the least capable tier the artifact is expected to run well on. A subagent template "
        "uses the model it pins. A skill gets one point each for writing files, using the web, asking the user "
        f"a question, and a procedure of {LONG_PROCEDURE_STEPS} or more steps: 0 points is Haiku, 1-2 is Sonnet, "
        f"{OPUS_DEMAND} or more is Opus, and a skill that starts subagents is Fable. This is an estimate from "
        "the file, not a measured result.\n"
        "- **Effort**: the level a template pins, or for a skill the registry's `routine` level (0 points) or "
        "`agentic` level of its minimum tier.\n"
        f"- **Status**: PASS when the score is {PASS_SCORE} or more under every model and the dry-test passes.",
        "## Regenerate",
        "```bash\nnpx tq-forge compat --write    # rewrite this file\nnpx tq-forge compat --check    # exit 1 when "
        "it is out of date or an artifact fails\n```",
    ]
    return "\n\n".join(parts) + "\n"


# -------------------------------------------------------------------- cli

def main(argv):
    parser = argparse.ArgumentParser(prog="compat", description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true", help=f"write the matrix to {DOC}")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when the file is out of date or an artifact fails")
    parser.add_argument("--json", action="store_true", help="print the raw report")
    parser.add_argument("--out", help="file to write or check instead of the default")
    args = parser.parse_args(argv[1:])
    report = build()
    text = render(report)
    target = pathlib.Path(args.out) if args.out else PACKAGE / DOC
    failing = [item["name"] for item in report["skills"] + report["subagents"] if not item["pass"]]
    if args.write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"compat: wrote {target}")
    elif args.json:
        print(json.dumps(report, indent=2))
    elif not args.check:
        print(text, end="")
    if failing:
        print(f"compat: below the gate: {', '.join(failing)}", file=sys.stderr)
    if args.check:
        current = target.read_text(encoding="utf-8") if target.is_file() else None
        if current != text:
            print(f"compat: {target} is out of date; run `tq-forge compat --write`", file=sys.stderr)
            return 1
        print(f"compat: {target} is current; {len(report['skills']) + len(report['subagents'])} artifacts checked")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
