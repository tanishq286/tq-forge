"""Minimal YAML-frontmatter reader for tq-forge (Python stdlib only).

It reads the subset of YAML that Claude Code documents for SKILL.md and
subagent files, which is also everything tq-forge writes:

    key: scalar                 -> str
    key: [a, b]                 -> list[str]
    key:                        -> list[str]   (block list of plain scalars)
      - a
    key: |                      -> str         (block scalar, also > |- >-)
      text
    key:                        -> Nested      (anything else, kept as raw text)
      child: value

It is not a general YAML parser. A structure it cannot classify comes back as
`Nested`, so callers can still tell that the key exists.
"""

import json
import re

_FENCE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_KEY = re.compile(r"^([A-Za-z_][\w-]*)[ \t]*:[ \t]*(.*)$")
_BLOCK_SCALARS = {"|", ">", "|-", ">-", "|+", ">+"}


class Nested(str):
    """Raw text of a nested mapping or a list of mappings."""


def split(text):
    """Return (frontmatter_text, body). frontmatter_text is None when absent."""
    match = _FENCE.match(text)
    if not match:
        return None, text
    return match.group(1), text[match.end():]


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:  # a double-quoted scalar carries escapes such as \" that must be decoded, not counted
            decoded = json.loads(value)
        except ValueError:
            return value[1:-1]
        return decoded if isinstance(decoded, str) else value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def _strip_comment(value):
    # A '#' starts a comment only at the start of the value or after whitespace.
    if value.lstrip().startswith(("'", '"')):
        return value
    return re.sub(r"(^|\s)#.*$", "", value).rstrip()


def _inline_list(value):
    inner = value.strip()[1:-1].strip()
    if not inner:
        return []
    return [_unquote(item) for item in inner.split(",") if item.strip()]


def _classify_block(lines):
    """Turn the indented lines under `key:` into a list or a Nested value."""
    content = [line for line in lines if line.strip() and not line.strip().startswith("#")]
    if not content:
        return ""
    is_plain_list = all(
        line.strip().startswith("- ") and not _KEY.match(line.strip()[2:].strip())
        for line in content
    )
    if is_plain_list:
        return [_unquote(line.strip()[2:]) for line in content]
    return Nested("\n".join(lines))


def parse(frontmatter_text):
    """Parse frontmatter text into a dict of top-level keys."""
    result = {}
    lines = (frontmatter_text or "").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip() or line.lstrip().startswith("#") or line[:1].isspace():
            continue
        match = _KEY.match(line)
        if not match:
            continue
        key, value = match.group(1), _strip_comment(match.group(2))
        block = []
        while index < len(lines) and (not lines[index].strip() or lines[index][:1].isspace()
                                      or (not value and lines[index].startswith("- "))):
            block.append(lines[index])  # YAML also allows list items flush with their key
            index += 1
        if value in _BLOCK_SCALARS:
            result[key] = " ".join(part.strip() for part in block if part.strip())
        elif value.startswith("[") and value.endswith("]"):
            result[key] = _inline_list(value)
        elif value:
            result[key] = _unquote(value)
        else:
            result[key] = _classify_block(block)
    return result


def read(text):
    """Return (fields, body, has_frontmatter) for a markdown document."""
    frontmatter_text, body = split(text)
    if frontmatter_text is None:
        return {}, body, False
    return parse(frontmatter_text), body, True


def as_list(value):
    """Normalise a tools-style field: YAML list or comma/space separated string."""
    if value is None or isinstance(value, Nested):
        return []
    if isinstance(value, list):
        return [item for item in value if item]
    return [item for item in re.split(r"[,\s]+", str(value)) if item]
