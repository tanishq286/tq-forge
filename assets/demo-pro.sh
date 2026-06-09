#!/usr/bin/env bash
# Pro demo: install → gold standard → forged skill passes → thin skill BLOCKED.
# All scores are live scorer output. ~40s total.
set -e
cd "$(dirname "$0")/.."                          # repo root
p(){ printf '\033[1;32m$\033[0m %s\n' "$1"; sleep 0.8; }
c(){ printf '\n\033[2;37m# %s\033[0m\n' "$1"; sleep 0.9; }

clear; sleep 0.5
printf '\033[1m  tq-forge\033[0m \033[2;37m— skills & agents for Claude Code, scored without an LLM\033[0m\n\n'
sleep 1.2

p  "npx tq-forge install"
printf '  \033[32m✓\033[0m 13 skills → ~/.claude/skills/    \033[2;37m(bash + python3 · 0 deps · 0 telemetry)\033[0m\n'
sleep 1.4

c  "1/3 · the bundled skill — the gold standard"
p  "bash scripts/quality-score.sh skills/tq-forge"
bash scripts/quality-score.sh skills/tq-forge
sleep 2.2

c  "2/3 · a forged skill — clears the gate at 7.8"
p  "bash scripts/quality-score.sh examples/forged-skills/github-pr-digest"
bash scripts/quality-score.sh examples/forged-skills/github-pr-digest
sleep 1.6
printf '  \033[32m7.8 ≥ 7 ✓\033[0m  eligible for \033[1m/tq-forge-promote\033[0m → ~/.claude/skills/\n'
sleep 2.0

c  "3/3 · a thin skill — the gate BLOCKS it"
mkdir -p /tmp/thin-skill
printf '# thin\n## When to use\nsometimes\n' > /tmp/thin-skill/SKILL.md
p  "bash scripts/quality-score.sh /tmp/thin-skill"
bash scripts/quality-score.sh /tmp/thin-skill
rm -rf /tmp/thin-skill
sleep 1.4
printf '  \033[31m3.2 < 7 ✗\033[0m  blocked — \033[1m/tq-forge-improve\033[0m rewrites only the weak sections\n'
sleep 1.6

printf '\n  \033[2;37mstatic python · 0 tokens · same input → same score · github.com/tanishq286/tq-forge\033[0m\n'
sleep 2.8
