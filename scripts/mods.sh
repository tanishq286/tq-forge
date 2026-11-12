#!/usr/bin/env bash
# mods.sh — the signal-driven mods: install, status, toggle, savings, keep-warm.
#
# Usage:
#   mods.sh install [--root DIR] [--apply] [--allow-autonomy] [--json]
#   mods.sh status | savings
#   mods.sh toggle <mod> <on|off|haiku|sonnet>
#   mods.sh keep-warm [--ttl 55m|4m] [--wait]
#   mods.sh handoff [--transcript FILE] [--cwd DIR]
#
# `install` is a dry run unless --apply is passed, and `optimize.sh restore` undoes it.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHONDONTWRITEBYTECODE=1 exec python3 "$HERE/lib/mods.py" "$@"
