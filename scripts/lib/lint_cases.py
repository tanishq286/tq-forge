"""Fixtures for the model-compatibility lint (Python stdlib only).

Each case is one deterministic assertion: a text, the model it targets, the
rule under test, and whether that rule must fire. `scripts/test-runner.py`
runs every case as part of the scorer assertion suite, and
`tests/test_model_compat.py` runs them as unit tests. The texts are the
anti-patterns themselves, so this file is expected to trip the lint.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import models  # noqa: E402

# Ids come from the bundled registry, so the cases still hold after `sync-models` adds a release.
_REGISTRY = json.loads(models.GENERATIONS_FILE.read_text(encoding="utf-8"))
FABLE, OPUS, SONNET, HAIKU = (models.family_current(family, _REGISTRY) for family in ("fable", "opus", "sonnet", "haiku"))


def newer(model_id):
    """An id one minor version ahead of `model_id`: newer than the registry, so not stale."""
    family, (major, minor) = models.parse_id(model_id)
    return f"claude-{family}-{major}-{minor + 1}"


def subagent(tools="Read, Edit, Bash", effort="medium", steps=3, extra=""):
    """A minimal subagent file. `tools=None` leaves the field out, so the agent inherits every tool."""
    tool_line = f"tools: {tools}\n" if tools else ""
    workflow = "\n".join(f"{number}. Do part {number} of the job." for number in range(1, steps + 1))
    return (f"---\nname: worker\ndescription: Applies the change in the brief. Use when a change is ready.\n"
            f"effort: {effort}\n{tool_line}---\n\nYou apply one change.\n\n## Workflow\n\n{workflow}\n{extra}")


FINISHING = "\n# Finishing work\n\nKeep working until everything in the brief is done, then stop and report.\n"

# (rule id, model, text, must fire, what the case shows)
PATTERN_CASES = (
    # M001: a fixed thinking budget instead of adaptive thinking + effort
    ("M001", FABLE, 'thinking={"type": "enabled", "budget_tokens": 10000}', True, "enabled thinking with a budget"),
    ("M001", OPUS, '"thinking": {"type": "enabled", "budget_tokens": 4096}', True, "JSON request body"),
    ("M001", SONNET, "thinking: { type: 'enabled', budgetTokens: 2048 }", True, "camelCase SDK field"),
    ("M001", HAIKU, "export MAX_THINKING_TOKENS=8000", True, "environment variable budget"),
    ("M001", FABLE, 'thinking={"type": "adaptive"}, output_config={"effort": "high"}', False, "adaptive thinking + effort"),
    ("M001", FABLE, "Never send budget_tokens; set effort instead.", False, "a negated mention"),
    # M010: thinking switched off
    ("M010", FABLE, 'thinking={"type": "disabled"}', True, "disabled thinking on Fable"),
    ("M010", OPUS, '"thinking": {"type": "disabled"}', True, "disabled thinking on Opus"),
    ("M010", SONNET, "Disable thinking for this route to save time.", True, "prose instruction on Sonnet"),
    ("M010", HAIKU, 'thinking={"type": "disabled"}', False, "Haiku accepts it at high effort or below"),
    ("M010", SONNET, 'thinking={"type": "between_tools"}', False, "the Sonnet replacement"),
    ("M010", FABLE, "Do not disable thinking; lower effort instead.", False, "a negated mention"),
    # M008: sampling parameters
    ("M008", FABLE, "temperature=0.2", True, "low temperature on Fable"),
    ("M008", FABLE, "temperature: 1", True, "Fable rejects every value, the default included"),
    ("M008", OPUS, '"top_p": 0.9', True, "top_p on Opus"),
    ("M008", SONNET, "temperature: 0", True, "non-default temperature on Sonnet"),
    ("M008", HAIKU, "top_k=40", True, "top_k on Haiku"),
    ("M008", SONNET, "topP: 0.5", True, "camelCase top_p"),
    ("M008", SONNET, "temperature: 1.0", False, "Sonnet accepts the default temperature"),
    ("M008", HAIKU, "top_p=0.99", False, "Haiku accepts the default top_p"),
    ("M008", FABLE, "Remove temperature=0.7 from the request.", False, "a negated mention"),
    ("M008", FABLE, "search({ query: topic, topK: 5 })", False, "a retrieval limit is not a sampling parameter"),
    ("M008", FABLE, "Store samples at a temperature: 21 degrees.", False, "an unrelated number"),
    # M004: raw reasoning asked for in the reply
    ("M004", FABLE, "Show your full chain of thought before the answer.", True, "chain of thought in the reply"),
    ("M004", OPUS, "Output your reasoning step by step in the reply.", True, "reasoning in the reply"),
    ("M004", SONNET, "Begin every response with a Reasoning section.", True, "a reasoning header"),
    ("M004", FABLE, "Wrap your analysis in <thinking> tags.", True, "thinking tags"),
    ("M004", FABLE, "Print the raw chain-of-thought to the user.", True, "raw chain-of-thought"),
    ("M004", FABLE, "Put a scratchpad block before the final answer.", True, "a scratchpad block"),
    ("M004", HAIKU, "Show your full chain of thought before the answer.", False,
     "Haiku has no reasoning_extraction category"),
    ("M004", FABLE, "Do not show your reasoning in the reply.", False, "a negated mention"),
    ("M004", FABLE, "Explain in two sentences why you chose this fix.", False, "a short explanation is fine"),
    ("M004", FABLE, 'thinking={"type": "adaptive", "display": "summarized"}', False, "summarized thinking blocks"),
    # an opt-out comment, and a target the lint has no rules for
    ("M001", FABLE, "budget_tokens: 4000\n<!-- tq-forge-lint-ignore: M001 -->", False, "an ignore comment"),
    ("M001", "gpt-5", 'thinking={"type": "enabled", "budget_tokens": 10000}', False, "a non-Claude target"),
)

# (model, subagent text, effort override, must fire, what the case shows)
COMPLETION_CASES = (
    (FABLE, subagent(effort="medium"), None, True, "Fable at medium, can edit files, no completion text"),
    (FABLE, subagent(effort="low"), None, True, "Fable at low"),
    (SONNET, subagent(effort="low"), None, True, "Sonnet at low"),
    (HAIKU, subagent(effort="low"), None, True, "Haiku at low"),
    (FABLE, subagent(tools="Read, Grep", effort="medium", steps=6), None, True, "read-only but six workflow steps"),
    (FABLE, subagent(tools=None, effort="medium"), None, True, "no tools field: inherits every tool"),
    (FABLE, subagent(effort="high"), "medium", True, "pinned high, asked about medium"),
    (FABLE, subagent(effort="high"), None, False, "Fable at high"),
    (SONNET, subagent(effort="medium"), None, False, "Sonnet at medium"),
    (OPUS, subagent(effort="low"), None, False, "Opus has no documented early stop"),
    (FABLE, subagent(effort="medium", extra=FINISHING), None, False, "a Finishing work block"),
    (FABLE, subagent(tools="Read, Grep", effort="medium"), None, False, "short and read-only"),
)

# (text, penalty or None when the rule must stay quiet, what the case shows)
STALE_ID_CASES = (
    ("model: claude-3-5-sonnet-20241022", 10, "a retired dated snapshot"),
    ("model: anthropic/claude-opus-4.1", 10, "a retired id in provider spelling"),
    ('modelId="anthropic.claude-3-5-sonnet-20241022-v2:0"', 10, "a retired id in Amazon Bedrock spelling"),
    ('model="claude-sonnet-4-5-20250929"', 6, "a deprecated id"),
    ("Run it on claude-mythos-preview.", 6, "a deprecated id listed by name"),
    ("model: claude-sonnet-4-6", 3, "an older version that is still served"),
    (f"model: {FABLE}", None, "the current id"),
    (f"model: {newer(FABLE)}", None, "an id newer than the registry"),
    (f"modelId: {OPUS.replace('claude-', 'anthropic.claude-', 1)}", None, "the current id in Amazon Bedrock spelling"),
    (f"Migrated from claude-sonnet-4-6 to {SONNET}.", None, "a line about model history"),
    ("Do not use claude-3-opus-20240229.", None, "a negated mention"),
    ("Install claude-code and claude-flow first.", None, "names that are not model ids"),
)


def skill_file(description, body):
    """A minimal SKILL.md, for the rules that compare the body with the frontmatter description."""
    return f"---\nname: example\ndescription: {description}\n---\n\n# Example\n\n{body}\n"


SILENT = "Summarizes a report. Use when the user asks for a summary."

# (description, body, must fire, what the case shows). M013 reads skills only.
LANGUAGE_CASES = (
    (SILENT, "Always respond in Chinese.", True, "a Chinese reply the description never names"),
    (SILENT, "Output in Japanese only.", True, "output in Japanese"),
    (SILENT, "Write the summary in Spanish.", True, "write in Spanish"),
    (SILENT, "Translate the result into Hindi.", True, "translate into Hindi"),
    (SILENT, "Output language: French", True, "an output-language line"),
    (SILENT, "The reply must be in German.", True, "must be in German"),
    (SILENT, "Reply in Simplified Chinese.", True, "a script variant"),
    (SILENT, "Write in Spanish. Then respond in Japanese.", True, "two languages, neither named"),
    ("Summarizes a report in Chinese. Use when asked.", "Always respond in Chinese.", False, "the description names it"),
    ("Summarizes a report. Use when asked for 中文 notes.", "Respond in Chinese.", False, "a native spelling counts"),
    ("Replies in Japanese. Use when asked.", "Write in Spanish. Respond in Japanese.", True, "only one of two is named"),
    (SILENT, "Respond in English.", False, "English is the default"),
    (SILENT, "Never respond in Chinese.", False, "a negated mention"),
    (SILENT, "Read reports written in Japanese.", False, "an input language is not an output language"),
    (SILENT, "```\nrespond in French\n```", False, "a sample prompt inside a code fence"),
    (SILENT, "Respond in Korean.\n<!-- tq-forge-lint-ignore: M013 -->", False, "the file opts out"),
    (SILENT, "Respond in the language the user writes in.", False, "no language is named"),
)
