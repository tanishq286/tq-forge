#!/usr/bin/env bash
# auto-improve.sh — self-improving pass over a Claude Code setup.
#
# Runs everything `optimize.sh optimize` does, then uses session logs and the
# 0-100 rubric to find what still costs tokens on every turn without being used.
#
# Dry run by default: prints the plan and the estimated before/after context.
# Nothing is written until you pass --apply. Every file it changes is copied to
# .tq-forge-backup/ first, and `optimize.sh restore` puts everything back.
#
# Usage:
#   auto-improve.sh [--root DIR] [--apply] [--follow-symlinks] [--dedupe-plugins]
#                   [--scope-rules] [--extract-scripts] [--keep-mcp a,b]
#                   [--threshold TOKENS] [--min-score N] [--description-limit CHARS]
#                   [--mcp-inventory FILE] [--listing-budget CHARS] [--json]
#
# Token numbers are estimates (characters / 4). Check real usage with /context.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHONDONTWRITEBYTECODE=1 exec python3 "$HERE/lib/auto_improve.py" "$@"
