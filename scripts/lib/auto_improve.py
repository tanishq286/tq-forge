"""Self-improving pass over a Claude Code setup (Python stdlib only).

`auto-improve` runs everything `optimize` does, then uses two more signals:

  usage   session logs under .claude/projects/ show which skills were ever
          invoked (see telemetry.py)
  score   the 0-100 rubric from score.py, for every skill and subagent

and plans these changes on top:

  claude_md  a CLAUDE.md over 300 tokens keeps its rule sections; every other
             section moves into an on-demand skill (`reference.md` plus a
             140-character trigger), and a one-line pointer stays behind. A
             kept rule bullet over 160 characters keeps its first sentence;
             its full wording moves to reference.md with the rest
  rules      with --scope-rules: a rule file over the threshold with no
             `paths:` gets any-file globs, so it loads the first time Claude
             touches a file instead of on every turn
  skills     descriptions are cut to 140 characters; a skill that still costs
             more than the threshold and was never invoked is listed by name only
  plugins    with --dedupe-plugins: a symlinked skill that a plugin also loads
             is unlinked, and idle plugin skills over the threshold are compacted

Usage is evidence only when there are session logs to read. With none, every
usage-based step is skipped and the report says so.
  upgrade    a skill or subagent scoring under 85 gets the mechanical fixes:
             outdated `model:` ids replaced and a missing `effort` filled in;
             with --add-paths, `paths:` for the file types its description
             names; with --extract-scripts, long shell blocks moved to scripts/

What it will not do: write missing sections for you, turn off a plugin, or
(unless asked) turn the shell examples in a skill into scripts. A skill's code
blocks are often examples to adapt, and replacing them with a script call
changes what the skill tells Claude. Those are listed as recommendations.

Dry run by default. --apply writes after backing up to .tq-forge-backup/;
`tq-forge restore` undoes it.

Usage: auto_improve.py [--root DIR] [--apply] [--follow-symlinks] [--dedupe-plugins] [--scope-rules]
                       [--add-paths] [--extract-scripts] [--threshold N] [--min-score N] [--json]
"""

import argparse
import collections
import json
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import context_cost  # noqa: E402
import frontmatter  # noqa: E402
import linkdedupe  # noqa: E402
import model_sync  # noqa: E402
import models  # noqa: E402
import optimize  # noqa: E402
import scaffold  # noqa: E402
import score  # noqa: E402
import telemetry  # noqa: E402

THRESHOLD_TOKENS = 150
MIN_SCORE = 85
DESCRIPTION_LIMIT = 140
CLAUDE_MD_TOKEN_LIMIT = 300
CLAUDE_MD_LINE_LIMIT = 35
KEEP_SECTION_TOKENS = 300
RULE_LINE_LIMIT = 160
MIN_FIRST_SENTENCE = 20
PATHS_MAX = 6
LONG_SCRIPT_LINES = 20
POINTER_TITLE = "On-demand reference"
FLOW_SKILL = "claude-flow"
GENERIC_SKILL = "project-reference"
KEEP_TITLE = re.compile(r"\b(rules?|conventions?|guidelines|norms|style|build|tests?|testing|commands?)\b", re.I)
FLOW_MARK = re.compile(r"claude-flow|ruflo", re.I)
EXTENSION = re.compile(r"\*\.([A-Za-z0-9]{1,5})\b")
FILE_GLOBS = ("**/*", "**/.*", "**/.*/**")  # any file in the working folder, dotfiles included


def _tokens(text):
    return context_cost.estimate_tokens(text)


# ------------------------------------------------------------- CLAUDE.md

def _shorten_rules(sections):
    """Cut long rule bullets to their first sentence. Returns (sections, the full lines that were cut)."""
    shortened, full = [], []
    for title, section in sections:
        lines, fenced = [], False
        for line in section.splitlines():
            if line.lstrip().startswith("```"):
                fenced = not fenced
            first = re.split(r"(?<=[.!?])\s+", line, maxsplit=1)[0]
            is_bullet = not fenced and line.lstrip().startswith(("- ", "* "))  # never cut a line of code
            if is_bullet and len(line) > RULE_LINE_LIMIT and MIN_FIRST_SENTENCE <= len(first) < len(line):
                lines.append(first)
                full.append(line)
            else:
                lines.append(line)
        shortened.append((title, "\n".join(lines)))
    return shortened, full


def _reference_skill(name, titles, workers):
    """SKILL.md for the on-demand skill that now holds the moved CLAUDE.md sections."""
    listed = ", ".join(titles)
    if name == FLOW_SKILL:
        description = ("claude-flow / ruflo reference: swarms, SPARC, agent routing, memory and CLI. "
                       "Use when a task needs swarm or ruflo orchestration.")
        subject = "claude-flow / ruflo orchestration (swarms, SPARC modes, agent routing, memory, hooks or the CLI)"
    else:
        description = optimize.compact_description(
            f"Project reference moved out of CLAUDE.md: {listed}. Use when a task needs one of these topics.",
            DESCRIPTION_LIMIT)
        subject = f"one of these topics: {listed}"
    steps = ["1. Find the section the task needs in the list under Sections below.",
             "2. Open [reference.md](reference.md) and read that section only. Skip the rest of the file."]
    if workers:
        steps.append(f"3. Send MCP tool calls through the {', '.join(f'`{worker}`' for worker in workers)} "
                     f"subagent. The main conversation no longer loads those tools, so calling them directly fails.")
    steps.append(f"{len(steps) + 1}. Carry on with the task. The rules in CLAUDE.md still apply while you do.")
    sections = "\n".join(f"- {title}" for title in titles)
    return (f"---\nname: {name}\ndescription: {json.dumps(description)}\nallowed-tools:\n  - Read\n---\n\n"
            f"# {name}\n\n"
            f"## When to use\n\nLoad this skill when a task needs {subject}. "
            f"This text used to sit in CLAUDE.md, where it cost tokens on every turn whether or not the task "
            f"needed it. It now loads only when this skill runs. Nothing about the content changed, only the "
            f"moment it is read.\n\n"
            f"## Procedure\n\n" + "\n".join(steps) + "\n\n"
            f"## Sections\n\nreference.md holds these sections, word for word as they were in CLAUDE.md:\n\n"
            f"{sections}\n\n"
            f"## Pitfalls\n\n"
            f"- Do not paste reference.md back into CLAUDE.md. That puts the cost back on every turn.\n"
            f"- reference.md is long. Read the one section you need, not the whole file.\n"
            f"- A command in reference.md is an example to adapt. Check its arguments against the task before "
            f"you run it.\n"
            f"- If a section seems to be missing, look in CLAUDE.md first: short rule sections stayed there.\n\n"
            f"## Verification\n\n"
            f"- The section you read is one of those listed under Sections.\n"
            f"- What you did follows that section and does not contradict a rule in CLAUDE.md.\n"
            f"- Run `tq-forge restore` in the project root if you need CLAUDE.md back the way it was.\n\n"
            f"## Tags\n\nreference, on-demand, {name}\n")


def plan_claude_md(root, text=None, workers=()):
    """Move reference sections of an oversized CLAUDE.md into an on-demand skill."""
    plan = optimize.new_plan()
    text = context_cost.read_text(root / "CLAUDE.md") if text is None else text
    if _tokens(text) <= CLAUDE_MD_TOKEN_LIMIT:
        plan["notes"].append(f"claude_md: within {CLAUDE_MD_TOKEN_LIMIT} tokens")
        return plan
    reason = optimize.skip_reason(root, "CLAUDE.md")
    if reason:
        plan["warnings"].append(f"claude_md: CLAUDE.md {reason}; left unchanged")
        return plan
    lines = text.splitlines()
    hygiene = [line for line in lines if line.startswith(optimize.HYGIENE_MARK)]  # the shield's note stays put
    preamble, sections = optimize.split_sections("\n".join(line for line in lines if line not in hygiene))
    kept, moved = [], []
    for title, section in sections:
        keep = title == POINTER_TITLE or (KEEP_TITLE.search(title) and _tokens(section) <= KEEP_SECTION_TOKENS)
        (kept if keep else moved).append((title, section))
    name = FLOW_SKILL if FLOW_MARK.search(text) else GENERIC_SKILL
    folder = f".claude/skills/{name}"
    taken = (root / folder / "SKILL.md").exists() or (root / folder / "reference.md").exists()
    if not moved or taken:
        why = "has no section to move" if not moved else f"{folder} already exists"
        plan["warnings"].append(f"claude_md: CLAUDE.md is {_tokens(text)} tokens but {why}; trim it by hand")
        return plan
    kept, full_lines = _shorten_rules(kept)
    titles = [title for title, _ in moved]
    full = ["## Full rule text\n\nThe complete wording of the rules that CLAUDE.md now states in one sentence.\n",
            *full_lines] if full_lines else []
    plan["writes"][f"{folder}/reference.md"] = optimize.join_markdown([
        f"# {name} reference",
        "Moved out of CLAUDE.md by `tq-forge auto-improve` so it loads on demand instead of on every turn.",
        *[section for _, section in moved], "\n".join(full)])
    plan["writes"][f"{folder}/SKILL.md"] = _reference_skill(name, titles, workers)
    pointer = (f"## {POINTER_TITLE}\n\n{len(moved)} reference sections moved to the `{name}` skill. "
               f"Load it only when a task needs them.")
    if workers:
        pointer += f" MCP tools run in the {', '.join(f'`{worker}`' for worker in workers)} subagent."
    lean = optimize.join_markdown([preamble, *[section for _, section in kept], pointer, *hygiene])
    plan["writes"]["CLAUDE.md"] = lean
    plan["notes"].append(f"claude_md: {len(moved)} sections -> {folder}/reference.md "
                         f"({_tokens(text)} -> {_tokens(lean)} tokens)")
    if _tokens(lean) > CLAUDE_MD_TOKEN_LIMIT or len(lean.splitlines()) > CLAUDE_MD_LINE_LIMIT:
        plan["warnings"].append(f"claude_md: CLAUDE.md is still {_tokens(lean)} tokens / "
                                f"{len(lean.splitlines())} lines; trim the kept rules by hand")
    return plan


# ------------------------------------------------------- idle-bloat rules

def big_rules(root, threshold):
    """[(relative path, text)] of rule files that load on every turn and cost more than the threshold."""
    found = []
    for path in context_cost.rule_files(root):
        relative = path.relative_to(root).as_posix()
        text = context_cost.read_text(path)
        block, _ = frontmatter.split(text)
        if relative == optimize.HYGIENE_RULE or "paths" in frontmatter.parse(block) or _tokens(text) <= threshold:
            continue  # a file that already has a `paths:` key, even an empty one, is the author's call
        found.append((relative, text))
    return found


def plan_idle_rules(root, threshold):
    """Give always-loaded rule files over the threshold a `paths:` scope of "any file".

    Such a rule then loads the first time Claude reads or edits a file in the
    working folder. It is absent from a session that touches no file, which is
    wrong for a rule about how to talk or answer, so this step is opt-in.
    """
    plan = optimize.new_plan()
    scope = "paths:\n" + "".join(f"  - {json.dumps(glob)}\n" for glob in FILE_GLOBS)
    for relative, text in big_rules(root, threshold):
        block, body = frontmatter.split(text)
        reason = optimize.skip_reason(root, relative)
        if reason:
            plan["warnings"].append(f"rules: {relative} {reason}; still loads on every turn")
            continue
        plan["writes"][relative] = (f"---\n{scope}---\n\n{text.lstrip()}" if block is None
                                    else f"---\n{block}\n{scope}---\n{body}")
        plan["notes"].append(f"rules: {relative} ({_tokens(text)} tokens) now loads on the first file touched")
    return plan


def plan_idle_skills(root, usage, threshold, base):
    """List by name only the skills that stay over the threshold and were never invoked."""
    plan = optimize.new_plan()
    if not usage["sessions"]:
        return plan  # no session logs, so no evidence that anything is unused
    overlay = {str((root / key).resolve()): text for key, text in base["writes"].items()}
    removed = set(base.get("remove_links", {}))
    chosen = context_cost.load_json(root / optimize.SETTINGS).get("skillOverrides")
    chosen = chosen if isinstance(chosen, dict) else {}
    quiet = {}
    for path in context_cost.skill_files(root):
        if path.parent.relative_to(root).as_posix() in removed:
            continue
        name = context_cost.skill_name(path, overlay)
        if name in chosen:
            continue  # the user already decided how this skill is listed
        listing = f"{name}: {context_cost._described(path, overlay)}"
        if _tokens(listing) > threshold and telemetry.uses(usage, name) == 0:
            quiet[name] = "name-only"
            plan["notes"].append(f"skills: {name} costs {_tokens(listing)} tokens a turn and was never invoked; "
                                 f"listed by name only")
    if quiet:
        plan["settings"]["skillOverrides"] = quiet
    return plan


def idle_plugin_selector(usage, threshold, twins=()):
    """Pick plugin skills to compact: idle ones over the threshold, and the twins of unlinked skills."""
    def select(item):
        listing = f"{item['plugin']}:{item['name']}: {context_cost._described(item['path'])}"
        idle = (usage["sessions"] > 0 and _tokens(listing) > threshold
                and telemetry.uses(usage, item["name"], item["plugin"]) == 0)
        return idle or item["name"] in twins
    return select


# -------------------------------------------------------------- upgrader

def _score_text(kind, text, filename):
    """Score planned text by writing it to a scratch file the scorer recognises."""
    with tempfile.TemporaryDirectory(prefix="tq-forge-score-") as scratch:
        folder = pathlib.Path(scratch) / "artifact"
        folder.mkdir()
        target = folder / ("SKILL.md" if kind == "skill" else filename)
        target.write_text(text, encoding="utf-8")
        try:
            return score.evaluate(target)["score"]
        except ValueError:
            return None


def _add_paths(block, fields):
    """Add `paths:` for the file types the description names. Opt-in (--add-paths).

    `paths:` stops Claude from loading the skill for any other file, and a
    description can name a file type it does not work on ("skips *.lock"), so
    this only runs when asked and the result needs a look.
    """
    if "paths" in fields:
        return block, None
    described = f"{fields.get('description', '')} {fields.get('when_to_use', '')}"
    chosen = list(dict.fromkeys(match.lower() for match in EXTENSION.findall(described)))[:PATHS_MAX]
    if not chosen:
        return block, None
    lines = "\n".join(f'  - "**/*.{extension}"' for extension in chosen)
    return optimize.replace_field(block, "paths", f"paths:\n{lines}"), f"paths: *.{', *.'.join(chosen)}"


def _add_effort(text, registry):
    """A subagent that pins a known model but no effort gets the registry's starting effort."""
    block, body = frontmatter.split(text)
    fields = frontmatter.parse(block)
    known = (registry.get("models") or {}).get(str(fields.get("model", "")))
    if block is None or not known or fields.get("effort"):
        return text, None
    return f"---\n{optimize.replace_field(block, 'effort', 'effort: ' + known['effort'])}\n---\n{body}", \
        f"effort: {known['effort']}"


def _fix(kind, text, folder, registry, extract, add_paths):
    """Apply the mechanical fixes. Returns (text, [fix names], {script name: text})."""
    fixes, scripts = [], {}
    text, change = model_sync.rewrite_model_field(text, registry)
    if change:
        fixes.append(f"model: {change[0]} -> {change[1]}")
    block, body = frontmatter.split(text)
    if block is None:
        return text, fixes, scripts
    if kind == "subagent":
        text, added = _add_effort(text, registry)
        return text, fixes + ([added] if added else []), scripts
    added = None
    if add_paths:
        block, added = _add_paths(block, frontmatter.parse(block))
    if added:
        fixes.append(added)
    if extract and not (folder / "scripts").exists():
        body, scripts = optimize._extract_scripts(body, LONG_SCRIPT_LINES)
        if scripts:
            fixes.append(f"{len(scripts)} long shell block(s) -> scripts/")
    return f"---\n{block}\n---\n{body}", fixes, scripts


def plan_upgrades(root, base, min_score, follow, extract=False, add_paths=False):
    """Fix every skill and subagent under `min_score`. Returns (plan, score records)."""
    plan, records = optimize.new_plan(), []
    registry = models.generations()
    removed = set(base.get("remove_links", {}))
    targets = [("skill", path) for path in context_cost.skill_files(root)]
    targets += [("subagent", path) for path in context_cost.agent_files(root)]
    for kind, path in targets:
        relative = path.relative_to(root).as_posix()
        if kind == "skill" and path.parent.relative_to(root).as_posix() in removed:
            continue
        try:
            before = score.evaluate(path)["score"]
        except (ValueError, OSError):
            continue
        if before >= min_score:
            continue
        record = {"path": relative, "kind": kind, "before": before, "after": before, "fixes": []}
        records.append(record)
        linked = optimize.skip_reason(root, relative)
        if linked and not (follow and kind == "skill"):
            record["blocked"] = linked
            continue
        base_key = optimize.write_base(root, path.parent) if linked else path.parent.relative_to(root).as_posix()
        key = f"{base_key}/{path.name}"
        text = base["writes"].get(key, context_cost.read_text(path))
        fixed, fixes, scripts = _fix(kind, text, path.parent, registry, extract, add_paths)
        record["fixes"] = fixes
        for name, content in {path.name: fixed, **scripts}.items():
            if name == path.name and fixed == text:
                continue
            plan["writes"][f"{base_key}/{name}"] = content
            if linked:
                plan["aliases"][f"{base_key}/{name}"] = f"{path.parent.relative_to(root).as_posix()}/{name}"
        record["after"] = _score_text(kind, fixed, path.name) or before
        if fixes:
            plan["notes"].append(f"upgrade: {relative} {before} -> {record['after']} ({'; '.join(fixes)})")
    return plan, records


# ----------------------------------------------------------- the full pass

def _unused_plugins(root, usage):
    """One recommendation per enabled plugin whose skills were never invoked."""
    if not usage["sessions"]:
        return []
    by_plugin = collections.defaultdict(list)
    for item in context_cost.plugin_skills(root):
        by_plugin[item["plugin"]].append(item)
    advice = []
    for plugin, items in sorted(by_plugin.items()):
        if any(telemetry.uses(usage, item["name"], plugin) for item in items):
            continue
        names = sum(_tokens(f"{plugin}:{item['name']}") for item in items)
        advice.append(f"plugin `{plugin}`: none of its {len(items)} skills were invoked in "
                      f"{usage['sessions']} session(s). skillOverrides cannot hide plugin skills; disabling the "
                      f"plugin with /plugin drops about {names} tokens of skill names, along with any agents, "
                      f"commands and hooks it ships, so check those first")
    return advice


def _long_blocks(root):
    """How many inline shell blocks --extract-scripts would move."""
    total = 0
    for path in context_cost.skill_files(root):
        _, body = frontmatter.split(context_cost.read_text(path))
        total += len(optimize._extract_scripts(body, LONG_SCRIPT_LINES)[1])
    return total


def build_plan(root, options):
    """Return (plan, extras) for one auto-improve pass over `root`."""
    usage = telemetry.scan(root)
    threshold = options["threshold"]
    mcp = optimize.plan_mcp(root, options["keep_mcp"])
    workers = sorted(pathlib.PurePosixPath(key).stem for key in mcp["writes"] if key.startswith(".claude/agents/"))
    rules = optimize.plan_rules(root)
    offload = plan_claude_md(root, rules["writes"].get("CLAUDE.md"), workers)
    skills = optimize.plan_skills(root, [], False, options["description_limit"], options["follow_symlinks"])
    base = optimize.merge_plans(mcp, rules, offload, skills)
    if offload["writes"]:  # the offload dealt with the long CLAUDE.md that plan_rules could not split
        base["warnings"] = [warning for warning in base["warnings"] if not warning.startswith("rules: CLAUDE.md")]
    if options["dedupe_plugins"]:
        dedupe = linkdedupe.plan_dedupe(root)
        twins = {pathlib.PurePosixPath(link).name for link in dedupe["remove_links"]}
        base = optimize.merge_plans(
            base, dedupe,
            linkdedupe.plan_plugin_skills(root, options["description_limit"],
                                          idle_plugin_selector(usage, threshold, twins)))
    if not usage["sessions"]:
        base["notes"].append("usage: no session logs found for this root; usage-based steps were skipped")
    if options["scope_rules"]:
        base = optimize.merge_plans(base, plan_idle_rules(root, threshold))
    base = optimize.merge_plans(base, plan_idle_skills(root, usage, threshold, base))
    upgrades, records = plan_upgrades(root, base, options["min_score"], options["follow_symlinks"],
                                      options["extract_scripts"], options["add_paths"])
    still_low = [record for record in records if record["after"] < options["min_score"]]
    advice = _unused_plugins(root, usage) if options["dedupe_plugins"] else []
    unscoped = [] if options["scope_rules"] else big_rules(root, threshold)
    if unscoped:
        advice.append(f"{len(unscoped)} rule file(s) load on every turn and cost about "
                      f"{sum(_tokens(text) for _, text in unscoped)} tokens. --scope-rules makes them load on the "
                      f"first file touched instead; leave it off for rules about how to talk or answer.")
    long_blocks = _long_blocks(root) if not options["extract_scripts"] else 0
    if long_blocks:
        advice.append(f"{long_blocks} shell block(s) of {LONG_SCRIPT_LINES}+ lines sit inline in skills. "
                      f"--extract-scripts moves them to scripts/; review the result, since examples become script calls.")
    if still_low:
        advice.append(f"{len(still_low)} of {len(records)} low-scoring skills and subagents are still under "
                      f"{options['min_score']}: they lack sections the rubric wants (When to use, Procedure, "
                      f"Pitfalls, Verification). Those need writing, not rewriting; see `tq-forge score`.")
    extras = {
        "telemetry": {"sessions": usage["sessions"], "megabytes_read": round(usage["bytes"] / 1_048_576, 1),
                      "skills_invoked": len(usage["skills"])},
        "scores": {"min_score": options["min_score"], "below_before": len(records),
                   "below_after": len(still_low), "records": records},
        "recommendations": advice,
    }
    return optimize.merge_plans(base, upgrades), extras


def render(report):
    lines = [optimize.render(report).replace("tq-forge optimize", "tq-forge auto-improve", 1), ""]
    seen, scores = report["telemetry"], report["scores"]
    lines.append(f"usage: {seen['sessions']} session log(s), {seen['megabytes_read']} MB read, "
                 f"{seen['skills_invoked']} distinct skills invoked")
    lines.append(f"scores: {scores['below_before']} artifact(s) under {scores['min_score']} before, "
                 f"{scores['below_after']} after")
    lines.extend(f"> {item}" for item in report["recommendations"])
    return "\n".join(lines)


def run(args):
    root = pathlib.Path(args.root).expanduser().resolve()
    if not root.is_dir():
        raise scaffold.ScaffoldError(f"not a directory: {root}")
    inventory = context_cost.load_json(pathlib.Path(args.mcp_inventory)) if args.mcp_inventory else None
    options = {"threshold": args.threshold, "min_score": args.min_score,
               "description_limit": args.description_limit, "follow_symlinks": args.follow_symlinks,
               "dedupe_plugins": args.dedupe_plugins, "scope_rules": args.scope_rules,
               "keep_mcp": optimize._names(args.keep_mcp), "extract_scripts": args.extract_scripts,
               "add_paths": args.add_paths}
    plan, extras = build_plan(root, options)
    report = optimize.build_report(root, plan, inventory, args.apply and not args.dry_run,
                                   args.dedupe_plugins, args.listing_budget)
    return {**report, **extras}


def build_parser():
    parser = argparse.ArgumentParser(prog="auto-improve", description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=".", help="project root (default: current directory; ~ for your user setup)")
    parser.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and write nothing (wins over --apply)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--follow-symlinks", action="store_true",
                        help="also compact skills behind symlinks and in .agents/skills/")
    parser.add_argument("--dedupe-plugins", action="store_true",
                        help="scan .claude/plugins/: unlink skills a plugin also loads, compact idle plugin skills")
    parser.add_argument("--threshold", type=int, default=THRESHOLD_TOKENS, metavar="TOKENS",
                        help=f"per-turn cost above which an unused item is treated as bloat (default {THRESHOLD_TOKENS})")
    parser.add_argument("--min-score", type=int, default=MIN_SCORE, metavar="SCORE",
                        help=f"rubric score below which a skill or subagent is upgraded (default {MIN_SCORE})")
    parser.add_argument("--description-limit", type=int, default=DESCRIPTION_LIMIT, metavar="CHARS",
                        help=f"longest skill description to keep (default {DESCRIPTION_LIMIT})")
    parser.add_argument("--keep-mcp", help="MCP servers to leave in .mcp.json")
    parser.add_argument("--scope-rules", action="store_true",
                        help="give always-loaded rule files over the threshold `paths:` so they load on the "
                             "first file touched, not on every turn")
    parser.add_argument("--add-paths", action="store_true",
                        help="also give low-scoring skills `paths:` for the file types their description names "
                             "(review the result)")
    parser.add_argument("--extract-scripts", action="store_true",
                        help="also move long shell blocks of low-scoring skills into scripts/ (review the result)")
    parser.add_argument("--mcp-inventory", help="JSON file with each MCP server's tool names and instructions")
    parser.add_argument("--listing-budget", type=int, metavar="CHARS",
                        help="cap skill-listing descriptions at this many characters, as Claude Code does")
    return parser


def main(argv):
    args = build_parser().parse_args(argv[1:])
    try:
        report = run(args)
    except scaffold.ScaffoldError as error:
        print(f"auto-improve: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
