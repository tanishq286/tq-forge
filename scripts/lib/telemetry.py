"""Count skill invocations in Claude Code's own session logs (Python stdlib only).

Claude Code keeps one JSONL transcript per session under
~/.claude/projects/<project>/, where <project> is the project path with every
non-alphanumeric character replaced by "-". This module reads the transcripts
that belong to a root (all of them when the root is the home folder) to answer
one question: which skills and slash commands were ever used. It counts names
only, reads nothing else from a transcript, and sends nothing anywhere.

A count of zero means "not seen in the sessions that were read", which is not
the same as "never useful". When no session was read at all (`sessions` is 0)
there is no evidence either way, and callers must not treat that as "unused".
"""

import collections
import json
import pathlib
import re

MAX_BYTES = 256 * 1024 * 1024
_SKILL_MARK = '"Skill"'
_COMMAND_MARK = "<command-name>"
_COMMAND = re.compile(r"<command-name>/?([\w:.-]+)</command-name>")
_SKILL_FALLBACK = re.compile(r'"name"\s*:\s*"Skill"\s*,\s*"input"\s*:\s*\{\s*"skill"\s*:\s*"([^"]+)"')


def _skill_calls(line):
    """Skill names invoked by the tool_use blocks in one transcript line."""
    try:
        record = json.loads(line)
    except ValueError:
        return _SKILL_FALLBACK.findall(line)
    message = record.get("message") if isinstance(record, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    names = []
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill":
            given = block.get("input")
            skill = given.get("skill") if isinstance(given, dict) else None
            if isinstance(skill, str) and skill:
                names.append(skill.lstrip("/"))
    return names


def transcripts(root, home=None):
    """Transcript files for `root`: its own .claude/projects/, plus its folder under the home one."""
    home = pathlib.Path(home) if home else pathlib.Path.home()
    encoded = re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))
    found = {}
    for path in [*(root / ".claude" / "projects").glob("*/*.jsonl"),
                 *(home / ".claude" / "projects" / encoded).glob("*.jsonl")]:
        try:
            found[path.resolve()] = path.stat()
        except OSError:
            continue
    return sorted(found, key=lambda path: found[path].st_mtime, reverse=True), found


def scan(root, max_bytes=MAX_BYTES, home=None):
    """Return {"sessions", "bytes", "skills": {name: count}} for the transcripts that belong to `root`."""
    ordered, stats = transcripts(root, home)
    counts, read, sessions = collections.Counter(), 0, 0
    for path in ordered:
        size = stats[path].st_size
        if read + size > max_bytes:
            break
        read += size
        sessions += 1
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if _SKILL_MARK in line:
                        counts.update(_skill_calls(line))
                    if _COMMAND_MARK in line:
                        counts.update(_COMMAND.findall(line))
        except OSError:
            continue
    return {"sessions": sessions, "bytes": read, "skills": dict(counts)}


def uses(usage, name, plugin=None):
    """How often a skill was invoked, under its bare name or its plugin-qualified one."""
    counts = usage.get("skills", {})
    return counts.get(name, 0) + (counts.get(f"{plugin}:{name}", 0) if plugin else 0)
