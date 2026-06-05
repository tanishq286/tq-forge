#!/usr/bin/env bash
# common.sh — shared paths + helpers for tq-forge scripts.
#
# State home (writable, survives plugin reinstall):
#   $TQ_FORGE_HOME   (default: ~/.tq-forge)
#
# Layout:
#   $TQ_FORGE_HOME/sandbox/forged-skills/<slug>/SKILL.md
#   $TQ_FORGE_HOME/sandbox/forged-agents/<slug>/{AGENT.md,...}
#   $TQ_FORGE_HOME/skill-log.json        # inventory of forged items
#   $TQ_FORGE_HOME/forge-queue.json      # deferred intents + needs_manual_review
#   $TQ_FORGE_HOME/context.md            # YOUR domain context (injected into agents)
#   $TQ_FORGE_HOME/halt.flag             # optional manual pause (touch to pause)
#
# Production install target for promoted skills (Claude Code user skills dir):
#   $CLAUDE_SKILLS_DIR   (default: ~/.claude/skills)

# Exported so the inline Python heredocs in the skills can read them via os.environ.
export TQ_FORGE_HOME="${TQ_FORGE_HOME:-$HOME/.tq-forge}"
export CLAUDE_SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

export SANDBOX_SKILLS="$TQ_FORGE_HOME/sandbox/forged-skills"
export SANDBOX_AGENTS="$TQ_FORGE_HOME/sandbox/forged-agents"
export SKILL_LOG="$TQ_FORGE_HOME/skill-log.json"
export FORGE_QUEUE="$TQ_FORGE_HOME/forge-queue.json"
export CONTEXT_FILE="$TQ_FORGE_HOME/context.md"
export HALT_FLAG="$TQ_FORGE_HOME/halt.flag"

tq_ensure_home() {
    mkdir -p "$SANDBOX_SKILLS" "$SANDBOX_AGENTS"
    [[ -f "$SKILL_LOG" ]]    || echo '[]' > "$SKILL_LOG"
    [[ -f "$FORGE_QUEUE" ]]  || echo '{"queue":[],"needs_manual_review":[]}' > "$FORGE_QUEUE"
    [[ -f "$CONTEXT_FILE" ]] || cat > "$CONTEXT_FILE" <<'EOF'
# Domain context

Replace this with the context your forged agents need to make non-generic
decisions: who you are, what you build, your customers, the inputs/outputs
your agents work with, and any hard rules ("never fabricate numbers").

This file is injected into every forged agent's system-prompt.md wherever
the `{{CONTEXT}}` token appears.
EOF
}

# Resolve a slug to its directory across sandbox + production.
tq_resolve() {
    local slug="$1"
    for d in "$SANDBOX_SKILLS/$slug" "$SANDBOX_AGENTS/$slug" \
             "$CLAUDE_SKILLS_DIR/$slug" "$CLAUDE_SKILLS_DIR/agents/$slug"; do
        [[ -d "$d" ]] && { echo "$d"; return 0; }
    done
    [[ -e "$slug" ]] && { echo "$slug"; return 0; }
    return 1
}
