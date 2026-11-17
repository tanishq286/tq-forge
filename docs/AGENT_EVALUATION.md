# Agent evaluation

tq-forge evaluate is a deterministic evaluator for recorded agent executions. It is deliberately separate from score and validate:

- score evaluates artifact structure and instruction quality.
- validate checks structural conformance.
- evaluate checks observable outcomes from an actual runtime execution.

The evaluator does not execute an agent, infer semantic correctness, or claim that a passing run proves safety. A runtime adapter (human, CI harness, Claude Code, Codex, or another supported runtime) must execute the task and export results.

## Quick start

```bash
npx tq-forge evaluate --suite evals/core-suite.json --results evals/fixtures/core-results.jsonl
npx tq-forge evaluate --suite evals/core-suite.json --results evals/fixtures/core-results.jsonl --json
```

## Suite format

A suite is a JSON object with schema_version: 1, a name, a pass-rate gate, and cases:

- id: stable unique case identifier.
- task: task text given to the agent (documentation/runtime adapter input).
- required_contains: case-insensitive phrases required in the final output.
- forbidden_contains: phrases prohibited in the final output.
- required_tools: tool names that must appear in the recorded tool trace.
- forbidden_tools: tool names that must not appear.
- max_latency_ms and max_cost_usd: optional numeric budgets.
- security: true means failures in this case trigger a hard gate failure.

A result file is JSON Lines (one object per executed case):

```json
{"case_id":"summarize-with-source","status":"completed","output":"Summary ... Source ...","tool_calls":[{"name":"document.read"}],"latency_ms":850,"cost_usd":0.002}
```

Every suite case must have a result. Missing results fail. Duplicate or unknown case IDs are invalid. Tool calls may be strings or objects with a name field.

## Interpreting results

The report includes case-level checks, overall pass rate, and security failures. A security case failure fails the gate even if the configured overall pass rate would otherwise pass.

Use multiple runs, different seeds, model versions, and realistic tasks. Keep benchmark datasets versioned. Report sample size and confidence intervals when publishing performance claims. Never publish a score without the suite version, model/runtime version, number of runs, and failure breakdown.

## Important limitations

This first evaluator is deterministic and observable. Phrase matching can be gamed and cannot establish factual correctness. Tool-name checks cannot establish that a tool was used appropriately. Latency and cost values are trusted inputs from the runtime adapter. For higher-assurance evaluations, add domain-specific assertions, human review, calibrated model judges with adjudication, security red-team suites, and repeated-run statistics.
