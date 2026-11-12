"""Signal-driven mods for Claude Code (Python stdlib only; Pillow is used when present).

Each mod is a hook handler that reads the hook's JSON from stdin and decides
from what is actually happening, instead of a static global setting:

  input-router             PreToolUse(Read): a data file over the threshold is
                           handed to the `input-reader` subagent, or read in ranges.
                           Reads made inside a subagent are never routed.
                           PostToolUse(mcp__*): connector output is cleaned of empty
                           fields, base64 blobs and avatar URLs; what is still over the
                           threshold is saved to a file and replaced by a preview.
  effort-optimizer         UserPromptSubmit: classifies the prompt and tells you when
                           the current effort is higher or lower than it needs. Hooks
                           cannot change the session's effort, so this recommends.
  subagent-model-selector  PreToolUse(Agent): easy jobs -> haiku, normal -> sonnet,
                           complex -> the session model. Never overrides a model the
                           call or the agent definition pins.
  cache-clock              Stop: records when the last reply landed; `statusline` and
                           `keep-warm` show how long the prompt cache stays warm.
  handoff                  Stop: past the token threshold, writes a HANDOFF.md skeleton
                           from the transcript and tells you to run /handoff.
  efficient-browser-use    PostToolUse(mcp__*): halves screenshot dimensions.

This one file is also what `mods install` copies to .claude/hooks/tq-forge/, so
it imports nothing else from tq-forge at module level. A handler that fails
prints nothing and exits 0: a mod must never block a session.

Token and dollar figures are estimates (characters / 4, pixels / 750, list
prices). They are for comparing mods, not for accounting.

Usage: mods.py {install|status|toggle|savings|statusline|handoff|keep-warm|hook NAME} [options]
"""

import argparse
import base64
import binascii
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import zlib

HERE = pathlib.Path(__file__).resolve().parent
USER_HOME = pathlib.Path(os.environ.get("TQ_FORGE_USER_HOME") or pathlib.Path.home())
STATE = USER_HOME / ".claude"
SAVINGS_FILE = STATE / "tq-forge-savings.json"
TOGGLES_FILE = STATE / "tq-forge-mods.json"
CLOCK_FILE = STATE / "tq-forge-cache-clock.json"
PAYLOAD_DIR = STATE / "tq-forge-payloads"
MODS = ("input-router", "effort-optimizer", "subagent-model-selector", "cache-clock", "handoff",
        "efficient-browser-use")
READERS = ("haiku", "sonnet")
CHARS_PER_TOKEN = 4
PIXELS_PER_TOKEN = 750
NOTES_TOKENS = 500  # what a reader subagent's notes cost, when estimating a routed read
MIN_CLEAN_SAVING = 50
RECENT_EVENTS = 200
TAIL_BYTES = 400_000
PAYLOAD_KEEP_SECONDS = 7 * 24 * 3600
STATUSLINE_TIMEOUT_SECONDS = 5
# Built-in agents that choose their own model, and a fork, which must stay on the session model.
OWN_MODEL_AGENTS = frozenset({"fork", "Explore", "Plan", "statusline-setup", "claude-code-guide"})
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DATA_SUFFIXES = frozenset({".json", ".jsonl", ".ndjson", ".log", ".csv", ".tsv", ".xml", ".html", ".htm", ".txt",
                           ".lock", ".map", ".out", ".yaml", ".yml", ".svg"})
SKIP_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ipynb"})
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BASE64_RUN = re.compile(r"(?:data:[\w/+.-]+;base64,)?[A-Za-z0-9+/]{200,}={0,2}")
NOISE_KEY = re.compile(r"avatar|gravatar", re.I)
COMPLEX = re.compile(r"\b(architect\w*|refactor\w*|redesign\w*|migrat\w+|root[- ]cause|debug\w*|race condition"
                     r"|deadlock|security (?:audit|review)|threat model|multi[- ]file|end[- ]to[- ]end"
                     r"|across (?:the )?(?:codebase|modules|files|repo)|investigat\w+|concurrency|distributed)\b", re.I)
DEEP = re.compile(r"\b(architect\w*|root[- ]cause|race condition|deadlock|security audit|threat model|redesign\w*"
                  r"|distributed|concurrency)\b", re.I)
BUILD = re.compile(r"\b(implement\w*|build|design|write|create|add|fix|update|edit|test\w*|analy[sz]e|review)\b", re.I)
SIMPLE = re.compile(r"^\s*(?:what|where|which|who|when|is|are|does|do|can|show|list|print|how (?:do|does|many|much))\b"
                    r"|\b(?:typo|rename|reformat|bump (?:the )?version|one[- ]liner|quick(?:ly)?|small (?:fix|change))\b",
                    re.I)
EASY = re.compile(r"\b(read|summari[sz]e|list|find|search|grep|scrape|fetch|collect|look ?up|count|locate|extract"
                  r"|pull (?:the )?metrics|run (?:the |a )?(?:single )?tests?|check (?:if|whether))\b", re.I)
DEFAULTS = {
    "input-router": {"enabled": True, "threshold_tokens": 2000, "source_threshold_tokens": 12000, "reader": "haiku",
                     "preview_chars": 1200,
                     "drop_keys": ["avatar_url", "gravatar_id", "node_id", "_links", "etag", "tracking_id"]},
    "effort-optimizer": {"enabled": True},
    "subagent-model-selector": {"enabled": True, "auto_allow": False,
                                "tiers": {"easy": "haiku", "normal": "sonnet", "complex": "inherit"}},
    "cache-clock": {"enabled": True, "ttl_minutes": "auto"},
    "handoff": {"enabled": True, "threshold_tokens": 250000, "repeat_every_tokens": 50000},
    "efficient-browser-use": {"enabled": True, "scale": 0.5, "tools": "screenshot|snapshot_image|capture",
                              "max_fallback_pixels": 2200000},
    "prices_per_million_input": {"haiku": 0.1, "sonnet": 2.0, "opus": 4.0, "fable": 8.0, "cache_read": 0.2},
}


# ------------------------------------------------------------- state files

def _read_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_config():
    """Built-in defaults, then config/mods.json (or the copy next to this file), then the user's toggles."""
    config = json.loads(json.dumps(DEFAULTS))
    for source in (HERE.parents[1] / "config" / "mods.json", HERE / "mods.json", TOGGLES_FILE):
        for key, value in _read_json(source).items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
    return config


def tokens_of(text):
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def log_saving(mod, tokens=0, usd=0.0, detail="", counters=None):
    """Add one event to ~/.claude/tq-forge-savings.json."""
    data = _read_json(SAVINGS_FILE)
    totals = data.setdefault("totals", {})
    entry = totals.setdefault(mod, {"events": 0, "tokens": 0, "usd": 0.0})
    entry["events"] += 1
    entry["tokens"] += int(tokens)
    entry["usd"] = round(entry["usd"] + usd, 6)
    for name, amount in (counters or {}).items():
        entry[name] = entry.get(name, 0) + amount
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    recent = data.setdefault("recent", [])
    recent.append({"ts": stamp, "mod": mod, "tokens": int(tokens), "usd": round(usd, 6), "detail": detail[:200]})
    data["recent"] = recent[-RECENT_EVENTS:]
    _write_json(SAVINGS_FILE, data)


def record_context_saving(tokens):
    """Add to the Context Optimizer row: tokens an `optimize --apply` takes off every turn from then on."""
    data = _read_json(SAVINGS_FILE)
    entry = data.setdefault("totals", {}).setdefault("context-optimizer", {"events": 0, "tokens": 0, "usd": 0.0})
    entry.update({"events": entry.get("events", 0) + 1, "tokens": entry.get("tokens", 0) + int(tokens),
                  "usd": round(entry.get("usd", 0.0) + _usd(tokens, DEFAULTS["prices_per_million_input"]["cache_read"]), 6)})
    _write_json(SAVINGS_FILE, data)


def _usd(tokens, price):
    return tokens * price / 1_000_000


# -------------------------------------------------------- mod 1: input router

def clean_value(value, drop_keys):
    """Drop empty fields, avatar URLs, API URL templates and base64 blobs from decoded JSON."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            noisy = key in drop_keys or NOISE_KEY.search(key) or \
                (key.endswith("_url") and isinstance(item, str) and "{" in item)
            item = None if noisy else clean_value(item, drop_keys)
            if item not in (None, "", [], {}):
                cleaned[key] = item
        return cleaned
    if isinstance(value, list):
        return [item for item in (clean_value(item, drop_keys) for item in value) if item not in (None, "", [], {})]
    if isinstance(value, str) and len(value) >= 200:
        return BASE64_RUN.sub(lambda match: f"[base64 removed, {len(match.group(0))} chars]", value)
    return value


def clean_text(text, drop_keys):
    """Clean a connector payload. JSON is cleaned and re-serialised compactly; other text loses base64 only."""
    stripped = text.strip()
    if stripped[:1] in "{[":
        try:
            return json.dumps(clean_value(json.loads(stripped), drop_keys), separators=(",", ":"), ensure_ascii=False)
        except ValueError:
            pass
    return BASE64_RUN.sub(lambda match: f"[base64 removed, {len(match.group(0))} chars]", text)


def _readable(text):
    """Compact JSON is one long line; indent it so the saved file can be read with offset/limit."""
    if text.lstrip()[:1] in ("{", "["):
        try:
            return json.dumps(json.loads(text), indent=1, ensure_ascii=False)
        except ValueError:
            pass
    return text


def _park_payload(text):
    """Save a payload under ~/.claude/tq-forge-payloads/ (owner-only) and drop week-old ones."""
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - PAYLOAD_KEEP_SECONDS
    for old in PAYLOAD_DIR.glob("*.txt"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass
    target = PAYLOAD_DIR / f"{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}.txt"
    target.touch(mode=0o600, exist_ok=True)
    target.write_text(_readable(text), encoding="utf-8")
    return target


def _route_text(text, tool, config):
    """Clean one text payload and, if still large, park it in a file behind a preview."""
    settings = config["input-router"]
    cleaned = clean_text(text, set(settings["drop_keys"]))
    saved = tokens_of(text) - tokens_of(cleaned)
    if saved < MIN_CLEAN_SAVING:
        cleaned, saved = text, 0
    if tokens_of(cleaned) > settings["threshold_tokens"]:
        target = _park_payload(cleaned)
        preview = cleaned[:settings["preview_chars"]]
        note = (f"\n[input-router: the full payload ({tokens_of(cleaned):,} tokens) is saved at {target}. "
                f"Read the lines you need with offset/limit, or hand the file to the `input-reader` subagent "
                f"and ask for notes.]")
        saved += tokens_of(cleaned) - tokens_of(preview + note)
        cleaned = preview + note
    if saved > 0:
        price = config["prices_per_million_input"]["fable"]
        log_saving("input-router", saved, _usd(saved, price), f"{tool}: connector payload")
    return cleaned


def handle_read(data, config):
    settings = config["input-router"]
    given = data.get("tool_input") or {}
    path = pathlib.Path(str(given.get("file_path") or ""))
    ranged = any(given.get(key) for key in ("offset", "limit", "pages"))
    in_subagent = bool(data.get("agent_id"))  # a subagent's context is the place a large read belongs
    if not settings["enabled"] or ranged or in_subagent or not path.is_file() or path.suffix.lower() in SKIP_SUFFIXES:
        return None
    is_data = path.suffix.lower() in DATA_SUFFIXES
    tokens = path.stat().st_size // CHARS_PER_TOKEN
    if tokens <= settings["threshold_tokens" if is_data else "source_threshold_tokens"]:
        return None
    saved = max(0, tokens - NOTES_TOKENS)
    log_saving("input-router", saved, _usd(saved, config["prices_per_million_input"]["fable"]),
               f"{path.name}: {tokens} tokens routed to the {settings['reader']} reader")
    reason = (f"input-router: {path.name} is about {tokens:,} tokens. Hand it to the `input-reader` subagent "
              f"(model: {settings['reader']}) with the question you need answered, and ask for notes with "
              f"file:line pointers. To read it yourself, call Read again with `offset` and `limit`. "
              f"(/switchboard turns this off.)")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


# ------------------------------------------------- mod 6: screenshot shrinker

def _unfilter(kind, line, previous, step):
    if kind == 1:
        for index in range(step, len(line)):
            line[index] = (line[index] + line[index - step]) & 255
    elif kind == 2:
        line[:] = bytes((a + b) & 255 for a, b in zip(line, previous))
    elif kind == 3:
        for index in range(len(line)):
            left = line[index - step] if index >= step else 0
            line[index] = (line[index] + ((left + previous[index]) >> 1)) & 255
    elif kind == 4:
        for index in range(len(line)):
            left = line[index - step] if index >= step else 0
            up = previous[index]
            corner = previous[index - step] if index >= step else 0
            guess = left + up - corner
            near_left, near_up, near_corner = abs(guess - left), abs(guess - up), abs(guess - corner)
            best = left if near_left <= near_up and near_left <= near_corner else up if near_up <= near_corner else corner
            line[index] = (line[index] + best) & 255


def _png_chunk(kind, payload):
    return (len(payload).to_bytes(4, "big") + kind + payload
            + (zlib.crc32(kind + payload) & 0xFFFFFFFF).to_bytes(4, "big"))


def halve_png(raw, max_pixels):
    """Halve an 8-bit non-interlaced PNG with the standard library. Returns (bytes, w, h, new_w, new_h) or None."""
    if raw[:8] != PNG_SIGNATURE:
        return None
    position, header, packed = 8, None, []
    while position + 8 <= len(raw):
        length = int.from_bytes(raw[position:position + 4], "big")
        kind = raw[position + 4:position + 8]
        body = raw[position + 8:position + 8 + length]
        if kind == b"IHDR":
            header = body
        elif kind == b"IDAT":
            packed.append(body)
        position += 12 + length
    if not header or not packed:
        return None
    width, height = int.from_bytes(header[:4], "big"), int.from_bytes(header[4:8], "big")
    depth, colour, interlace = header[8], header[9], header[12]
    step = {0: 1, 2: 3, 4: 2, 6: 4}.get(colour)
    if depth != 8 or step is None or interlace or width < 2 or height < 2 or width * height > max_pixels:
        return None
    pixels = zlib.decompress(b"".join(packed))
    stride, rows, previous = width * step, [], bytearray(width * step)
    for row in range(height):
        start = row * (stride + 1)
        line = bytearray(pixels[start + 1:start + 1 + stride])
        _unfilter(pixels[start], line, previous, step)
        rows.append(line)
        previous = line
    new_width, new_height, out = width // 2, height // 2, bytearray()
    for row in range(new_height):
        line = rows[row * 2]
        channels = [line[channel::step][::2][:new_width] for channel in range(step)]
        out.append(0)
        out.extend(bytes(value for pixel in zip(*channels) for value in pixel))
    new_header = new_width.to_bytes(4, "big") + new_height.to_bytes(4, "big") + header[8:]
    shrunk = (PNG_SIGNATURE + _png_chunk(b"IHDR", new_header) + _png_chunk(b"IDAT", zlib.compress(bytes(out), 6))
              + _png_chunk(b"IEND", b""))
    return shrunk, width, height, new_width, new_height


def shrink_image(raw, settings):
    """Downscale a screenshot. Pillow handles every format; without it, PNG is handled here."""
    try:
        from PIL import Image  # optional
        import io
        image = Image.open(io.BytesIO(raw))
        width, height = image.size
        new_size = (max(1, int(width * settings["scale"])), max(1, int(height * settings["scale"])))
        buffer = io.BytesIO()
        image.resize(new_size).save(buffer, format=image.format or "PNG")
        return buffer.getvalue(), width, height, new_size[0], new_size[1]
    except ImportError:
        return halve_png(raw, settings["max_fallback_pixels"]) if settings["scale"] == 0.5 else None
    except Exception:  # noqa: BLE001 (a broken image must not break the hook)
        return None


def _shrink_block(block, tool, config):
    holder = block["source"] if isinstance(block.get("source"), dict) else block
    try:
        raw = base64.b64decode(holder.get("data") or "", validate=True)
    except (binascii.Error, ValueError, TypeError):
        return False
    result = shrink_image(raw, config["efficient-browser-use"])
    if not result:
        return False
    shrunk, width, height, new_width, new_height = result
    holder["data"] = base64.b64encode(shrunk).decode("ascii")
    saved = (width * height - new_width * new_height) // PIXELS_PER_TOKEN
    log_saving("efficient-browser-use", saved, _usd(saved, config["prices_per_million_input"]["fable"]),
               f"{tool}: {width}x{height} -> {new_width}x{new_height}")
    return True


def _walk_output(value, tool, config, shrink, route):
    """Rewrite text and image blocks in a tool response, whatever shape it has. Returns (value, changed)."""
    if isinstance(value, str):
        routed = _route_text(value, tool, config) if route else value
        return routed, routed != value
    if isinstance(value, list):
        results = [_walk_output(item, tool, config, shrink, route) for item in value]
        return [item for item, _ in results], any(changed for _, changed in results)
    if isinstance(value, dict):
        if value.get("type") == "image":
            return value, bool(shrink and _shrink_block(value, tool, config))
        changed = False
        for key in ("text", "content", "result", "structuredContent"):
            if key in value and isinstance(value[key], (str, list, dict)):
                value[key], touched = _walk_output(value[key], tool, config, shrink, route)
                changed = changed or touched
        return value, changed
    return value, False


def handle_mcp_output(data, config):
    tool = str(data.get("tool_name") or "")
    browser = config["efficient-browser-use"]
    shrink = browser["enabled"] and re.search(browser["tools"], tool, re.I)
    route = config["input-router"]["enabled"]
    if not (shrink or route) or data.get("tool_response") is None:
        return None
    output, changed = _walk_output(json.loads(json.dumps(data["tool_response"])), tool, config, shrink, route)
    if not changed:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": output}}


# --------------------------------------------------- mod 2: effort optimizer

def classify_effort(prompt):
    """low / medium / high / xhigh for a prompt. Never `max`: that is a choice for a person to make."""
    words = len(prompt.split())
    signals = len(set(match.lower() for match in COMPLEX.findall(prompt)))
    steps = len(re.findall(r"^\s*(?:\d+[.)]|[-*])\s", prompt, re.M))
    if DEEP.search(prompt) and (signals >= 2 or words > 120):
        return "xhigh"
    if signals or words > 150 or steps >= 3 or (BUILD.search(prompt) and words > 60):
        return "high"
    if SIMPLE.search(prompt) and words <= 40 and not BUILD.search(prompt):
        return "low"
    return "medium"


def _current_effort(data, entry=None):
    """The session's effort: from the hook input, else $CLAUDE_EFFORT, else what the last Stop saw, else settings."""
    effort = data.get("effort")
    effort = effort.get("level") if isinstance(effort, dict) else effort
    effort = effort or os.environ.get("CLAUDE_EFFORT") or (entry or {}).get("effort")
    if not effort:
        settings = _read_json(STATE / "settings.json")
        per_model = settings.get("modelSettings") if isinstance(settings.get("modelSettings"), dict) else {}
        levels = {str(item["effortLevel"]) for item in per_model.values()
                  if isinstance(item, dict) and item.get("effortLevel")}
        effort = settings.get("effortLevel") or (levels.pop() if len(levels) == 1 else "")
    return str(effort or "").lower()


def handle_prompt(data, config):
    prompt = str(data.get("prompt") or "")
    session = str(data.get("session_id") or "")
    clock = _read_json(CLOCK_FILE)
    entry = clock.get(session) if isinstance(clock.get(session), dict) else {}
    if config["cache-clock"]["enabled"] and entry.get("last_reply"):
        warm = time.time() - entry["last_reply"] <= ttl_seconds(config)
        log_saving("cache-clock", 0, 0.0, "warm turn" if warm else "cold turn",
                   {"warm" if warm else "cold": 1})
    current = _current_effort(data, entry)
    if not config["effort-optimizer"]["enabled"] or not prompt.strip() or current not in EFFORTS:
        return None
    wanted = classify_effort(prompt)
    if wanted == current or entry.get("last_effort_advice") == f"{current}>{wanted}":
        return None
    clock[session] = {**entry, "last_effort_advice": f"{current}>{wanted}"}
    _write_json(CLOCK_FILE, clock)
    lower = EFFORTS.index(wanted) < EFFORTS.index(current)
    log_saving("effort-optimizer", 0, 0.0, f"{current} -> {wanted} recommended")
    why = "a quick lookup or small edit" if lower else "multi-step or high-stakes work"
    return {"systemMessage": f"effort-optimizer: this prompt looks like {why}. Effort is `{current}`; "
                             f"`/effort {wanted}` fits it better."}


# -------------------------------------------- mod 3: subagent model selector

def classify_task(text):
    if COMPLEX.search(text):
        return "complex"
    return "easy" if EASY.search(text) and not BUILD.search(text) else "normal"


def _pinned_model(agent, cwd):
    """True when a user or project agent definition with this name sets its own model."""
    for folder in (STATE / "agents", pathlib.Path(cwd or ".") / ".claude" / "agents"):
        for path in folder.rglob(f"{agent}.md") if folder.is_dir() and agent else ():
            match = re.search(r"^model[ \t]*:[ \t]*(\S+)", path.read_text(encoding="utf-8", errors="replace"), re.M)
            if match and match.group(1).strip("\"'") != "inherit":
                return True
    return False


def handle_subagent(data, config):
    settings = config["subagent-model-selector"]
    given = data.get("tool_input")
    if not isinstance(given, dict) or not given.get("prompt"):
        return None  # not a subagent call this hook understands: never replace its input
    agent = str(given.get("subagent_type") or "")
    if not settings["enabled"] or given.get("model") or agent in OWN_MODEL_AGENTS or ":" in agent \
            or _pinned_model(agent, data.get("cwd")):
        return None  # an explicit model, a plugin agent or a pinned definition is someone's decision: keep it
    tier = classify_task(f"{given.get('description', '')} {given.get('prompt', '')}")
    model = settings["tiers"].get(tier, "inherit")
    log_saving("subagent-model-selector", 0, 0.0, f"{tier} -> {model}: {str(given.get('description', ''))[:80]}",
               {tier: 1})
    if model == "inherit":
        return None
    output = {"hookEventName": "PreToolUse", "updatedInput": {**given, "model": model}}
    if settings["auto_allow"]:
        output["permissionDecision"] = "allow"
    return {"hookSpecificOutput": output}


def _find_number(value, names):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names and isinstance(item, (int, float)):
                return item
            found = _find_number(item, names)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_number(item, names)
            if found:
                return found
    return 0


def handle_subagent_done(data, config):
    """Price the tokens a routed subagent used against what the session model would have cost."""
    model = str((data.get("tool_input") or {}).get("model") or "")
    prices = config["prices_per_million_input"]
    used = _find_number(data.get("tool_response"), {"totalTokens", "total_tokens"})
    if model in READERS and used and config["subagent-model-selector"]["enabled"]:
        saved = _usd(used, prices["fable"] - prices[model])
        log_saving("subagent-model-selector", 0, saved, f"{int(used)} tokens ran on {model}")
    return None


# ------------------------------------------ mods 4 and 5: cache clock, handoff

def ttl_seconds(config):
    minutes = config["cache-clock"]["ttl_minutes"]
    if minutes == "auto":  # a subscription session caches for an hour, an API key for five minutes
        minutes = 5 if os.environ.get("ANTHROPIC_API_KEY") else 60
    return float(minutes) * 60


def _transcript_tail(path):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - TAIL_BYTES))
            return handle.read().decode("utf-8", errors="replace").splitlines()
    except (OSError, TypeError):
        return []


def context_tokens(transcript):
    """Tokens the last request carried, from the newest usage record in the transcript."""
    for line in reversed(_transcript_tail(transcript)):
        if '"usage"' not in line:
            continue
        try:
            usage = (json.loads(line).get("message") or {}).get("usage") or {}
        except (ValueError, AttributeError):
            continue
        total = sum(int(usage.get(key) or 0) for key in
                    ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))
        if total:
            return total
    return 0


def _clean_prompt(text):
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    return " ".join(text.split())[:400]


def build_handoff(transcript, cwd):
    """A HANDOFF.md skeleton built from the transcript: what was asked, touched, used and fetched."""
    prompts, read, changed, skills, urls = [], [], [], [], []
    try:
        lines = pathlib.Path(transcript).read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, TypeError):
        lines = []
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        message = record.get("message") if isinstance(record, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if record.get("type") == "user" and isinstance(content, str) and _clean_prompt(content):
            prompts.append(_clean_prompt(content))
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if record.get("type") == "user" and block.get("type") == "text" and _clean_prompt(block.get("text", "")):
                prompts.append(_clean_prompt(block["text"]))
            given = block.get("input") if isinstance(block.get("input"), dict) else {}
            name = block.get("name") if block.get("type") == "tool_use" else None
            target = {"Read": read, "Edit": changed, "Write": changed, "NotebookEdit": changed}.get(name)
            if target is not None and given.get("file_path"):
                target.append(str(given["file_path"]))
            elif name == "Skill" and given.get("skill"):
                skills.append(str(given["skill"]))
            elif name == "WebFetch" and given.get("url"):
                urls.append(str(given["url"]))

    def listed(items, limit=40):
        unique = list(dict.fromkeys(items))
        return "\n".join(f"- `{item}`" for item in unique[:limit]) or "- none recorded"

    return "\n".join([
        "# Handoff", "",
        f"Generated by tq-forge from the session transcript on {datetime.date.today().isoformat()}. "
        "Paste this file into a fresh chat to continue with a small context.", "",
        f"Working folder: `{cwd}`", "",
        "## Goal", "", prompts[0] if prompts else "_No user prompt found in the transcript._", "",
        "## Latest requests", "", "\n".join(f"- {prompt}" for prompt in prompts[-5:]) or "- none recorded", "",
        "## State of the work", "",
        "_Claude fills this in when you run /handoff: what is finished, what is not, decisions and why, "
        "and the next three steps._", "",
        "## Files changed", "", listed(changed), "",
        "## Files read", "", listed([path for path in read if path not in changed]), "",
        "## Skills used", "", listed(skills), "",
        "## URLs fetched", "", listed(urls), ""])


def write_handoff(transcript, cwd):
    target = pathlib.Path(cwd or ".") / ".claude" / "HANDOFF.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_handoff(transcript, cwd), encoding="utf-8")
    return target


def handle_stop(data, config):
    session, cwd = str(data.get("session_id") or ""), str(data.get("cwd") or ".")
    used = context_tokens(data.get("transcript_path"))
    clock = _read_json(CLOCK_FILE)
    entry = clock.get(session) if isinstance(clock.get(session), dict) else {}
    entry.update({"last_reply": time.time(), "cwd": cwd, "context_tokens": used,
                  "transcript": str(data.get("transcript_path") or "")})
    if _current_effort(data) in EFFORTS:
        entry["effort"] = _current_effort(data)
    message = None
    settings = config["handoff"]
    due = max(settings["threshold_tokens"], entry.get("handoff_at", 0) + settings["repeat_every_tokens"])
    if settings["enabled"] and used >= due and data.get("transcript_path"):
        target = write_handoff(data["transcript_path"], cwd)
        entry["handoff_at"] = used
        log_saving("handoff", 0, 0.0, f"{used} tokens in the session; skeleton at {target}")
        message = (f"handoff: this session now carries about {used:,} tokens on every turn. A HANDOFF.md skeleton "
                   f"is at {target}. Run /handoff to finish it, then continue in a fresh chat.")
    clock[session] = entry
    _write_json(CLOCK_FILE, clock)
    return {"systemMessage": message} if message else None


def cache_status(config, session=None):
    """(seconds left, entry) for a session, or for the most recent one."""
    clock = {key: value for key, value in _read_json(CLOCK_FILE).items() if isinstance(value, dict)}
    entry = clock.get(session) if session else max(clock.values(), key=lambda item: item.get("last_reply", 0),
                                                   default=None)
    if not entry or not entry.get("last_reply"):
        return None, None
    return entry["last_reply"] + ttl_seconds(config) - time.time(), entry


# -------------------------------------------------------------------- cli

HANDLERS = {"read": handle_read, "mcp-output": handle_mcp_output, "prompt": handle_prompt,
            "subagent": handle_subagent, "subagent-done": handle_subagent_done, "stop": handle_stop}


def run_hook(name):
    try:
        data = json.loads(sys.stdin.read() or "{}")
        result = HANDLERS[name](data if isinstance(data, dict) else {}, load_config())
        if result:
            print(json.dumps(result))
    except Exception:  # noqa: BLE001 (a mod must never block or break a session)
        pass
    return 0


def toggle(mod, value):
    if mod not in MODS:
        raise SystemExit(f"mods: unknown mod '{mod}'; choose from {', '.join(MODS)}")
    toggles = _read_json(TOGGLES_FILE)
    entry = toggles.setdefault(mod, {})
    if value in ("on", "off"):
        entry["enabled"] = value == "on"
    elif value in READERS and mod == "input-router":
        entry["reader"] = value
    else:
        raise SystemExit("mods: use on or off" + (", or haiku / sonnet for input-router" if mod == "input-router" else ""))
    _write_json(TOGGLES_FILE, toggles)
    return f"{mod}: {value}"


def render_status(config):
    lines = ["tq-forge mods", ""]
    for mod in MODS:
        extra = f" (reader: {config[mod]['reader']})" if mod == "input-router" else ""
        lines.append(f"  {'on ' if config[mod]['enabled'] else 'off'}  {mod}{extra}")
    left, entry = cache_status(config)
    if entry:
        state = f"warm for {int(left // 60)}m {int(left % 60)}s" if left > 0 else "cold"
        lines += ["", f"cache: {state} ({entry.get('cwd')}, {entry.get('context_tokens', 0):,} tokens in context)"]
    return "\n".join(lines)


def render_savings(config):
    totals = _read_json(SAVINGS_FILE).get("totals", {})
    rows = [("Input Router", "input-router"), ("Effort Optimizer", "effort-optimizer"),
            ("Subagent Model Selector", "subagent-model-selector"), ("Cache Clock", "cache-clock"),
            ("Handoff", "handoff"), ("Browser Screenshot Shrinker", "efficient-browser-use"),
            ("Context Optimizer", "context-optimizer")]
    notes = {"effort-optimizer": "recommendations shown; a hook cannot change effort itself",
             "cache-clock": "warm/cold turns: {warm}/{cold}", "handoff": "handoff prompts written",
             "subagent-model-selector": "routed easy/normal/complex: {easy}/{normal}/{complex}",
             "context-optimizer": "tokens (and cached-read cost) taken off every turn by optimize --apply"}
    lines = ["tq-forge savings (estimates: characters / 4, pixels / 750, list prices)", "",
             f"{'Mod':<30}{'Events':>8}{'Tokens':>12}{'USD':>10}  Note", "-" * 96]
    tokens_sum = usd_sum = 0
    for label, mod in rows:
        entry = totals.get(mod, {})
        counted = {key: entry.get(key, 0) for key in ("warm", "cold", "easy", "normal", "complex")}
        status = "" if mod not in config or config[mod]["enabled"] else " (off)"
        lines.append(f"{label + status:<30}{entry.get('events', 0):>8}{entry.get('tokens', 0):>12,}"
                     f"{entry.get('usd', 0.0):>10.4f}  {notes.get(mod, '').format(**counted)}")
        if mod != "context-optimizer":
            tokens_sum += entry.get("tokens", 0)
            usd_sum += entry.get("usd", 0.0)
    lines += ["-" * 96, f"{'Total (excluding per-turn row)':<30}{'':>8}{tokens_sum:>12,}{usd_sum:>10.4f}"]
    return "\n".join(lines)


def statusline(config, raw, chain=None):
    """The cache countdown. With `chain`, the earlier status line command runs first and keeps its place."""
    try:
        session = json.loads(raw or "{}").get("session_id")
    except (ValueError, AttributeError):
        session = None
    left, _ = cache_status(config, session)
    clock = "cache: --" if left is None else f"cache: {int(left // 60)}m" if left > 0 else "cache: cold"
    earlier = ""
    if chain and pathlib.Path(chain).is_file():
        import subprocess  # only the chained status line needs it
        try:
            done = subprocess.run(["sh", str(chain)], input=raw, capture_output=True, text=True,
                                  timeout=STATUSLINE_TIMEOUT_SECONDS, check=False)
            earlier = done.stdout.rstrip("\n")
        except (OSError, subprocess.SubprocessError):
            pass
    return f"{earlier} | {clock}" if earlier.strip() else clock


def _parse_minutes(text):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*m?", str(text).strip())
    if not match:
        raise SystemExit("mods: --ttl takes minutes, for example 55m or 4m")
    return float(match.group(1))


def keep_warm(config, ttl, wait):
    """Say when the cache goes cold and when to ping. The ping itself is /keep-warm, sent in the session."""
    left, entry = cache_status(config)
    if not entry:
        return "keep-warm: no session recorded yet. The cache-clock mod records one after each reply."
    ping_in = entry["last_reply"] + _parse_minutes(ttl) * 60 - time.time()
    if left <= 0:
        return f"keep-warm: the cache for {entry.get('cwd')} is already cold; the next turn re-writes it."
    if wait and ping_in > 0:
        time.sleep(ping_in)
        return f"\akeep-warm: send /keep-warm in the session at {entry.get('cwd')} now; the cache has about " \
               f"{int((left - ping_in) // 60)}m left."
    return (f"keep-warm: cache for {entry.get('cwd')} stays warm for {int(left // 60)}m {int(left % 60)}s. "
            f"Ping due in {max(0, int(ping_in // 60))}m; send /keep-warm in that session to reset the clock "
            f"(--wait blocks until then and rings the bell).")


def main(argv):
    parser = argparse.ArgumentParser(prog="mods", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("hook").add_argument("name", choices=sorted(HANDLERS))
    install = commands.add_parser("install")
    install.add_argument("--root", default=".")
    install.add_argument("--apply", action="store_true")
    install.add_argument("--json", action="store_true")
    install.add_argument("--allow-autonomy", action="store_true",
                         help="also pre-approve WebSearch, WebFetch, `gh api` and the learn/scout commands")
    install.add_argument("--chain-statusline", action="store_true",
                         help="keep an existing status line and append the cache clock to it")
    commands.add_parser("status")
    commands.add_parser("savings")
    commands.add_parser("statusline").add_argument("--chain", metavar="FILE",
                                                   help="a file holding the status line command to run first")
    switch = commands.add_parser("toggle")
    switch.add_argument("mod")
    switch.add_argument("value")
    handoff = commands.add_parser("handoff")
    handoff.add_argument("--transcript")
    handoff.add_argument("--cwd", default=".")
    warm = commands.add_parser("keep-warm")
    warm.add_argument("--ttl", default="55m")
    warm.add_argument("--wait", action="store_true")
    args = parser.parse_args(argv[1:])
    config = load_config()
    if args.command == "hook":
        return run_hook(args.name)
    if args.command == "install":
        import mods_install  # needs the rest of tq-forge; the installed hook copy never gets here
        return mods_install.main(args)
    if args.command == "toggle":
        print(toggle(args.mod, args.value))
    elif args.command == "status":
        print(render_status(config))
    elif args.command == "savings":
        print(render_savings(config))
    elif args.command == "statusline":
        print(statusline(config, sys.stdin.read(), args.chain))
    elif args.command == "handoff":
        _, entry = cache_status(config)
        transcript = args.transcript or (entry or {}).get("transcript")
        if not transcript:
            raise SystemExit("mods: no transcript known yet; pass --transcript <file.jsonl>")
        print(f"wrote {write_handoff(transcript, args.cwd)}")
    elif args.command == "keep-warm":
        print(keep_warm(config, args.ttl, args.wait))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
