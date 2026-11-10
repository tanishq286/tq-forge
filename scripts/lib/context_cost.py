"""Estimate the always-loaded context of a Claude Code project (Python stdlib only).

"Always-loaded" means text Claude Code puts in the main conversation before
the first prompt and resends on every turn:

  claude_md   CLAUDE.md at the project root (and .claude/CLAUDE.md)
  rules       .claude/rules/**/*.md that have no `paths:` frontmatter
  skills      each skill's listing: name + description + when_to_use
  agents      each subagent's listing: name + description
  mcp         per server on the main thread: tool names + server instructions
              (what loads with MCP tool search, the Claude Code default)

Skill bodies, reference files, path-scoped rules and subagent prompts load on
demand and are not counted.

Tokens are ESTIMATED as characters / 4. There is no tokenizer in the standard
library, so treat the numbers as relative sizes. For real counts, run /context
in Claude Code before and after.

MCP tool names and instructions come from the servers themselves, not from
.mcp.json, so they are counted only when an inventory file supplies them:

    {"servers": {"github": {"instructions": "...", "tools": [{"name": "..."}]}}}
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import frontmatter  # noqa: E402

CHARS_PER_TOKEN = 4
SKILL_LISTING_CAP = 1536
HIDDEN_SKILL_STATES = frozenset({"off", "user-invocable-only"})


def estimate_tokens(text):
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def read_text(path):
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def load_json(path):
    try:
        data = json.loads(read_text(path) or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def skill_files(root):
    return sorted((root / ".claude" / "skills").glob("*/SKILL.md"))


def agent_files(root):
    return sorted((root / ".claude" / "agents").glob("*.md"))


def rule_files(root):
    return sorted((root / ".claude" / "rules").rglob("*.md"))


def _claude_md_tokens(root):
    return sum(estimate_tokens(read_text(path))
               for path in (root / "CLAUDE.md", root / ".claude" / "CLAUDE.md"))


def _rules_tokens(root):
    total = 0
    for path in rule_files(root):
        text = read_text(path)
        fields, _, _ = frontmatter.read(text)
        if not fields.get("paths"):
            total += estimate_tokens(text)
    return total


def _skills_tokens(root):
    overrides = load_json(root / ".claude" / "settings.json").get("skillOverrides")
    overrides = overrides if isinstance(overrides, dict) else {}
    total = 0
    for path in skill_files(root):
        fields, _, _ = frontmatter.read(read_text(path))
        name = str(fields.get("name") or path.parent.name)
        state = overrides.get(name, "on")
        if state in HIDDEN_SKILL_STATES:
            continue
        listing = name
        if state != "name-only":
            described = f"{fields.get('description', '')} {fields.get('when_to_use', '')}".strip()
            listing = f"{name}: {described[:SKILL_LISTING_CAP]}"
        total += estimate_tokens(listing)
    return total


def _agents_tokens(root):
    total = 0
    for path in agent_files(root):
        fields, _, _ = frontmatter.read(read_text(path))
        if fields.get("name"):
            total += estimate_tokens(f"{fields['name']}: {fields.get('description', '')}")
    return total


def _mcp_tokens(root, inventory):
    """Return (tokens, measured server names, unmeasured server names)."""
    servers = load_json(root / ".mcp.json").get("mcpServers")
    servers = servers if isinstance(servers, dict) else {}
    known = (inventory or {}).get("servers", {})
    total, measured, unmeasured = 0, [], []
    for name in servers:
        entry = known.get(name)
        if not isinstance(entry, dict):
            unmeasured.append(name)
            continue
        names = " ".join(str(tool.get("name", "")) for tool in entry.get("tools", []))
        total += estimate_tokens(f"{name}: {entry.get('instructions', '')} {names}")
        measured.append(name)
    return total, measured, unmeasured


def measure(root, inventory=None):
    """Return the estimated always-loaded context of the project at `root`."""
    root = pathlib.Path(root)
    mcp_tokens, measured, unmeasured = _mcp_tokens(root, inventory)
    parts = {
        "claude_md": _claude_md_tokens(root),
        "rules": _rules_tokens(root),
        "skills": _skills_tokens(root),
        "agents": _agents_tokens(root),
        "mcp": mcp_tokens,
    }
    return {
        "estimated_tokens": sum(parts.values()),
        "parts": parts,
        "mcp_servers_measured": measured,
        "mcp_servers_not_measured": unmeasured,
        "method": f"characters / {CHARS_PER_TOKEN}; an estimate, not a tokenizer count",
    }


def reduction_percent(before, after):
    if before <= 0:
        return 0.0
    return round((before - after) / before * 100, 1)
