"""Target-model profiles for tq-forge (Python stdlib only).

Profiles live in templates/models.json so they can be edited without touching
code. This module resolves a user-supplied name (full id or alias) to a
profile and loads the prompt snippets a profile asks for.
"""

import json
import os
import pathlib
import re

TEMPLATES = pathlib.Path(__file__).resolve().parents[2] / "templates"
_REGISTRY_FILE = TEMPLATES / "models.json"
GENERATIONS_FILE = TEMPLATES.parent / "config" / "models.json"
FALLBACK_SUBAGENT = "claude-haiku-5-5"
TIERS = ("haiku", "sonnet", "opus", "fable")  # least to most capable; mythos shares fable's tier

_SUFFIX = r"(?:-\d{8}|-latest)?(?:-v\d+)?"  # a dated snapshot or -latest, then Bedrock's -v1 / -v2
_CURRENT_ID = re.compile(rf"^claude-(fable|mythos|opus|sonnet|haiku)-(\d{{1,2}})(?:-(\d{{1,2}}))?{_SUFFIX}$")
_LEGACY_ID = re.compile(rf"^claude-(\d{{1,2}})(?:-(\d{{1,2}}))?-(opus|sonnet|haiku){_SUFFIX}$")
_PROVIDER_PREFIX = "anthropic."  # Amazon Bedrock spells ids anthropic.claude-...


def registry():
    return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))


def state_generations_file():
    """Where `sync-models` keeps the registry when the package folder is read-only."""
    home = os.environ.get("TQ_FORGE_HOME") or str(pathlib.Path.home() / ".tq-forge")
    return pathlib.Path(home) / "models.json"


def generations():
    """The model-generation registry `sync-models` maintains: the newer of the bundled and the synced copy."""
    found = []
    for path in (GENERATIONS_FILE, state_generations_file()):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("models"), dict):
            found.append(data)
    # A synced copy written by an older tq-forge lacks the fields a newer schema added,
    # so the schema decides first and the date second.
    return max(found, key=lambda data: (_schema(data), str(data.get("updated", ""))), default={})


def _schema(data):
    try:
        return int(data.get("schema", 1))
    except (TypeError, ValueError):
        return 1


def normalize_id(model_id):
    """Strip provider spellings: anthropic/claude-opus-5.5, anthropic.claude-opus-5-5, claude-opus-4-5@20251101, a :tag."""
    text = str(model_id or "").strip().lower().split("/")[-1].split(":")[0].split("@")[0]
    if text.startswith(_PROVIDER_PREFIX):
        text = text[len(_PROVIDER_PREFIX):]
    return text.replace(".", "-")


def parse_id(model_id):
    """Return (family, (major, minor)) for a Claude model id, or None.

    Accepts current ids (claude-opus-5-5), dated snapshots, `-latest`, the
    older version-first form (claude-3-5-sonnet-20241022), and provider
    spellings such as anthropic/claude-opus-5.5 or claude-opus-4-5@20251101.
    """
    text = normalize_id(model_id)
    match = _CURRENT_ID.match(text)
    if match:
        return match.group(1), (int(match.group(2)), int(match.group(3) or 0))
    match = _LEGACY_ID.match(text)
    if match:
        return match.group(3), (int(match.group(1)), int(match.group(2) or 0))
    return None


def family_current(family, registry=None):
    """The registry's current model id for a family, or None."""
    registry = generations() if registry is None else registry
    return ((registry.get("families") or {}).get(family) or {}).get("current")


def _current_version(registry, family):
    current = family_current(family, registry)
    version = ((registry.get("models") or {}).get(current) or {}).get("version")
    if isinstance(version, list) and len(version) == 2:
        return tuple(version)
    parsed = parse_id(current)
    return parsed[1] if parsed else None


def status(model_id, registry=None):
    """Where a model id stands against the registry.

    Returns {"status", "replacement", "date"}. `status` is one of:
      current     the family's current model
      superseded  an older version that is still served
      deprecated  has a published retirement date
      retired     requests to it fail
      unknown     not a Claude model id this registry can place (a newer or foreign id)
    """
    registry = generations() if registry is None else registry
    wanted = normalize_id(model_id)
    parsed = parse_id(model_id)
    for rule in registry.get("deprecations") or []:
        if "id" in rule and normalize_id(rule["id"]) == wanted:
            return {"status": rule["status"], "replacement": rule.get("replacement"), "date": rule.get("date")}
        if parsed and rule.get("family") == parsed[0] and tuple(rule.get("version") or ()) == parsed[1]:
            return {"status": rule["status"], "replacement": family_current(parsed[0], registry),
                    "date": rule.get("date")}
    if not parsed:
        return {"status": "unknown", "replacement": None, "date": None}
    current = _current_version(registry, parsed[0])
    if current is None or parsed[1] > current:
        return {"status": "unknown", "replacement": None, "date": None}
    if parsed[1] == current:
        return {"status": "current", "replacement": None, "date": None}
    return {"status": "superseded", "replacement": family_current(parsed[0], registry), "date": None}


def lead_model():
    """The model the registry recommends for the main conversation."""
    return (generations().get("pair") or {}).get("lead") or default_model()


def subagent_model():
    """The model the registry recommends for worker subagents."""
    return (generations().get("pair") or {}).get("subagent") or FALLBACK_SUBAGENT


def default_model():
    return registry()["default"]


def known_ids():
    return list(registry()["models"])


def effort_levels():
    return list(registry()["effort_levels"])


def resolve(name):
    """Map a full model id or alias to a known model id, or None if unknown."""
    if not name:
        return None
    wanted = str(name).strip().lower()
    for model_id, profile in registry()["models"].items():
        if wanted in (model_id, profile["alias"]):
            return model_id
    return None


def profile(model_id):
    """Return the profile dict for a known model id, with its id included."""
    data = registry()["models"][model_id]
    return {**data, "id": model_id}


def snippet(name):
    """Load one prompt snippet from templates/snippets/<name>.md."""
    return (TEMPLATES / "snippets" / f"{name}.md").read_text(encoding="utf-8").strip()


def lint_target(declared):
    """Decide which model the lint should assume for an artifact.

    Returns (model_id_or_None, note). An artifact that pins no model, or says
    `inherit`, is linted against the default profile. One that pins an older
    id of a known family is linted against that family's current model, the
    one it has to move to; before 1.3.0 such a file got no model rules at all
    and scored as if it were clean. Only an id of no known family is skipped.
    """
    if not declared or str(declared).strip().lower() == "inherit":
        return default_model(), "no model pinned; assuming the default profile"
    model_id = resolve(declared)
    if model_id:
        return model_id, "model pinned in frontmatter"
    parsed = parse_id(declared)
    current = family_current(parsed[0]) if parsed else None
    if current:
        return current, f"no profile for '{declared}'; linted against {current}, the current {parsed[0]} model"
    return None, f"no profile for '{declared}'; model-specific rules skipped"
