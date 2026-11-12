"""Tests for the signal-driven mods (scripts/lib/mods.py) and their installer.

Every test points the mod state (savings, toggles, cache clock, payloads) at a
temporary folder, so nothing under the real ~/.claude is read or written.

Run: python3 -m unittest discover -s tests -v
"""

import base64
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import mods  # noqa: E402
import mods_install  # noqa: E402
import optimize  # noqa: E402

PNG_COLOUR_TYPE = {1: 0, 2: 4, 3: 2, 4: 6}


def _png_filter(kind, line, previous, step):
    """Apply PNG filter `kind` to one scanline (the inverse of what the mod has to undo)."""
    out = bytearray(len(line))
    for index, value in enumerate(line):
        left = line[index - step] if index >= step else 0
        up = previous[index]
        corner = previous[index - step] if index >= step else 0
        guess = left + up - corner
        near = (abs(guess - left), abs(guess - up), abs(guess - corner))
        paeth = left if near[0] <= near[1] and near[0] <= near[2] else up if near[1] <= near[2] else corner
        predicted = (0, left, up, (left + up) // 2, paeth)[kind]
        out[index] = (value - predicted) & 255
    return out


def _chunk(tag, body):
    return len(body).to_bytes(4, "big") + tag + body + zlib.crc32(tag + body).to_bytes(4, "big")


def make_png(width, height, pixel, kind=0, channels=3, depth=8, interlace=0):
    raw, previous = bytearray(), bytearray(width * channels)
    for row in range(height):
        line = bytearray(value for column in range(width) for value in pixel(column, row))
        raw.append(kind)
        raw.extend(_png_filter(kind, line, previous, channels))
        previous = line
    header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes([depth, PNG_COLOUR_TYPE[channels], 0, 0, interlace])
    return mods.PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(bytes(raw))) + _chunk(b"IEND", b"")


def png_size(raw):
    return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")


def png_rows(raw, channels=3):
    """Scanlines of a PNG whose rows all use filter 0, which is what the mod writes."""
    width, height = png_size(raw)
    start = raw.index(b"IDAT") + 4
    length = int.from_bytes(raw[start - 8:start - 4], "big")
    data = zlib.decompress(raw[start:start + length])
    stride = width * channels + 1
    return [data[row * stride + 1:(row + 1) * stride] for row in range(height)]


def colour(column, row):
    return (column * 7 % 256, row * 11 % 256, (column + row) * 5 % 256)


class ModsCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = pathlib.Path(self._tmp.name).resolve()
        self.state = self.home / ".claude"
        for name, value in (("USER_HOME", self.home), ("STATE", self.state),
                            ("SAVINGS_FILE", self.state / "tq-forge-savings.json"),
                            ("TOGGLES_FILE", self.state / "tq-forge-mods.json"),
                            ("CLOCK_FILE", self.state / "tq-forge-cache-clock.json"),
                            ("PAYLOAD_DIR", self.state / "tq-forge-payloads")):
            patcher = mock.patch.object(mods, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for name in ("CLAUDE_EFFORT", "ANTHROPIC_API_KEY"):
            os.environ.pop(name, None)

    def config(self):
        return mods.load_config()

    def totals(self, mod):
        return mods._read_json(mods.SAVINGS_FILE).get("totals", {}).get(mod, {})


class InputRouterTest(ModsCase):
    def _payload(self, count):
        return [{"id": n, "title": f"Issue {n}: the importer drops rows", "avatar_url": f"https://a.example/u/{n}.png",
                 "body": "", "labels": [], "user": {"login": f"user{n}", "node_id": "MDQ6VXNlcjE=", "gravatar_id": "",
                                                  "events_url": "https://api.example/users/x/events{/privacy}"}}
                for n in range(count)]

    def test_cleaner_drops_empty_fields_avatars_url_templates_and_base64(self):
        blob = "A" * 400
        cleaned = mods.clean_value({"keep": "yes", "empty": "", "none": None, "list": [], "avatar_url": "https://x/y.png",
                                    "owner_avatar": "z", "repos_url": "https://api/x{/id}", "html_url": "https://x/y",
                                    "image": f"data:image/png;base64,{blob}", "nested": {"etag": "W/1", "n": 0}},
                                   {"etag"})
        self.assertEqual(cleaned["keep"], "yes")
        self.assertEqual(cleaned["html_url"], "https://x/y")
        self.assertEqual(cleaned["nested"], {"n": 0}, "zero is a value, not an empty field")
        self.assertEqual(cleaned["image"], "[base64 removed, 422 chars]")
        for gone in ("empty", "none", "list", "avatar_url", "owner_avatar", "repos_url"):
            self.assertNotIn(gone, cleaned)
        self.assertIn("[base64 removed", mods.clean_text("log line " + blob, set()))

    def test_large_connector_payload_is_cleaned_parked_and_replaced_by_a_preview(self):
        text = json.dumps(self._payload(300), indent=2)
        data = {"tool_name": "mcp__github__list_issues", "tool_response": [{"type": "text", "text": text}]}
        result = mods.handle_mcp_output(data, self.config())
        shown = result["hookSpecificOutput"]["updatedToolOutput"][0]["text"]
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("input-router: the full payload", shown)
        self.assertLess(mods.tokens_of(shown), 500)
        saved = list(mods.PAYLOAD_DIR.glob("*.txt"))
        self.assertEqual(len(saved), 1)
        parked = saved[0].read_text()
        self.assertGreater(len(parked.splitlines()), 300, "indented, so it can be read with offset and limit")
        self.assertNotIn("avatar_url", parked)
        self.assertEqual(len(json.loads(parked)), 300, "every record is still there")
        self.assertEqual(saved[0].stat().st_mode & 0o077, 0, "payloads are readable by the owner only")
        entry = self.totals("input-router")
        self.assertEqual(entry["events"], 1)
        self.assertGreater(entry["tokens"], 2000)
        self.assertGreater(entry["usd"], 0)
        self.assertEqual(text, data["tool_response"][0]["text"], "the hook input is not mutated")

    def test_payload_under_the_threshold_is_cleaned_in_place_and_a_clean_one_is_left_alone(self):
        noisy = {"tool_name": "mcp__github__get", "tool_response": json.dumps(self._payload(8))}
        result = mods.handle_mcp_output(noisy, self.config())
        shown = result["hookSpecificOutput"]["updatedToolOutput"]
        self.assertNotIn("avatar_url", shown)
        self.assertNotIn("input-router", shown, "small enough to stay in the conversation")
        self.assertFalse(mods.PAYLOAD_DIR.exists())
        tidy = {"tool_name": "mcp__docs__search", "tool_response": {"content": [{"type": "text", "text": "Three results."}]}}
        self.assertIsNone(mods.handle_mcp_output(tidy, self.config()))

    def test_old_parked_payloads_are_pruned(self):
        mods.PAYLOAD_DIR.mkdir(parents=True)
        stale = mods.PAYLOAD_DIR / "stale.txt"
        stale.write_text("old")
        long_ago = time.time() - mods.PAYLOAD_KEEP_SECONDS - 60
        os.utime(stale, (long_ago, long_ago))
        mods._park_payload("fresh payload")
        self.assertFalse(stale.exists())
        self.assertEqual(len(list(mods.PAYLOAD_DIR.glob("*.txt"))), 1)

    def test_large_data_file_read_is_routed_to_the_reader(self):
        big = self.home / "export.json"
        big.write_text("x" * 12_000)
        result = mods.handle_read({"tool_input": {"file_path": str(big)}}, self.config())
        output = result["hookSpecificOutput"]
        self.assertEqual((output["hookEventName"], output["permissionDecision"]), ("PreToolUse", "deny"))
        self.assertIn("`input-reader` subagent (model: haiku)", output["permissionDecisionReason"])
        self.assertIn("`offset` and `limit`", output["permissionDecisionReason"])
        self.assertEqual(self.totals("input-router")["tokens"], 3000 - mods.NOTES_TOKENS)
        mods.toggle("input-router", "sonnet")
        again = mods.handle_read({"tool_input": {"file_path": str(big)}}, self.config())
        self.assertIn("(model: sonnet)", again["hookSpecificOutput"]["permissionDecisionReason"])

    def test_reads_that_must_not_be_routed(self):
        big = self.home / "export.json"
        big.write_text("x" * 12_000)
        source = self.home / "module.py"
        source.write_text("x" * 12_000)
        small = self.home / "small.json"
        small.write_text("x" * 4_000)
        image = self.home / "shot.png"
        image.write_bytes(b"x" * 40_000)
        config = self.config()
        for given, why in (({"file_path": str(big), "offset": 1, "limit": 200}, "a ranged read"),
                           ({"file_path": str(source)}, "source under the source threshold"),
                           ({"file_path": str(small)}, "a small data file"),
                           ({"file_path": str(image)}, "an image"),
                           ({"file_path": str(self.home / "missing.json")}, "a missing file")):
            self.assertIsNone(mods.handle_read({"tool_input": given}, config), why)
        inside = {"tool_input": {"file_path": str(big)}, "agent_id": "agent-1", "agent_type": "input-reader"}
        self.assertIsNone(mods.handle_read(inside, config), "the reader subagent must be able to read the file")
        mods.toggle("input-router", "off")
        self.assertIsNone(mods.handle_read({"tool_input": {"file_path": str(big)}}, self.config()))
        self.assertEqual(self.totals("input-router"), {})


class EffortOptimizerTest(ModsCase):
    DEEP = ("Investigate the race condition in the session cache, find the root cause, and redesign the "
            "architecture of the worker pool across the codebase.")

    def test_classification_follows_the_work_and_never_picks_max(self):
        cases = {"what is the default port?": "low", "rename this variable": "low",
                 "Tell me about the tradeoffs here": "medium",
                 "Refactor the billing module and update every caller": "high", self.DEEP: "xhigh",
                 "1. add the endpoint\n2. write the migration\n3. update the docs\n4. run the tests": "high"}
        for prompt, expected in cases.items():
            self.assertEqual(mods.classify_effort(prompt), expected, prompt)
        for prompt in (*cases, "x " * 5000, self.DEEP * 20):
            self.assertIn(mods.classify_effort(prompt), mods.EFFORTS[:-1])

    def test_recommends_lower_effort_for_a_lookup_and_higher_for_deep_work_once_each(self):
        simple = {"prompt": "what is the default port?", "session_id": "s1", "effort": {"level": "high"}}
        message = mods.handle_prompt(simple, self.config())["systemMessage"]
        self.assertIn("`/effort low`", message)
        self.assertIn("Effort is `high`", message)
        self.assertIsNone(mods.handle_prompt(simple, self.config()), "the same advice is not repeated")
        deep = {"prompt": self.DEEP, "session_id": "s2", "effort": {"level": "low"}}
        self.assertIn("`/effort xhigh`", mods.handle_prompt(deep, self.config())["systemMessage"])
        fitting = {"prompt": self.DEEP, "session_id": "s3", "effort": {"level": "xhigh"}}
        self.assertIsNone(mods.handle_prompt(fitting, self.config()))
        self.assertEqual(self.totals("effort-optimizer")["events"], 2)

    def test_effort_is_found_when_the_prompt_hook_does_not_carry_it(self):
        prompt = {"prompt": "what is the default port?", "session_id": "s1"}
        self.assertIsNone(mods.handle_prompt(prompt, self.config()), "unknown effort: say nothing")
        mods.handle_stop({"session_id": "s1", "cwd": str(self.home), "effort": {"level": "high"}}, self.config())
        self.assertIn("`/effort low`", mods.handle_prompt(prompt, self.config())["systemMessage"])
        self.state.mkdir(exist_ok=True)
        (self.state / "settings.json").write_text(json.dumps(
            {"modelSettings": {"claude-fable-5-2": {"effortLevel": "high"}, "claude-opus-5-5": {"effortLevel": "high"}}}))
        other = {"prompt": "what is the default port?", "session_id": "s9"}
        self.assertIn("Effort is `high`", mods.handle_prompt(other, self.config())["systemMessage"])
        os.environ["CLAUDE_EFFORT"] = "low"
        self.assertIsNone(mods.handle_prompt({**other, "session_id": "s10"}, self.config()), "already low")

    def test_switched_off_it_says_nothing(self):
        mods.toggle("effort-optimizer", "off")
        data = {"prompt": "what is the default port?", "session_id": "s1", "effort": {"level": "max"}}
        self.assertIsNone(mods.handle_prompt(data, self.config()))


class SubagentModelSelectorTest(ModsCase):
    def _spawn(self, description, prompt="Report back when done.", **extra):
        given = {"subagent_type": "general-purpose", "description": description, "prompt": prompt, **extra}
        return mods.handle_subagent({"tool_input": given, "cwd": str(self.home)}, self.config())

    def test_easy_normal_and_complex_jobs_get_different_models(self):
        easy = self._spawn("Summarize the logs", "Read the log file and list the errors", run_in_background=True)
        output = easy["hookSpecificOutput"]
        self.assertEqual(output["updatedInput"]["model"], "haiku")
        self.assertEqual(output["updatedInput"]["prompt"], "Read the log file and list the errors")
        self.assertTrue(output["updatedInput"]["run_in_background"], "the rest of the input is passed through")
        self.assertNotIn("permissionDecision", output, "routing does not approve the call")
        normal = self._spawn("Add validation", "Add input validation to the signup form and write tests for it")
        self.assertEqual(normal["hookSpecificOutput"]["updatedInput"]["model"], "sonnet")
        self.assertIsNone(self._spawn("Find the deadlock", "Root-cause the deadlock in the worker pool"),
                          "complex work stays on the session model")
        self.assertIsNone(self._spawn("Security audit of the auth flow"))
        entry = self.totals("subagent-model-selector")
        self.assertEqual((entry["easy"], entry["normal"], entry["complex"], entry["events"]), (1, 1, 2, 4))

    def test_a_model_someone_chose_is_never_overridden(self):
        self.assertIsNone(self._spawn("Summarize the logs", model="opus"), "explicit model on the call")
        for agent in ("ecc:planner", "Explore", "fork", "claude-code-guide"):
            self.assertIsNone(self._spawn("Summarize the logs", subagent_type=agent), agent)
        (self.state / "agents" / "team").mkdir(parents=True)
        (self.state / "agents" / "team" / "auditor.md").write_text("---\nname: auditor\nmodel: claude-opus-5-5\n---\n")
        (self.state / "agents" / "helper.md").write_text("---\nname: helper\nmodel: inherit\n---\n")
        self.assertIsNone(self._spawn("Summarize the logs", subagent_type="auditor"), "pinned in its definition")
        routed = self._spawn("Summarize the logs", subagent_type="helper")
        self.assertEqual(routed["hookSpecificOutput"]["updatedInput"]["model"], "haiku")
        mods.toggle("subagent-model-selector", "off")
        self.assertIsNone(self._spawn("Summarize the logs"))

    def test_auto_allow_is_opt_in_and_token_cost_is_logged_when_the_agent_finishes(self):
        self.state.mkdir(exist_ok=True)
        mods.TOGGLES_FILE.write_text(json.dumps({"subagent-model-selector": {"auto_allow": True}}))
        self.assertEqual(self._spawn("Summarize the logs")["hookSpecificOutput"]["permissionDecision"], "allow")
        done = {"tool_input": {"model": "haiku"}, "tool_response": {"content": [], "usage": {"totalTokens": 100_000}}}
        self.assertIsNone(mods.handle_subagent_done(done, self.config()))
        self.assertAlmostEqual(self.totals("subagent-model-selector")["usd"], 100_000 * (8.0 - 0.1) / 1_000_000)
        mods.handle_subagent_done({"tool_input": {"model": "opus"}, "tool_response": {"totalTokens": 5}}, self.config())
        self.assertEqual(self.totals("subagent-model-selector")["events"], 2, "an unrouted run adds nothing")


class CacheClockTest(ModsCase):
    def _reply(self, session="s1", **extra):
        mods.handle_stop({"session_id": session, "cwd": str(self.home), **extra}, self.config())

    def test_ttl_is_an_hour_on_a_subscription_and_five_minutes_with_an_api_key(self):
        self.assertEqual(mods.ttl_seconds(self.config()), 3600)
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        self.assertEqual(mods.ttl_seconds(self.config()), 300)
        self.state.mkdir(exist_ok=True)
        mods.TOGGLES_FILE.write_text(json.dumps({"cache-clock": {"ttl_minutes": 30}}))
        self.assertEqual(mods.ttl_seconds(self.config()), 1800)

    def test_status_line_counts_down_from_the_last_reply(self):
        self.assertEqual(mods.statusline(self.config(), "{}"), "cache: --")
        self._reply()
        self.assertEqual(mods.statusline(self.config(), json.dumps({"session_id": "s1"})), "cache: 59m")
        self.assertEqual(mods.statusline(self.config(), json.dumps({"session_id": "other"})), "cache: --")
        clock = json.loads(mods.CLOCK_FILE.read_text())
        clock["s1"]["last_reply"] -= 3601
        mods.CLOCK_FILE.write_text(json.dumps(clock))
        self.assertEqual(mods.statusline(self.config(), json.dumps({"session_id": "s1"})), "cache: cold")
        self.assertEqual(mods.statusline(self.config(), "not json"), "cache: cold", "falls back to the newest session")

    def test_an_earlier_status_line_keeps_its_place_when_chained(self):
        self._reply()
        earlier = self.home / "earlier.sh"
        earlier.write_text('read -r line; printf "main %s\\n" "${#line}"\n')
        raw = json.dumps({"session_id": "s1"})
        self.assertEqual(mods.statusline(self.config(), raw, str(earlier)), f"main {len(raw)} | cache: 59m")
        earlier.write_text("exit 3\n")
        self.assertEqual(mods.statusline(self.config(), raw, str(earlier)), "cache: 59m")
        self.assertEqual(mods.statusline(self.config(), raw, str(self.home / "gone.sh")), "cache: 59m")

    def test_keep_warm_reports_time_left_and_warm_and_cold_turns_are_counted(self):
        self.assertIn("no session recorded yet", mods.keep_warm(self.config(), "55m", False))
        self._reply()
        self.assertIn("stays warm for 59m", mods.keep_warm(self.config(), "55m", False))
        self.assertIn("Ping due in 54m", mods.keep_warm(self.config(), "55m", False))
        mods.handle_prompt({"prompt": "next", "session_id": "s1"}, self.config())
        clock = json.loads(mods.CLOCK_FILE.read_text())
        clock["s1"]["last_reply"] -= 7200
        mods.CLOCK_FILE.write_text(json.dumps(clock))
        self.assertIn("already cold", mods.keep_warm(self.config(), "55m", False))
        mods.handle_prompt({"prompt": "much later", "session_id": "s1"}, self.config())
        entry = self.totals("cache-clock")
        self.assertEqual((entry["warm"], entry["cold"]), (1, 1))
        for bad in ("soon", "-5m", ""):
            with self.assertRaises(SystemExit):
                mods._parse_minutes(bad)
        self.assertEqual(mods._parse_minutes("4m"), 4.0)


class HandoffTest(ModsCase):
    def _transcript(self, context_tokens):
        usage = {"input_tokens": 1000, "cache_read_input_tokens": context_tokens - 5000,
                 "cache_creation_input_tokens": 3000, "output_tokens": 1000}
        tools = [("Read", {"file_path": "/work/src/orders.py"}), ("Edit", {"file_path": "/work/src/importer.py"}),
                 ("Read", {"file_path": "/work/src/importer.py"}), ("Write", {"file_path": "/work/tests/test_importer.py"}),
                 ("Skill", {"skill": "test-driven-development"}), ("WebFetch", {"url": "https://example.com/csv-spec"})]
        records = [
            {"type": "user", "message": {"role": "user", "content": "<system-reminder>noise</system-reminder>Build the order importer"}},
            {"type": "assistant", "message": {"role": "assistant", "usage": usage, "content": [
                {"type": "tool_use", "name": name, "input": given} for name, given in tools]}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "Now handle duplicate rows"}]}},
            "not json at all",
        ]
        path = self.home / "session.jsonl"
        path.write_text("\n".join(record if isinstance(record, str) else json.dumps(record) for record in records) + "\n")
        return path

    def test_a_handoff_is_written_once_the_session_passes_the_threshold(self):
        project = self.home / "project"
        project.mkdir()
        data = {"session_id": "s1", "cwd": str(project), "transcript_path": str(self._transcript(260_000))}
        message = mods.handle_stop(data, self.config())["systemMessage"]
        self.assertIn("260,000 tokens", message)
        self.assertIn("/handoff", message)
        text = (project / ".claude" / "HANDOFF.md").read_text()
        goal, _, rest = text.partition("## Latest requests")
        self.assertIn("Build the order importer", goal)
        self.assertNotIn("system-reminder", text)
        self.assertIn("- Now handle duplicate rows", rest)
        changed = rest.split("## Files changed")[1].split("## Files read")[0]
        read = rest.split("## Files read")[1].split("## Skills used")[0]
        self.assertIn("`/work/src/importer.py`", changed)
        self.assertIn("`/work/tests/test_importer.py`", changed)
        self.assertIn("`/work/src/orders.py`", read)
        self.assertNotIn("importer.py", read, "a changed file is listed once, under changed")
        self.assertIn("`test-driven-development`", rest)
        self.assertIn("`https://example.com/csv-spec`", rest)
        self.assertIsNone(mods.handle_stop(data, self.config()), "not again until the session grows by the repeat step")
        data["transcript_path"] = str(self._transcript(311_000))
        self.assertIn("311,000", mods.handle_stop(data, self.config())["systemMessage"])
        self.assertEqual(self.totals("handoff")["events"], 2)

    def test_a_short_session_or_a_disabled_mod_writes_nothing(self):
        project = self.home / "project"
        project.mkdir()
        data = {"session_id": "s1", "cwd": str(project), "transcript_path": str(self._transcript(90_000))}
        self.assertIsNone(mods.handle_stop(data, self.config()))
        self.assertEqual(json.loads(mods.CLOCK_FILE.read_text())["s1"]["context_tokens"], 90_000)
        mods.toggle("handoff", "off")
        data["transcript_path"] = str(self._transcript(400_000))
        self.assertIsNone(mods.handle_stop(data, self.config()))
        self.assertFalse((project / ".claude" / "HANDOFF.md").exists())

    def test_handoff_command_builds_the_file_on_request(self):
        project = self.home / "project"
        project.mkdir()
        target = mods.write_handoff(str(self._transcript(10_000)), str(project))
        self.assertEqual(target, project / ".claude" / "HANDOFF.md")
        self.assertIn("_Claude fills this in when you run /handoff", target.read_text())
        self.assertIn("No user prompt found", mods.build_handoff(str(self.home / "missing.jsonl"), "."))


class ScreenshotShrinkerTest(ModsCase):
    def test_png_is_halved_for_every_filter_type_and_keeps_its_pixels(self):
        for kind in range(5):
            shrunk, width, height, new_width, new_height = mods.halve_png(make_png(64, 48, colour, kind), 10 ** 7)
            self.assertEqual((width, height, new_width, new_height), (64, 48, 32, 24), kind)
            rows = png_rows(shrunk)
            self.assertEqual(png_size(shrunk), (32, 24))
            for row, column in ((0, 0), (5, 9), (23, 31)):
                self.assertEqual(tuple(rows[row][column * 3:column * 3 + 3]), colour(column * 2, row * 2), (kind, row, column))
        rgba = mods.halve_png(make_png(10, 6, lambda c, r: (c, r, 9, 255), 4, channels=4), 10 ** 7)
        self.assertEqual(rgba[3:], (5, 3))

    def test_images_it_cannot_halve_safely_are_left_alone(self):
        self.assertIsNone(mods.halve_png(b"not a png", 10 ** 7))
        self.assertIsNone(mods.halve_png(make_png(8, 8, colour, interlace=1), 10 ** 7))
        self.assertIsNone(mods.halve_png(make_png(8, 8, colour, depth=16), 10 ** 7))
        self.assertIsNone(mods.halve_png(make_png(64, 48, colour), 1000), "over the fallback pixel limit")
        self.assertIsNone(mods.halve_png(make_png(1, 1, colour), 10 ** 7))

    def test_a_1280x720_screenshot_costs_a_quarter_of_the_image_tokens(self):
        shot = base64.b64encode(make_png(1280, 720, lambda c, r: (30, 60, 90))).decode()
        for block in ({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": shot}},
                      {"type": "image", "data": shot, "mimeType": "image/png"}):
            data = {"tool_name": "mcp__playwright__browser_take_screenshot", "tool_response": [block]}
            result = mods.handle_mcp_output(data, self.config())
            out = result["hookSpecificOutput"]["updatedToolOutput"][0]
            smaller = base64.b64decode((out.get("source") or out)["data"])
            self.assertEqual(png_size(smaller), (640, 360))
        entry = self.totals("efficient-browser-use")
        self.assertEqual(entry["events"], 2)
        self.assertEqual(entry["tokens"], 2 * ((1280 * 720 - 640 * 360) // mods.PIXELS_PER_TOKEN))
        self.assertAlmostEqual(640 * 360 / (1280 * 720), 0.25)

    def test_only_screenshot_tools_are_touched_and_the_mod_can_be_switched_off(self):
        shot = base64.b64encode(make_png(64, 48, colour)).decode()
        block = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": shot}}]
        self.assertIsNone(mods.handle_mcp_output({"tool_name": "mcp__figma__get_design", "tool_response": block}, self.config()))
        broken = [{"type": "image", "source": {"type": "base64", "data": "!!not base64!!"}}]
        self.assertIsNone(mods.handle_mcp_output({"tool_name": "mcp__x__screenshot", "tool_response": broken}, self.config()))
        mods.toggle("efficient-browser-use", "off")
        self.assertIsNone(mods.handle_mcp_output({"tool_name": "mcp__x__screenshot", "tool_response": block}, self.config()))


class SavingsAndSwitchboardTest(ModsCase):
    def test_savings_table_has_a_row_per_mod_and_a_total(self):
        mods.log_saving("input-router", 4000, 0.032, "export.json")
        mods.log_saving("efficient-browser-use", 900, 0.0072, "1280x720 -> 640x360")
        mods.record_context_saving(2500)
        mods.toggle("handoff", "off")
        table = mods.render_savings(self.config())
        for label in ("Input Router", "Effort Optimizer", "Subagent Model Selector", "Cache Clock", "Handoff (off)",
                      "Browser Screenshot Shrinker", "Context Optimizer"):
            self.assertIn(label, table)
        total = [line for line in table.splitlines() if line.startswith("Total")][0]
        self.assertIn("4,900", total, "the per-turn Context Optimizer row is not added to the total")
        self.assertIn("0.0392", total)
        self.assertIn("2,500", table)
        recent = json.loads(mods.SAVINGS_FILE.read_text())["recent"]
        self.assertEqual([event["mod"] for event in recent], ["input-router", "efficient-browser-use"])
        self.assertRegex(recent[0]["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")

    def test_recent_events_are_capped(self):
        for number in range(mods.RECENT_EVENTS + 5):
            mods.log_saving("input-router", 1, 0.0, str(number))
        data = json.loads(mods.SAVINGS_FILE.read_text())
        self.assertEqual(len(data["recent"]), mods.RECENT_EVENTS)
        self.assertEqual(data["totals"]["input-router"]["events"], mods.RECENT_EVENTS + 5)

    def test_switchboard_turns_mods_on_and_off_and_switches_the_reader(self):
        self.assertTrue(all(self.config()[mod]["enabled"] for mod in mods.MODS))
        self.assertEqual(mods.toggle("cache-clock", "off"), "cache-clock: off")
        mods.toggle("input-router", "sonnet")
        config = self.config()
        self.assertFalse(config["cache-clock"]["enabled"])
        self.assertEqual(config["input-router"]["reader"], "sonnet")
        self.assertTrue(config["input-router"]["enabled"], "switching the reader does not switch the mod off")
        status = mods.render_status(config)
        self.assertIn("off  cache-clock", status)
        self.assertIn("on   input-router (reader: sonnet)", status)
        mods.toggle("cache-clock", "on")
        self.assertTrue(self.config()["cache-clock"]["enabled"])
        for mod, value in (("handoff", "sonnet"), ("input-router", "opus"), ("no-such-mod", "on"), ("handoff", "maybe")):
            with self.assertRaises(SystemExit):
                mods.toggle(mod, value)

    def test_a_hook_never_fails_a_session(self):
        environment = {**os.environ, "TQ_FORGE_USER_HOME": str(self.home)}
        for name in sorted(mods.HANDLERS):
            for stdin in ("not json", "[1, 2]", '{"tool_input": 7, "tool_response": 7, "prompt": 7}', ""):
                done = subprocess.run([sys.executable, str(ROOT / "scripts" / "lib" / "mods.py"), "hook", name],
                                      input=stdin, capture_output=True, text=True, env=environment)
                self.assertEqual((done.returncode, done.stdout), (0, ""), (name, stdin, done.stderr))


class InstallTest(ModsCase):
    EXISTING = {"model": "claude-fable-5-2", "permissions": {"allow": ["Bash(git push:*)"]},
                "spinnerVerbs": {"verbs": ["✨ Forging", "Señalando"]},
                "statusLine": {"type": "command", "command": "printf 'mine'"},
                "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo guard"}]}]}}

    def setUp(self):
        super().setUp()
        self.root = self.home / "project"
        (self.root / ".claude").mkdir(parents=True)
        self.settings = self.root / ".claude" / "settings.json"
        self.settings.write_text(json.dumps(self.EXISTING, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _install(self, *flags):
        done = subprocess.run(["bash", str(ROOT / "scripts" / "mods.sh"), "install", "--root", str(self.root), "--json", *flags],
                              capture_output=True, text=True, env={**os.environ, "TQ_FORGE_USER_HOME": str(self.home)})
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def _commands(self, settings):
        return [hook["command"] for groups in settings["hooks"].values() for group in groups for hook in group["hooks"]]

    def test_dry_run_writes_nothing(self):
        before = self.settings.read_text()
        report = self._install()
        self.assertEqual(report["mode"], "dry-run")
        self.assertIn(".claude/hooks/tq-forge/mods.py", report["files"])
        self.assertEqual(self.settings.read_text(), before)
        self.assertFalse((self.root / ".claude" / "hooks").exists())

    def test_apply_adds_the_hooks_and_keeps_everything_that_was_there(self):
        before = self.settings.read_text()
        report = self._install("--apply")
        for name in ("savings", "switchboard", "handoff", "keep-warm", "tq-forge-learn"):
            self.assertTrue((self.root / ".claude" / "skills" / name / "SKILL.md").is_file(), name)
        for name in ("input-reader", "omni-scout"):
            self.assertTrue((self.root / ".claude" / "agents" / f"{name}.md").is_file(), name)
        settings = json.loads(self.settings.read_text())
        commands = self._commands(settings)
        self.assertEqual(commands[0], "echo guard", "the existing hook still runs first")
        runtime = 'python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/tq-forge/mods.py hook '
        self.assertEqual(sorted(command[len(runtime):] for command in commands if command.startswith(runtime)),
                         ["mcp-output", "prompt", "read", "stop", "subagent", "subagent-done"])
        matchers = {group["hooks"][0]["command"].split()[-1]: group.get("matcher")
                    for groups in settings["hooks"].values() for group in groups}
        self.assertEqual((matchers["read"], matchers["subagent"], matchers["mcp-output"], matchers["prompt"]),
                         ("Read", "Agent|Task", "mcp__.*", None))
        self.assertEqual(settings["statusLine"], self.EXISTING["statusLine"], "an existing status line is kept")
        self.assertEqual(settings["permissions"], self.EXISTING["permissions"], "nothing is pre-approved by default")
        self.assertEqual(settings["model"], "claude-fable-5-2")
        self.assertNotIn("effortLevel", settings)
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", json.dumps(settings))
        self.assertTrue(report["nothing_lost"]["ok"])
        applied = self.settings.read_text(encoding="utf-8")
        self.assertIn('"✨ Forging"', applied, "non-ASCII text is written as it was, not as \\u escapes")
        self.assertEqual(self._install("--apply")["mode"], "applied")
        self.assertEqual(self.settings.read_text(), applied, "a second install adds no duplicate hooks")
        optimize.restore(self.root)
        self.assertEqual(self.settings.read_text(), before, "restore is byte-identical")
        self.assertFalse((self.root / ".claude" / "hooks").exists())
        self.assertFalse((self.root / ".claude" / "skills").exists())

    def test_the_installed_copy_runs_on_its_own(self):
        self._install("--apply")
        runtime = self.root / ".claude" / "hooks" / "tq-forge" / "mods.py"
        spawn = {"tool_input": {"subagent_type": "general-purpose", "description": "Summarize the logs", "prompt": "list errors"}}
        done = subprocess.run([sys.executable, "-I", str(runtime), "hook", "subagent"], input=json.dumps(spawn),
                              capture_output=True, text=True, cwd=str(self.home),
                              env={"PATH": os.environ["PATH"], "TQ_FORGE_USER_HOME": str(self.home)})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["hookSpecificOutput"]["updatedInput"]["model"], "haiku")
        self.assertTrue((self.state / "tq-forge-savings.json").is_file())
        self.assertEqual(json.loads((runtime.parent / "mods.json").read_text())["input-router"]["threshold_tokens"], 2000)

    def test_status_line_is_set_when_there_is_none_and_chained_only_on_request(self):
        chained = self._install("--apply", "--chain-statusline")
        self.assertIn(".claude/hooks/tq-forge/statusline-earlier.sh", chained["files"])
        settings = json.loads(self.settings.read_text())
        self.assertEqual((self.root / mods_install.EARLIER_STATUSLINE).read_text(), "printf 'mine'\n")
        self.assertEqual(settings["statusLine"]["command"],
                         'python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/tq-forge/mods.py statusline --chain '
                         '"$CLAUDE_PROJECT_DIR"/.claude/hooks/tq-forge/statusline-earlier.sh')
        self.assertNotIn(mods_install.EARLIER_STATUSLINE, self._install("--apply", "--chain-statusline")["files"],
                         "chaining twice does not wrap the wrapper")
        self.assertEqual((self.root / mods_install.EARLIER_STATUSLINE).read_text(), "printf 'mine'\n")
        optimize.restore(self.root)
        self.settings.write_text(json.dumps({"model": "claude-fable-5-2"}))
        self._install("--apply")
        self.assertEqual(json.loads(self.settings.read_text())["statusLine"]["command"],
                         'python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/tq-forge/mods.py statusline')

    def test_autonomy_permissions_are_added_only_with_the_flag(self):
        self._install("--apply", "--allow-autonomy")
        allowed = json.loads(self.settings.read_text())["permissions"]["allow"]
        command = mods_install.cli_command()
        self.assertEqual(allowed, ["Bash(git push:*)", "WebSearch", "WebFetch", f"Bash({command} learn *)",
                                   f"Bash({command} scout *)", "Bash(gh api *)"])
        self._install("--apply", "--allow-autonomy")
        self.assertEqual(json.loads(self.settings.read_text())["permissions"]["allow"], allowed, "no duplicates")
        learn = (self.root / ".claude" / "skills" / "tq-forge-learn" / "SKILL.md").read_text()
        self.assertIn(f'{command} learn "$ARGUMENTS"', learn, "the skill runs the command that was pre-approved")

    def test_cli_command_never_records_an_npx_cache_path(self):
        self.assertTrue(mods_install.cli_command().startswith("node "))
        cached = self.home / ".npm" / "_npx" / "ab12" / "node_modules" / "tq-forge"
        (cached / "bin").mkdir(parents=True)
        (cached / "bin" / "cli.js").write_text("")
        self.assertEqual(mods_install.cli_command(cached), "npx tq-forge")
        self.assertEqual(mods_install.cli_command(self.home / "nowhere"), "npx tq-forge")
        with tempfile.TemporaryDirectory(dir="/tmp") as elsewhere:
            package = pathlib.Path(elsewhere).resolve()
            (package / "bin").mkdir()
            (package / "bin" / "cli.js").write_text("")
            self.assertEqual(mods_install.cli_command(package), f"node {package.as_posix()}/bin/cli.js")
        self.assertEqual(mods_install._prefix(self.root), '"$CLAUDE_PROJECT_DIR"')
        self.assertEqual(mods_install._prefix(pathlib.Path.home()), '"$HOME"')

    def test_an_applied_optimize_shows_up_on_the_savings_dashboard(self):
        prose = "\n".join(f"This paragraph explains idea {n} at length so that a new reader understands it." for n in range(150))
        (self.root / "CLAUDE.md").write_text(f"# Project\n\n## Rules\n\n- Use tabs.\n\n## Background\n\n{prose}\n")
        environment = {**os.environ, "TQ_FORGE_USER_HOME": str(self.home)}
        command = ["bash", str(ROOT / "scripts" / "optimize.sh"), "optimize", "--root", str(self.root), "--apply", "--json"]
        first = json.loads(subprocess.run(command, capture_output=True, text=True, env=environment).stdout)
        self.assertGreater(first["reduction_percent"], 0)
        self.assertFalse(mods.SAVINGS_FILE.exists(), "a project without the mods is not tracked")
        optimize.restore(self.root)
        self._install("--apply")
        report = json.loads(subprocess.run(command, capture_output=True, text=True, env=environment).stdout)
        saved = report["before"]["estimated_tokens"] - report["after"]["estimated_tokens"]
        self.assertGreater(saved, 0)
        self.assertEqual(self.totals("context-optimizer")["tokens"], saved)
        (self.root / ".mcp.json").write_text(json.dumps({"mcpServers": {"flow": {"command": "npx", "alwaysLoad": True}}}))
        subprocess.run(command, capture_output=True, text=True, env=environment)
        merged = self.settings.read_text(encoding="utf-8")
        self.assertEqual(json.loads(merged)["env"], {"ENABLE_TOOL_SEARCH": "true"})
        self.assertIn('"✨ Forging"', merged, "the settings merge keeps non-ASCII text too")


if __name__ == "__main__":
    unittest.main()
