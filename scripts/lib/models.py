"""Target-model profiles for tq-forge (Python stdlib only).

Profiles live in templates/models.json so they can be edited without touching
code. This module resolves a user-supplied name (full id or alias) to a
profile and loads the prompt snippets a profile asks for.
"""

import json
import os
import pathlib

TEMPLATES = pathlib.Path(__file__).resolve().parents[2] / "templates"
_REGISTRY_FILE = TEMPLATES / "models.json"
GENERATIONS_FILE = TEMPLATES.parent / "config" / "models.json"
FALLBACK_SUBAGENT = "claude-haiku-5-5"


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
    return max(found, key=lambda data: str(data.get("updated", "")), default={})


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
    `inherit`, is linted against the default profile. One that pins a model
    tq-forge has no profile for gets no model-specific rules.
    """
    if not declared or str(declared).strip().lower() == "inherit":
        return default_model(), "no model pinned; assuming the default profile"
    model_id = resolve(declared)
    if model_id:
        return model_id, "model pinned in frontmatter"
    return None, f"no profile for '{declared}'; model-specific rules skipped"
