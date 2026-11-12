#!/usr/bin/env bash
# optimize.sh — shrink the always-loaded context of a Claude Code project.
#
# Dry run by default: prints the plan and the estimated before/after context.
# Nothing is written until you pass --apply. Every file it changes is copied to
# .tq-forge-backup/ first, and `restore` puts everything back.
#
# Usage:
#   optimize.sh measure  [--root DIR] [--mcp-inventory FILE] [--json]
#   optimize.sh optimize [--root DIR] [--only mcp,skills,rules,prose] [--isolate-mcp [--keep-mcp a,b]]
#                        [--description-limit CHARS] [--mute-skills a,b] [--extract-scripts]
#                        [--follow-symlinks] [--dedupe-plugins]
#                        [--mcp-inventory FILE] [--apply] [--json]
#   optimize.sh shield   [--root DIR] [--strict] [--deny-env] [--effort LEVEL] [--subagent-model <id|alias>] [--apply] [--json]
#   optimize.sh restore  [--root DIR] [--outside] [--discard-edits]
#
# Lossless by default: MCP servers stay in .mcp.json with their tools deferred, descriptions of
# 350 characters or fewer are never cut, and files under .claude/plugins/ are never written.
#
# Token numbers are estimates (characters / 4). Check real usage with /context.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHONDONTWRITEBYTECODE=1 exec python3 "$HERE/lib/optimize.py" "$@"
