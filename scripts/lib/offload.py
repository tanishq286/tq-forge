"""Lossless CLAUDE.md slimming for the context optimizer (Python stdlib only).

A long CLAUDE.md usually mixes two kinds of text. Routing is what Claude needs
on every turn: rules, tables, short lists, command triggers. Prose is the
explanation around it: paragraphs, long examples, long list items.

`plan_prose` keeps the routing where it is and moves only the prose into an
on-demand skill (`reference.md`). Every section that loses anything is copied
to reference.md whole, so the full original wording is one skill load away and
the optimizer's nothing-lost check holds.

It runs only on a CLAUDE.md over LINE_LIMIT lines, and only when the result is
shorter.
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import auto_improve  # noqa: E402
import context_cost  # noqa: E402
import optimize  # noqa: E402

LINE_LIMIT = 80
ITEM_LIMIT = 160
TRIGGER_LIMIT = 480  # the longest paragraph still read as a trigger when it names a tool or command
CODE_KEEP_LINES = 3
_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_HEADING = re.compile(r"^#{1,6}\s")


def _take_fence(lines, start):
    """Lines of the fenced block that opens at `start`, including both fences."""
    end = start + 1
    while end < len(lines) and not lines[end].lstrip().startswith("```"):
        end += 1
    return lines[start:end + 1]


def _take_item(lines, start):
    """A list item with its indented continuation lines."""
    end = start + 1
    while end < len(lines) and lines[end].strip() and lines[end][:1].isspace() and not _ITEM.match(lines[end]):
        end += 1
    return lines[start:end]


def _take_paragraph(lines, start):
    """Consecutive plain lines: everything up to a blank line, heading, list item, table row or fence."""
    end = start + 1
    while end < len(lines) and lines[end].strip() and not _HEADING.match(lines[end]) and not _ITEM.match(lines[end]) \
            and not lines[end].lstrip().startswith(("|", "```")):
        end += 1
    return lines[start:end]


def _tidy(lines):
    """Drop sub-headings left with nothing under them, and runs of blank lines."""
    kept = []
    for index, line in enumerate(lines):
        if _HEADING.match(line) and index:
            rest = [later for later in lines[index + 1:] if later.strip()]
            if not rest or _HEADING.match(rest[0]):
                continue
        if not line.strip() and kept and not kept[-1].strip():
            continue
        kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    return kept


def trim_section(section):
    """Return (routing text or "" when nothing is left, whether anything was moved)."""
    lines = section.splitlines()
    kept, moved, index = [lines[0]], False, 1
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith("```"):
            block = _take_fence(lines, index)
            keep = len(block) - 2 <= CODE_KEEP_LINES
        elif _ITEM.match(line):
            block = _take_item(lines, index)
            # A short rule is still a rule when the file hard-wraps it; only a long item is prose.
            keep = len(" ".join(part.strip() for part in block)) <= ITEM_LIMIT
        elif not line.strip() or _HEADING.match(line) or line.lstrip().startswith("|"):
            block, keep = [line], True
        else:
            block = _take_paragraph(lines, index)
            text = " ".join(part.strip() for part in block)
            short_label = len(block) == 1 and line.lstrip().startswith("**") and len(line) <= ITEM_LIMIT
            # A short paragraph that names a tool or command in backticks is a trigger, not an explanation.
            keep = short_label or ("`" in text and len(text) <= TRIGGER_LIMIT)
        if keep:
            kept.extend(block)
        else:
            moved = True
        index += len(block)
    kept = _tidy(kept)
    return ("\n".join(kept) if len(kept) > 1 else ""), moved


def plan_prose(root, text=None):
    """Move the prose of an oversized CLAUDE.md into an on-demand skill, keeping every table and rule."""
    plan = optimize.new_plan()
    text = context_cost.read_text(root / "CLAUDE.md") if text is None else text
    original = len(text.splitlines())
    if original <= LINE_LIMIT:
        plan["notes"].append(f"prose: CLAUDE.md is within {LINE_LIMIT} lines")
        return plan
    reason = optimize.skip_reason(root, "CLAUDE.md")
    if reason:
        plan["warnings"].append(f"prose: CLAUDE.md {reason}; left unchanged")
        return plan
    lines = text.splitlines()
    hygiene = [line for line in lines if line.startswith(optimize.HYGIENE_MARK)]
    preamble, sections = optimize.split_sections("\n".join(line for line in lines if line not in hygiene))
    kept, trimmed = [], []
    for title, section in sections:
        core = auto_improve.KEEP_TITLE.search(title) and \
            context_cost.estimate_tokens(section) <= auto_improve.KEEP_SECTION_TOKENS
        routing, moved = (section, False) if core or title == auto_improve.POINTER_TITLE else trim_section(section)
        if routing:
            kept.append(routing)
        if moved:
            trimmed.append((title, section))
    name = auto_improve.FLOW_SKILL if auto_improve.FLOW_MARK.search(text) else auto_improve.GENERIC_SKILL
    folder = f".claude/skills/{name}"
    taken = (root / folder / "SKILL.md").exists() or (root / folder / "reference.md").exists()
    if not trimmed or taken:
        why = "holds no prose to move" if not trimmed else f"{folder} already exists"
        plan["warnings"].append(f"prose: CLAUDE.md is {original} lines but {why}; left unchanged")
        return plan
    pointer = (f"## {auto_improve.POINTER_TITLE}\n\nThe explanations and long examples for {len(trimmed)} "
               f"sections are in the `{name}` skill. The rules, tables and triggers above are complete; "
               f"load the skill when you need the detail.")
    lean = optimize.join_markdown([preamble, *kept, pointer, *hygiene])
    if len(lean.splitlines()) >= original:
        plan["notes"].append("prose: CLAUDE.md is already mostly rules and tables; left unchanged")
        return plan
    titles = [title for title, _ in trimmed]
    plan["writes"][f"{folder}/reference.md"] = optimize.join_markdown([
        f"# {name} reference",
        "The full text of the CLAUDE.md sections whose prose `tq-forge optimize` moved out. "
        "CLAUDE.md keeps their rules, tables and triggers.",
        *[section for _, section in trimmed]])
    plan["writes"][f"{folder}/SKILL.md"] = auto_improve._reference_skill(name, titles, ())
    plan["writes"]["CLAUDE.md"] = lean
    plan["notes"].append(f"prose: CLAUDE.md {original} -> {len(lean.splitlines())} lines "
                         f"({context_cost.estimate_tokens(text)} -> {context_cost.estimate_tokens(lean)} tokens); "
                         f"prose of {len(trimmed)} sections -> {folder}/reference.md")
    return plan
