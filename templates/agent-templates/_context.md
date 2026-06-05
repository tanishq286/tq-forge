# Domain context (template)

This file is a placeholder. The real context lives in your state home at
`$TQ_FORGE_HOME/context.md` (default: `~/.tq-forge/context.md`), which
`/tq-forge-agent` injects wherever the `{{CONTEXT}}` token appears in a
generated `system-prompt.md`.

Edit `~/.tq-forge/context.md` once with who you are, what you build, your
customers, the inputs/outputs your agents work with, and any hard rules.
Every agent you forge afterward inherits it — update in one place, not per
agent.

A good context block answers:
- **Who** is the operator the agent works for?
- **What** domain / product / customers?
- **Inputs** the agent commonly receives.
- **Outputs** the agent commonly produces.
- **Invariants**: currency, timezone, follow-up cadence, "never fabricate X".
