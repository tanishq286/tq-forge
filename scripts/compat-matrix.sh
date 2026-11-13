#!/usr/bin/env bash
# compat-matrix.sh — cross-model compatibility matrix for the bundled skills and templates.
#
# Scores every bundled skill and subagent template under the lint rules of each
# current Claude model and prints the result as Markdown. Static analysis only:
# no model is called and no network request is made.
#
# Usage:
#   compat-matrix.sh [--write] [--check] [--json] [--out FILE]

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHONDONTWRITEBYTECODE=1 exec python3 "$HERE/lib/compat_matrix.py" "$@"
