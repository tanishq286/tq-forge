"""Tests for the model registry, the model-compatibility lint and the compatibility matrix.

The lint fixtures live in scripts/lib/lint_cases.py so the scorer assertion
suite (scripts/test-runner.py) and these unit tests run the same cases.

Run: python3 -m unittest discover -s tests -v
"""

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import compat_matrix  # noqa: E402
import frontmatter  # noqa: E402
import lint_cases  # noqa: E402
import model_lint  # noqa: E402
import model_sync  # noqa: E402
import models  # noqa: E402
import scaffold  # noqa: E402
import score  # noqa: E402

# Current ids come from the bundled registry (see lint_cases), so these tests still hold on
# the pull request that the weekly model sync opens after a new Claude model is released.
FABLE, OPUS, SONNET, HAIKU = lint_cases.FABLE, lint_cases.OPUS, lint_cases.SONNET, lint_cases.HAIKU
NEXT_FABLE = lint_cases.newer(FABLE)


def rule_ids(text, model_id, **options):
    return [finding["id"] for finding in model_lint.lint(text, model_id, **options)]


class IsolatedStateTest(unittest.TestCase):
    """Points TQ_FORGE_HOME at an empty folder so only the bundled registry is read."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="tq-forge-compat-")
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        patcher = mock.patch.dict(os.environ, {"TQ_FORGE_HOME": str(self.tmp / "state")})
        patcher.start()
        self.addCleanup(patcher.stop)


class LintCaseTest(IsolatedStateTest):
    def test_pattern_rules_fire_only_on_the_models_and_texts_they_cover(self):
        for rule_id, model_id, text, must_fire, why in lint_cases.PATTERN_CASES:
            with self.subTest(rule=rule_id, model=model_id, why=why):
                target, _ = models.lint_target(model_id)

                fired = rule_id in rule_ids(text, target)

                self.assertEqual(fired, must_fire)

    def test_completion_rule_fires_for_long_horizon_subagents_at_early_stop_efforts(self):
        for model_id, text, effort, must_fire, why in lint_cases.COMPLETION_CASES:
            with self.subTest(model=model_id, why=why):
                fired = "M011" in rule_ids(text, model_id, kind="subagent", effort=effort)

                self.assertEqual(fired, must_fire)

    def test_completion_rule_ignores_skills_and_unknown_kinds(self):
        text = lint_cases.subagent(effort="medium")

        self.assertNotIn("M011", rule_ids(text, FABLE, kind="skill"))
        self.assertNotIn("M011", rule_ids(text, FABLE))

    def test_stale_id_rule_scales_the_penalty_with_the_status(self):
        for text, penalty, why in lint_cases.STALE_ID_CASES:
            with self.subTest(why=why):
                found = [finding for finding in model_lint.lint(text, FABLE) if finding["id"] == "M012"]

                self.assertEqual(found[0]["penalty"] if found else None, penalty)

    def test_stale_id_finding_names_the_id_and_its_replacement(self):
        finding = model_lint.lint("model: claude-3-5-sonnet-20241022", None)[0]

        self.assertEqual(finding["id"], "M012")
        self.assertIn("claude-3-5-sonnet-20241022", finding["message"])
        self.assertIn(SONNET, finding["message"])
        self.assertIn("2025-10-28", finding["message"])

    def test_stale_id_rule_reports_the_worst_status_and_counts_every_hit(self):
        text = "a: claude-sonnet-4-6\nb: claude-3-opus-20240229\nc: claude-haiku-4-5\n"

        finding = [f for f in model_lint.lint(text, FABLE) if f["id"] == "M012"][0]

        self.assertEqual((finding["penalty"], finding["count"], finding["line"]), (10, 3, 1))

    def test_total_penalty_is_capped(self):
        text = ('thinking={"type": "enabled", "budget_tokens": 1}\nthinking={"type": "disabled"}\n'
                "temperature=0.1\nShow your full chain of thought.\nmodel: claude-3-opus-20240229\n"
                'tool_choice={"type": "any"}\nDo not think.\nYou have 500 tokens.\n')

        findings = model_lint.lint(text, FABLE)

        self.assertGreater(sum(finding["penalty"] for finding in findings), model_lint.MAX_TOTAL_PENALTY)
        self.assertEqual(model_lint.total_penalty(findings), model_lint.MAX_TOTAL_PENALTY)

    def test_rules_for_lists_fewer_model_rules_for_haiku(self):
        fable, haiku = model_lint.rules_for(FABLE), model_lint.rules_for(HAIKU)

        self.assertEqual(set(fable) - set(haiku), {"M004", "M007", "M010"})
        self.assertEqual(model_lint.rules_for(None), ["M012", "S001", "S002"])


class LongHorizonTest(unittest.TestCase):
    def fields(self, text):
        fields, body, _ = frontmatter.read(text)
        return fields, body

    def test_read_only_agent_with_a_short_workflow_is_not_long_horizon(self):
        self.assertFalse(model_lint.is_long_horizon(*self.fields(lint_cases.subagent(tools="Read, Grep"))))

    def test_an_agent_that_can_write_or_delegate_is_long_horizon(self):
        for tools in ("Read, Write", "Read, Agent", "Task", "NotebookEdit"):
            with self.subTest(tools=tools):
                self.assertTrue(model_lint.is_long_horizon(*self.fields(lint_cases.subagent(tools=tools))))

    def test_background_and_many_turns_make_an_agent_long_horizon(self):
        base = lint_cases.subagent(tools="Read, Grep")

        self.assertTrue(model_lint.is_long_horizon(*self.fields(base.replace("effort:", "background: true\neffort:"))))
        self.assertTrue(model_lint.is_long_horizon(*self.fields(base.replace("effort:", "maxTurns: 40\neffort:"))))
        self.assertFalse(model_lint.is_long_horizon(*self.fields(base.replace("effort:", "maxTurns: 5\neffort:"))))
        self.assertFalse(model_lint.is_long_horizon(*self.fields(base.replace("effort:", "maxTurns: many\neffort:"))))

    def test_completion_instructions_are_recognised_in_several_wordings(self):
        for text in ("# Finishing work\n\nGo on.", "Keep working until the task is done.",
                     "Do not stop until every file is reviewed.", "Avoid stopping while you still owe work.",
                     "Continue until the suite passes.", "Work until everything the user asked for is done."):
            with self.subTest(text=text):
                self.assertTrue(model_lint.has_completion_instructions(text))
        self.assertFalse(model_lint.has_completion_instructions("Report when you are done."))


class ModelStatusTest(IsolatedStateTest):
    def test_status_places_ids_against_the_registry(self):
        expected = {
            FABLE: "current", OPUS.replace("claude-", "anthropic/claude-", 1): "current",
            "claude-opus-5": "superseded", "claude-fable-5-1": "superseded", "claude-haiku-4-5-20251001": "superseded",
            "claude-sonnet-4-5": "deprecated", "claude-opus-4-5@20251101": "superseded",
            "claude-mythos-preview": "deprecated",
            "claude-3-5-sonnet-latest": "retired", "claude-opus-4-20250514": "retired", "claude-2.1": "retired",
            "anthropic.claude-3-5-sonnet-20241022-v2:0": "retired", "anthropic.claude-sonnet-4-6": "superseded",
            NEXT_FABLE: "unknown", "claude-code": "unknown", "gpt-5": "unknown", "": "unknown",
        }
        for model_id, status in expected.items():
            with self.subTest(model=model_id):
                self.assertEqual(models.status(model_id)["status"], status)

    def test_a_family_rule_is_replaced_by_the_family_current_model(self):
        found = models.status("claude-3-7-sonnet-20250219")

        self.assertEqual(found, {"status": "retired", "replacement": SONNET, "date": "2026-02-19"})

    def test_lint_target_falls_back_to_the_family_current_model_for_a_stale_id(self):
        self.assertEqual(models.lint_target("claude-sonnet-4-6")[0], SONNET)
        self.assertEqual(models.lint_target("claude-3-opus-20240229")[0], OPUS)
        self.assertEqual(models.lint_target(NEXT_FABLE)[0], FABLE)
        self.assertEqual(models.lint_target("opus")[0], OPUS)
        self.assertEqual(models.lint_target("inherit")[0], models.default_model())
        self.assertIsNone(models.lint_target("gpt-5")[0])

    def test_a_synced_registry_with_an_older_schema_does_not_shadow_the_bundled_one(self):
        state = models.state_generations_file()
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({"schema": 1, "updated": "2099-01-01", "models": {"claude-old": {}}}))

        registry = models.generations()

        self.assertEqual(registry["schema"], 2)
        self.assertIn(FABLE, registry["models"])

    def test_a_synced_registry_with_the_same_schema_and_a_later_date_wins(self):
        bundled = json.loads(models.GENERATIONS_FILE.read_text(encoding="utf-8"))
        state = models.state_generations_file()
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({**bundled, "updated": "2099-01-01"}))

        self.assertEqual(models.generations()["updated"], "2099-01-01")


class RegistryShapeTest(IsolatedStateTest):
    def setUp(self):
        super().setUp()
        self.registry = models.generations()

    def test_every_current_model_has_capabilities_and_an_effort_guide(self):
        for family in model_sync.FAMILIES:
            entry = self.registry["models"][models.family_current(family)]
            with self.subTest(family=family):
                self.assertEqual(set(entry["effort_guide"]),
                                 {"api_default", "routine", "agentic", "hardest", "stops_early_at"})
                self.assertGreaterEqual(entry["capabilities"]["context_window"], 1000000)
                self.assertEqual(entry["capabilities"]["max_output"], 128000)

    def test_lint_rules_and_registry_prompting_rules_agree_for_every_model(self):
        for model_id, entry in self.registry["models"].items():
            family = model_lint.family(model_id)
            for rule in model_lint.RULES:
                if "registry" not in rule:
                    continue
                with self.subTest(model=model_id, rule=rule["id"]):
                    self.assertEqual(family in rule["models"], rule["registry"] in entry["prompting"])

    def test_early_stop_levels_match_the_lint(self):
        for model_id, entry in self.registry["models"].items():
            with self.subTest(model=model_id):
                self.assertEqual(set(entry["effort_guide"]["stops_early_at"]),
                                 set(model_lint.EARLY_STOP_EFFORTS.get(model_lint.family(model_id), ())))

    def test_a_new_model_inherits_capabilities_and_the_deprecation_table_is_kept(self):
        updated, upgrades, _ = model_sync.plan_registry(self.registry, {NEXT_FABLE: {}}, today="2099-12-01")

        self.assertEqual(upgrades, {FABLE: NEXT_FABLE})
        self.assertEqual(updated["models"][NEXT_FABLE]["capabilities"], self.registry["models"][FABLE]["capabilities"])
        self.assertEqual(updated["models"][NEXT_FABLE]["effort_guide"], self.registry["models"][FABLE]["effort_guide"])
        self.assertEqual(updated["deprecations"], self.registry["deprecations"])
        self.assertEqual(models.status(FABLE, updated)["status"], "superseded")
        self.assertEqual(models.status(NEXT_FABLE, updated)["status"], "current")


class SyncUpgradeTargetTest(IsolatedStateTest):
    def setUp(self):
        super().setUp()
        self.registry = models.generations()

    def test_upgrade_target_for_superseded_retired_and_ambiguous_ids(self):
        cases = {
            "claude-sonnet-4-6": SONNET, "claude-3-5-sonnet-latest": SONNET,
            "claude-2.1": self.registry["deprecations"][-2]["replacement"], "claude-mythos-preview": None,
            FABLE: None, NEXT_FABLE: None, "opus": None, "gpt-5": None, None: None,
        }
        for model_id, target in cases.items():
            with self.subTest(model=model_id):
                self.assertEqual(model_sync.upgrade_target(model_id, self.registry), target)

    def test_a_retired_id_pinned_in_frontmatter_is_rewritten_and_the_body_is_untouched(self):
        text = "---\nname: a\nmodel: claude-2.1\n---\nUse claude-2.1 here.\n"

        rewritten, change = model_sync.rewrite_model_field(text, self.registry)

        replacement = models.status("claude-2.1", self.registry)["replacement"]
        self.assertEqual(change, ("claude-2.1", replacement))
        self.assertEqual(rewritten, f"---\nname: a\nmodel: {replacement}\n---\nUse claude-2.1 here.\n")


class ScoreTest(IsolatedStateTest):
    def write(self, name, text):
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_stale_pinned_id_no_longer_switches_the_model_rules_off(self):
        body = lint_cases.subagent(effort="high", extra=lint_cases.FINISHING)
        stale = self.write("stale.md", body.replace("effort: high", "model: claude-sonnet-4-6\neffort: high")
                           + '\nthinking={"type": "enabled", "budget_tokens": 8000}\n')

        report = score.evaluate(stale)

        self.assertEqual(report["lint_model"], SONNET)
        self.assertEqual([finding["id"] for finding in report["findings"]], ["M001", "M012"])
        self.assertEqual(report["penalty"], 11)

    def test_effort_override_asks_what_the_lint_says_at_another_level(self):
        agent = self.write("agent.md", lint_cases.subagent(effort="high").replace(
            "effort: high", f"model: {FABLE}\neffort: high"))

        pinned, lowered = score.evaluate(agent), score.evaluate(agent, None, "medium")

        self.assertEqual(pinned["findings"], [])
        self.assertEqual([finding["id"] for finding in lowered["findings"]], ["M011"])
        self.assertEqual(pinned["dimensions"], lowered["dimensions"])
        self.assertEqual(pinned["score"] - lowered["score"], 6)

    def test_every_bundled_template_keeps_its_score_at_low_medium_and_high_effort(self):
        for path in compat_matrix.subagent_files(ROOT):
            for model_id in (FABLE, OPUS, SONNET, HAIKU):
                for effort in compat_matrix.SWEEP_EFFORTS:
                    with self.subTest(template=path.name, model=model_id, effort=effort):
                        self.assertEqual(score.evaluate(path, model_id, effort)["findings"], [])


class ScaffoldSnippetTest(IsolatedStateTest):
    def test_keep_working_is_added_only_where_the_model_stops_early(self):
        cases = {("sonnet", "low"): True, ("sonnet", "medium"): False, ("opus", "low"): False,
                 ("haiku", "low"): True, ("fable", "medium"): True, ("fable", "high"): True}
        for (alias, effort), expected in cases.items():
            with self.subTest(model=alias, effort=effort):
                profile = models.profile(models.resolve(alias))

                names = scaffold.agent_snippets(profile, effort)

                self.assertEqual(bool(set(names) & set(scaffold.COMPLETION_SNIPPETS)), expected)
                self.assertEqual(len(names), len(set(names)), "no snippet is added twice")

    def test_agent_snippets_does_not_change_the_profile(self):
        profile = models.profile(models.resolve("sonnet"))
        before = list(profile["snippets"])

        scaffold.agent_snippets(profile, "low")

        self.assertEqual(profile["snippets"], before)


SKILL = """---
name: {name}
description: Does one job for the test. Use when the test asks for it.
allowed-tools:
{tools}
---

# /{name}

## When to use

Use this skill when the test suite needs an example skill with a real procedure and a clear trigger, so that the scorer has every section it looks for and gives a stable result.

## Procedure

{steps}

## Pitfalls

- Run `tq-forge score` on the file before you rely on it.

## Verification

- `tq-forge validate` passes.
{extra}
"""


def skill_text(name="example", tools=("Bash",), steps=3, extra=""):
    return SKILL.format(name=name, tools="\n".join(f"  - {tool}" for tool in tools), extra=extra,
                        steps="\n".join(f"{n}. Run `step-{n}` and check `out-{n}.txt`." for n in range(1, steps + 1)))


class CompatMatrixTest(IsolatedStateTest):
    def setUp(self):
        super().setUp()
        self.registry = models.generations()

    def recommend(self, **options):
        fields, body, _ = frontmatter.read(skill_text(**options))
        return compat_matrix.recommend("skill", fields, body, self.registry)[:2]

    def test_minimum_tier_and_effort_follow_what_a_skill_is_allowed_to_do(self):
        self.assertEqual(self.recommend(tools=("Bash", "Read")), ("haiku", "low"))
        self.assertEqual(self.recommend(tools=("Bash", "Edit")), ("sonnet", "medium"))
        self.assertEqual(self.recommend(tools=("Bash", "WebFetch", "AskUserQuestion")), ("sonnet", "medium"))
        self.assertEqual(self.recommend(tools=("Write", "WebSearch", "AskUserQuestion")), ("opus", "medium"))
        self.assertEqual(self.recommend(tools=("Bash", "Write", "AskUserQuestion"), steps=8), ("opus", "medium"))
        self.assertEqual(self.recommend(tools=("Bash", "Agent")), ("fable", "high"))

    def test_a_subagent_uses_the_tier_and_effort_it_pins(self):
        fields, body, _ = frontmatter.read((ROOT / "templates" / "agents" / "code-reviewer.md").read_text())

        self.assertEqual(compat_matrix.recommend("subagent", fields, body, self.registry)[:2], ("opus", "high"))

    def test_the_bundled_matrix_passes_and_matches_the_committed_document(self):
        report = compat_matrix.build(ROOT)

        self.assertEqual((len(report["skills"]), len(report["subagents"]), len(report["base_agents"])), (18, 9, 8))
        self.assertTrue(all(item["pass"] for item in report["skills"] + report["subagents"]))
        self.assertEqual((ROOT / compat_matrix.DOC).read_text(encoding="utf-8"), compat_matrix.render(report))

    def package_with(self, skill):
        package = self.tmp / "package"
        (package / "skills" / "example").mkdir(parents=True)
        (package / "skills" / "example" / "SKILL.md").write_text(skill, encoding="utf-8")
        return package

    def test_a_skill_that_breaks_the_rules_fails_under_the_models_that_reject_it(self):
        bad = skill_text(extra='\nShow your full chain of thought.\nthinking={"type": "disabled"}\n'
                               'thinking={"type": "enabled", "budget_tokens": 9}\ntemperature=0.3\n')

        item = compat_matrix.build(self.package_with(bad))["skills"][0]

        self.assertEqual(item["findings"]["fable"], ["M001", "M004", "M008", "M010"])
        self.assertEqual(item["findings"]["haiku"], ["M001", "M008"])
        self.assertLess(item["scores"]["fable"], compat_matrix.PASS_SCORE)
        self.assertGreaterEqual(item["scores"]["haiku"], compat_matrix.PASS_SCORE)
        self.assertFalse(item["pass"])

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = compat_matrix.main(["compat", *args])
        return code, out.getvalue(), err.getvalue()

    def test_check_fails_on_a_missing_or_edited_file_and_passes_after_write(self):
        target = self.tmp / "matrix.md"

        missing, _, missing_err = self.run_main("--check", "--out", str(target))
        written, _, _ = self.run_main("--write", "--out", str(target))
        current, current_out, _ = self.run_main("--check", "--out", str(target))
        target.write_text(target.read_text(encoding="utf-8") + "edited\n", encoding="utf-8")
        edited, _, _ = self.run_main("--check", "--out", str(target))

        self.assertEqual((missing, written, current, edited), (1, 0, 0, 1))
        self.assertIn("out of date", missing_err)
        self.assertIn("27 artifacts checked", current_out)

    def test_render_of_an_empty_package_does_not_crash(self):
        (self.tmp / "empty").mkdir()

        text = compat_matrix.render(compat_matrix.build(self.tmp / "empty"))

        self.assertIn("No bundled skills or subagent templates were found", text)

    def test_json_output_is_the_raw_report(self):
        code, out, _ = self.run_main("--json")

        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["skills"]), 18)


if __name__ == "__main__":
    unittest.main()
