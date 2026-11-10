"""Model-compatibility lint for skills and subagent prompts (Python stdlib only).

Static, token-free checks for instructions that current Claude models reject
or that are documented to make them perform worse. Each rule names the models
it applies to; the caller passes the model the artifact targets.

Findings are heuristics over text, not proof. A file can opt out of a rule it
has a good reason to break with an HTML comment:

    <!-- tq-forge-lint-ignore: M002, M005 -->
"""

import re

FABLE = "claude-fable-5-2"
OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
ALL_MODELS = frozenset({FABLE, OPUS, SONNET, HAIKU})
ANY_TARGET = None  # structural rules: apply whatever the target model is

MAX_TOTAL_PENALTY = 40
PLACEHOLDER = "TODO(tq-forge)"

_IGNORE = re.compile(r"<!--\s*tq-forge-lint-ignore:\s*([A-Za-z0-9,\s]+?)\s*-->")
_NEGATION = re.compile(
    r"\b(?:never|don'?t|do not|does not|doesn'?t|avoid|no longer|instead of|rather than"
    r"|not to|without|must not|should not|shouldn'?t|cannot|can'?t|won'?t"
    r"|remove|delete|flags?|rejects?)\b",
    re.I,
)
_NEGATION_WINDOW = 80

_NUMBER = r"\d[\d,.]*\s*k?"
_TOKENS = r"(?:output\s+|thinking\s+|reasoning\s+)?tokens?\b"

RULES = (
    {
        "id": "M001",
        "name": "thinking-budget-param",
        "penalty": 8,
        "models": ALL_MODELS,
        "pattern": r"budget_tokens|max_thinking_tokens"
        r"|thinking[\"']?\s*[:=]\s*\{[^}\n]{0,40}[\"']enabled[\"']",
        "message": "A fixed thinking-token budget is rejected by this model; depth is set by effort.",
        "fix": "Delete the budget and set `effort` in the frontmatter instead.",
    },
    {
        "id": "M002",
        "name": "prompt-token-budget",
        "penalty": 8,
        "models": ALL_MODELS,
        "pattern": rf"\btoken\s+budget\s*(?:of|is|:|=)\s*{_NUMBER}"
        rf"|\b{_NUMBER}[- ]?tokens?\s+budget\b"
        rf"|\b(?:thinking|reasoning)\s+budget\b"
        rf"|\bbudget\s+of\s+{_NUMBER}\s*{_TOKENS}"
        rf"|\byou\s+have\s+(?:only\s+|at\s+most\s+)?{_NUMBER}\s*{_TOKENS}"
        rf"|\b(?:use|spend|stay\s+under|stay\s+within|limit\s+yourself\s+to|no\s+more\s+than|at\s+most)"
        rf"\s+{_NUMBER}\s*{_TOKENS}",
        "message": "A hardcoded token budget shown to the model changes how much it spends and can cut work short.",
        "fix": "Remove the number. Control depth with `effort`; state the outcome you need instead.",
    },
    {
        "id": "M003",
        "name": "think-less-instruction",
        "penalty": 8,
        "models": ALL_MODELS,
        "pattern": r"\bwithout\s+(?:deliberat\w+|overthinking)"
        r"|\b(?:answer|respond|reply)\s+(?:directly\s+|immediately\s+|instantly\s+)?without\s+(?:thinking|reasoning)"
        r"|\bdo(?:n'?t|\s+not)\s+(?:deliberate|overthink)\b"
        r"|\bdo(?:n'?t|\s+not)\s+(?:think|reason)\b(?!\s+(?:of|about|that)\b)"
        r"|\bthink\s+less\b"
        r"|\bskip\s+(?:the\s+|your\s+)?(?:thinking|reasoning|deliberation)\b"
        r"|\bno\s+need\s+to\s+(?:think|deliberate|reason)\b",
        "message": "Telling this model to think less does not reduce thinking; it only adds noise.",
        "fix": "Delete the line and lower `effort` in the frontmatter.",
    },
    {
        "id": "M004",
        "name": "reasoning-in-response",
        "penalty": 10,
        "models": frozenset({FABLE, OPUS, SONNET}),
        "pattern": r"\b(?:show|output|print|include|write(?:\s+out)?|reveal|expose|display|return|share)\s+"
        r"(?:all\s+(?:of\s+)?)?(?:your|its)\s+"
        r"(?:full\s+|raw\s+|complete\s+|internal\s+|entire\s+|detailed\s+|step[- ]by[- ]step\s+)*"
        r"(?:chain[- ]of[- ]thought|thought\s+process|reasoning|thinking|internal\s+monologue|scratchpad)\b"
        r"|\bshow\s+your\s+work\b"
        r"|\b(?:reason|think)\s+(?:out\s+loud|aloud)\b"
        r"|<(?:thinking|scratchpad|reasoning)>",
        "message": "Asking for raw reasoning in the response text can be declined as reasoning extraction.",
        "fix": 'Read thinking blocks with `display: "summarized"`, or ask for a short explanation of the answer.',
    },
    {
        "id": "M005",
        "name": "thinking-scaffold",
        "penalty": 3,
        "models": ALL_MODELS,
        "pattern": r"\bthink(?:ing)?\s+step[- ]by[- ]step\b|\btake\s+a\s+deep\s+breath\b|\bthink\s+harder\b",
        "message": "Thinking incantations are redundant on a model that always thinks.",
        "fix": "Delete the phrase. Raise `effort` if the task needs more depth.",
    },
    {
        "id": "M006",
        "name": "history-editing",
        "penalty": 8,
        "models": ALL_MODELS,
        "pattern": r"\b(?:strip|remove|drop|delete|prune|discard)\w*\s+"
        r"(?:the\s+|all\s+|any\s+|old\s+|older\s+|earlier\s+|previous\s+|prior\s+)*thinking\s+blocks?\b"
        r"|\b(?:edit|rewrite|delete|remove|prune|truncate|trim|replace|modify)\w*\s+(?:the\s+|all\s+|any\s+)*"
        r"(?:earlier|previous|prior|older|old|past)\s+(?:messages?|turns?|tool\s+results?|history)\b"
        r"|\b(?:rewrite|regenerate|swap|change|edit)\w*\s+the\s+system\s+prompt\s+(?:mid|during|between|each|every)",
        "message": "Editing earlier turns invalidates this model's preserved thinking blocks.",
        "fix": "Keep the conversation append-only: add new instructions as new messages.",
    },
    {
        "id": "M007",
        "name": "forced-tool-choice",
        "penalty": 5,
        "models": frozenset({FABLE, OPUS, SONNET}),
        "pattern": r"tool_choice[\"']?\s*[:=]\s*\{?[^}\n]{0,40}[\"'](?:any|tool)[\"']",
        "message": "Forced tool_choice (`any` / `tool`) is rejected by this model.",
        "fix": "Use `auto` and name the tool in the prompt; add `strict: true` for schema-valid input.",
    },
    {
        "id": "M008",
        "name": "sampling-params",
        "penalty": 4,
        "models": ALL_MODELS,
        "pattern": r"[\"']?\btemperature[\"']?\s*[:=]\s*[01](?:\.\d+)?(?![\d.])|\btop_[pk][\"']?\s*[:=]\s*[\d.]+",
        "message": "Sampling parameters (temperature, top_p, top_k) are rejected by this model.",
        "fix": "Remove them from the request example.",
    },
    {
        "id": "M009",
        "name": "assistant-prefill",
        "penalty": 5,
        "models": ALL_MODELS,
        "pattern": r"\bprefill(?:ed|ing|s)?\b[^.\n]{0,30}\b(?:assistant|response|reply|answer|turn)\b"
        r"|\b(?:assistant|response)\s+prefill\b",
        "message": "Assistant-turn prefill is rejected by this model.",
        "fix": "Use structured outputs or describe the format in the prompt.",
    },
    {
        "id": "M010",
        "name": "thinking-disabled",
        "penalty": 6,
        "models": frozenset({FABLE, OPUS, SONNET}),
        "pattern": r"thinking[\"']?\s*[:=]\s*\{?[^}\n]{0,30}[\"']?disabled\b"
        r"|\b(?:disable|turn\s+off)\s+(?:extended\s+|adaptive\s+)?thinking\b",
        "message": "Thinking cannot be disabled on this model.",
        "fix": "Remove the setting and lower `effort` instead.",
    },
    {
        "id": "S001",
        "name": "unfilled-placeholder",
        "penalty": 25,  # large enough that an unfilled scaffold never passes the >= 70 gate
        "models": ANY_TARGET,
        "pattern": re.escape(PLACEHOLDER),
        "negatable": False,
        "message": "The scaffold still has unfilled placeholders.",
        "fix": f"Replace every `{PLACEHOLDER}` marker with real content, then re-score.",
    },
    {
        "id": "S002",
        "name": "bypass-permissions",
        "penalty": 10,
        "models": ANY_TARGET,
        "pattern": r"permissionMode\s*:\s*[\"']?bypassPermissions\b|--dangerously-skip-permissions\b",
        "message": "The artifact asks to skip permission checks.",
        "fix": "Use `plan` for read-only work or `acceptEdits` for edits inside the working directory.",
    },
)


def _ignored_rules(text):
    ids = set()
    for match in _IGNORE.finditer(text):
        ids.update(part.strip().upper() for part in match.group(1).split(",") if part.strip())
    return ids


def _is_negated(text, start):
    line_start = text.rfind("\n", 0, start) + 1
    window = text[max(line_start, start - _NEGATION_WINDOW):start]
    return bool(_NEGATION.search(window))


def _applies(rule, model_id):
    return rule["models"] is ANY_TARGET or (model_id is not None and model_id in rule["models"])


def _find(rule, text):
    """Return the character offsets where the rule really fires."""
    negatable = rule.get("negatable", True)
    return [
        match.start()
        for match in re.finditer(rule["pattern"], text, re.I)
        if not (negatable and _is_negated(text, match.start()))
    ]


def lint(text, model_id):
    """Return one finding per rule that fires, in rule order."""
    ignored = _ignored_rules(text)
    findings = []
    for rule in RULES:
        if rule["id"] in ignored or not _applies(rule, model_id):
            continue
        offsets = _find(rule, text)
        if not offsets:
            continue
        findings.append({
            "id": rule["id"],
            "name": rule["name"],
            "penalty": rule["penalty"],
            "line": text.count("\n", 0, offsets[0]) + 1,
            "count": len(offsets),
            "message": rule["message"],
            "fix": rule["fix"],
        })
    return findings


def total_penalty(findings):
    """Points to subtract on the 0-100 scale, capped."""
    return min(MAX_TOTAL_PENALTY, sum(finding["penalty"] for finding in findings))
