#!/usr/bin/env bash
# Evaluate recorded agent runs against a deterministic suite.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/lib/evaluate.py" "$@"
