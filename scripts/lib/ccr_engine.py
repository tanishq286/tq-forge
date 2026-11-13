"""Reversible compression for large tool output (Python stdlib only).

Each shaper stores the full text in the CCR store and returns a short form that
ends with a `[CCR-ID: ...]` line, so nothing is lost: `tq-forge retrieve <id>`
prints the original, a line range of it, or the lines matching a keyword.

  smart_crush_json    a long list of records becomes a schema, the first rows and a count
  compress_code_ast   source becomes its imports, assignments and definition lines
  rtk_shape_logs      a log loses colour codes, blank lines and repeated lines
  retrieve_ccr        the stored text for an id, optionally a line range or a keyword

The store is ~/.claude/tq-forge-ccr/ (owner-only; entries older than a week are
deleted on the next store). This file is also copied next to the installed mod
runtime, so it imports nothing else from tq-forge.

Usage: ccr_engine.py <ccr_id> [--lines A:B] [--search KW]
"""

import argparse
import ast
import hashlib
import json
import os
import pathlib
import re
import sys
import time

USER_HOME = pathlib.Path(os.environ.get("TQ_FORGE_USER_HOME") or pathlib.Path.home())
CCR_DIR = USER_HOME / ".claude" / "tq-forge-ccr"
CCR_ID_PATTERN = r"^[a-f0-9]{12}$"
CCR_ID_RE = re.compile(CCR_ID_PATTERN)
LINES_RE = re.compile(r"^(\d+):(\d+)$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
SIGNATURE_RE = re.compile(r"^\s*(export\s+|import\s+|def\s+|class\s+|function\s+|interface\s+|type\s+"
                          r"|pub\s+fn\s+|fn\s+|func\s+)")
CLI = "npx tq-forge retrieve"
CHARS_PER_TOKEN = 4
KEEP_SECONDS = 7 * 24 * 3600
MIN_CODE_TOKENS = 500
MAX_JSON_ROWS = 15
MAX_OUTLINE_LINES = 120
MAX_LOG_LINES = 80
DEPENDENCY_LINES_KEPT = 15
EXIT_INVALID, EXIT_NOT_FOUND = 2, 1


class CCRError(ValueError):
    """A CCR id or a --lines range that is not valid."""


class CCRNotFound(CCRError):
    """A well-formed CCR id with nothing stored under it."""


def _tokens(text):
    return len(text) // CHARS_PER_TOKEN


def valid_ccr_id(ccr_id):
    """True for exactly twelve lowercase hex characters (fullmatch, so a trailing newline fails too)."""
    return isinstance(ccr_id, str) and CCR_ID_RE.fullmatch(ccr_id) is not None


def _footer(ccr_id, before, after, hint=""):
    return f"[CCR-ID: {ccr_id} | {before}->{after} tokens | Retrieve: {CLI} {ccr_id}{hint}]"


def _prune(directory):
    cutoff = time.time() - KEEP_SECONDS
    for old in directory.glob("*.json"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass


def store_ccr(content, kind="raw", directory=None):
    """Save `content` (owner-only) and return its id: the first 12 hex characters of its SHA-256."""
    directory = pathlib.Path(directory or CCR_DIR)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    _prune(directory)
    ccr_id = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:12]
    entry = {"id": ccr_id, "kind": kind, "timestamp": int(time.time()), "content": content}
    target = directory / f"{ccr_id}.json"
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.touch(mode=0o600, exist_ok=True)
    temporary.write_text(json.dumps(entry), encoding="utf-8")
    temporary.replace(target)
    return ccr_id


def _parse_lines(lines):
    match = LINES_RE.fullmatch(str(lines))
    start, end = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
    if start < 1 or end < start:
        raise CCRError(f"--lines takes START:END with 1 <= START <= END, not '{lines}'")
    return start, end


def retrieve_ccr(ccr_id, lines=None, search=None, directory=None):
    """The text stored under `ccr_id`: all of it, lines START:END (1-based, inclusive), or the lines
    containing `search` (case-insensitive, numbered). Both together search inside the range."""
    if not valid_ccr_id(ccr_id):
        raise CCRError(f"not a CCR id (expected {CCR_ID_PATTERN}): {str(ccr_id)[:40]!r}")
    span = _parse_lines(lines) if lines else None
    path = pathlib.Path(directory or CCR_DIR) / f"{ccr_id}.json"
    try:
        content = json.loads(path.read_text(encoding="utf-8")).get("content", "")
    except (OSError, ValueError, AttributeError) as error:
        raise CCRNotFound(f"CCR id {ccr_id} is not in {path.parent} (entries are kept for a week)") from error
    if not span and not search:
        return content
    numbered = list(enumerate(str(content).splitlines(), 1))
    if span:
        numbered = numbered[span[0] - 1:span[1]]
    if search:
        needle = search.lower()
        return "\n".join(f"{number}: {line}" for number, line in numbered if needle in line.lower())
    return "\n".join(line for _, line in numbered)


def _crush(value, max_rows):
    if isinstance(value, dict):
        return {key: _crush(item, max_rows) for key, item in value.items()
                if item not in (None, "", [], {}) and not (isinstance(item, str) and item.startswith("data:image/"))}
    if isinstance(value, list):
        if len(value) > 3 and all(isinstance(row, dict) for row in value):
            shown = value[:max_rows]
            keys = list(dict.fromkeys(key for row in shown for key in row))
            table = {"_schema": keys, "_rows": [[_crush(row.get(key), max_rows) for key in keys] for row in shown],
                     "_total_rows": len(value)}
            return {**table, "_elided_rows": len(value) - max_rows} if len(value) > max_rows else table
        return [_crush(item, max_rows) for item in value[:max_rows]]
    return value


def smart_crush_json(raw_json, max_rows=MAX_JSON_ROWS, directory=None):
    """Compact JSON whose lists of records are cut to a schema and `max_rows` rows. Not JSON: returned as is."""
    try:
        data = json.loads(raw_json)
    except (TypeError, ValueError):
        return raw_json
    ccr_id = store_ccr(raw_json, "json", directory)
    crushed = json.dumps(_crush(data, max_rows), separators=(",", ":"), ensure_ascii=False)
    return f"{crushed}\n{_footer(ccr_id, _tokens(raw_json), _tokens(crushed), ' --search KEYWORD')}"


def _python_outline(source, ccr_id):
    lines = source.splitlines()
    kept = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign)):
            kept.append(f"L{node.lineno}: {lines[node.lineno - 1]}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = getattr(node, "end_lineno", node.lineno)
            kept.append(f"L{node.lineno}: {lines[node.lineno - 1]}  # body: lines {node.lineno}-{end} in CCR {ccr_id}")
    return kept


def compress_code_ast(source, filename="file.py", directory=None):
    """An outline of a source file: top-level imports, assignments and definitions with their line numbers.
    Python is parsed; other languages (and Python that does not parse) are matched line by line.
    Source under 500 tokens is returned as is."""
    before = _tokens(source)
    if before < MIN_CODE_TOKENS:
        return source
    ccr_id = store_ccr(source, "code", directory)
    kept = None
    if filename.endswith(".py"):
        try:
            kept = _python_outline(source, ccr_id)
        except (SyntaxError, ValueError, RecursionError):
            kept = None
    if kept is None:
        kept = [f"L{number}: {line}" for number, line in enumerate(source.splitlines(), 1) if SIGNATURE_RE.match(line)]
    if len(kept) > MAX_OUTLINE_LINES:
        kept = [*kept[:MAX_OUTLINE_LINES], f"... [{len(kept) - MAX_OUTLINE_LINES} more definitions]"]
    outline = "\n".join(kept)
    return f"{outline}\n{_footer(ccr_id, before, _tokens(outline), ' --lines START:END')}"


def rtk_shape_logs(log_text, directory=None):
    """A log without colour codes, blank lines or runs of one repeated line, cut to 80 lines."""
    ccr_id = store_ccr(log_text, "logs", directory)
    shaped, previous, count = [], None, 0
    for line in (ANSI_RE.sub("", raw) for raw in log_text.splitlines() if raw.strip()):
        if "node_modules/" in line and len(shaped) > DEPENDENCY_LINES_KEPT:
            continue
        if line == previous:
            count += 1
            continue
        if count > 1:
            shaped.append(f"  ... [repeated {count} times]")
        shaped.append(line)
        previous, count = line, 1
    if count > 1:
        shaped.append(f"  ... [repeated {count} times]")
    if len(shaped) > MAX_LOG_LINES:
        shaped = [*shaped[:MAX_LOG_LINES], f"... [{len(shaped) - MAX_LOG_LINES} more lines]"]
    out = "\n".join(shaped)
    return f"{out}\n{_footer(ccr_id, _tokens(log_text), _tokens(out), ' --search ERROR')}"


def main(argv):
    parser = argparse.ArgumentParser(prog="tq-forge retrieve", description="Print the full text behind a CCR id.")
    parser.add_argument("ccr_id", help="the 12 hex characters after `CCR-ID:`")
    parser.add_argument("--lines", metavar="A:B", help="only lines A to B (1-based, inclusive)")
    parser.add_argument("--search", metavar="KW", help="only the lines containing KW, with their line numbers")
    args = parser.parse_args(argv[1:])
    try:
        print(retrieve_ccr(args.ccr_id, args.lines, args.search))
    except CCRNotFound as error:
        print(f"retrieve: {error}", file=sys.stderr)
        return EXIT_NOT_FOUND
    except CCRError as error:
        print(f"retrieve: {error}", file=sys.stderr)
        return EXIT_INVALID
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
