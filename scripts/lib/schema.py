"""Schemas for the Claude Code files tq-forge generates (Python stdlib only).

Field names and allowed values follow the Claude Code documentation for
subagents, hooks, and MCP configuration. Claude Code silently ignores a
frontmatter field it does not recognize, so an unknown field is almost always
a typo worth reporting.
"""

SUBAGENT_FIELDS = frozenset({
    "name", "description", "tools", "disallowedTools", "allowed-tools", "allowedTools",
    "model", "permissionMode", "maxTurns", "autoCompactWindow", "skills", "mcpServers",
    "hooks", "memory", "background", "omitClaudeMd", "effort", "isolation", "color",
    "initialPrompt", "experimental",
})

SKILL_FIELDS = frozenset({
    "name", "description", "when_to_use", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "allowed-tools", "disallowed-tools",
    "tools", "model", "effort", "context", "agent", "background", "hooks", "paths", "shell",
    "metadata", "license", "compatibility",
})

MODEL_ALIASES = frozenset({"sonnet", "opus", "haiku", "fable", "inherit"})
PERMISSION_MODES = frozenset({
    "default", "manual", "acceptEdits", "auto", "dontAsk", "bypassPermissions", "plan",
})
MEMORY_SCOPES = frozenset({"user", "project", "local"})
ISOLATION_MODES = frozenset({"worktree"})
COLORS = frozenset({"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"})
NAME_MAX_LENGTH = 256

# Events tq-forge scaffolds, with whether exit code 2 blocks the action.
SCAFFOLDED_HOOK_EVENTS = {
    "PreToolUse": True,
    "PostToolUse": False,
    "SessionStart": False,
    "Stop": True,
}

HOOK_EVENTS = frozenset({
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "PostToolBatch", "PermissionRequest",
    "PermissionDenied", "UserPromptSubmit", "UserPromptExpansion", "Notification", "Stop",
    "StopFailure", "SubagentStart", "SubagentStop", "SessionStart", "SessionEnd", "Setup",
    "PreCompact", "PostCompact", "PreModelSwitch", "PostModelSwitch", "TaskCreated",
    "TaskCompleted", "TeammateIdle", "ConfigChange", "CwdChanged", "DirectoryAdded",
    "FileChanged", "InstructionsLoaded", "MessageDisplay", "Elicitation", "ElicitationResult",
    "WorktreeCreate", "WorktreeRemove",
})
HOOK_HANDLER_TYPES = frozenset({"command", "http", "mcp_tool", "prompt", "agent"})

MCP_TRANSPORTS = frozenset({"stdio", "http", "streamable-http", "sse", "ws"})
MCP_REMOTE_TRANSPORTS = frozenset({"http", "streamable-http", "sse", "ws"})
SECRET_KEY_HINT = ("key", "token", "secret", "password", "passwd", "authorization", "credential")


def is_model_value(value):
    """True for an alias, `inherit`, or anything shaped like a full model id."""
    text = str(value).strip()
    return text in MODEL_ALIASES or text.startswith("claude-")


def name_problem(name):
    """Return why a subagent name would make Claude Code skip the file, or None."""
    text = str(name)
    if not text:
        return "name is empty"
    if text.startswith("-"):
        return "name starts with '-'"
    if ":" in text:
        return "name contains ':' (reserved for plugin-scoped names)"
    if len(text) > NAME_MAX_LENGTH:
        return f"name is longer than {NAME_MAX_LENGTH} characters"
    return None


def looks_like_secret_key(key):
    lowered = str(key).lower()
    return any(hint in lowered for hint in SECRET_KEY_HINT)
