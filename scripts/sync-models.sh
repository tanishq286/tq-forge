#!/usr/bin/env bash
# sync-models.sh — keep the model registry and pinned model ids current.
#
# Reads the live list of Claude model ids (Anthropic's /v1/models when
# ANTHROPIC_API_KEY is set, otherwise OpenRouter's public model list) and, when
# a family has a newer version, updates config/models.json and every pinned
# `model:` id that is now behind.
#
# Dry run by default; --apply writes. --offline makes no network call.
#
# Usage:
#   sync-models.sh [--root DIR] [--source auto|anthropic|openrouter|offline]
#                  [--offline] [--ids-file FILE] [--no-templates] [--apply] [--json]

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHONDONTWRITEBYTECODE=1 exec python3 "$HERE/lib/model_sync.py" "$@"
