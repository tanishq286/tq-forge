#!/usr/bin/env python3
"""Deterministic evaluator for recorded agent runs; does not execute agents."""
from __future__ import annotations
import argparse
import json
import pathlib
import sys
from typing import Any

class EvaluationError(ValueError):
    pass

def read_json(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvaluationError(f"cannot read JSON file {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvaluationError(f"{path}: expected a JSON object")
    return value

def read_results(path: pathlib.Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise EvaluationError(f"cannot read results file {path}: {error}") from error
    records = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise EvaluationError(f"{path}:{number}: invalid JSON: {error}") from error
        if not isinstance(record, dict):
            raise EvaluationError(f"{path}:{number}: each result must be a JSON object")
        records.append(record)
    return records

def strings(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise EvaluationError(f"{label} must be an array of non-empty strings")
    return value

def tool_names(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise EvaluationError(f"{label} must be an array")
    names = []
    for item in value:
        name = item if isinstance(item, str) else item.get("name") if isinstance(item, dict) else None
        if not isinstance(name, str) or not name:
            raise EvaluationError(f"{label} entries must be strings or objects with a name")
        names.append(name)
    return names

def validate_suite(suite: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    if suite.get("schema_version") != 1:
        raise EvaluationError("suite schema_version must be 1")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvaluationError("suite cases must be a non-empty array")
    threshold = suite.get("min_pass_rate", 1.0)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise EvaluationError("min_pass_rate must be a number between 0 and 1")
    seen = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise EvaluationError(f"cases[{index}] must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise EvaluationError(f"cases[{index}].id must be a non-empty string")
        if case_id in seen:
            raise EvaluationError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        for field in ("required_contains", "forbidden_contains", "required_tools", "forbidden_tools"):
            strings(case.get(field), f"case {case_id}.{field}")
        for field in ("max_latency_ms", "max_cost_usd"):
            value = case.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
                raise EvaluationError(f"case {case_id}.{field} must be a non-negative number")
        if "security" in case and not isinstance(case["security"], bool):
            raise EvaluationError(f"case {case_id}.security must be boolean")
    return cases, float(threshold)

def evaluate_case(case: dict[str, Any], result: dict[str, Any] | None) -> dict[str, Any]:
    checks = []
    security_case = bool(case.get("security"))
    def check(name: str, passed: bool, detail: str = "", security: bool = False) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail,
                       "security": security_case or security})
    if result is None:
        check("result_present", False, "No result record was supplied.")
    else:
        status = result.get("status", "completed")
        check("status", status == "completed", f"Observed status: {status!r}.")
        output = result.get("output", "")
        if not isinstance(output, str):
            output = json.dumps(output, ensure_ascii=False, sort_keys=True)
        lowered = output.casefold()
        for phrase in strings(case.get("required_contains"), f"case {case['id']}.required_contains"):
            check(f"required_output:{phrase}", phrase.casefold() in lowered, f"Required phrase: {phrase!r}.")
        for phrase in strings(case.get("forbidden_contains"), f"case {case['id']}.forbidden_contains"):
            check(f"forbidden_output:{phrase}", phrase.casefold() not in lowered, f"Forbidden phrase: {phrase!r}.")
        tools = tool_names(result.get("tool_calls", []), f"result {case['id']}.tool_calls")
        for name in strings(case.get("required_tools"), f"case {case['id']}.required_tools"):
            check(f"required_tool:{name}", name in tools, f"Required tool: {name!r}.")
        for name in strings(case.get("forbidden_tools"), f"case {case['id']}.forbidden_tools"):
            check(f"forbidden_tool:{name}", name not in tools, f"Forbidden tool: {name!r}.", bool(case.get("security")))
        for field, result_field in (("max_latency_ms", "latency_ms"), ("max_cost_usd", "cost_usd")):
            limit = case.get(field)
            if limit is not None:
                observed = result.get(result_field)
                valid = isinstance(observed, (int, float)) and not isinstance(observed, bool) and observed <= limit
                check(field, valid, f"Observed {observed!r}; limit {limit}.")
    passed = all(item["passed"] for item in checks)
    security_passed = all(item["passed"] for item in checks if item["security"])
    return {"id": case["id"], "passed": passed, "security_passed": security_passed, "checks": checks}

def evaluate(suite: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    cases, threshold = validate_suite(suite)
    by_id = {}
    for record in results:
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise EvaluationError("every result record needs a non-empty case_id")
        if case_id in by_id:
            raise EvaluationError(f"duplicate result for case_id: {case_id}")
        by_id[case_id] = record
    expected = {case["id"] for case in cases}
    unexpected = sorted(set(by_id) - expected)
    if unexpected:
        raise EvaluationError(f"results contain unknown case ids: {', '.join(unexpected)}")
    evaluated = [evaluate_case(case, by_id.get(case["id"])) for case in cases]
    passed = sum(item["passed"] for item in evaluated)
    security_ids = {case["id"] for case in cases if case.get("security")}
    security_failures = sum(not item["security_passed"] for item in evaluated if item["id"] in security_ids)
    rate = passed / len(cases)
    gate_passed = rate >= threshold and security_failures == 0
    return {
        "schema_version": 1, "suite": suite.get("name", "unnamed"),
        "summary": {"cases": len(cases), "passed": passed, "failed": len(cases) - passed,
                    "pass_rate": round(rate, 4), "required_pass_rate": threshold,
                    "security_failures": security_failures, "gate": "pass" if gate_passed else "fail"},
        "cases": evaluated,
        "limitations": [
            "Deterministic observable checks are not a semantic judge of answer correctness.",
            "The evaluator does not execute agents or validate claims absent from observable outputs.",
            "Repeat suites across seeds and model versions before drawing reliability conclusions."
        ]
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate recorded agent runs against a deterministic JSON suite.")
    parser.add_argument("--suite", required=True, help="Path to evaluation suite JSON")
    parser.add_argument("--results", required=True, help="Path to JSONL runtime results")
    parser.add_argument("--json", action="store_true", help="Print machine-readable report")
    args = parser.parse_args(argv)
    try:
        report = evaluate(read_json(pathlib.Path(args.suite)), read_results(pathlib.Path(args.results)))
    except EvaluationError as error:
        print(f"tq-forge evaluate: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        summary = report["summary"]
        print(f"{report['suite']}: {summary['passed']}/{summary['cases']} passed ({summary['pass_rate']:.1%}); security failures: {summary['security_failures']}")
        print(f"Gate: {summary['gate'].upper()} (required {summary['required_pass_rate']:.1%})")
        for case in report["cases"]:
            if not case["passed"]:
                failed = [item["name"] for item in case["checks"] if not item["passed"]]
                print(f"  FAIL {case['id']}: {', '.join(failed)}")
    return 0 if report["summary"]["gate"] == "pass" else 1

if __name__ == "__main__":
    raise SystemExit(main())
