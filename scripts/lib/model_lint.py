"""Model-compatibility lint for skills and subagent prompts (Python stdlib only).

Static, token-free checks for instructions that current Claude models reject
or that are documented to make them perform worse. Each rule names the models
it applies to; the caller passes the model the artifact targets.

Two kinds of rule:

  pattern rules  a regular expression over the text (M001-M010, S001, S002)
  check rules    a function over the parsed file (M011 completion instructions,
                 M012 stale model ids)

Findings are heuristics over text, not proof. A file can opt out of a rule it
has a good reason to break with an HTML comment:

    <!-- tq-forge-lint-ignore: M002, M005 -->
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import frontmatter  # noqa: E402
import models  # noqa: E402

# Rules are keyed by model family, so a model that `sync-models` adds is linted
# from the day it is added. Mythos shares Fable's API surface.
FABLE = "fable"
OPUS = "opus"
SONNET = "sonnet"
HAIKU = "haiku"
ALL_MODELS = frozenset({FABLE, OPUS, SONNET, HAIKU})
_FAMILY = re.compile(r"^(?:claude-)?(fable|mythos|opus|sonnet|haiku)\b")
ANY_TARGET = None  # structural rules: apply whatever the target model is

# Effort levels at which each family is documented to end a long task early.
# config/models.json carries the same data as `effort_guide.stops_early_at`;
# the test suite fails when the two disagree.
EARLY_STOP_EFFORTS = {
    FABLE: frozenset({"low", "medium"}),
    SONNET: frozenset({"low"}),
    HAIKU: frozenset({"low"}),
}
WRITE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
DELEGATE_TOOLS = frozenset({"Agent", "Task"})
LONG_WORKFLOW_STEPS = 6
LONG_MAX_TURNS = 20
STALE_PENALTY = {"retired": 10, "deprecated": 6, "superseded": 3}

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
_REASONING_VERB = (r"(?:show|output|print|include|write(?:\s+out)?|reveal|expose|display|return|share"
                   r"|dump|emit|reproduce|repeat|transcribe|narrate)")
_REASONING_STRONG = r"(?:full|raw|complete|internal|entire|hidden|verbatim)"
_REASONING_ADJECTIVE = rf"(?:{_REASONING_STRONG}|detailed|step[- ]by[- ]step)"
_REASONING_NOUN = (r"(?:chain[- ]of[- ]thought|thought\s+process|internal\s+monologue|scratchpad"
                   r"|reasoning(?:\s+(?:trace|steps|tokens))?|thinking(?:\s+(?:trace|tokens|process))?)")
_REPLY = r"(?:reply|response|answer|message|output)"
# Sonnet 5.5 and Haiku 5.5 accept the two default values; every other value is rejected.
_DEFAULT_SAMPLING = re.compile(r"temperature[\"']?\s*[:=]\s*1(?:\.0+)?$|top_?p[\"']?\s*[:=]\s*0\.99$", re.I)

RULES = (
    {
        "id": "M001",
        "name": "thinking-budget-param",
        "penalty": 8,
        "models": ALL_MODELS,
        "registry": "effort-not-budget",
        "pattern": r"budget_?tokens|max_thinking_tokens|thinking_budget"
        r"|thinking[\"']?\s*[:=]\s*\{[^}\n]{0,40}[\"']enabled[\"']",
        "message": "A fixed thinking-token budget is rejected by this model; depth is set by effort.",
        "fix": "Delete the budget. Use adaptive thinking (`thinking: {type: \"adaptive\"}`, or omit the field) "
        "and set `output_config.effort` in the request or `effort` in the frontmatter.",
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
        "registry": "no-reasoning-in-reply",
        "pattern": rf"\b{_REASONING_VERB}\s+(?:all\s+(?:of\s+)?)?(?:your|its)\s+(?:{_REASONING_ADJECTIVE}\s+)*{_REASONING_NOUN}\b"
        rf"|\b{_REASONING_VERB}\s+(?:the\s+|a\s+)?(?:{_REASONING_STRONG}\s+)+{_REASONING_NOUN}\b"
        r"|\bshow\s+your\s+work\b"
        r"|\b(?:reason|think)\s+(?:out\s+loud|aloud)\b"
        r"|<(?:thinking|scratchpad|reasoning)>"
        rf"|\b(?:begin|start|open|preface|precede)\w*\s+(?:each|every|your|the)\s+(?:final\s+)?{_REPLY}\s+with\s+"
        rf"(?:a\s+|an\s+|your\s+|the\s+)?[\"'`#*\s]*{_REASONING_NOUN}\b"
        rf"|\b{_REASONING_NOUN}\s+(?:section|block|header|heading)\s+(?:before|ahead\s+of|above)\s+"
        r"(?:the\s+|your\s+)?(?:final\s+)?answer\b",
        "message": "Asking for raw reasoning in the reply text can be declined with the "
        "`reasoning_extraction` refusal category.",
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
        "registry": "append-only-history",
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
        "registry": "no-forced-tool-choice",
        "pattern": r"tool_choice[\"']?\s*[:=]\s*\{?[^}\n]{0,40}[\"'](?:any|tool)[\"']",
        "message": "Forced tool_choice (`any` / `tool`) is rejected by this model.",
        "fix": "Use `auto` and name the tool in the prompt; add `strict: true` for schema-valid input.",
    },
    {
        "id": "M008",
        "name": "sampling-params",
        "penalty": 4,
        "models": ALL_MODELS,
        "registry": "no-sampling-params",
        "pattern": r"[\"']?\btemperature[\"']?\s*[:=]\s*[0-2](?:\.\d+)?(?![\d.])"
        # `topK` is left out on purpose: in agent files it is nearly always a retrieval limit.
        r"|\b(?:top_?p|top_k)[\"']?\s*[:=]\s*\d+(?:\.\d+)?(?![\d.])",
        "exempt": {SONNET: _DEFAULT_SAMPLING, HAIKU: _DEFAULT_SAMPLING},
        "message": "Sampling parameters (temperature, top_p, top_k) are rejected by this model.",
        "fix": "Remove them from the request example and steer the output from the prompt.",
    },
    {
        "id": "M009",
        "name": "assistant-prefill",
        "penalty": 5,
        "models": ALL_MODELS,
        "registry": "no-prefill",
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
        "registry": "thinking-always-on",
        "pattern": r"thinking[\"']?\s*[:=]\s*\{?[^}\n]{0,30}[\"']?disabled\b"
        r"|\b(?:disable|turn\s+off)\s+(?:extended\s+|adaptive\s+)?thinking\b",
        "message": "Thinking cannot be disabled on this model.",
        "fix": "Remove the setting and lower `output_config.effort` instead. On Sonnet 5.5 a route that "
        "must stay thinking-off sends `{type: \"between_tools\"}` at `high` effort or below.",
    },
    {
        "id": "M011",
        "name": "missing-completion-instructions",
        "penalty": 6,
        "models": frozenset(EARLY_STOP_EFFORTS),
        "registry": "finish-the-task",
        "check": "_check_completion",
        "message": "A long-horizon subagent at this effort level can end its turn before the work is done.",
        "fix": "Add a `# Finishing work` block (templates/snippets/finishing-work.md or keep-working.md), "
        "or raise `effort`.",
    },
    {
        "id": "M012",
        "name": "stale-model-id",
        "penalty": STALE_PENALTY["retired"],  # the worst case; the finding carries the real penalty
        "models": ANY_TARGET,
        "check": "_check_stale_ids",
        "message": "The file names a Claude model id that is behind the registry.",
        "fix": "Use the current id, or run `tq-forge sync-models --apply` to rewrite pinned `model:` fields.",
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


_COMPLETION = re.compile(
    r"^#{1,4}\s*(?:Finishing work|Finish the (?:whole )?task|Completion|Persistence|Keep working)\b"
    r"|\bkeep (?:working|going) until\b"
    r"|\b(?:do not|don'?t|never) stop (?:early|unless|until|before|while)\b"
    r"|\bavoid stopping (?:while|before|early)\b"
    r"|\bcontinue (?:working )?until\b"
    r"|\bfinish the (?:whole|entire|full) task\b"
    r"|\buntil (?:the (?:whole |entire )?(?:task|job|work|question)|everything|all (?:of )?the work)"
    r"[^.\n]{0,60}\b(?:done|complete|completed|finished|answered)\b",
    re.I | re.M,
)
_NUMBERED_STEP = re.compile(r"^\s*\d+[.)]\s", re.M)
_MODEL_TOKEN = re.compile(r"(?<![\w/.-])(?:anthropic[/.])?claude-[a-z0-9][a-z0-9.@-]*", re.I)
# A line that is about model history names old ids on purpose.
_HISTORY_LINE = re.compile(
    r"\b(?:retir\w+|deprecat\w+|legacy|supersed\w+|migrat\w+|upgrad\w+|older|previous|formerly|was|were)\b|->|\u2192",
    re.I,
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


def family(model_id):
    """The model family a rule set is keyed by, or None for an id this lint does not know."""
    match = _FAMILY.match(str(model_id or "").lower())
    if not match:
        return None
    return FABLE if match.group(1) == "mythos" else match.group(1)


def _applies(rule, model_id):
    return rule["models"] is ANY_TARGET or family(model_id) in rule["models"]


def rules_for(model_id):
    """Ids of the rules that apply when an artifact targets `model_id`."""
    return [rule["id"] for rule in RULES if _applies(rule, model_id)]


def _find(rule, text, model_id):
    """Return the character offsets where a pattern rule really fires."""
    negatable = rule.get("negatable", True)
    exempt = (rule.get("exempt") or {}).get(family(model_id))
    return [
        match.start()
        for match in re.finditer(rule["pattern"], text, re.I)
        if not (negatable and _is_negated(text, match.start()))
        and not (exempt and exempt.search(match.group(0)))
    ]


def is_long_horizon(fields, body):
    """True for a subagent that can run a long, multistep task.

    It can change files or start other agents (or inherits every tool because
    it lists none), it runs in the background, it allows many turns, or its
    prompt has a workflow of six or more numbered steps.
    """
    tools = set(frontmatter.as_list(fields.get("tools") or fields.get("allowed-tools")
                                    or fields.get("allowedTools")))
    if not tools or tools & (WRITE_TOOLS | DELEGATE_TOOLS):
        return True
    if str(fields.get("background", "")).strip().lower() == "true":
        return True
    try:
        if int(str(fields.get("maxTurns", "0")).strip()) >= LONG_MAX_TURNS:
            return True
    except ValueError:
        pass
    return len(_NUMBERED_STEP.findall(body)) >= LONG_WORKFLOW_STEPS


def has_completion_instructions(text):
    """True when the prompt tells the agent to keep going until the work is done."""
    return bool(_COMPLETION.search(text))


def needs_completion_instructions(model_id, effort):
    """True when `model_id` at `effort` is documented to stop a long task early."""
    return str(effort or "").strip().lower() in EARLY_STOP_EFFORTS.get(family(model_id), ())


def _check_completion(text, model_id, kind, effort):
    if kind != "subagent":
        return None
    fields, body, _ = frontmatter.read(text)
    level = effort or fields.get("effort")
    if not needs_completion_instructions(model_id, level):
        return None
    if not is_long_horizon(fields, body) or has_completion_instructions(body):
        return None
    return {"offsets": [0], "detail": f"effort `{level}` on a {family(model_id)} model"}


def _check_stale_ids(text, model_id, kind, effort):
    registry = models.generations()
    offsets, worst, detail = [], None, ""
    for match in _MODEL_TOKEN.finditer(text):
        token = match.group(0).rstrip(".-@")
        found = models.status(token, registry)
        if found["status"] not in STALE_PENALTY:
            continue
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line = text[line_start:len(text) if line_end < 0 else line_end]
        if _HISTORY_LINE.search(line) or _is_negated(text, match.start()):
            continue
        offsets.append(match.start())
        if worst is None or STALE_PENALTY[found["status"]] > STALE_PENALTY[worst]:
            worst = found["status"]
            when = f" ({found['date']})" if found["date"] else ""
            target = f"; use `{found['replacement']}`" if found["replacement"] else ""
            detail = f"`{token}` is {worst}{when}{target}"
    if not offsets:
        return None
    return {"offsets": offsets, "penalty": STALE_PENALTY[worst], "detail": detail}


_CHECKS = {"_check_completion": _check_completion, "_check_stale_ids": _check_stale_ids}


def lint(text, model_id, kind=None, effort=None):
    """Return one finding per rule that fires, in rule order.

    `kind` is the artifact kind the scorer detected (`skill`, `subagent`,
    `agent`); rules about a file's role need it. `effort` overrides the level
    in the frontmatter, to ask what would happen at another level.
    """
    ignored = _ignored_rules(text)
    findings = []
    for rule in RULES:
        if rule["id"] in ignored or not _applies(rule, model_id):
            continue
        penalty, detail = rule["penalty"], ""
        if "check" in rule:
            result = _CHECKS[rule["check"]](text, model_id, kind, effort)
            if not result:
                continue
            offsets, detail = result["offsets"], result.get("detail", "")
            penalty = result.get("penalty", penalty)
        else:
            offsets = _find(rule, text, model_id)
            if not offsets:
                continue
        findings.append({
            "id": rule["id"],
            "name": rule["name"],
            "penalty": penalty,
            "line": text.count("\n", 0, offsets[0]) + 1,
            "count": len(offsets),
            "message": rule["message"] + (f" {detail[0].upper()}{detail[1:]}." if detail else ""),
            "fix": rule["fix"],
        })
    return findings


def total_penalty(findings):
    """Points to subtract on the 0-100 scale, capped."""
    return min(MAX_TOTAL_PENALTY, sum(finding["penalty"] for finding in findings))
