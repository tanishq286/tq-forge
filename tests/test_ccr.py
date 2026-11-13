"""Tests for the reversible store (scripts/lib/ccr_engine.py) and `tq-forge retrieve`.

Every test stores under a temporary folder, so the real ~/.claude is never read or written.

Run: python3 -m unittest discover -s tests -v
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import ccr_engine  # noqa: E402

CLI = ROOT / "bin" / "cli.js"
NOT_AN_ID = ("", "abc", "0123456789abc", "0123456789AB", "0123456789ag", "0123456789ab\n", "../../etc/pw",
             "..%2f..%2fpass", "0123456789a/", None, 123456789012)


class CcrCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = pathlib.Path(self._tmp.name).resolve()
        self.store = self.home / ".claude" / "tq-forge-ccr"

    def keep(self, text, kind="raw"):
        return ccr_engine.store_ccr(text, kind, self.store)

    def fetch(self, ccr_id, **options):
        return ccr_engine.retrieve_ccr(ccr_id, directory=self.store, **options)


class StoreAndRetrieveTest(CcrCase):
    def test_stored_text_comes_back_unchanged_under_a_twelve_hex_id(self):
        text = "first line\nsecond line — ünïcode\n\nlast"
        ccr_id = self.keep(text, "logs")
        self.assertRegex(ccr_id, r"\A[a-f0-9]{12}\Z")
        self.assertEqual(self.fetch(ccr_id), text)
        entry = json.loads((self.store / f"{ccr_id}.json").read_text(encoding="utf-8"))
        self.assertEqual((entry["id"], entry["kind"]), (ccr_id, "logs"))
        self.assertAlmostEqual(entry["timestamp"], time.time(), delta=60)
        self.assertEqual(self.keep(text), ccr_id, "the id is the content hash, so storing twice is one entry")
        self.assertEqual(len(list(self.store.iterdir())), 1)

    def test_entries_are_owner_only_and_week_old_ones_are_pruned(self):
        stale = self.keep("old")
        long_ago = time.time() - ccr_engine.KEEP_SECONDS - 60
        os.utime(self.store / f"{stale}.json", (long_ago, long_ago))
        fresh = self.keep("new")
        self.assertEqual((self.store / f"{fresh}.json").stat().st_mode & 0o077, 0)
        self.assertFalse((self.store / f"{stale}.json").exists())
        with self.assertRaises(ccr_engine.CCRNotFound):
            self.fetch(stale)

    def test_only_twelve_lowercase_hex_characters_are_an_id(self):
        outside = self.home / "secret.json"
        outside.write_text(json.dumps({"content": "must never be printed"}))
        self.assertTrue(ccr_engine.valid_ccr_id("0123456789ab"))
        for bad in NOT_AN_ID:
            self.assertFalse(ccr_engine.valid_ccr_id(bad), repr(bad))
            with self.assertRaises(ccr_engine.CCRError, msg=repr(bad)) as caught:
                self.fetch(bad)
            self.assertNotIsInstance(caught.exception, ccr_engine.CCRNotFound, "rejected before any path is built")

    def test_missing_and_corrupt_entries_are_reported_as_not_found(self):
        with self.assertRaises(ccr_engine.CCRNotFound):
            self.fetch("0123456789ab")
        self.store.mkdir(parents=True)
        (self.store / "0123456789ab.json").write_text("{not json")
        with self.assertRaises(ccr_engine.CCRNotFound):
            self.fetch("0123456789ab")

    def test_lines_and_search_select_part_of_the_text(self):
        ccr_id = self.keep("\n".join(f"line {n}{' ERROR boom' if n % 4 == 0 else ''}" for n in range(1, 11)))
        self.assertEqual(self.fetch(ccr_id, lines="2:3"), "line 2\nline 3")
        self.assertEqual(self.fetch(ccr_id, lines="9:500"), "line 9\nline 10", "a range past the end stops at the end")
        self.assertEqual(self.fetch(ccr_id, search="error"), "4: line 4 ERROR boom\n8: line 8 ERROR boom")
        self.assertEqual(self.fetch(ccr_id, lines="5:10", search="ERROR"), "8: line 8 ERROR boom")
        self.assertEqual(self.fetch(ccr_id, search="absent"), "")
        for bad in ("0:5", "5:2", "3", "a:b", "1:2:3", "-1:4", "1:", " 1:2"):
            with self.assertRaises(ccr_engine.CCRError, msg=bad):
                self.fetch(ccr_id, lines=bad)


class ShaperTest(CcrCase):
    def _footer_id(self, shaped):
        footer = shaped.splitlines()[-1]
        self.assertTrue(footer.startswith("[CCR-ID: "), footer)
        return footer.split()[1]

    def test_json_records_become_a_schema_rows_and_a_count_and_stay_retrievable(self):
        rows = [{"id": n, "name": f"row {n}", "note": "", "icon": "data:image/png;base64,AAAA", "tags": []}
                for n in range(40)]
        raw = json.dumps({"items": rows, "next": None, "few": [1, 2, 3]})
        shaped = ccr_engine.smart_crush_json(raw, directory=self.store)
        crushed = json.loads(shaped.splitlines()[0])
        table = crushed["items"]
        self.assertEqual(table["_schema"], ["id", "name", "note", "icon", "tags"])
        self.assertEqual(len(table["_rows"]), ccr_engine.MAX_JSON_ROWS)
        self.assertEqual((table["_total_rows"], table["_elided_rows"]), (40, 25))
        self.assertEqual(table["_rows"][0][:2], [0, "row 0"], "zero is a value and is kept")
        self.assertNotIn("next", crushed)
        self.assertEqual(crushed["few"], [1, 2, 3])
        self.assertLess(len(shaped), len(raw) / 2)
        self.assertEqual(json.loads(self.fetch(self._footer_id(shaped))), json.loads(raw), "nothing is lost")

    def test_short_lists_and_text_that_is_not_json_are_left_alone(self):
        self.assertEqual(ccr_engine.smart_crush_json("plain text, not JSON", directory=self.store), "plain text, not JSON")
        self.assertFalse(self.store.exists(), "nothing is stored for text that is returned as is")
        shaped = ccr_engine.smart_crush_json(json.dumps([{"a": 1}, {"a": 2}]), directory=self.store)
        self.assertEqual(json.loads(shaped.splitlines()[0]), [{"a": 1}, {"a": 2}])

    def test_python_source_becomes_an_outline_with_line_ranges(self):
        body = "\n".join(f"    total += {n}" for n in range(120))
        source = (f"import os\nfrom pathlib import Path\n\nLIMIT = 5\n\n\ndef first(total=0):\n{body}\n    return total\n"
                  f"\n\nclass Thing:\n    def method(self, total=0):\n{body.replace('    ', '        ')}\n        return total\n")
        outline = ccr_engine.compress_code_ast(source, "module.py", directory=self.store)
        ccr_id = self._footer_id(outline)
        self.assertIn("L1: import os", outline)
        self.assertIn("L4: LIMIT = 5", outline)
        self.assertIn(f"L7: def first(total=0):  # body: lines 7-128 in CCR {ccr_id}", outline)
        self.assertIn("class Thing:", outline)
        self.assertNotIn("total += 7", outline)
        self.assertEqual(self.fetch(ccr_id, lines="7:8"), "def first(total=0):\n    total += 0")
        self.assertEqual(self.fetch(ccr_id), source)

    def test_other_languages_broken_python_and_small_files(self):
        script = "\n".join(f"export function handler{n}(request) {{\n  return request.body + {n};\n}}\n" for n in range(200))
        outline = ccr_engine.compress_code_ast(script, "handlers.ts", directory=self.store)
        self.assertIn("L1: export function handler0(request) {", outline)
        self.assertIn(f"... [{200 - ccr_engine.MAX_OUTLINE_LINES} more definitions]", outline)
        self.assertNotIn("return request.body", outline)
        broken = "def ok():\n    return 1\n" + "def broken(:\n    pass\n" * 200
        self.assertIn("L1: def ok():", ccr_engine.compress_code_ast(broken, "broken.py", directory=self.store))
        small = "def tiny():\n    return 1\n"
        self.assertEqual(ccr_engine.compress_code_ast(small, "tiny.py", directory=self.store), small)

    def test_logs_lose_colour_blank_lines_and_repeats(self):
        log = "\n".join(["\x1b[32m10:00:01 INFO start\x1b[0m", "", *["10:00:02 WARN retrying"] * 50,
                         "10:00:03 ERROR connection refused", *[f"    at node_modules/pkg/file{n}.js" for n in range(40)],
                         *[f"10:01:{n:02d} INFO step {n}" for n in range(60)], *[f"tail {n}" for n in range(60)]])
        shaped = ccr_engine.rtk_shape_logs(log, directory=self.store)
        lines = shaped.splitlines()
        self.assertEqual(lines[0], "10:00:01 INFO start")
        self.assertEqual(lines[1:3], ["10:00:02 WARN retrying", "  ... [repeated 50 times]"])
        self.assertIn("10:00:03 ERROR connection refused", lines)
        self.assertLess(sum("node_modules/" in line for line in lines), 40, "dependency frames are thinned")
        self.assertRegex(lines[-2], r"^\.\.\. \[\d+ more lines\]$")
        self.assertEqual(len(lines), ccr_engine.MAX_LOG_LINES + 2)
        ccr_id = self._footer_id(shaped)
        self.assertEqual(self.fetch(ccr_id), log)
        self.assertIn("ERROR connection refused", self.fetch(ccr_id, search="error"))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class RetrieveCommandTest(CcrCase):
    def run_cli(self, *args):
        return subprocess.run(["node", str(CLI), "retrieve", *args], capture_output=True, text=True,
                              env={**os.environ, "TQ_FORGE_USER_HOME": str(self.home), "NO_COLOR": "1"})

    def test_prints_the_stored_text_a_range_or_the_matching_lines(self):
        ccr_id = self.keep("alpha\nbeta ERROR\ngamma\ndelta error")
        whole = self.run_cli(ccr_id)
        self.assertEqual((whole.returncode, whole.stdout), (0, "alpha\nbeta ERROR\ngamma\ndelta error\n"), whole.stderr)
        self.assertEqual(self.run_cli(ccr_id, "--lines", "2:3").stdout, "beta ERROR\ngamma\n")
        self.assertEqual(self.run_cli(ccr_id, "--search", "error").stdout, "2: beta ERROR\n4: delta error\n")
        self.assertEqual(self.run_cli("--lines=1:2", "--search=ALPHA", ccr_id).stdout, "1: alpha\n")
        dashed = self.run_cli(ccr_id, "--search", "--lines")
        self.assertEqual((dashed.returncode, dashed.stdout), (0, "\n"), "a keyword that looks like an option is a keyword")

    def test_a_bad_id_or_range_is_refused_before_anything_is_read(self):
        outside = self.home / "secret.json"
        outside.write_text(json.dumps({"content": "must never be printed"}))
        ccr_id = self.keep("text")
        for args in (["../secret"], ["../../secret"], ["0123456789AB"], ["abc"], ["0123456789abc"], [],
                     [ccr_id, "0123456789ab"], [ccr_id, "--lines", "1-2"], [ccr_id, "--lines"], [ccr_id, "--all"]):
            done = self.run_cli(*args)
            self.assertEqual(done.returncode, 2, args)
            self.assertEqual(done.stdout, "", args)
            self.assertIn("Usage: tq-forge retrieve <ccr_id> [--lines A:B] [--search KW]", done.stderr)
        backwards = self.run_cli(ccr_id, "--lines", "5:2")
        self.assertEqual((backwards.returncode, backwards.stdout), (2, ""))
        self.assertIn("--lines takes START:END", backwards.stderr)

    def test_an_unknown_id_exits_one_and_help_is_listed(self):
        missing = self.run_cli("0123456789ab")
        self.assertEqual((missing.returncode, missing.stdout), (1, ""))
        self.assertIn("is not in", missing.stderr)
        self.assertIn("Usage: tq-forge retrieve", self.run_cli("--help").stdout)
        listed = subprocess.run(["node", str(CLI), "help"], capture_output=True, text=True)
        self.assertIn("retrieve <ccr_id>", listed.stdout)


if __name__ == "__main__":
    unittest.main()
