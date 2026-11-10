# Contributing to tq-forge

Thank you for contributing to `tq-forge`! This project is maintained as a clean, deterministic, and dependency-free toolkit for Claude Code skills and autonomous subagents.

## Development Principles

1. **No External Runtime Dependencies**: All runtime scripts must use pure `bash` and the `python3` standard library. No pip packages and no npm runtime dependencies.
2. **Deterministic & Token-Free Scoring**: The quality scorer (`scripts/quality-score.sh` and `scripts/lib/score.py`) must remain static, deterministic, and token-free. Never call an LLM API inside the scorer or linter.
3. **Spec Compliance**: All generated skills must adhere to Claude Code's specification (e.g. `description` <= 1536 characters, `allowed-tools`, valid YAML frontmatter). All subagents must use documented fields (`model`, `effort`, `isolation`, `permissionMode`, `memory`, `tools`).
4. **Safety & Hook Enforcement**: Lifecycle hooks must adhere strictly to exit code semantics: `exit 0` to allow, `exit 2` to block. Destructive actions must be prevented by default.
5. **State Isolation**: User state under `$TQ_FORGE_HOME` is isolated in a sandbox until explicitly promoted. Writes are atomic.

## Local Development & Testing

Run the full automated test suite and quantitative scorer benchmarks locally:

```bash
# Run the complete test suite (225+ assertions)
npm test

# Run shellcheck across all shell scripts
npx shellcheck scripts/*.sh templates/hooks/*.sh

# Run structural dry-test on any skill or subagent
bash scripts/dry-test.sh skills/tq-forge
bash scripts/dry-test.sh templates/agents/fable-5-2-orchestrator.md

# Score any artifact on the 0-100 quality scale
bash scripts/quality-score.sh skills/tq-forge
bash scripts/quality-score.sh templates/agents/fable-5-2-advisor.md

# Test CLI smoke test in isolated directories
export TQ_FORGE_HOME="/tmp/tqhome"
export CLAUDE_SKILLS_DIR="/tmp/skills"
node bin/cli.js install
node bin/cli.js doctor
```

## Pull Request Guidelines

- Ensure `npm test` passes 100% cleanly before opening a pull request.
- Ensure all shell scripts pass `shellcheck` with zero warnings.
- Keep changes modular and adhere to [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`, `ci:`).
- Document new features in `CHANGELOG.md` under `[Unreleased]`.
