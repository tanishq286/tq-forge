#!/usr/bin/env bash
# scaffold.sh — deterministic scaffolder for Claude Code artifacts.
#
# Same input, same output, no model call. Writes structure and frontmatter and
# leaves judgment-heavy content as TODO(tq-forge) markers for you (or the
# /tq-forge-* skills) to fill in. The scorer penalises unfilled markers.
#
# Usage:
#   scaffold.sh skill "<intent>" [--model <id|alias>] [--effort <level>] [--name <slug>]
#   scaffold.sh agent "<intent>" [--model ...] [--effort ...] [--name ...]
#   scaffold.sh agent --template <fable-5-2-orchestrator|code-reviewer|test-runner|security-auditor>
#   scaffold.sh hooks [--events PreToolUse,PostToolUse,SessionStart,Stop]
#   scaffold.sh mcp --name <server> (--url <https-url> [--token-env VAR] | --command <exe> [--arg A]...)
#                   [--scope project|subagent]
#   scaffold.sh mcp --example
#   scaffold.sh list
#
# Common options: --out <project-root>  --force  --json
# Without --out, output goes to the sandbox under $TQ_FORGE_HOME (default ~/.tq-forge).

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PYTHONDONTWRITEBYTECODE=1 exec python3 "$HERE/lib/scaffold.py" "$@"
