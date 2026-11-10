#!/usr/bin/env bash
# dry-test.sh — structural validation of a forged artifact.
#
# This is NOT a live LLM run. It's a static check that the artifact is shaped
# so Claude Code will load it and would behave coherently if invoked. For live
# behavior testing, the user runs the skill manually after promote.
#
# Accepts: a skill (SKILL.md or its directory), a 5-file agent directory, a
# Claude Code subagent file (.claude/agents/<name>.md), an MCP config
# (.mcp.json), or a settings file with a hooks block (.claude/settings.json).
#
# Usage:
#   dry-test.sh <path>
#   dry-test.sh --json <path>

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

JSON_OUT=false
[[ "${1:-}" == "--json" ]] && { JSON_OUT=true; shift; }
TARGET="${1:-}"
[[ -z "$TARGET" ]] && { echo "usage: dry-test.sh [--json] <path>" >&2; exit 2; }

PYTHONDONTWRITEBYTECODE=1 exec python3 "$HERE/lib/drytest.py" "$TARGET" "$JSON_OUT"
