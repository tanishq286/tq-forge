"""Tests for the deterministic recorded-agent evaluation harness."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))
import evaluate  # noqa: E402


class EvaluateTest(unittest.TestCase):
    def setUp(self):
        self.suite = {
            "schema_version": 1, "name": "test-suite", "min_pass_rate": 0.5,
            "cases": [
                {"id": "ok", "required_contains": ["answer"], "required_tools": ["search"]},
                {"id": "safe", "forbidden_tools": ["shell.exec"], "security": True},
            ],
        }

    def test_passes_required_output_tool_and_security_policy(self):
        results = [
            {"case_id": "ok", "status": "completed", "output": "An answer.", "tool_calls": ["search"]},
            {"case_id": "safe", "status": "completed", "output": "Done.", "tool_calls": ["read"]},
        ]
        report = evaluate.evaluate(self.suite, results)
        self.assertEqual(report["summary"]["gate"], "pass")
        self.assertEqual(report["summary"]["pass_rate"], 1.0)
        self.assertEqual(report["summary"]["security_failures"], 0)

    def test_security_failure_fails_gate_even_when_rate_threshold_passes(self):
        results = [
            {"case_id": "ok", "status": "completed", "output": "An answer.", "tool_calls": ["search"]},
            {"case_id": "safe", "status": "completed", "output": "Done.", "tool_calls": ["shell.exec"]},
        ]
        report = evaluate.evaluate(self.suite, results)
        self.assertEqual(report["summary"]["gate"], "fail")
        self.assertEqual(report["summary"]["security_failures"], 1)

    def test_missing_result_fails_case(self):
        report = evaluate.evaluate(self.suite, [])
        self.assertEqual(report["summary"]["failed"], 2)
        self.assertEqual(report["summary"]["gate"], "fail")

    def test_unknown_and_duplicate_results_are_rejected(self):
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.evaluate(self.suite, [{"case_id": "unknown"}])
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.evaluate(self.suite, [{"case_id": "ok"}, {"case_id": "ok"}])

    def test_invalid_suite_is_rejected(self):
        with self.assertRaises(evaluate.EvaluationError):
            evaluate.validate_suite({"schema_version": 2, "cases": []})

    def test_committed_example_passes(self):
        suite = evaluate.read_json(ROOT / "evals" / "core-suite.json")
        results = evaluate.read_results(ROOT / "evals" / "fixtures" / "core-results.jsonl")
        self.assertEqual(evaluate.evaluate(suite, results)["summary"]["gate"], "pass")


if __name__ == "__main__":
    unittest.main()
