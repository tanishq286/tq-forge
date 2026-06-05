# Contributing to tq-forge

Thanks for your interest! tq-forge is small and hackable on purpose.

## Ways to contribute

- **New agent archetypes** — add a `templates/agent-templates/<kind>.md` following
  the existing shape (yaml block, Persona, Output format, NEVER, `{{CONTEXT}}`),
  then list it in `/tq-forge-agent`'s kind options.
- **Smarter scoring** — improve the heuristics in `scripts/quality-score.sh` or
  `scripts/dry-test.sh`. Keep them pure-stdlib and token-free.
- **Example skills** — drop runnable examples under `docs/examples/`.
- **Docs + fixes** — typos, clarity, edge cases.

## Ground rules

- **No new runtime dependencies.** Scripts use `bash` + `python3` stdlib only.
  No pip, no npm. This keeps install a one-liner.
- **State is sacred.** Anything under `$TQ_FORGE_HOME` is user data. Read it,
  don't clobber it. All writes are read-modify-write with atomic replace.
- **Scoring stays free.** The scorer must never make an LLM/API call.
- **Keep skills self-describing.** Every SKILL.md keeps its When-to-use,
  Procedure, Pitfalls, Verification, and Tags sections (it has to pass its own
  dry-test).

## Local testing

```bash
# Lint the shell scripts (if you have shellcheck)
shellcheck scripts/*.sh

# Score one of the bundled skills against the scorer
bash scripts/quality-score.sh skills/tq-forge
bash scripts/dry-test.sh skills/tq-forge
```

## PRs

Keep them focused — one archetype, one heuristic, or one fix per PR. Describe the
before/after and include a sample of the scorer output if you touched scoring.
