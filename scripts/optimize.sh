#!/usr/bin/env bash
# optimize.sh — shrink the always-loaded context of a Claude Code project.
#
# Dry run by default: prints the plan and the estimated before/after context.
# Nothing is written until you pass --apply. Every file it changes is copied to
# .tq-forge-backup/ first, and `restore` puts everything back.
#
# Usage:
#   optimize.sh measure  [--root DIR] [--mcp-inventory FILE] [--json]
#   optimize.sh optimize [--root DIR] [--only mcp,skills,rules] [--keep-mcp a,b]
#                        [--mute-skills a,b] [--extract-scripts]
#                        [--mcp-inventory FILE] [--apply] [--json]
#   optimize.sh shield   [--root DIR] [--strict] [--subagent-model <id|alias>] [--apply] [--json]
#   optimize.sh restore  [--root DIR]
#
# Token numbers are estimates (characters / 4). Check real usage with /context.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHONDONTWRITEBYTECODE=1 exec python3 "$HERE/lib/optimize.py" "$@"
