"""Estimate the always-loaded context of a Claude Code project (Python stdlib only).

"Always-loaded" means text Claude Code puts in the main conversation before
the first prompt and resends on every turn:

  claude_md   CLAUDE.md at the project root (and .claude/CLAUDE.md)
  rules       .claude/rules/**/*.md that have no `paths:` frontmatter
  skills      each skill's listing: name + description + when_to_use
  agents      each subagent's listing: name + description
  mcp         per server on the main thread: tool names + server instructions
              (what loads with MCP tool search, the Claude Code default)
  plugin_skills  (only with plugins=True) the listing of every skill that an
              enabled plugin under .claude/plugins/ ships

Skill bodies, reference files, path-scoped rules and subagent prompts load on
demand and are not counted.

Tokens are ESTIMATED as characters / 4. There is no tokenizer in the standard
library, so treat the numbers as relative sizes. For real counts, run /context
in Claude Code before and after.

Claude Code trims the skill listing to a character budget (1% of the context
window): every name stays, descriptions are dropped once the budget is spent.
Pass `listing_budget` (characters) to model that; without it every description
is counted, which is an upper bound on a setup with hundreds of skills.

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


def shared_skill_files(root):
    """SKILL.md files in the cross-agent .agents/skills/ folder (the usual symlink target)."""
    return sorted((root / ".agents" / "skills").glob("*/SKILL.md"))


def agent_files(root):
    """Subagent files. Claude Code reads .claude/agents/ recursively, so this does too."""
    return sorted((root / ".claude" / "agents").rglob("*.md"))


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


def _text(path, overlay=None):
    """File text, or the planned replacement for it when `overlay` holds one."""
    planned = (overlay or {}).get(str(path.resolve()))
    return read_text(path) if planned is None else planned


def skill_name(path, overlay=None):
    fields, _, _ = frontmatter.read(_text(path, overlay))
    return str(fields.get("name") or path.parent.name)


def _described(path, overlay=None):
    fields, _, _ = frontmatter.read(_text(path, overlay))
    text = f"{fields.get('description', '')} {fields.get('when_to_use', '')}".strip()
    return " ".join(text.split())[:SKILL_LISTING_CAP]


def skill_listing(root):
    """[(name, description)] for the skills Claude Code lists from .claude/skills/."""
    overrides = load_json(root / ".claude" / "settings.json").get("skillOverrides")
    overrides = overrides if isinstance(overrides, dict) else {}
    entries = []
    for path in skill_files(root):
        name = skill_name(path)
        state = overrides.get(name, "on")
        if state in HIDDEN_SKILL_STATES:
            continue
        entries.append((name, "" if state == "name-only" else _described(path)))
    return entries


def _plugin_skill_dirs(install):
    manifest = load_json(install / ".claude-plugin" / "plugin.json") or load_json(install / "plugin.json")
    declared = manifest.get("skills", "skills")
    declared = declared if isinstance(declared, list) else [declared]
    return [install / str(item) for item in declared if isinstance(item, str)]


def plugin_skills(root):
    """Skills shipped by the enabled plugins under `root`/.claude/plugins/.

    Returns [{"plugin", "name", "path"}], one per SKILL.md, in a stable order.
    `skillOverrides` does not apply to these: Claude Code manages plugin skills
    through /plugin, so the only ways to shrink them are to edit the description
    or to disable the plugin.
    """
    plugins_dir = root / ".claude" / "plugins"
    installed = load_json(plugins_dir / "installed_plugins.json").get("plugins")
    enabled = load_json(root / ".claude" / "settings.json").get("enabledPlugins")
    enabled = enabled if isinstance(enabled, dict) else {}
    found, seen = [], set()
    for key, installs in sorted((installed if isinstance(installed, dict) else {}).items()):
        if enabled.get(key) is False or not isinstance(installs, list):
            continue
        for entry in installs:
            location = entry.get("installPath") if isinstance(entry, dict) else None
            if not isinstance(location, str):
                continue
            install = pathlib.Path(location)
            install = install if install.is_absolute() else plugins_dir / install
            for folder in _plugin_skill_dirs(install):
                for path in sorted(folder.glob("*/SKILL.md")):
                    if path.resolve() not in seen:
                        seen.add(path.resolve())
                        found.append({"plugin": key.split("@")[0], "name": skill_name(path), "path": path})
    return found


def plugin_listing(root, overlay=None):
    return [(f"{item['plugin']}:{item['name']}", _described(item["path"], overlay))
            for item in plugin_skills(root)]


def listing_tokens(entries, budget=None, spent=0):
    """Estimated tokens of a skill listing. Returns (tokens, characters of budget used).

    With a `budget`, names are always kept and descriptions are kept in order
    until the budget is used up, the way Claude Code trims an oversized listing.
    """
    if budget is None:
        return sum(estimate_tokens(f"{name}: {text}" if text else name) for name, text in entries), spent
    spent += sum(len(name) for name, _ in entries)
    total = 0
    for name, text in entries:
        kept = text[:max(0, budget - spent)]
        spent += len(kept)
        total += estimate_tokens(f"{name}: {kept}" if kept else name)
    return total, spent


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


def measure(root, inventory=None, plugins=False, listing_budget=None, plugin_root=None, overlay=None):
    """Return the estimated always-loaded context of the project at `root`.

    `plugins` adds a `plugin_skills` part for the enabled plugins' skills.
    `listing_budget` caps the skill-listing descriptions at that many characters.
    `plugin_root` and `overlay` let a preview copy be measured with the real
    project's plugins as they would read after the planned writes.
    """
    root = pathlib.Path(root)
    mcp_tokens, measured, unmeasured = _mcp_tokens(root, inventory)
    skills, spent = listing_tokens(skill_listing(root), listing_budget)
    parts = {
        "claude_md": _claude_md_tokens(root),
        "rules": _rules_tokens(root),
        "skills": skills,
        "agents": _agents_tokens(root),
        "mcp": mcp_tokens,
    }
    result = {}
    if plugins:
        entries = plugin_listing(pathlib.Path(plugin_root or root), overlay)
        parts["plugin_skills"], _ = listing_tokens(entries, listing_budget, spent)
        result["plugin_skill_count"] = len(entries)
    if listing_budget is not None:
        result["listing_budget_chars"] = listing_budget
    return {
        "estimated_tokens": sum(parts.values()),
        "parts": parts,
        **result,
        "mcp_servers_measured": measured,
        "mcp_servers_not_measured": unmeasured,
        "method": f"characters / {CHARS_PER_TOKEN}; an estimate, not a tokenizer count",
    }


def reduction_percent(before, after):
    if before <= 0:
        return 0.0
    return round((before - after) / before * 100, 1)
