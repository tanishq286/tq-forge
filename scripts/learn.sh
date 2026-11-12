#!/usr/bin/env bash
# learn.sh — research a URL or a topic and turn what was found into a skill.
#
# Usage:
#   learn.sh learn <url-or-query> [--apply] [--root DIR] [--offline] [--json]
#   learn.sh scout <topic> [--sources youtube,github,social,web] [--limit N] [--apply] [--root DIR] [--json]
#
# Without --apply the synthesized skill goes to the sandbox ($TQ_FORGE_HOME/sandbox/learned/)
# for you to read. With --apply a skill scoring 85 or more is written to
# <root>/.claude/skills/learned-<slug>/, backed up like any optimizer change.
#
# External text is treated as data: lines that look like prompt injection or
# unsafe shell are removed before anything is written.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHONDONTWRITEBYTECODE=1 exec python3 "$HERE/lib/self_evolve.py" "$@"
