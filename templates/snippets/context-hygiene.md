# Context hygiene

Delegation costs a full subagent run, so decide by cost first:

- Do the work yourself when it is a direct edit to five or fewer files you already know.
- Delegate to a worker subagent when the task means reading more than ten files, running a test suite, reading a long log, or calling tools from an MCP server that lives in an `mcp-*` subagent.
- Ask every worker for a summary of 15 lines or fewer with exact `file:line` pointers. Do not ask for raw logs or full file listings.

Keep the conversation append-only: put a correction in a new message, and leave earlier turns, the system prompt, and the tool list as they are for the whole session.

When a skill bundles scripts, run them with Bash instead of reading them into the conversation, and open a skill's `reference.md` only when a step needs it.
