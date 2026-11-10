"""Target-model profiles for tq-forge (Python stdlib only).

Profiles live in templates/models.json so they can be edited without touching
code. This module resolves a user-supplied name (full id or alias) to a
profile and loads the prompt snippets a profile asks for.
"""

import json
import pathlib

TEMPLATES = pathlib.Path(__file__).resolve().parents[2] / "templates"
_REGISTRY_FILE = TEMPLATES / "models.json"


def registry():
    return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))


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
