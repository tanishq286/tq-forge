"""Install the tq-forge mods into a Claude Code setup (Python stdlib only).

`mods install` plans one backed-up change, the same way `optimize` does:

  .claude/hooks/tq-forge/mods.py    the mod runtime (a copy of mods.py)
  .claude/hooks/tq-forge/mods.json  its defaults
  .claude/skills/<name>/SKILL.md    /savings, /switchboard, /handoff, /keep-warm, /tq-forge-learn
  .claude/agents/<name>.md          input-reader and omni-scout (kept if they already exist)
  .claude/settings.json             one hook entry per mod event; a statusLine only if none is set

Existing hooks, the existing status line and every other setting are kept.
Dry run by default; `tq-forge restore` undoes an --apply.

--chain-statusline keeps a status line you already have and appends the cache
clock to it: the old command is saved to .claude/hooks/tq-forge/statusline-earlier.sh
and runs first on every refresh.

--allow-autonomy additionally pre-approves WebSearch, WebFetch, `gh api` and the
learn/scout commands. That lets Claude research and install learned skills
without asking, and `gh api` can also write with your GitHub token, so it is
never added unless you pass the flag.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import context_cost  # noqa: E402
import optimize  # noqa: E402
import scaffold  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
PACKAGE = HERE.parents[1]
HOOK_DIR = ".claude/hooks/tq-forge"
HOOK_TIMEOUT_SECONDS = 15
HOOKS = (("UserPromptSubmit", None, "prompt"), ("PreToolUse", "Read", "read"),
         ("PreToolUse", "Agent|Task", "subagent"), ("PostToolUse", "mcp__.*", "mcp-output"),
         ("PostToolUse", "Agent|Task", "subagent-done"), ("Stop", None, "stop"))
SKILLS = ("savings", "switchboard", "handoff", "keep-warm", "tq-forge-learn")
AGENTS = ("input-reader", "omni-scout")
GENERIC_CLI = "npx tq-forge"  # how the bundled skill and agent texts spell the command
EARLIER_STATUSLINE = f"{HOOK_DIR}/statusline-earlier.sh"


def _prefix(root):
    """How a hook command reaches the root: $HOME for a user setup, the project folder otherwise."""
    return '"$HOME"' if root.resolve() == pathlib.Path.home().resolve() else '"$CLAUDE_PROJECT_DIR"'


def cli_command(package=PACKAGE):
    """The command that reaches this CLI: `node <path>` for a checkout or a global install, else `npx tq-forge`.

    An npx run lives in a cache folder that is gone by the next session, so its path is never written down.
    """
    cli = pathlib.Path(package) / "bin" / "cli.js"
    if "_npx" in cli.parts or not cli.is_file():
        return GENERIC_CLI
    try:
        return "node ~/" + cli.relative_to(pathlib.Path.home()).as_posix()
    except ValueError:
        return f"node {cli.as_posix()}"


def autonomy_rules(command=None):
    command = command or cli_command()
    return ["WebSearch", "WebFetch", f"Bash({command} learn *)", f"Bash({command} scout *)", "Bash(gh api *)"]


def _commands(group):
    return [hook.get("command") for hook in group.get("hooks", []) if isinstance(hook, dict)] \
        if isinstance(group, dict) else []


def merged_settings(root, allow_autonomy, chain_statusline=False):
    """Return (settings dict, notes, extra files) with the mod hooks added and everything else untouched."""
    settings = scaffold.load_json_object(root / optimize.SETTINGS)
    runtime = f"python3 {_prefix(root)}/{HOOK_DIR}/mods.py"
    notes, extra = [], {}
    hooks = dict(settings.get("hooks") if isinstance(settings.get("hooks"), dict) else {})
    for event, matcher, name in HOOKS:
        command = f"{runtime} hook {name}"
        groups = list(hooks.get(event) if isinstance(hooks.get(event), list) else [])
        if any(command in _commands(group) for group in groups):
            continue
        group = {"hooks": [{"type": "command", "command": command, "timeout": HOOK_TIMEOUT_SECONDS}]}
        if matcher:
            group = {"matcher": matcher, **group}
        hooks[event] = [*groups, group]
        notes.append(f"mods: {event}{f' ({matcher})' if matcher else ''} -> hook {name}")
    result = {**settings, "hooks": hooks}
    current = settings.get("statusLine")
    earlier = current.get("command") if isinstance(current, dict) else None
    if "statusLine" not in settings:
        result["statusLine"] = {"type": "command", "command": f"{runtime} statusline"}
        notes.append("mods: status line shows the cache clock")
    elif isinstance(earlier, str) and f"{HOOK_DIR}/mods.py" in earlier:
        pass  # already ours
    elif chain_statusline and isinstance(earlier, str) and current.get("type", "command") == "command":
        extra[EARLIER_STATUSLINE] = earlier.rstrip("\n") + "\n"
        result["statusLine"] = {**current, "command": f"{runtime} statusline --chain {_prefix(root)}/{EARLIER_STATUSLINE}"}
        notes.append(f"mods: your status line still runs (saved to {EARLIER_STATUSLINE}); the cache clock is appended")
    else:
        notes.append("mods: your status line is kept; pass --chain-statusline to append the cache clock to it")
    if allow_autonomy:
        permissions = settings.get("permissions") if isinstance(settings.get("permissions"), dict) else {}
        allowed = permissions.get("allow") if isinstance(permissions.get("allow"), list) else []
        added = [rule for rule in autonomy_rules() if rule not in allowed]
        if added:
            result["permissions"] = {**permissions, "allow": [*allowed, *added]}
            notes.append(f"mods: pre-approved {', '.join(added)}")
    return result, notes, extra


def plan_install(root, allow_autonomy=False, chain_statusline=False):
    plan = optimize.new_plan()
    command = cli_command()

    def bundled(path):  # the texts say `npx tq-forge`; write the command that works on this machine
        return context_cost.read_text(path).replace(GENERIC_CLI, command)

    plan["writes"][f"{HOOK_DIR}/mods.py"] = context_cost.read_text(HERE / "mods.py")
    plan["writes"][f"{HOOK_DIR}/mods.json"] = context_cost.read_text(PACKAGE / "config" / "mods.json")
    for name in SKILLS:
        plan["writes"][f".claude/skills/{name}/SKILL.md"] = bundled(PACKAGE / "skills" / name / "SKILL.md")
    for name in AGENTS:
        target = f".claude/agents/{name}.md"
        if (root / target).exists():
            plan["notes"].append(f"mods: {target} already exists; kept")
        else:
            plan["writes"][target] = bundled(PACKAGE / "templates" / "agents" / f"{name}.md")
    settings, notes, extra = merged_settings(root, allow_autonomy, chain_statusline)
    plan["writes"].update(extra)
    plan["writes"][optimize.SETTINGS] = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
    plan["notes"].extend(notes)
    for relative in list(plan["writes"]):
        reason = optimize.skip_reason(root, relative)
        if reason:
            plan["warnings"].append(f"mods: {relative} {reason}; not installed")
            del plan["writes"][relative]
    return plan


def main(args):
    root = pathlib.Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"mods: not a directory: {root}", file=sys.stderr)
        return 1
    try:
        plan = plan_install(root, args.allow_autonomy, args.chain_statusline)
        report = optimize.build_report(root, plan, None, args.apply)
    except scaffold.ScaffoldError as error:
        print(f"mods: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    verb = "installed" if args.apply else "would install (dry run; pass --apply)"
    print(f"tq-forge mods install: {verb} into {root}")
    for line in [*(f"- {note}" for note in report["notes"]), *(f"! {warning}" for warning in report["warnings"]),
                 *(f"  {path}" for path in report["files"])]:
        print(line)
    return 0
