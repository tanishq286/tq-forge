"""Structural validation for tq-forge artifacts (Python stdlib only).

This is not a live LLM run. It checks that an artifact is shaped so Claude
Code will load it and so it would behave coherently when invoked.

Kinds:
  skill     SKILL.md or a directory holding one
  agent     tq-forge 5-file agent directory (AGENT.md ...)
  subagent  Claude Code subagent file (.claude/agents/<name>.md)
  mcp       an MCP config file with `mcpServers` (.mcp.json)
  hooks     a settings file with a `hooks` block (.claude/settings.json)

Usage: drytest.py <target> <json:true|false>
"""

import json
import os
import pathlib
import re
import shlex
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import frontmatter  # noqa: E402
import models  # noqa: E402
import schema  # noqa: E402

AGENT_FILES = ("AGENT.md", "system-prompt.md", "tools.json",
               "trigger-conditions.md", "example-tasks.md")
MIN_SUBAGENT_PROMPT_WORDS = 60
PASS_PERCENT = 85
WARN_PERCENT = 60
# Config kinds are loaded by Claude Code as-is, so one failed check is not a pass.
STRICT_KINDS = frozenset({"subagent", "mcp", "hooks", "config"})
ROOT_SENTINEL = "__TQ_FORGE_PROJECT_ROOT__"
PROJECT_DIR_REF = re.compile(r"\"?\$\{?CLAUDE_PROJECT_DIR\}?\"?")


class Checks:
    """Collects pass/fail results for one artifact."""

    def __init__(self):
        self.passed = 0
        self.total = 0
        self.issues = []

    def check(self, label, ok, hint=""):
        self.total += 1
        if ok:
            self.passed += 1
        else:
            self.issues.append(f"{label}: {hint}" if hint else label)


def check_skill(path, checks):
    text = path.read_text(errors="replace")
    fields, body, has_frontmatter = frontmatter.read(text)
    checks.check("frontmatter present", has_frontmatter, "missing --- ... --- block")
    if has_frontmatter:
        name = fields.get("name")
        checks.check("name field", bool(name), "name field missing or empty")
        desc = fields.get("description")
        checks.check("description field", bool(desc), "description field missing or empty")
        if desc:
            desc_len = len(str(desc))
            checks.check("description <= 1536 chars", desc_len <= 1536, f"got {desc_len} chars")
        has_tools = "allowed-tools" in fields or "tools" in fields
        checks.check("allowed-tools", has_tools, "missing allowed-tools")
        if "paths" in fields:
            paths = fields.get("paths")
            checks.check("paths field valid", paths is not None and isinstance(paths, (list, str)),
                         "paths must be a string or list of paths")
        unknown = sorted(set(fields) - schema.SKILL_FIELDS)
        checks.check("only documented frontmatter fields", not unknown,
                     "unrecognized skill fields: " + ", ".join(unknown))
    checks.check("when-to-use section", "## When to use" in text)
    checks.check("procedure section", re.search(r"##\s*Procedure", text, re.I) is not None)
    checks.check("pitfalls section", re.search(r"##\s*Pitfalls", text, re.I) is not None)
    checks.check("verification section", re.search(r"##\s*Verification", text, re.I) is not None)
    word_count = len(re.sub(r"```.*?```", "", text, flags=re.S).split())
    checks.check("word count 200-1500", 200 <= word_count <= 1500, f"got {word_count}")


def check_agent(directory, checks):
    for name in AGENT_FILES:
        checks.check(f"{name} present", (directory / name).exists())
    try:
        tools = json.loads((directory / "tools.json").read_text())
        checks.check("tools.json valid JSON", True)
        checks.check("tools.json has tools list", isinstance(tools.get("tools"), list))
        checks.check("tools.json has hand_off_to", "hand_off_to" in tools)
    except Exception as error:
        checks.check("tools.json valid JSON", False, str(error))
    try:
        prompt = (directory / "system-prompt.md").read_text()
        words = len(prompt.split())
        checks.check("system-prompt 500-1500 words", 500 <= words <= 1500, f"got {words}")
        checks.check("NEVER block present", "## NEVER" in prompt)
        checks.check("output format defined",
                     re.search(r"##\s*Output format", prompt, re.I) is not None)
        has_context = "{{CONTEXT}}" in prompt or bool(
            re.search(r"##\s*Domain context", prompt, re.I))
        checks.check("domain context injected", has_context,
                     "no {{CONTEXT}} token or '## Domain context' section")
    except Exception as error:
        checks.check("system-prompt readable", False, str(error))
    try:
        examples = (directory / "example-tasks.md").read_text()
        count = len(re.findall(r"^##\s*Task\s*\d+", examples, re.M))
        checks.check("example-tasks has >=3 entries", count >= 3, f"got {count}")
    except Exception:
        checks.check("example-tasks readable", False)


def _enum_problems(fields):
    """Return a list of 'field=value' strings for values Claude Code would not accept."""
    rules = (
        ("permissionMode", schema.PERMISSION_MODES),
        ("memory", schema.MEMORY_SCOPES),
        ("isolation", schema.ISOLATION_MODES),
        ("color", schema.COLORS),
        ("effort", frozenset(models.effort_levels())),
    )
    return [f"{key}={fields[key]}" for key, allowed in rules
            if key in fields and str(fields[key]) not in allowed]


def check_subagent(path, checks):
    fields, body, has_frontmatter = frontmatter.read(path.read_text(errors="replace"))
    checks.check("frontmatter present", has_frontmatter,
                 "the opening --- must be the first line of the file")
    problem = schema.name_problem(fields.get("name", ""))
    checks.check("name field valid", problem is None, problem or "")
    desc = fields.get("description")
    checks.check("description field", bool(desc),
                 "Claude Code skips a subagent with no description")
    if desc:
        desc_len = len(str(desc))
        checks.check("description <= 1536 chars", desc_len <= 1536, f"got {desc_len} chars")
    unknown = sorted(set(fields) - schema.SUBAGENT_FIELDS)
    checks.check("only documented frontmatter fields", not unknown,
                 "unrecognized (Claude Code ignores these silently): " + ", ".join(unknown))
    model = fields.get("model")
    checks.check("model value", model is None or schema.is_model_value(model),
                 f"got '{model}'; use an alias, a full claude-* id, or inherit")
    bad_enums = _enum_problems(fields)
    checks.check("enum fields valid", not bad_enums, ", ".join(bad_enums))
    checks.check("does not bypass permissions",
                 str(fields.get("permissionMode", "")) != "bypassPermissions",
                 "use plan or acceptEdits")
    declared_tools = "tools" in fields or "allowed-tools" in fields or "allowedTools" in fields
    checks.check("tools list not empty",
                 not declared_tools or bool(frontmatter.as_list(fields.get("tools") or fields.get("allowed-tools") or fields.get("allowedTools"))),
                 "a subagent whose tools resolve to nothing fails to launch")
    words = len(body.split())
    checks.check(f"system prompt >= {MIN_SUBAGENT_PROMPT_WORDS} words",
                 words >= MIN_SUBAGENT_PROMPT_WORDS, f"got {words}")


def _literal_secrets(server):
    """Names of header/env entries that hold a literal value for a secret-looking key."""
    leaked = []
    for section in ("headers", "env"):
        for key, value in (server.get(section) or {}).items():
            if schema.looks_like_secret_key(key) and "${" not in str(value):
                leaked.append(f"{section}.{key}")
    return leaked


def check_mcp(config, checks):
    servers = config.get("mcpServers")
    checks.check("mcpServers object", isinstance(servers, dict) and bool(servers),
                 "expected a non-empty object keyed by server name")
    if not isinstance(servers, dict):
        return
    for name, server in servers.items():
        if not isinstance(server, dict):
            checks.check(f"{name}: server entry is an object", False)
            continue
        transport = server.get("type", "stdio" if "command" in server else None)
        checks.check(f"{name}: transport", transport in schema.MCP_TRANSPORTS,
                     f"got '{transport}'")
        if transport in schema.MCP_REMOTE_TRANSPORTS:
            checks.check(f"{name}: url set", bool(server.get("url")))
        else:
            checks.check(f"{name}: command set", bool(server.get("command")))
        leaked = _literal_secrets(server)
        checks.check(f"{name}: no literal secrets", not leaked,
                     "use ${VAR} expansion for " + ", ".join(leaked))


def _project_root(settings_path):
    parent = settings_path.resolve().parent
    return parent.parent if parent.name == ".claude" else parent


def _script_problem(command, root):
    """Return a problem with a hook command's project-local script, or None."""
    if not PROJECT_DIR_REF.search(command):
        return None
    try:
        first = shlex.split(PROJECT_DIR_REF.sub(ROOT_SENTINEL, command))[0]
    except (ValueError, IndexError):
        return f"cannot parse hook command: {command}"
    script = pathlib.Path(first.replace(ROOT_SENTINEL, str(root)))
    if not script.is_file():
        return f"script not found: {script}"
    if not os.access(script, os.X_OK):
        return f"script not executable: {script}"
    return None


def check_hooks(config, settings_path, checks):
    hooks = config.get("hooks")
    checks.check("hooks object", isinstance(hooks, dict) and bool(hooks))
    if not isinstance(hooks, dict):
        return
    root = _project_root(settings_path)
    for event, groups in hooks.items():
        checks.check(f"{event}: known hook event", event in schema.HOOK_EVENTS)
        if not isinstance(groups, list) or not groups:
            checks.check(f"{event}: matcher groups", False, "expected a non-empty list")
            continue
        for group in groups:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(handlers, list) or not handlers:
                checks.check(f"{event}: handlers", False, "each matcher group needs a hooks list")
                continue
            for handler in handlers:
                kind = handler.get("type")
                checks.check(f"{event}: handler type", kind in schema.HOOK_HANDLER_TYPES,
                             f"got '{kind}'")
                if kind == "command":
                    command = str(handler.get("command", ""))
                    checks.check(f"{event}: command set", bool(command))
                    problem = _script_problem(command, root)
                    checks.check(f"{event}: script runnable", problem is None, problem or "")


def _load_json(path):
    try:
        return json.loads(path.read_text()), None
    except Exception as error:
        return None, str(error)


def run(target):
    """Return (kind, checks, resolved_target) or raise ValueError for an unknown shape."""
    checks = Checks()
    if target.is_dir() and (target / "AGENT.md").exists():
        check_agent(target, checks)
        return "agent", checks, target
    if target.is_dir() and (target / "SKILL.md").exists():
        target = target / "SKILL.md"
    if target.is_file() and target.name == "SKILL.md":
        check_skill(target, checks)
        return "skill", checks, target
    if target.is_file() and target.suffix == ".json":
        config, error = _load_json(target)
        checks.check("valid JSON", config is not None, error or "")
        if not isinstance(config, dict):
            return "config", checks, target
        if "mcpServers" in config:
            check_mcp(config, checks)
            return "mcp", checks, target
        check_hooks(config, target, checks)
        return "hooks", checks, target
    if target.is_file() and target.suffix == ".md":
        check_subagent(target, checks)
        return "subagent", checks, target
    raise ValueError("unrecognized shape")


def main(argv):
    if len(argv) < 3:
        print("usage: drytest.py <target> <json:true|false>", file=sys.stderr)
        return 2
    target = pathlib.Path(argv[1])
    json_out = argv[2].lower() == "true"

    if not target.exists():
        print(json.dumps({"verdict": "fail", "reason": "not found", "target": str(target)}))
        return 1
    try:
        kind, checks, target = run(target)
    except ValueError as error:
        print(json.dumps({"verdict": "fail", "reason": str(error)}))
        return 1

    percent = (checks.passed / checks.total * 100) if checks.total else 0
    pass_percent = 100 if kind in STRICT_KINDS else PASS_PERCENT
    verdict = "pass" if percent >= pass_percent else "warn" if percent >= WARN_PERCENT else "fail"
    score = round(percent / 10, 2)
    payload = {
        "kind": kind, "target": str(target),
        "checks_passed": checks.passed, "checks_total": checks.total,
        "score": score, "verdict": verdict, "issues": checks.issues, "warnings": [],
    }

    if json_out:
        print(json.dumps(payload, indent=2))
    else:
        emoji = {"pass": "✅", "warn": "⚠️", "fail": "\U0001F534"}[verdict]
        print(f"{emoji} {kind} dry-test: {checks.passed}/{checks.total} ({score}/10) — {verdict}")
        for issue in checks.issues:
            print(f"   ❌ {issue}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
