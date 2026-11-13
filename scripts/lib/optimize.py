"""Context optimizer for Claude Code projects (Python stdlib only).

Shrinks what Claude Code loads into the main conversation on every turn,
without deleting anything:

  mcp     move each server in .mcp.json into its own .claude/agents/mcp-<name>.md
          worker (inline `mcpServers:`), so its tool list loads only in that worker
  skills  cut each skill description to <= 160 characters (the full text moves
          into the skill body) and move reference sections of long skills into
          reference.md
  rules   move CLAUDE.md sections that name specific paths into
          .claude/rules/<topic>.md with `paths:` frontmatter
  shield  settings that keep generated files out of context, a default effort
          and subagent model, two "soaker" subagents, and a one-line
          context-hygiene note in CLAUDE.md

Lossless by default: MCP servers stay in .mcp.json with their tool schemas
deferred (ENABLE_TOOL_SEARCH=true), descriptions of 350 characters or fewer are
never cut, files under .claude/plugins/ are never edited, and `shield` changes
neither effort, nor the subagent model, nor permissions.

Opt-in extras for `optimize`:

  --isolate-mcp       move each MCP server into its own worker subagent

  --follow-symlinks   also compact skills reached through a symlink (and the
                      shared .agents/skills/ folder); the real file is backed up
                      under .tq-forge-backup/symlink-targets/ first
  --dedupe-plugins    drop a symlinked skill that an enabled plugin already loads
  --description-limit 160   the aggressive description limit

Dry run by default. --apply writes, after copying every file it changes to
.tq-forge-backup/. `restore` undoes an apply (see backup.py).

These are structural changes, not free ones: a shorter description gives Claude
less to match a skill on, a path-scoped rule loads only when a matching file is
read, and an isolated MCP server is reached through a worker subagent. The
report lists every change so you can review it.

Usage: optimize.py {measure|optimize|shield|restore} [options]
"""

import argparse
import json
import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import backup  # noqa: E402
import context_cost  # noqa: E402
import drytest  # noqa: E402
import frontmatter  # noqa: E402
import models  # noqa: E402
import scaffold  # noqa: E402
from backup import BACKUP_DIR, LINK_BACKUPS, MANIFEST, apply_writes, restore  # noqa: E402,F401 (re-exported)

DESCRIPTION_LIMIT = 160  # the aggressive limit; pass it with --description-limit
LOSSLESS_DESCRIPTION_LIMIT = 350  # the default: a description this short keeps every trigger keyword
SKILL_BODY_LIMIT = 120
TOOL_SEARCH_ENV = "ENABLE_TOOL_SEARCH"
CLAUDE_MD_LIMIT = 80
SCRIPT_MIN_LINES = 8
MIN_LEAD_CHARS = 20
TRIGGER_SHARE = 3  # a lead-in may take up to a third of the limit when the trigger has to be cut
SUMMARY_LINES = 15
HYGIENE_MARK = "Context hygiene:"
DEFAULT_EFFORT = "medium"
SETTINGS_EFFORTS = ("low", "medium", "high", "xhigh")  # the values `effortLevel` accepts in settings.json
KEEP = "keep"
EXISTING_WINS = ("env", "skillOverrides")  # settings maps where a value the user already set is never replaced
SETTINGS = ".claude/settings.json"
HYGIENE_RULE = ".claude/rules/tq-forge-context-hygiene.md"
SOAKERS = ("context-soaker", "test-soaker")
STEPS = ("mcp", "skills", "rules", "prose")
REFERENCE_TITLE = re.compile(
    r"reference|api|schema|example|appendix|background|faq|troubleshoot|changelog|history", re.I)
CORE_TITLE = re.compile(
    r"\b(build|commands?|setup|install\w*|architecture|overview|quick ?start|project structure"
    r"|getting started)\b", re.I)
REQUIRED_SKILL_TITLE = re.compile(r"when to use|procedure|pitfalls|verification|tags", re.I)
BACKTICKED = re.compile(r"`([^`\s]+)`")
GLOB_CHARS = re.compile(r"^[\w.*/{},@-]+$")
SAFE_KEY = re.compile(r"[\w.-]+")
CLAUDE_MD_EXCLUDES = ("**/node_modules/**", "**/dist/**", "**/build/**",
                      "**/coverage/**", "**/.next/**", "**/vendor/**")
ENV_DENY_READS = ("Read(./.env)", "Read(./.env.*)")
STRICT_DENY_READS = ("Read(./node_modules/**)", "Read(./package-lock.json)",
                     "Read(./pnpm-lock.yaml)", "Read(./yarn.lock)")


def new_plan():
    """A set of planned changes.

    writes        {key: text}; a key is a path relative to the root, or an
                  absolute path when --follow-symlinks reaches a file outside it
    aliases       {key: path the root sees it under}, for writes made through a symlink
    remove_links  {relative path of a symlink: why it goes}
    settings      a patch for .claude/settings.json
    """
    return {"writes": {}, "settings": {}, "notes": [], "warnings": [], "aliases": {}, "remove_links": {}}


def merge_plans(*plans):
    merged = new_plan()
    for plan in plans:
        merged["writes"].update(plan["writes"])
        merged["notes"].extend(plan["notes"])
        merged["warnings"].extend(plan["warnings"])
        merged["aliases"].update(plan.get("aliases", {}))
        merged["remove_links"].update(plan.get("remove_links", {}))
        for key, value in plan["settings"].items():
            if isinstance(value, dict):
                merged["settings"][key] = {**merged["settings"].get(key, {}), **value}
            elif isinstance(value, list):
                merged["settings"][key] = [*merged["settings"].get(key, []), *value]
            else:
                merged["settings"][key] = value
    return merged


def split_sections(text):
    """Split markdown into (preamble, [(title, section_text)]) on `## ` headings."""
    preamble, sections, current, title, fenced = [], [], [], None, False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            if title is not None:
                sections.append((title, "\n".join(current)))
            title, current = line[3:].strip(), [line]
        elif title is None:
            preamble.append(line)
        else:
            current.append(line)
    if title is not None:
        sections.append((title, "\n".join(current)))
    return "\n".join(preamble), sections


def join_markdown(parts):
    return "\n\n".join(part.strip("\n") for part in parts if part.strip()) + "\n"


# ------------------------------------------------------------------- mcp

def plan_tool_search(root):
    """Keep every MCP server where it is and make sure its tool schemas stay deferred.

    This is the default, lossless MCP step. Claude Code's tool search already
    defers schemas; this pins it on and removes per-server `alwaysLoad` flags
    that would load a whole server upfront. Tool names and server instructions
    still load, and every tool stays callable from the main thread and from
    subagents. Use `plan_mcp` (--isolate-mcp) to move servers out instead.
    """
    plan = new_plan()
    config = context_cost.load_json(root / ".mcp.json")
    servers = config.get("mcpServers") if isinstance(config.get("mcpServers"), dict) else {}
    if not servers:
        plan["notes"].append("mcp: no servers in .mcp.json")
        return plan
    upfront = [name for name, entry in servers.items() if isinstance(entry, dict) and entry.get("alwaysLoad") is True]
    reason = skip_reason(root, ".mcp.json")
    if upfront and reason:
        plan["warnings"].append(f"mcp: .mcp.json {reason}; alwaysLoad left on {', '.join(upfront)}")
    elif upfront:
        cleaned = {name: ({key: value for key, value in entry.items() if key != "alwaysLoad"}
                          if name in upfront else entry) for name, entry in servers.items()}
        plan["writes"][".mcp.json"] = json.dumps({**config, "mcpServers": cleaned}, indent=2, ensure_ascii=False) + "\n"
        plan["notes"].append(f"mcp: removed alwaysLoad from {', '.join(upfront)}")
    env = context_cost.load_json(root / SETTINGS).get("env")
    current = env.get(TOOL_SEARCH_ENV) if isinstance(env, dict) else None
    if current is None:
        plan["settings"]["env"] = {TOOL_SEARCH_ENV: "true"}
    elif str(current).lower() != "true":
        plan["warnings"].append(f"mcp: {TOOL_SEARCH_ENV} is {json.dumps(current)} in settings.json; left as you set it")
    plan["notes"].append(f"mcp: {len(servers)} server(s) kept in .mcp.json with tool schemas deferred "
                         f"({TOOL_SEARCH_ENV}=true); tool names and server instructions still load")
    return plan


def worker_name(server):
    return "mcp-" + (re.sub(r"[^a-z0-9]+", "-", server.lower()).strip("-") or "server")


def skip_reason(root, relative, follow=False):
    """Why the optimizer must leave this path alone, or None when it is safe to write."""
    path = root / relative
    if not follow and path.resolve() != root.resolve() / relative:
        return "is a symlink or sits under one"
    if path.is_file():
        try:
            path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            return "is not valid UTF-8"
    return None


def _server_problem(server, entry):
    """Why a server cannot be written into agent frontmatter as it stands, or None."""
    keys = [server, *entry]
    for section, value in entry.items():
        if isinstance(value, dict):
            keys.extend(value)
        elif section in ("headers", "env") and value is not None:
            return f"`{section}` is not an object"
    if not all(SAFE_KEY.fullmatch(key) for key in keys):
        return "a name or key has characters other than letters, digits, `_`, `.` and `-`"
    return None


def plan_mcp(root, keep):
    plan = new_plan()
    reason = skip_reason(root, ".mcp.json")
    if reason:
        plan["warnings"].append(f"mcp: .mcp.json {reason}; left unchanged")
        return plan
    config = context_cost.load_json(root / ".mcp.json")
    servers = config.get("mcpServers") if isinstance(config.get("mcpServers"), dict) else {}
    moved = {}
    for server, entry in servers.items():
        target = f".claude/agents/{worker_name(server)}.md"
        if server in keep or not isinstance(entry, dict):
            continue
        problem = _server_problem(server, entry)
        if not problem and target in moved.values():
            problem = f"{target} is already taken by another server"
        if not problem and (root / target).exists():
            problem = f"{target} already exists"
        if not problem and skip_reason(root, target):
            problem = f"{target} {skip_reason(root, target)}"
        if problem:
            plan["warnings"].append(f"mcp: left {json.dumps(server)} in .mcp.json ({problem})")
            continue
        leaked = drytest._literal_secrets(entry)
        if leaked:
            plan["warnings"].append(
                f"`{server}` holds a literal secret ({', '.join(leaked)}); use ${{VAR}} expansion")
        description = (f"Runs {server} MCP tools in an isolated context and returns a short "
                       f"summary. Use when a task needs the {server} server.")
        plan["writes"][target] = scaffold.render("mcp/isolated-worker.md.tmpl", {
            "NAME": worker_name(server), "DESCRIPTION": json.dumps(description),
            "MODEL": models.subagent_model(),  # the registry's worker model, so a sync keeps it current
            "SERVER": server, "SUMMARY_LINES": str(SUMMARY_LINES),
            "SERVER_BLOCK": scaffold._yaml_server_block(server, entry),
        })
        moved[server] = target
    if not moved:
        plan["notes"].append("mcp: no servers to move")
        return plan
    remaining = {name: entry for name, entry in servers.items() if name not in moved}
    plan["writes"][".mcp.json"] = json.dumps({**config, "mcpServers": remaining}, indent=2, ensure_ascii=False) + "\n"
    plan["notes"].extend(f"mcp: `{server}` -> {target}" for server, target in moved.items())
    return plan


# ---------------------------------------------------------------- skills

def _cut(text, limit):
    """`text` cut at a word boundary to fit `limit`, with an ellipsis; "" when too little would be left."""
    if len(text) <= limit:
        return text
    cut = text[:max(0, limit - 1)].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…" if len(cut) >= MIN_LEAD_CHARS else ""


def _fit_sentences(sentences, limit):
    """Leading whole sentences that fit in `limit`, or a cut first sentence."""
    kept = ""
    for sentence in sentences:
        candidate = f"{kept} {sentence}".strip()
        if len(candidate) > limit:
            break
        kept = candidate
    if kept or limit < MIN_LEAD_CHARS:
        return kept
    return _cut(sentences[0], limit)


def compact_description(text, limit=DESCRIPTION_LIMIT):
    """Shorten a description to `limit` characters, keeping its "Use when" sentence.

    The trigger sentence is what Claude matches a skill on, so it is reserved
    first and the lead-in fills the space that is left. A trigger too long to
    fit is cut, never dropped: a skill with no trigger is hard to match at all.
    """
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    sentences = re.split(r"(?<=[.!?])\s+", flat)
    trigger = next((s for s in sentences if s.lower().startswith("use when")), "")
    if not trigger:
        return _fit_sentences(sentences, limit)
    others = [s for s in sentences if s != trigger]
    if len(trigger) > limit - MIN_LEAD_CHARS:
        lead = others[0] if others and len(others[0]) <= limit // TRIGGER_SHARE else ""
        return f"{lead} {_cut(trigger, limit - len(lead) - 1 if lead else limit)}".strip()
    lead = _fit_sentences(others, limit - len(trigger) - 1)
    return f"{lead} {trigger}".strip()


def replace_field(block, key, line):
    """Replace a frontmatter key (and its continuation lines) with one new line."""
    output, skipping, done = [], False, False
    for current in block.splitlines():
        if skipping and (not current.strip() or current[:1].isspace() or current.startswith("- ")):
            continue
        skipping = False
        if not done and re.match(rf"^{re.escape(key)}\s*:", current):
            output.append(line)
            skipping = done = True
            continue
        output.append(current)
    return "\n".join(output if done else [*output, line])


def _extract_scripts(body, min_lines=SCRIPT_MIN_LINES):
    """Move long, placeholder-free shell blocks into scripts/. Returns (body, {name: text})."""
    scripts = {}

    def swap(match):
        code = match.group(2)
        if len(code.strip().splitlines()) < min_lines or re.search(r"<[\w -]+>|\$ARGUMENTS", code):
            return match.group(0)
        name = f"scripts/step-{len(scripts) + 1}.sh"
        scripts[name] = f"#!/usr/bin/env bash\nset -euo pipefail\n{code.rstrip()}\n"
        return f'{match.group(1)}bash "${{CLAUDE_SKILL_DIR}}/{name}"\n{match.group(3)}'

    pattern = re.compile(r"(^[ \t]*```(?:bash|sh)[ \t]*\n)(.*?)(^[ \t]*```[ \t]*$)", re.S | re.M)
    return pattern.sub(swap, body), scripts


def _split_reference(name, body):
    """Move reference-like sections out of a long skill body. Returns (body, reference_text)."""
    preamble, sections = split_sections(body)
    moved = [text for title, text in sections
             if REFERENCE_TITLE.search(title) and not REQUIRED_SKILL_TITLE.search(title)]
    if not moved:
        return body, ""
    kept = [text for _, text in sections if text not in moved]
    pointer = ("## Reference\n\nLong-form details are in [reference.md](reference.md). "
               "Open it only when a step needs it.")
    return join_markdown([preamble, *kept, pointer]), join_markdown([f"# {name} reference", *moved])


def write_base(root, folder):
    """Key prefix for writes into `folder`: its real location, relative to the root when inside it."""
    real = folder.resolve()
    try:
        return real.relative_to(root.resolve()).as_posix()
    except ValueError:
        return real.as_posix()


def _plan_one_skill(root, path, extract_scripts, limit=DESCRIPTION_LIMIT, follow=False, split=True):
    plan = new_plan()
    relative = path.parent.relative_to(root).as_posix()
    reason = skip_reason(root, f"{relative}/SKILL.md", follow)
    if reason:
        plan["warnings"].append(f"skills: {relative}/SKILL.md {reason}; left unchanged")
        return plan
    base = write_base(root, path.parent) if follow else relative

    def write(name, text):
        plan["writes"][f"{base}/{name}"] = text
        if base != relative:
            plan["aliases"][f"{base}/{name}"] = f"{relative}/{name}"
    block, body = frontmatter.split(context_cost.read_text(path))
    if block is None:
        plan["warnings"].append(f"{relative}/SKILL.md has no frontmatter; skipped")
        return plan
    fields = frontmatter.parse(block)
    name = str(fields.get("name") or path.parent.name)
    description = " ".join(str(fields.get("description", "")).split())
    new_block, new_body = block, body

    if len(description) > limit:
        short = compact_description(description, limit)
        new_block = replace_field(block, "description", f"description: {json.dumps(short, ensure_ascii=False)}")
        if not re.search(r"^## Full description\s*$", body, re.M):  # an earlier run already kept the original
            new_body = join_markdown([body, f"## Full description\n\n{description}"])
        plan["notes"].append(f"skills: {name} description {len(description)} -> {len(short)} chars")

    if split and len(new_body.splitlines()) > SKILL_BODY_LIMIT:
        if (path.parent / "reference.md").exists():
            plan["warnings"].append(f"{relative}/reference.md exists; long body left as is")
        else:
            new_body, reference = _split_reference(name, new_body)
            if reference:
                write("reference.md", reference)
                plan["notes"].append(f"skills: {name} reference sections -> reference.md")
            else:
                plan["warnings"].append(f"{relative}/SKILL.md is long but has no reference-like sections")

    if extract_scripts:
        new_body, scripts = _extract_scripts(new_body)
        for script, text in scripts.items():
            write(script, text)
            plan["notes"].append(f"skills: {name} shell block -> {script}")

    extensions = sorted(set(re.findall(r"\*\.([A-Za-z0-9]{1,5})\b", body)))
    if extensions and not fields.get("paths"):
        plan["notes"].append(f"skills: {name} mentions *.{', *.'.join(extensions)}; "
                             f"consider adding `paths:` by hand")
    if (new_block, new_body) != (block, body):
        write("SKILL.md", f"---\n{new_block}\n---\n{new_body}")
    return plan


def skill_sources(root, follow=False):
    """SKILL.md files to compact: .claude/skills/, plus the shared .agents/skills/ when following links."""
    paths = list(context_cost.skill_files(root))
    if follow:
        seen = {path.resolve() for path in paths}
        paths.extend(path for path in context_cost.shared_skill_files(root) if path.resolve() not in seen)
    return paths


def plan_skills(root, mute, extract_scripts, limit=DESCRIPTION_LIMIT, follow=False):
    plans = [_plan_one_skill(root, path, extract_scripts, limit, follow) for path in skill_sources(root, follow)]
    plan = merge_plans(*plans)
    if mute:
        plan["settings"]["skillOverrides"] = {name: "off" for name in mute}
        plan["notes"].append(f"skills: skillOverrides off for {', '.join(mute)}")
    if not plan["writes"] and not mute:
        plan["notes"].append("skills: nothing to compact")
    return plan


# ----------------------------------------------------------------- rules

def path_scopes(section, root):
    """Globs for the paths a CLAUDE.md section names in backticks and that exist."""
    scopes = []
    for token in BACKTICKED.findall(section):
        token = token.rstrip("/")
        if not token or token.startswith(("/", "~", "$", "-", ".")) or ".." in token:
            continue
        if not GLOB_CHARS.match(token):
            continue
        if "*" in token:
            scope = token
        elif (root / token).is_dir():
            scope = f"{token}/**"
        elif "/" in token and (root / token).is_file():
            scope = token
        else:
            continue
        if scope not in scopes:
            scopes.append(scope)
    return scopes


def plan_rules(root):
    plan = new_plan()
    text = context_cost.read_text(root / "CLAUDE.md")
    if len(text.splitlines()) <= CLAUDE_MD_LIMIT:
        plan["notes"].append(f"rules: CLAUDE.md is within {CLAUDE_MD_LIMIT} lines")
        return plan
    for relative in ("CLAUDE.md", ".claude/rules/rule.md"):
        reason = skip_reason(root, relative)
        if reason:
            where = relative if relative == "CLAUDE.md" else ".claude/rules/"
            plan["warnings"].append(f"rules: {where} {reason}; left CLAUDE.md unchanged")
            return plan
    preamble, sections = split_sections(text)
    kept = [preamble]
    for title, section in sections:
        scopes = [] if CORE_TITLE.search(title) else path_scopes(section, root)
        target = f".claude/rules/{scaffold.slugify(title)}.md"
        if not scopes or target in plan["writes"] or (root / target).exists():
            kept.append(section)
            continue
        paths = "".join(f"  - {json.dumps(scope)}\n" for scope in scopes)
        plan["writes"][target] = f"---\npaths:\n{paths}---\n\n{section.strip()}\n"
        plan["notes"].append(f"rules: \"{title}\" -> {target} ({', '.join(scopes)})")
    if len(kept) == len(sections) + 1:
        plan["warnings"].append("rules: CLAUDE.md is long but no section names an existing path")
        return plan
    plan["writes"]["CLAUDE.md"] = join_markdown(kept)
    remaining = len(plan["writes"]["CLAUDE.md"].splitlines())
    if remaining > CLAUDE_MD_LIMIT:
        plan["warnings"].append(f"rules: CLAUDE.md still has {remaining} lines; split the rest by hand")
    return plan


# ---------------------------------------------------------------- shield

def _effort_models(settings):
    """Model ids whose per-model effort must follow the shield's effort.

    Claude Code resolves effort per model, and a `modelSettings` entry wins over
    the top-level `effortLevel`, so both are set.
    """
    listed = settings.get("modelSettings")
    names = set(listed) if isinstance(listed, dict) else set()
    return sorted(names | {models.resolve(settings.get("model")) or models.lead_model()})


def plan_shield(root, strict, subagent_model, deny_env=False, effort=None):
    plan = new_plan()
    plan["settings"]["claudeMdExcludes"] = list(CLAUDE_MD_EXCLUDES)
    denied = [*(ENV_DENY_READS if deny_env else ()), *(STRICT_DENY_READS if strict else ())]
    if denied:  # build folders are never denied: Claude often has to read build output to debug it
        plan["settings"]["permissions.deny"] = denied
    if effort:
        if effort not in SETTINGS_EFFORTS:
            raise scaffold.ScaffoldError(f"unknown effort '{effort}'; use {', '.join(SETTINGS_EFFORTS)}")
        names = _effort_models(context_cost.load_json(root / SETTINGS))
        plan["settings"]["effortLevel"] = effort
        plan["settings"]["modelSettings"] = {name: {"effortLevel": effort} for name in names}
        plan["warnings"].append(f"shield: effort is now {effort} for {', '.join(names)}")
    if subagent_model:
        model_id = models.resolve(subagent_model)
        if not model_id:
            raise scaffold.ScaffoldError(f"unknown model '{subagent_model}'")
        plan["settings"]["env"] = {"CLAUDE_CODE_SUBAGENT_MODEL": model_id}
        plan["warnings"].append(f"shield: every subagent without its own model now runs on {model_id}")
    text = context_cost.read_text(root / "CLAUDE.md")
    reason = skip_reason(root, "CLAUDE.md")
    if reason:
        plan["warnings"].append(f"shield: CLAUDE.md {reason}; hygiene note not added")
    elif HYGIENE_MARK not in text and not (root / HYGIENE_RULE).exists():
        plan["writes"]["CLAUDE.md"] = join_markdown([text, models.snippet("shield")])
    for name in SOAKERS:
        target = f".claude/agents/{name}.md"
        if (root / target).exists():
            plan["notes"].append(f"shield: {target} already exists; kept")
            continue
        plan["writes"][target] = context_cost.read_text(scaffold.TEMPLATES / "agents" / f"{name}.md")
    plan["notes"].append("shield: claudeMdExcludes, soaker subagents, hygiene note in CLAUDE.md; "
                         "effort, subagent model and permissions are left as they are unless a flag asks")
    return plan


def settings_content(root, patch):
    """Merge a settings patch into .claude/settings.json without dropping existing keys."""
    settings = scaffold.load_json_object(root / SETTINGS)
    result = {**settings}
    for key, value in patch.items():
        if key == "permissions.deny":
            permissions = settings.get("permissions") if isinstance(settings.get("permissions"), dict) else {}
            current = permissions.get("deny") if isinstance(permissions.get("deny"), list) else []
            result["permissions"] = {**permissions, "deny": [*current, *[v for v in value if v not in current]]}
        elif key == "modelSettings":
            current = settings.get(key) if isinstance(settings.get(key), dict) else {}
            merged = {name: {**(current.get(name) if isinstance(current.get(name), dict) else {}), **entry}
                      for name, entry in value.items()}
            result[key] = {**current, **merged}
        elif isinstance(value, dict):
            current = settings.get(key) if isinstance(settings.get(key), dict) else {}
            result[key] = {**value, **current} if key in EXISTING_WINS else {**current, **value}
        elif isinstance(value, list):
            current = settings.get(key) if isinstance(settings.get(key), list) else []
            result[key] = [*current, *[v for v in value if v not in current]]
        else:
            result[key] = value
    return json.dumps(result, indent=2, ensure_ascii=False) + "\n"


# ------------------------------------------------------- apply and report

def finalize(root, plan):
    """Fold the settings patch into the write list. Returns {relative_path: content}."""
    writes = {**plan["writes"]}
    if plan["settings"]:
        writes[SETTINGS] = settings_content(root, plan["settings"])
    return {path: text for path, text in writes.items()
            if context_cost.read_text(root / path) != text or not (root / path).exists()}


def _context_lines(root, skip=()):
    """Every non-empty instruction line the project holds, for the nothing-lost check.

    `skip` names skill folders to leave out: a removed symlink deletes a link,
    not the skill it pointed at.
    """
    files = [root / "CLAUDE.md", *context_cost.rule_files(root)]
    for skill in context_cost.skill_files(root):
        if skill.parent.relative_to(root).as_posix() in skip:
            continue
        files.extend(path for path in skill.parent.rglob("*") if path.is_file())
    lines = set()
    for path in files:
        _, body = frontmatter.split(context_cost.read_text(path))
        lines.update(line.strip() for line in body.splitlines() if line.strip())
    return lines


def _mcp_names(root):
    servers = context_cost.load_json(root / ".mcp.json").get("mcpServers")
    names = set(servers) if isinstance(servers, dict) else set()
    for agent in context_cost.agent_files(root):
        names.update(re.findall(r"^  - ([\w.-]+):\s*$", context_cost.read_text(agent), re.M))
    return names


def preview(root, writes, aliases=None, remove_links=None):
    """Apply the writes to a temporary copy and return that copy's path.

    The copy holds real folders where the project has symlinks, so a write made
    through a link lands on the path the project sees it under. A write that has
    no path inside the project is left out: the preview never touches a real file.
    """
    aliases = aliases or {}
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="tq-forge-optimize-"))
    for name in ("CLAUDE.md", ".mcp.json"):
        if (root / name).is_file():
            shutil.copy2(root / name, scratch / name)
    for name in ("skills", "agents", "rules"):
        if (root / ".claude" / name).is_dir():
            try:
                shutil.copytree(root / ".claude" / name, scratch / ".claude" / name)
            except shutil.Error:
                pass  # copytree copies everything it can, then reports dangling links
    for name in (SETTINGS, ".claude/CLAUDE.md"):
        if (root / name).is_file():
            (scratch / ".claude").mkdir(exist_ok=True)
            shutil.copy2(root / name, scratch / name)
    seen = {aliases.get(key, key): text for key, text in writes.items()}
    inside = {key: text for key, text in seen.items() if not backup.is_absolute(key)}
    apply_writes(scratch, inside, backup=False, remove_links=remove_links)
    return scratch


def build_report(root, plan, inventory, apply, plugins=False, listing_budget=None):
    planned = finalize(root, plan)
    aliases = {key: alias for key, alias in plan.get("aliases", {}).items() if key in planned}
    remove_links = {link: why for link, why in plan.get("remove_links", {}).items() if (root / link).is_symlink()}
    blocked = {path: skip_reason(root, path, path in aliases) for path in planned
               if skip_reason(root, path, path in aliases)}
    writes = {path: text for path, text in planned.items() if path not in blocked}
    warnings = [*plan["warnings"],
                *(f"{path} {reason}; left unchanged" for path, reason in sorted(blocked.items()))]
    overlay = {str((root / key).resolve()): text for key, text in writes.items()}
    before = context_cost.measure(root, inventory, plugins, listing_budget)
    scratch = preview(root, writes, aliases, remove_links)
    try:
        after = context_cost.measure(scratch, inventory, plugins, listing_budget, plugin_root=root, overlay=overlay)
        lost_lines = sorted(_context_lines(root, set(remove_links)) - _context_lines(scratch))
        lost_servers = sorted(_mcp_names(root) - _mcp_names(scratch))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if apply and (lost_lines or lost_servers):
        missing = ", ".join([*lost_servers, *(repr(line) for line in lost_lines[:3])])
        raise scaffold.ScaffoldError(
            f"refusing to apply: the preview no longer contains {missing}; nothing was written")
    if apply:
        apply_writes(root, writes, aliases=aliases, remove_links=remove_links)
    return {
        "mode": "applied" if apply else "dry-run",
        "before": before,
        "after": after,
        "reduction_percent": context_cost.reduction_percent(
            before["estimated_tokens"], after["estimated_tokens"]),
        "files": sorted(writes),
        "removed_links": sorted(remove_links),
        "notes": plan["notes"],
        "warnings": warnings,
        "nothing_lost": {"ok": not lost_lines and not lost_servers,
                         "missing_lines": lost_lines[:20], "missing_mcp_servers": lost_servers},
    }


def render(report):
    if report["mode"] == "restored":
        lines = [f"restored {len(report['files'])} file(s)", *report["files"]]
        if report.get("kept_edited"):
            lines.append(f"kept {len(report['kept_edited'])} file(s) an apply created and you edited since "
                         f"(--discard-edits deletes them):")
            lines.extend(f"  {path}" for path in report["kept_edited"])
        if report.get("skipped"):
            lines.append(f"left {len(report['skipped'])} file(s) outside the root as they are; their backups are kept. "
                         f"Run restore again with --outside to put them back:")
            lines.extend(f"  {path}" for path in report["skipped"])
        return "\n".join(lines)
    lines = [f"tq-forge optimize ({report['mode']})", "",
             f"{'always-loaded context':<24}{'before':>9}{'after':>9}"]
    for part in report["before"]["parts"]:
        lines.append(f"  {part:<22}{report['before']['parts'][part]:>9}{report['after']['parts'][part]:>9}")
    lines.append(f"  {'total (est. tokens)':<22}{report['before']['estimated_tokens']:>9}"
                 f"{report['after']['estimated_tokens']:>9}   {-report['reduction_percent']:+}%")
    lines.append(f"  method: {report['before']['method']}")
    unmeasured = report["before"]["mcp_servers_not_measured"]
    if unmeasured:
        lines.append(f"  not measured (no inventory): MCP servers {', '.join(unmeasured)}")
    lines.extend(["", *[f"- {note}" for note in report["notes"]]])
    lines.extend(f"! {warning}" for warning in report["warnings"])
    lines.append(f"nothing lost: {'yes' if report['nothing_lost']['ok'] else 'NO - see --json'}")
    lines.append("files " + ("written" if report["mode"] == "applied" else "that --apply would write") + ":")
    lines.extend(f"  {path}" for path in report["files"])
    if report.get("removed_links"):
        lines.append("symlinks " + ("removed" if report["mode"] == "applied" else "that --apply would remove") + ":")
        lines.extend(f"  {path}" for path in report["removed_links"])
    return "\n".join(lines)


# -------------------------------------------------------------------- cli

def _names(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _choice(value, default):
    """A flag left unset takes the default; `keep` leaves the setting alone."""
    if value is None:
        return default
    return None if value == KEEP else value


def run(args):
    root = pathlib.Path(args.root).resolve()
    if not root.is_dir():
        raise scaffold.ScaffoldError(f"not a directory: {root}")
    inventory = context_cost.load_json(pathlib.Path(args.mcp_inventory)) if args.mcp_inventory else None
    if args.command == "restore":
        return restore(root, args.outside, args.discard_edits)
    if args.command == "measure":
        return {"mode": "measure", **context_cost.measure(root, inventory, args.plugins, args.listing_budget)}
    apply = args.apply and not args.dry_run
    plugins = args.plugins
    if args.command == "shield":
        plan = plan_shield(root, args.strict, _choice(args.subagent_model, None),
                           args.deny_env, _choice(args.effort, None))
    else:
        steps = _names(args.only) or list(STEPS)
        unknown = [step for step in steps if step not in STEPS]
        if unknown:
            raise scaffold.ScaffoldError(f"unknown step {', '.join(unknown)}; use {', '.join(STEPS)}")
        isolate = lambda: plan_mcp(root, _names(args.keep_mcp))  # noqa: E731
        builders = {"mcp": isolate if args.isolate_mcp else (lambda: plan_tool_search(root)),
                    "prose": lambda: _plan_prose(root),
                    "skills": lambda: plan_skills(root, _names(args.mute_skills), args.extract_scripts,
                                                  args.description_limit, args.follow_symlinks),
                    "rules": lambda: plan_rules(root)}
        plans = [builders[step]() for step in steps]
        if "rules" in steps and "prose" in steps:  # the prose step works on what the rules step left
            rules = plans[steps.index("rules")]
            plans[steps.index("prose")] = _plan_prose(root, rules["writes"].get("CLAUDE.md"))
        if args.dedupe_plugins:
            import linkdedupe  # imports this module, so it is loaded only when asked for
            plugins = True
            plans.append(linkdedupe.plan_dedupe(root))
        plan = merge_plans(*plans)
    report = build_report(root, plan, inventory, apply, plugins, args.listing_budget)
    if apply and args.command == "optimize":
        record_saving(root, report)
    return report


def record_saving(root, report):
    """Add an applied reduction to the /savings dashboard, for the user setup or a project with the mods installed."""
    import mods  # the mod runtime; loaded only after an apply
    saved = report["before"]["estimated_tokens"] - report["after"]["estimated_tokens"]
    tracked = root.resolve() == mods.USER_HOME.resolve() or (root / ".claude/hooks/tq-forge/mods.py").is_file()
    if saved > 0 and tracked:
        mods.record_context_saving(saved)


def _plan_prose(root, text=None):
    import offload  # imports this module, so it is loaded only when the step runs
    return offload.plan_prose(root, text)


def build_parser():
    parser = argparse.ArgumentParser(prog="optimize", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("measure", "optimize", "shield", "restore"):
        sub = commands.add_parser(name)
        sub.add_argument("--root", default=".", help="project root (default: current directory)")
        sub.add_argument("--json", action="store_true")
        sub.add_argument("--mcp-inventory", help="JSON file with each server's tool names and instructions")
        sub.add_argument("--plugins", action="store_true",
                         help="also count the skills of enabled plugins under .claude/plugins/")
        sub.add_argument("--listing-budget", type=int, metavar="CHARS",
                         help="cap skill-listing descriptions at this many characters, as Claude Code does")
        sub.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
        sub.add_argument("--dry-run", action="store_true",
                         help="print the plan and write nothing (the default; wins over --apply)")
        if name == "optimize":
            sub.add_argument("--isolate-mcp", action="store_true",
                             help="move each MCP server into its own worker subagent (the main thread loses "
                                  "direct access to its tools); default is to keep servers and defer their tools")
            sub.add_argument("--keep-mcp", help="with --isolate-mcp: servers to leave in .mcp.json")
            sub.add_argument("--mute-skills", help="skill names to set to off in skillOverrides")
            sub.add_argument("--extract-scripts", action="store_true",
                             help="move long shell blocks into scripts/ (review the result)")
            sub.add_argument("--only", help="comma-separated subset of: " + ", ".join(STEPS))
            sub.add_argument("--description-limit", type=int, default=LOSSLESS_DESCRIPTION_LIMIT, metavar="CHARS",
                             help=f"longest skill description to keep (default {LOSSLESS_DESCRIPTION_LIMIT}; "
                                  f"{DESCRIPTION_LIMIT} is the aggressive setting)")
            sub.add_argument("--follow-symlinks", action="store_true",
                             help="also compact skills behind symlinks and in .agents/skills/")
            sub.add_argument("--dedupe-plugins", action="store_true",
                             help="remove a symlinked skill that an enabled plugin already loads")
        if name == "restore":
            sub.add_argument("--outside", action="store_true",
                             help="also restore files outside the root (the targets of followed symlinks)")
            sub.add_argument("--discard-edits", action="store_true",
                             help="also delete files an apply created that you have edited since")
        if name == "shield":
            sub.add_argument("--strict", action="store_true",
                             help="also deny reading node_modules and lockfiles")
            sub.add_argument("--deny-env", action="store_true", help="also deny reading .env files")
            sub.add_argument("--effort", metavar="LEVEL",
                             help="set a static effortLevel (opt-in; the effort-optimizer mod is the dynamic way)")
            sub.add_argument("--subagent-model", metavar="MODEL",
                             help="set a static CLAUDE_CODE_SUBAGENT_MODEL (opt-in; the subagent-model-selector "
                                  "mod is the dynamic way)")
    return parser


def main(argv):
    args = build_parser().parse_args(argv[1:])
    try:
        report = run(args)
    except scaffold.ScaffoldError as error:
        print(f"optimize: {error}", file=sys.stderr)
        return 1
    if args.json or report["mode"] == "measure":
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
