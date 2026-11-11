"""Keep tq-forge current with new Claude model releases (Python stdlib only).

`config/models.json` is the registry of Claude model generations: one current
model per family (fable, mythos, opus, sonnet, haiku) with its role, starting
effort, prices and prompting rules, plus the recommended lead + subagent pair.

`sync-models` reads the list of live model ids, and when a family has a newer
version than the registry:

  1. adds the model to the registry (role, effort and prompting rules carry
     over from the version it replaces; prices come from the source when it
     reports them, otherwise they are marked as inherited)
  2. rewrites pinned `model:` ids that are now behind, in
     .claude/agents/**/*.md and .claude/settings.json under --root, and in the
     tq-forge templates

Where the ids come from, in order:

  anthropic   GET https://api.anthropic.com/v1/models   (needs ANTHROPIC_API_KEY)
  openrouter  GET https://openrouter.ai/api/v1/models   (public, includes prices)
  offline     the registry itself, so nothing changes   (CI, air-gapped runs)

These two GET requests are the only network calls tq-forge makes. They send
the API key (Anthropic only) and nothing about your project.

Dry run by default. --apply writes; files under --root are backed up to
.tq-forge-backup/ like every other optimizer change.

Usage: model_sync.py [--root DIR] [--source auto|anthropic|openrouter|offline]
                     [--ids-file FILE] [--no-templates] [--apply] [--json]
"""

import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import context_cost  # noqa: E402
import frontmatter  # noqa: E402
import models  # noqa: E402
import optimize  # noqa: E402
import scaffold  # noqa: E402

FAMILIES = ("fable", "mythos", "opus", "sonnet", "haiku")
LEAD_FAMILY = "fable"
SUBAGENT_FAMILY = "haiku"
ANTHROPIC_URL = "https://api.anthropic.com/v1/models"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
ANTHROPIC_VERSION = "2023-06-01"
PAGE_SIZE = 1000
MAX_PAGES = 20
TIMEOUT_SECONDS = 15
MAX_MAJOR_JUMP = 1
PER_MILLION = 1_000_000
SOURCES = ("auto", "anthropic", "openrouter", "offline")
STAMP = "model-sync.json"

_CURRENT = re.compile(r"^claude-(fable|mythos|opus|sonnet|haiku)-(\d{1,2})(?:-(\d{1,2}))?(?:-\d{8})?$")
_LEGACY = re.compile(r"^claude-(\d{1,2})(?:-(\d{1,2}))?-(opus|sonnet|haiku)(?:-\d{8})?$")
_MODEL_LINE = re.compile(r"^(model[ \t]*:[ \t]*)([\"']?)([^\s\"'#]+)\2([ \t]*(?:#.*)?)$", re.M)


# ------------------------------------------------------------------ ids

def parse(model_id):
    """Return (family, (major, minor)) for a Claude model id, or None.

    Accepts current ids (claude-opus-5-5), dated snapshots, the older
    version-first form (claude-3-5-sonnet-20241022), and provider spellings
    such as anthropic/claude-opus-5.5 or claude-opus-4-5@20251101.
    """
    text = str(model_id or "").strip().lower().split("/")[-1].split(":")[0].split("@")[0].replace(".", "-")
    match = _CURRENT.match(text)
    if match:
        return match.group(1), (int(match.group(2)), int(match.group(3) or 0))
    match = _LEGACY.match(text)
    if match:
        return match.group(3), (int(match.group(1)), int(match.group(2) or 0))
    return None


def canonical(family, version):
    major, minor = version
    return f"claude-{family}-{major}" + (f"-{minor}" if minor else "")


def label(family, version):
    major, minor = version
    return f"Claude {family.title()} {major}" + (f".{minor}" if minor else "")


def current_id(registry, family):
    return ((registry.get("families") or {}).get(family) or {}).get("current")


def _version_of(registry, model_id):
    entry = (registry.get("models") or {}).get(model_id) or {}
    version = entry.get("version")
    if isinstance(version, list) and len(version) == 2:
        return tuple(version)
    parsed = parse(model_id)
    return parsed[1] if parsed else (0, 0)


def upgrade_target(model_id, registry):
    """The family's current model when `model_id` is an older version of it, else None."""
    parsed = parse(model_id)
    if not parsed:
        return None
    family, version = parsed
    current = current_id(registry, family)
    if not current or version >= _version_of(registry, current):
        return None
    return current


# ------------------------------------------------------------ discovery

def _get_json(url, headers=None):
    request = urllib.request.Request(url, headers={"User-Agent": "tq-forge-model-sync", **(headers or {})})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 (https constants)
        return json.loads(response.read().decode("utf-8"))


def _record(found, model_id, pricing=None):
    parsed = parse(model_id)
    if not parsed:
        return
    key = canonical(*parsed)
    found.setdefault(key, {})
    if pricing:
        found[key]["pricing"] = pricing


def fetch_anthropic(api_key, get=_get_json):
    found, after = {}, None
    for _ in range(MAX_PAGES):
        url = f"{ANTHROPIC_URL}?limit={PAGE_SIZE}" + (f"&after_id={urllib.parse.quote(str(after), safe='')}" if after else "")
        page = get(url, {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION})
        for item in page.get("data", []):
            _record(found, item.get("id"))
        after = page.get("last_id")
        if not page.get("has_more") or not after:
            break
    return found


def _per_million(value):
    try:
        return round(float(value) * PER_MILLION, 4)
    except (TypeError, ValueError):
        return None


def fetch_openrouter(get=_get_json):
    found = {}
    for item in get(OPENROUTER_URL).get("data", []):
        model_id = str(item.get("id", ""))
        if not model_id.startswith("anthropic/"):
            continue
        prices = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
        pricing = {"input": _per_million(prices.get("prompt")), "output": _per_million(prices.get("completion")),
                   "cache_read": _per_million(prices.get("input_cache_read")), "source": "openrouter"}
        _record(found, model_id, pricing if pricing["input"] and pricing["output"] else None)
    return found


def discover(source="auto", environ=None, get=_get_json):
    """Return {"source", "models": {id: {...}}, "errors": [...]}. Never raises on a network failure."""
    environ = os.environ if environ is None else environ
    api_key = (environ.get("ANTHROPIC_API_KEY") or "").strip()
    order = {"auto": ["anthropic", "openrouter"], "anthropic": ["anthropic"],
             "openrouter": ["openrouter"], "offline": []}[source]
    errors = []
    for name in order:
        if name == "anthropic" and not api_key:
            if source == "anthropic":
                errors.append("anthropic: ANTHROPIC_API_KEY is not set")
            continue
        try:
            found = fetch_anthropic(api_key, get) if name == "anthropic" else fetch_openrouter(get)
        except (urllib.error.URLError, OSError, ValueError, AttributeError) as error:
            errors.append(f"{name}: {error}")
            continue
        if found:
            return {"source": name, "models": found, "errors": errors}
        errors.append(f"{name}: returned no Claude model ids")
    return {"source": "offline", "models": {}, "errors": errors}


# ------------------------------------------------------------- registry

def load_registry():
    registry = models.generations()
    if not registry:
        raise scaffold.ScaffoldError(f"no model registry at {models.GENERATIONS_FILE}")
    return registry


def plan_registry(registry, found, today=None):
    """Return (new_registry, {old_id: new_id}, notes) for the model ids in `found`."""
    today = today or datetime.date.today().isoformat()
    updated = json.loads(json.dumps(registry))
    upgrades, notes = {}, []
    by_family = {}
    for model_id in found:
        parsed = parse(model_id)
        if parsed:
            by_family.setdefault(parsed[0], set()).add(parsed[1])
    for family in FAMILIES:
        current = current_id(updated, family)
        if not current or family not in by_family:
            continue
        have = _version_of(updated, current)
        newest = max(by_family[family])
        if newest <= have:
            continue
        if newest[0] - have[0] > MAX_MAJOR_JUMP:
            notes.append(f"{family}: ignored {canonical(family, newest)}, too far ahead of {current} to trust")
            continue
        new_id = canonical(family, newest)
        previous = updated["models"][current]
        entry = {key: value for key, value in previous.items() if key != "superseded_by"}
        entry.update({"version": list(newest), "added": today})
        live = (found.get(new_id) or {}).get("pricing")
        entry["pricing"] = live or {**(previous.get("pricing") or {}), "inherited_from": current}
        updated["models"][new_id] = entry
        updated["models"][current] = {**previous, "superseded_by": new_id}
        updated["families"][family]["current"] = new_id
        upgrades[current] = new_id
        notes.append(f"{family}: {current} -> {new_id}"
                     + ("" if live else " (prices copied from the old model; check them)"))
    if upgrades:
        updated["updated"] = today
        updated["pair"] = {"lead": current_id(updated, LEAD_FAMILY), "subagent": current_id(updated, SUBAGENT_FAMILY)}
    return updated, upgrades, notes


# ------------------------------------------------------------- rewrites

def rewrite_model_field(text, registry):
    """Upgrade a pinned `model:` id in frontmatter. Returns (text, (old, new) or None)."""
    block, body = frontmatter.split(text)
    if block is None:
        return text, None
    change = []

    def swap(match):
        target = upgrade_target(match.group(3), registry)
        if not target or change:
            return match.group(0)
        change.append((match.group(3), target))
        return f"{match.group(1)}{match.group(2)}{target}{match.group(2)}{match.group(4)}"

    new_block = _MODEL_LINE.sub(swap, block)
    return (f"---\n{new_block}\n---\n{body}", change[0]) if change else (text, None)


def _upgrade_settings(settings, registry):
    """Return (settings, notes) with outdated full model ids replaced. Aliases are left alone."""
    result, notes = dict(settings), []
    target = upgrade_target(settings.get("model"), registry)
    if target:
        result["model"] = target
        notes.append(f"settings: model {settings['model']} -> {target}")
    env = settings.get("env")
    if isinstance(env, dict):
        target = upgrade_target(env.get("CLAUDE_CODE_SUBAGENT_MODEL"), registry)
        if target:
            result["env"] = {**env, "CLAUDE_CODE_SUBAGENT_MODEL": target}
            notes.append(f"settings: CLAUDE_CODE_SUBAGENT_MODEL {env['CLAUDE_CODE_SUBAGENT_MODEL']} -> {target}")
    per_model = settings.get("modelSettings")
    if isinstance(per_model, dict):
        renamed = {}
        for name, entry in per_model.items():
            target = upgrade_target(name, registry)
            if target and target not in per_model:
                notes.append(f"settings: modelSettings {name} -> {target}")
            renamed[target if target and target not in per_model else name] = entry
        result["modelSettings"] = renamed
    return result, notes


def plan_root(root, registry):
    """Plan the upgrades for the Claude Code files under `root`."""
    plan = optimize.new_plan()
    for path in context_cost.agent_files(root):
        relative = path.relative_to(root).as_posix()
        text, change = rewrite_model_field(context_cost.read_text(path), registry)
        if not change:
            continue
        reason = optimize.skip_reason(root, relative)
        if reason:
            plan["warnings"].append(f"models: {relative} {reason}; left on {change[0]}")
            continue
        plan["writes"][relative] = text
        plan["notes"].append(f"models: {relative} {change[0]} -> {change[1]}")
    settings_path = root / optimize.SETTINGS
    if settings_path.is_file() and not optimize.skip_reason(root, optimize.SETTINGS):
        settings = scaffold.load_json_object(settings_path)
        upgraded, notes = _upgrade_settings(settings, registry)
        if notes:
            plan["writes"][optimize.SETTINGS] = json.dumps(upgraded, indent=2) + "\n"
            plan["notes"].extend(f"models: {note}" for note in notes)
    if not plan["writes"]:
        plan["notes"].append("models: every pinned model is current")
    return plan


def _upgrade_profiles(profiles, registry, upgrades):
    """Add a templates/models.json profile for each new model, ahead of the one it replaces."""
    result = {key: value for key, value in profiles.items() if key != "models"}
    result["models"] = {}
    for model_id, profile in profiles.get("models", {}).items():
        new_id = upgrades.get(model_id)
        if new_id and new_id not in profiles["models"]:
            family, version = parse(new_id)
            effort = (registry["models"].get(new_id) or {}).get("effort", profile.get("effort"))
            result["models"][new_id] = {**profile, "label": label(family, version), "effort": effort}
        result["models"][model_id] = profile
    if result.get("default") in upgrades:
        result["default"] = upgrades[result["default"]]
    return result


def plan_package(package, registry, old_registry, upgrades):
    """Return {path: text} for the tq-forge files that must follow a registry change."""
    writes = {}
    if registry != old_registry:
        writes[package / "config" / "models.json"] = json.dumps(registry, indent=2) + "\n"
    if not upgrades:
        return writes
    profiles_path = package / "templates" / "models.json"
    profiles = context_cost.load_json(profiles_path)
    if profiles:
        writes[profiles_path] = json.dumps(_upgrade_profiles(profiles, registry, upgrades), indent=2) + "\n"
    for path in sorted((package / "templates").rglob("*.md")):
        text, change = rewrite_model_field(context_cost.read_text(path), registry)
        if change:
            writes[path] = text
    return writes


def _write_package(writes):
    """Write the package files. Returns (written paths, notes); a read-only package falls back to state."""
    written, notes = [], []
    for path, text in writes.items():
        try:
            scaffold.write_file(path, text, True)
            written.append(str(path))
        except OSError as error:
            if path.name == "models.json" and path.parent.name == "config":
                fallback = models.state_generations_file()
                scaffold.write_file(fallback, text, True)
                written.append(str(fallback))
                notes.append(f"{path} is read-only; registry saved to {fallback}")
            else:
                notes.append(f"could not write {path}: {error}")
    return written, notes


def _stamp(upgrades):
    """Tell the session hook that a sync changed something."""
    path = models.state_generations_file().with_name(STAMP)
    record = {"synced_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "upgrades": upgrades}
    try:
        scaffold.write_file(path, json.dumps(record, indent=2) + "\n", True)
    except OSError:
        pass  # the stamp is a hint for the hook, never a reason to fail a sync


# -------------------------------------------------------------------- cli

def sync(root, found, source="offline", apply=False, templates=True, package=None, errors=()):
    """Plan (and with `apply`, write) one sync. Returns the report dict."""
    package = pathlib.Path(package) if package else models.GENERATIONS_FILE.parents[1]
    old_registry = load_registry()
    registry, upgrades, notes = plan_registry(old_registry, found)
    plan = plan_root(root, registry)
    package_writes = plan_package(package, registry, old_registry, upgrades) if templates else {}
    package_writes = {path: text for path, text in package_writes.items()
                      if context_cost.read_text(path) != text}
    report = optimize.build_report(root, plan, None, apply)
    written = [str(path) for path in package_writes]
    if apply:
        written, extra = _write_package(package_writes)
        notes = [*notes, *extra]
        if upgrades or report["files"]:
            _stamp(upgrades)
    return {
        "mode": "applied" if apply else "dry-run",
        "source": source,
        "discovered": len(found),
        "upgrades": upgrades,
        "pair": registry.get("pair", {}),
        "files": report["files"],
        "package_files": sorted(written),
        "notes": [*notes, *report["notes"]],
        "warnings": [*errors, *report["warnings"]],
    }


def render(report):
    lines = [f"tq-forge sync-models ({report['mode']}, source: {report['source']}, "
             f"{report['discovered']} Claude model ids seen)"]
    if report["upgrades"]:
        lines.extend(f"  new: {old} -> {new}" for old, new in report["upgrades"].items())
    else:
        lines.append("  the registry is current; no newer model found")
    pair = report["pair"]
    lines.append(f"  recommended pair: lead {pair.get('lead')}, subagents {pair.get('subagent')}")
    lines.extend(f"- {note}" for note in report["notes"])
    lines.extend(f"! {warning}" for warning in report["warnings"])
    verb = "written" if report["mode"] == "applied" else "that --apply would write"
    lines.append(f"files {verb}:")
    lines.extend(f"  {path}" for path in [*report["files"], *report["package_files"]])
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(prog="sync-models", description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=".", help="project root whose .claude/ files to upgrade (default: .)")
    parser.add_argument("--source", choices=SOURCES, default="auto", help="where to read live model ids from")
    parser.add_argument("--offline", action="store_true", help="same as --source offline")
    parser.add_argument("--ids-file", help="JSON list of model ids to use instead of a network source")
    parser.add_argument("--no-templates", action="store_true",
                        help="leave the tq-forge registry and templates alone; only upgrade --root")
    parser.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and write nothing (wins over --apply)")
    parser.add_argument("--json", action="store_true")
    return parser


def run(args):
    root = pathlib.Path(args.root).resolve()
    if not root.is_dir():
        raise scaffold.ScaffoldError(f"not a directory: {root}")
    if args.ids_file:
        try:
            listed = json.loads(pathlib.Path(args.ids_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise scaffold.ScaffoldError(f"cannot read --ids-file: {error}")
        if not isinstance(listed, list):
            raise scaffold.ScaffoldError("--ids-file must hold a JSON list of model ids")
        found = {}
        for model_id in listed:
            _record(found, model_id)
        result = {"source": "ids-file", "models": found, "errors": []}
    else:
        result = discover("offline" if args.offline else args.source)
    return sync(root, result["models"], result["source"], args.apply and not args.dry_run,
                not args.no_templates, errors=result["errors"])


def main(argv):
    args = build_parser().parse_args(argv[1:])
    try:
        report = run(args)
    except scaffold.ScaffoldError as error:
        print(f"sync-models: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
