"""Deterministic scaffolder for Claude Code artifacts (Python stdlib only).

Same input, same output, no model call. It writes structure and frontmatter;
judgment-heavy content is left as `TODO(tq-forge)` markers, which the scorer
penalises until they are filled in.

    scaffold.py skill  "<intent>" [--model M] [--effort E] [--name N]
    scaffold.py agent  "<intent>" [--model M] [--effort E] [--name N]
    scaffold.py agent  --template <name> [--model M] [--effort E] [--name N]
    scaffold.py hooks  [--events PreToolUse,Stop]
    scaffold.py mcp    --name N (--url U [--token-env VAR] | --command C [--arg A]...)
                       [--scope project|subagent] [--model M] [--effort E]
    scaffold.py mcp    --example
    scaffold.py list

Common options: --out DIR (project root to write into), --force, --json.
Without --out, skills go to the tq-forge sandbox and everything else to
$TQ_FORGE_HOME/sandbox/project, so nothing lands in a live project by accident.
"""

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import frontmatter  # noqa: E402
import models  # noqa: E402
import schema  # noqa: E402

TEMPLATES = models.TEMPLATES
SLUG_MAX = 32
INTENT_MAX = 300
TITLE_MAX = 60
DEFAULT_AGENT_TOOLS = "Read, Grep, Glob, Bash"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
TOKEN_RE = re.compile(r"\{\{([A-Z_]+)\}\}")
STOPWORDS = frozenset({
    "a", "an", "the", "that", "which", "to", "for", "of", "my", "me", "our", "and",
    "skill", "agent", "subagent", "command", "every", "each", "all", "please", "make",
    "build", "create", "forge", "it", "is", "in", "on", "with",
})
HOOK_SCRIPTS = {
    "PreToolUse": "pre-tool-use.sh",
    "PostToolUse": "post-tool-use.sh",
    "SessionStart": "session-start.sh",
    "Stop": "stop.sh",
}


class ScaffoldError(Exception):
    """A user-facing problem with the request; printed without a traceback."""


# ---------------------------------------------------------------- helpers

def clean_intent(words):
    text = re.sub(r"\s+", " ", " ".join(words)).strip()
    text = "".join(ch for ch in text if ch.isprintable())
    if not re.search(r"[A-Za-z0-9]", text):
        raise ScaffoldError("give a one-line intent, for example: skill \"summarize open pull requests\"")
    return text[:INTENT_MAX].rstrip(" .")


def slugify(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    kept = [word for word in words if word not in STOPWORDS] or words
    slug = ""
    for word in kept:
        candidate = f"{slug}-{word}" if slug else word
        if len(candidate) > SLUG_MAX:
            break
        slug = candidate
    return slug or kept[0][:SLUG_MAX]


def checked_name(name):
    if not NAME_RE.match(name):
        raise ScaffoldError(f"invalid name '{name}': use lowercase letters, digits and hyphens")
    return name


def sentence(text):
    return text[:1].upper() + text[1:]


def resolve_profile(model, effort):
    model_id = models.resolve(model) if model else models.default_model()
    if not model_id:
        known = ", ".join(models.known_ids())
        raise ScaffoldError(f"unknown model '{model}'. Known models: {known}")
    profile = models.profile(model_id)
    chosen = effort or profile["effort"]
    if chosen not in models.effort_levels():
        raise ScaffoldError(f"unknown effort '{chosen}'. Use one of: {', '.join(models.effort_levels())}")
    return profile, chosen


def state_home():
    return pathlib.Path(os.environ.get("TQ_FORGE_HOME") or pathlib.Path.home() / ".tq-forge")


def project_root(out):
    return pathlib.Path(out) if out else state_home() / "sandbox" / "project"


def render(template_name, values):
    text = (TEMPLATES / template_name).read_text(encoding="utf-8")

    def substitute(match):
        key = match.group(1)
        if key not in values:
            raise ScaffoldError(f"template {template_name} needs a value for {key}")
        return values[key]

    return TOKEN_RE.sub(substitute, text)


def write_file(path, content, force, executable=False):
    if path.exists() and not force:
        if path.read_text(encoding="utf-8", errors="replace") == content:
            return False
        raise ScaffoldError(f"{path} already exists with different content; pass --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    if executable:
        temporary.chmod(0o755)
    temporary.replace(path)
    return True


def load_json_object(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ScaffoldError(f"{path} is not valid JSON ({error}); fix it before merging into it")
    if not isinstance(data, dict):
        raise ScaffoldError(f"{path} must hold a JSON object")
    return data


def set_frontmatter_field(text, key, value):
    """Replace one top-level scalar field inside the frontmatter block."""
    block, body = frontmatter.split(text)
    if block is None:
        raise ScaffoldError("template has no frontmatter")
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    line = f"{key}: {value}"
    block = pattern.sub(lambda _: line, block, count=1) if pattern.search(block) else f"{block}\n{line}"
    return f"---\n{block}\n---\n{body}"


# ---------------------------------------------------------------- commands

def scaffold_skill(args):
    intent = clean_intent(args.intent)
    name = checked_name(args.name or slugify(intent))
    profile, effort = resolve_profile(args.model, args.effort)
    description = f'{sentence(intent)}. Use when asked for "/{name}" or to {intent}.'
    content = render("skill-scaffold.md.tmpl", {
        "NAME": name,
        "DESCRIPTION": json.dumps(description, ensure_ascii=False),
        "MODEL": profile["id"],
        "EFFORT": effort,
        "TITLE": sentence(intent)[:TITLE_MAX],
        "INTENT": intent,
        "TAG": name.split("-")[0],
    })
    if args.out:
        path = pathlib.Path(args.out) / ".claude" / "skills" / name / "SKILL.md"
    else:
        path = state_home() / "sandbox" / "forged-skills" / name / "SKILL.md"
    write_file(path, content, args.force)
    return {"kind": "skill", "name": name, "model": profile["id"], "effort": effort,
            "files": [str(path)], "score_target": str(path.parent)}


def _builtin_agent(args):
    template = args.template
    source = TEMPLATES / "agents" / f"{template}.md"
    if not NAME_RE.match(template) or not source.is_file():
        raise ScaffoldError(f"unknown agent template '{template}'. Available: {', '.join(agent_templates())}")
    text = source.read_text(encoding="utf-8")
    fields, _, _ = frontmatter.read(text)
    name = checked_name(args.name) if args.name else fields["name"]
    model, effort = fields.get("model"), fields.get("effort")
    if args.model or args.effort:
        profile, effort = resolve_profile(args.model or model, args.effort or (None if args.model else effort))
        model = profile["id"]
        text = set_frontmatter_field(text, "model", model)
        text = set_frontmatter_field(text, "effort", effort)
    if args.name:
        text = set_frontmatter_field(text, "name", name)
    return name, model, effort, text


def _custom_agent(args):
    intent = clean_intent(args.intent)
    name = checked_name(args.name or slugify(intent))
    profile, effort = resolve_profile(args.model, args.effort)
    description = f"{sentence(intent)}. Use when the task is to {intent}."
    text = render("agents/_custom.md.tmpl", {
        "NAME": name,
        "DESCRIPTION": json.dumps(description, ensure_ascii=False),
        "MODEL": profile["id"],
        "EFFORT": effort,
        "TOOLS": DEFAULT_AGENT_TOOLS,
        "INTENT": intent,
        "SNIPPETS": "\n\n".join(models.snippet(item) for item in profile["snippets"]),
    })
    return name, profile["id"], effort, text


def scaffold_agent(args):
    if args.template and args.intent:
        raise ScaffoldError("give either an intent or --template, not both")
    name, model, effort, text = _builtin_agent(args) if args.template else _custom_agent(args)
    tools_val = getattr(args, "allowed_tools", None) or getattr(args, "tools", None)
    if tools_val:
        text = set_frontmatter_field(text, "tools", tools_val)
    if getattr(args, "isolated", False) or getattr(args, "isolation", None):
        isolation = getattr(args, "isolation", None) or "worktree"
        text = set_frontmatter_field(text, "isolation", isolation)
        perm = getattr(args, "permission_mode", None) or "plan"
        text = set_frontmatter_field(text, "permissionMode", perm)
        mem = getattr(args, "memory", None) or "project"
        text = set_frontmatter_field(text, "memory", mem)
    else:
        if getattr(args, "permission_mode", None):
            text = set_frontmatter_field(text, "permissionMode", args.permission_mode)
        if getattr(args, "memory", None):
            text = set_frontmatter_field(text, "memory", args.memory)
    path = project_root(args.out) / ".claude" / "agents" / f"{name}.md"
    write_file(path, text, args.force)
    return {"kind": "subagent", "name": name, "model": model, "effort": effort,
            "template": args.template or "custom", "files": [str(path)], "score_target": str(path)}


def _merge_hook_groups(existing, incoming):
    """Append each incoming matcher group whose command is not registered yet."""
    known = {handler.get("command") for group in existing if isinstance(group, dict)
             for handler in group.get("hooks", []) if isinstance(handler, dict)}
    fresh = [group for group in incoming
             if not all(handler.get("command") in known for handler in group["hooks"])]
    return [*existing, *fresh]


def scaffold_hooks(args):
    events = [item.strip() for item in args.events.split(",") if item.strip()] if args.events \
        else list(HOOK_SCRIPTS)
    unknown = [event for event in events if event not in HOOK_SCRIPTS]
    if unknown:
        raise ScaffoldError(f"cannot scaffold {', '.join(unknown)}. Supported: {', '.join(HOOK_SCRIPTS)}")
    root = project_root(args.out)
    files = []
    for event in events:
        script = HOOK_SCRIPTS[event]
        target = root / ".claude" / "hooks" / script
        write_file(target, (TEMPLATES / "hooks" / script).read_text(encoding="utf-8"),
                   args.force, executable=True)
        files.append(str(target))

    template = json.loads((TEMPLATES / "hooks" / "settings.hooks.json").read_text(encoding="utf-8"))
    settings_path = root / ".claude" / "settings.json"
    settings = load_json_object(settings_path)
    current = settings.get("hooks") if isinstance(settings.get("hooks"), dict) else {}
    merged = {**current}
    for event in events:
        existing = current.get(event) if isinstance(current.get(event), list) else []
        merged[event] = _merge_hook_groups(existing, template["hooks"][event])
    write_file(settings_path, json.dumps({**settings, "hooks": merged}, indent=2) + "\n", True)
    files.append(str(settings_path))
    blocking = {event: schema.SCAFFOLDED_HOOK_EVENTS[event] for event in events}
    return {"kind": "hooks", "events": events, "exit_2_blocks": blocking,
            "files": files, "check_target": str(settings_path)}


def _remote_server(args):
    url = args.url
    parsed = urllib.parse.urlsplit(url.split("${", 1)[0] if url.startswith("${") else url)
    if "@" in parsed.netloc:
        raise ScaffoldError("do not put credentials in the URL; use --token-env VAR")
    local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    if not url.startswith("${") and parsed.scheme != "https" and not (parsed.scheme == "http" and local):
        raise ScaffoldError("use an https:// URL (http:// is accepted only for localhost)")
    server = {"type": args.transport or "http", "url": url}
    if args.token_env:
        if not ENV_NAME_RE.match(args.token_env):
            raise ScaffoldError("--token-env takes an environment variable NAME, not a value")
        server["headers"] = {"Authorization": "Bearer ${" + args.token_env + "}"}
    return server


def _local_server(args):
    server = {"type": "stdio", "command": args.command, "args": list(args.arg or [])}
    passed = args.env_var or []
    bad = [item for item in passed if not ENV_NAME_RE.match(item)]
    if bad:
        raise ScaffoldError(f"--env-var takes variable NAMES, got: {', '.join(bad)}")
    if passed:
        server["env"] = {item: "${" + item + "}" for item in passed}
    return server


def _yaml_server_block(name, server):
    lines = [f"  - {name}:"]
    for key, value in server.items():
        if isinstance(value, dict):
            lines.append(f"      {key}:")
            lines.extend(f"        {inner}: {json.dumps(text)}" for inner, text in value.items())
        else:
            lines.append(f"      {key}: {json.dumps(value)}")
    return "\n".join(lines)


def _mcp_servers(args):
    if args.example:
        example = json.loads((TEMPLATES / "mcp" / "project.mcp.json").read_text(encoding="utf-8"))
        return example["mcpServers"]
    if not args.name or not SERVER_NAME_RE.match(args.name):
        raise ScaffoldError("--name is required: letters, digits, hyphens and underscores")
    if bool(args.url) == bool(args.command):
        raise ScaffoldError("give exactly one of --url (remote server) or --command (local server)")
    return {args.name: _remote_server(args) if args.url else _local_server(args)}


def scaffold_mcp(args):
    servers = _mcp_servers(args)
    root = project_root(args.out)
    if args.scope == "project":
        path = root / ".mcp.json"
        config = load_json_object(path)
        current = config.get("mcpServers") if isinstance(config.get("mcpServers"), dict) else {}
        clash = [name for name in servers if name in current and current[name] != servers[name]]
        if clash and not args.force:
            raise ScaffoldError(f"{path} already defines {', '.join(clash)}; pass --force to replace")
        write_file(path, json.dumps({**config, "mcpServers": {**current, **servers}}, indent=2) + "\n", True)
        return {"kind": "mcp", "scope": "project", "servers": list(servers),
                "files": [str(path)], "check_target": str(path)}

    if args.example:
        raise ScaffoldError("--example writes a project .mcp.json; use it without --scope subagent")
    profile, effort = resolve_profile(args.model, args.effort)
    agent = checked_name(args.agent_name or f"{args.name.lower().replace('_', '-')}-agent")
    description = (f"Works with the {args.name} MCP server in isolation. Use when a task needs "
                   f"{args.name} tools without loading them into the main conversation.")
    text = render("mcp/subagent-isolated.md.tmpl", {
        "NAME": agent, "DESCRIPTION": json.dumps(description), "MODEL": profile["id"],
        "EFFORT": effort, "SERVER": args.name,
        "SERVER_BLOCK": _yaml_server_block(args.name, servers[args.name]),
    })
    path = root / ".claude" / "agents" / f"{agent}.md"
    write_file(path, text, args.force)
    return {"kind": "mcp", "scope": "subagent", "servers": list(servers), "name": agent,
            "model": profile["id"], "effort": effort, "files": [str(path)], "score_target": str(path)}


def agent_templates():
    return sorted(path.stem for path in (TEMPLATES / "agents").glob("*.md")
                  if not path.name.startswith("_"))


def list_all(_args):
    registry = models.registry()
    return {"kind": "list", "default_model": registry["default"],
            "models": {model_id: {key: profile[key] for key in ("alias", "role", "effort")}
                       for model_id, profile in registry["models"].items()},
            "agent_templates": agent_templates(), "hook_events": list(HOOK_SCRIPTS), "files": []}


# ---------------------------------------------------------------- cli

def build_parser():
    parser = argparse.ArgumentParser(prog="scaffold", description="Deterministic tq-forge scaffolder.")
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name, handler, intent=False, model=False):
        sub = commands.add_parser(name)
        sub.set_defaults(handler=handler)
        sub.add_argument("--out", help="project root to write into (default: the tq-forge sandbox)")
        sub.add_argument("--force", action="store_true", help="overwrite existing files")
        sub.add_argument("--json", action="store_true", help="machine-readable result")
        if intent:
            sub.add_argument("intent", nargs="*", help="one-line description of what to build")
        if model:
            sub.add_argument("--model", help="target model id or alias")
            sub.add_argument("--effort", help="effort level for the frontmatter")
            sub.add_argument("--name", help="explicit name (lowercase, hyphenated)")
        return sub

    add("skill", scaffold_skill, intent=True, model=True)
    agent_cmd = add("agent", scaffold_agent, intent=True, model=True)
    agent_cmd.add_argument("--template", help="built-in agent template (see: scaffold list)")
    agent_cmd.add_argument("--isolation", choices=("worktree",), help="isolation mode for subagent")
    agent_cmd.add_argument("--permission-mode", choices=sorted(schema.PERMISSION_MODES), help="permissionMode for subagent")
    agent_cmd.add_argument("--memory", choices=sorted(schema.MEMORY_SCOPES), help="memory scope (project, user, local)")
    agent_cmd.add_argument("--tools", help="comma-separated tools")
    agent_cmd.add_argument("--allowed-tools", help="alias for --tools")
    agent_cmd.add_argument("--isolated", action="store_true", help="scaffold with worktree isolation, plan mode, and project memory")
    add("hooks", scaffold_hooks).add_argument(
        "--events", help="comma-separated subset of: " + ", ".join(HOOK_SCRIPTS))
    mcp = add("mcp", scaffold_mcp, model=True)
    mcp.add_argument("--scope", choices=("project", "subagent"), default="project")
    mcp.add_argument("--example", action="store_true", help="write the reference .mcp.json")
    mcp.add_argument("--url", help="remote server URL (https)")
    mcp.add_argument("--transport", choices=sorted(schema.MCP_REMOTE_TRANSPORTS))
    mcp.add_argument("--token-env", help="NAME of the env var holding the bearer token")
    mcp.add_argument("--command", help="executable of a local stdio server")
    mcp.add_argument("--arg", action="append", help="argument for --command (repeatable)")
    mcp.add_argument("--env-var", action="append", help="env var NAME to pass through (repeatable)")
    mcp.add_argument("--agent-name", help="subagent file name for --scope subagent")
    add("list", list_all)
    return parser


def report(result, as_json):
    if as_json:
        print(json.dumps(result, indent=2))
        return
    if result["kind"] == "list":
        print("models:          " + ", ".join(result["models"]))
        print("agent templates: " + ", ".join(result["agent_templates"]))
        print("hook events:     " + ", ".join(result["hook_events"]))
        return
    for path in result["files"]:
        print(f"wrote {path}")
    if result.get("score_target"):
        print(f"next: quality-score.sh {result['score_target']}")
    if result.get("check_target"):
        print(f"next: dry-test.sh {result['check_target']}")


def main(argv):
    args = build_parser().parse_args(argv[1:])
    try:
        result = args.handler(args)
    except ScaffoldError as error:
        print(f"scaffold: {error}", file=sys.stderr)
        return 1
    report(result, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
