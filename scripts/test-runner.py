#!/usr/bin/env python3
"""Comprehensive test suite and quantitative skill scorer benchmarks for tq-forge.

Validates:
1. Repository manifests and license configurations
2. Frontmatter of all bundled skills:
   - name, description <= 1536 chars, allowed-tools, paths
3. Built-in subagent templates:
   - Claude Fable 5.2 orchestrator & advisor with effort: high and # Finishing work
   - Isolated subagents with isolation: worktree, permissionMode, memory: project
4. Deterministic scaffolding of skills, subagents, MCP servers, and hooks
5. Lifecycle hooks JSON stdin validation and exit-code enforcement (exit 0 allow, exit 2 block)
6. Quantitative quality scorer benchmarks (0-100 scale)
7. Model-compatibility lint: thinking config, sampling parameters, reasoning in
   the reply, completion instructions and stale model ids, per model
8. Registry capabilities, effort guide and deprecations, and their agreement with the lint
9. Cross-model compatibility matrix and docs/MODEL_COMPATIBILITY.md

Exit code 0 on all tests passing, non-zero on any failure.
"""

import contextlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import compat_matrix  # noqa: E402
import drytest  # noqa: E402
import frontmatter  # noqa: E402
import lint_cases  # noqa: E402
import model_lint  # noqa: E402
import model_sync  # noqa: E402
import models  # noqa: E402
import scaffold  # noqa: E402
import schema  # noqa: E402
import score  # noqa: E402

C_GREEN = "\033[32m"
C_RED = "\033[31m"
C_YELLOW = "\033[33m"
C_CYAN = "\033[36m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"


class TestFailure(Exception):
    pass


class TestSuite:
    def __init__(self):
        self.total_tests = 0
        self.passed_tests = 0
        self.benchmark_records = []

    def assert_true(self, condition, message):
        self.total_tests += 1
        if condition:
            self.passed_tests += 1
        else:
            raise TestFailure(message)

    def log_section(self, title):
        print(f"\n{C_BOLD}{C_CYAN}=== {title} ==={C_RESET}")

    def log_pass(self, name, detail=""):
        suffix = f" {C_YELLOW}({detail}){C_RESET}" if detail else ""
        print(f"  {C_GREEN}✓{C_RESET} {name}{suffix}")

    def log_benchmark(self, name, kind, model, dims, final_score):
        self.benchmark_records.append({
            "name": name,
            "kind": kind,
            "model": model,
            "dims": dims,
            "score": final_score,
        })


def test_manifests(suite: TestSuite):
    suite.log_section("1. Repository Manifests & Program Licensing")

    license_file = ROOT / "LICENSE"
    suite.assert_true(license_file.is_file(), "Root LICENSE file must exist")
    license_text = license_file.read_text(encoding="utf-8")
    suite.assert_true("MIT License" in license_text, "LICENSE must be standard MIT")
    suite.assert_true("Copyright (c) 2026 Tanishq Agarwal" in license_text,
                      "LICENSE copyright must match 'Copyright (c) 2026 Tanishq Agarwal'")
    suite.log_pass("LICENSE file", "MIT License, Copyright (c) 2026 Tanishq Agarwal")

    pkg_file = ROOT / "package.json"
    suite.assert_true(pkg_file.is_file(), "package.json must exist")
    pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
    suite.assert_true(pkg.get("license") == "MIT", "package.json license must be MIT")
    suite.assert_true(pkg.get("repository", {}).get("type") == "git", "package.json repo type must be git")
    suite.assert_true(pkg.get("repository", {}).get("url") == "https://github.com/tanishq286/tq-forge.git",
                      "package.json repo url must match exact https url")

    required_keywords = [
        "claude-code", "claude-fable-5-2", "anthropic", "ai-agents",
        "claude-skills", "subagents", "mcp", "cli"
    ]
    keywords = pkg.get("keywords", [])
    for kw in required_keywords:
        suite.assert_true(kw in keywords, f"package.json must contain keyword '{kw}'")
    suite.log_pass("package.json metadata", f"MIT license, git repo, keywords: {len(keywords)}")


def test_bundled_skills(suite: TestSuite):
    suite.log_section("2. Bundled Skills Frontmatter & Scorer Benchmarks")

    skills_dir = ROOT / "skills"
    skill_dirs = sorted([d for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").is_file()])
    suite.assert_true(len(skill_dirs) >= 13, f"Expected >= 13 skills, found {len(skill_dirs)}")

    for d in skill_dirs:
        skill_file = d / "SKILL.md"
        text = skill_file.read_text(encoding="utf-8")
        fields, body, has_fm = frontmatter.read(text)

        suite.assert_true(has_fm, f"{d.name}: missing YAML frontmatter fence")
        name = fields.get("name")
        suite.assert_true(name == d.name, f"{d.name}: frontmatter name '{name}' != dir name '{d.name}'")

        desc = fields.get("description", "")
        suite.assert_true(bool(desc), f"{d.name}: description is required")
        desc_len = len(str(desc))
        suite.assert_true(desc_len <= 1536,
                          f"{d.name}: description length ({desc_len}) exceeds Claude Code 1536 char limit")

        has_tools = "allowed-tools" in fields or "tools" in fields
        suite.assert_true(has_tools, f"{d.name}: allowed-tools must be present")

        if "paths" in fields:
            paths = fields["paths"]
            suite.assert_true(isinstance(paths, (list, str)), f"{d.name}: paths must be list or string")

        for key in fields:
            suite.assert_true(key in schema.SKILL_FIELDS, f"{d.name}: unexpected skill frontmatter field '{key}'")

        # Dry-test check
        checks = drytest.Checks()
        drytest.check_skill(skill_file, checks)
        pct = (checks.passed / checks.total * 100) if checks.total else 0
        suite.assert_true(pct >= 85, f"{d.name}: dry-test failed ({checks.passed}/{checks.total}): {checks.issues}")

        # Quantitative quality score benchmark (0-100)
        res = score.evaluate(skill_file)
        final_score = res["score"]
        avg = res["average"]
        suite.assert_true(final_score >= 70 and avg >= 7.0,
                          f"{d.name}: quality score {final_score}/100 ({avg}/10) is below promotion threshold 70/100")

        suite.log_benchmark(d.name, "skill", "claude-fable-5-2", res["dimensions"], final_score)
        suite.log_pass(f"skill: /{d.name}", f"score {final_score}/100, desc: {desc_len} chars, drytest {checks.passed}/{checks.total}")


def test_agent_templates(suite: TestSuite):
    suite.log_section("3. Claude Fable 5.2 Subagent Templates & Isolated Archetypes")

    templates_dir = ROOT / "templates" / "agents"
    templates = sorted([f for f in templates_dir.glob("*.md") if not f.name.startswith("_")])
    suite.assert_true(len(templates) >= 5, f"Expected >= 5 agent templates, found {len(templates)}")

    # 3a. Claude Fable 5.2 Orchestrator & Advisor verification
    fable_orchestrator = templates_dir / "fable-5-2-orchestrator.md"
    fable_advisor = templates_dir / "fable-5-2-advisor.md"
    suite.assert_true(fable_orchestrator.is_file(), "fable-5-2-orchestrator.md template must exist")
    suite.assert_true(fable_advisor.is_file(), "fable-5-2-advisor.md template must exist")

    for path in (fable_orchestrator, fable_advisor):
        text = path.read_text(encoding="utf-8")
        fields, body, _ = frontmatter.read(text)
        # The lead model comes from the registry, so this still holds after `sync-models` adds a release.
        suite.assert_true(fields.get("model") == models.default_model(),
                          f"{path.name}: model must be the registry's lead model '{models.default_model()}'")
        suite.assert_true(fields.get("effort") == "high",
                          f"{path.name}: effort must be 'high'")
        suite.assert_true("# Finishing work" in body,
                          f"{path.name}: must contain '# Finishing work' persistence block")
        suite.assert_true(len(str(fields.get("description", ""))) <= 1536,
                          f"{path.name}: description must be <= 1536 characters")

    # 3b. Isolated subagent templates verification
    isolated_templates = ["code-reviewer.md", "security-auditor.md", "test-runner.md"]
    for name in isolated_templates:
        p = templates_dir / name
        suite.assert_true(p.is_file(), f"{name} template must exist")
        fields, body, _ = frontmatter.read(p.read_text(encoding="utf-8"))
        suite.assert_true(fields.get("isolation") == "worktree",
                          f"{name}: must have 'isolation: worktree'")
        suite.assert_true(fields.get("permissionMode") in schema.PERMISSION_MODES,
                          f"{name}: invalid permissionMode")
        suite.assert_true(fields.get("memory") == "project",
                          f"{name}: must have 'memory: project'")
        suite.assert_true("tools" in fields or "allowed-tools" in fields,
                          f"{name}: must declare tools or allowed-tools")

    # Score and drytest all agent templates
    for p in templates:
        text = p.read_text(encoding="utf-8")
        fields, body, _ = frontmatter.read(text)
        desc = fields.get("description", "")
        suite.assert_true(len(desc) <= 1536, f"{p.name}: description exceeds 1536 chars")

        checks = drytest.Checks()
        drytest.check_subagent(p, checks)
        suite.assert_true(checks.passed == checks.total,
                          f"{p.name}: dry-test failed ({checks.passed}/{checks.total}): {checks.issues}")

        res = score.evaluate(p)
        suite.assert_true(res["score"] >= 80, f"{p.name}: score {res['score']}/100 is below 80")
        suite.log_benchmark(p.name, "subagent", fields.get("model", "n/a"), res["dimensions"], res["score"])
        suite.log_pass(f"subagent: {p.stem}", f"model: {fields.get('model')}, effort: {fields.get('effort')}, score: {res['score']}/100")


def test_dynamic_scaffolding(suite: TestSuite):
    suite.log_section("4. Dynamic Scaffolding & Isolated Subagent Generation")

    with tempfile.TemporaryDirectory() as temp_dir:
        out_dir = pathlib.Path(temp_dir)

        # 4a. Scaffold skill
        skill_res = scaffold.main(["scaffold", "skill", "build automated deployment pipeline",
                                   "--name", "deploy-pipeline", "--out", str(out_dir), "--json"])
        suite.assert_true(skill_res == 0, "scaffold skill command must return exit 0")
        generated_skill = out_dir / ".claude" / "skills" / "deploy-pipeline" / "SKILL.md"
        suite.assert_true(generated_skill.is_file(), "Scaffolded SKILL.md must exist")
        sf_fields, sf_body, _ = frontmatter.read(generated_skill.read_text(encoding="utf-8"))
        suite.assert_true(len(sf_fields.get("description", "")) <= 1536, "Generated skill desc <= 1536")
        suite.assert_true("allowed-tools" in sf_fields, "Generated skill has allowed-tools")
        suite.log_pass("scaffold skill", "deterministic skill with valid frontmatter")

        # 4b. Scaffold isolated subagent
        agent_res = scaffold.main([
            "scaffold", "agent", "perform security audit and diff review",
            "--name", "isolated-sec-auditor", "--isolated",
            "--allowed-tools", "Read, Grep, Glob, Bash",
            "--out", str(out_dir), "--json"
        ])
        suite.assert_true(agent_res == 0, "scaffold agent --isolated command must return exit 0")
        generated_agent = out_dir / ".claude" / "agents" / "isolated-sec-auditor.md"
        suite.assert_true(generated_agent.is_file(), "Scaffolded isolated subagent must exist")
        af_fields, af_body, _ = frontmatter.read(generated_agent.read_text(encoding="utf-8"))
        suite.assert_true(af_fields.get("isolation") == "worktree", "Isolated agent has isolation: worktree")
        suite.assert_true(af_fields.get("permissionMode") == "plan", "Isolated agent has permissionMode: plan")
        suite.assert_true(af_fields.get("memory") == "project", "Isolated agent has memory: project")
        suite.assert_true(af_fields.get("model") == models.default_model(), "Isolated agent has the lead model")
        suite.assert_true(af_fields.get("effort") == "high", "Isolated agent has effort: high")
        suite.assert_true("# Finishing work" in af_body, "Isolated agent prompt has # Finishing work")
        suite.log_pass("scaffold agent --isolated", "worktree isolation, permissionMode: plan, memory: project, effort: high")

        # 4c. Scaffold project MCP server
        mcp_res = scaffold.main([
            "scaffold", "mcp", "--name", "cloud-db",
            "--url", "https://api.example.com/mcp", "--token-env", "DB_API_TOKEN",
            "--scope", "project", "--out", str(out_dir), "--json"
        ])
        suite.assert_true(mcp_res == 0, "scaffold mcp project must return exit 0")
        mcp_file = out_dir / ".mcp.json"
        suite.assert_true(mcp_file.is_file(), ".mcp.json must exist")
        mcp_json = json.loads(mcp_file.read_text(encoding="utf-8"))
        suite.assert_true("cloud-db" in mcp_json.get("mcpServers", {}), "cloud-db server in .mcp.json")
        suite.log_pass("scaffold mcp --scope project", "valid .mcp.json scaffolding")

        # 4d. Scaffold subagent-scoped MCP server
        mcp_sub_res = scaffold.main([
            "scaffold", "mcp", "--name", "local-sqlite",
            "--command", "python3", "--arg=-m", "--arg=sqlite_mcp",
            "--scope", "subagent", "--out", str(out_dir), "--json"
        ])
        suite.assert_true(mcp_sub_res == 0, "scaffold mcp subagent must return exit 0")
        sub_mcp_file = out_dir / ".claude" / "agents" / "local-sqlite-agent.md"
        suite.assert_true(sub_mcp_file.is_file(), "Subagent-scoped MCP file must exist")
        sub_fields, _, _ = frontmatter.read(sub_mcp_file.read_text(encoding="utf-8"))
        suite.assert_true("mcpServers" in sub_fields, "mcpServers frontmatter in subagent")
        suite.log_pass("scaffold mcp --scope subagent", "valid subagent-scoped MCP server")

        # 4e. Scaffold lifecycle hooks
        hooks_res = scaffold.main([
            "scaffold", "hooks", "--events", "PreToolUse,PostToolUse,SessionStart,Stop",
            "--out", str(out_dir), "--json"
        ])
        suite.assert_true(hooks_res == 0, "scaffold hooks must return exit 0")
        settings_file = out_dir / ".claude" / "settings.json"
        suite.assert_true(settings_file.is_file(), ".claude/settings.json must exist")
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
        for ev in ("PreToolUse", "PostToolUse", "SessionStart", "Stop"):
            suite.assert_true(ev in settings.get("hooks", {}), f"settings.json missing hook event '{ev}'")
            hook_script = out_dir / ".claude" / "hooks" / scaffold.HOOK_SCRIPTS[ev]
            suite.assert_true(hook_script.is_file() and os.access(hook_script, os.X_OK),
                              f"Hook script {hook_script.name} must exist and be executable")
        suite.log_pass("scaffold hooks", "PreToolUse, PostToolUse, SessionStart, Stop scripts + settings.json")


def test_hook_lifecycle_enforcement(suite: TestSuite):
    suite.log_section("5. Hook Lifecycle Enforcement & JSON stdin Validation (exit 0 / exit 2)")

    hooks_dir = ROOT / "templates" / "hooks"

    def run_hook(script_name, stdin_json):
        script = hooks_dir / script_name
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)}
        proc = subprocess.run(
            ["bash", str(script)],
            input=stdin_json.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(ROOT),
            env=env,
            timeout=10,
        )
        return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")

    # PreToolUse: allow safe commands (exit 0), block destructive (exit 2)
    code, _, _ = run_hook("pre-tool-use.sh", json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "git status && npm run build"}
    }))
    suite.assert_true(code == 0, f"pre-tool-use.sh must allow benign command (got exit {code})")

    code, _, err = run_hook("pre-tool-use.sh", json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf /"}
    }))
    suite.assert_true(code == 2, f"pre-tool-use.sh must block rm -rf / with exit 2 (got exit {code})")
    suite.assert_true("Blocked by .claude/hooks/pre-tool-use.sh" in err, "pre-tool-use stderr reason")

    code, _, err = run_hook("pre-tool-use.sh", json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main --force"}
    }))
    suite.assert_true(code == 2, f"pre-tool-use.sh must block git push --force with exit 2 (got exit {code})")
    suite.log_pass("PreToolUse enforcement", "exit 0 for safe commands, exit 2 blocks destructive commands")

    # PostToolUse: syntax validation on edited files
    code, _, _ = run_hook("post-tool-use.sh", json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": str(ROOT / "package.json")}
    }))
    suite.assert_true(code == 0, f"post-tool-use.sh must exit 0 on valid package.json (got {code})")

    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        f.write("{ invalid json: broken")
        bad_file = f.name
    try:
        code, _, err = run_hook("post-tool-use.sh", json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": bad_file}
        }))
        suite.assert_true(code == 2, f"post-tool-use.sh must exit 2 on broken JSON (got {code})")
        suite.assert_true("Syntax check failed" in err, "post-tool-use error message")
    finally:
        os.remove(bad_file)
    suite.log_pass("PostToolUse enforcement", "exit 0 on clean file, exit 2 on syntax defect")

    # SessionStart: repository context injection
    code, out, _ = run_hook("session-start.sh", json.dumps({"session_id": "test-session-001"}))
    suite.assert_true(code == 0, f"session-start.sh must exit 0 (got {code})")
    suite.assert_true("Repository state" in out, "session-start output format")
    suite.log_pass("SessionStart enforcement", "exit 0, emits context without blocking")

    # Stop: loop protection & unfinished markers
    code, _, _ = run_hook("stop.sh", json.dumps({"stop_hook_active": True}))
    suite.assert_true(code == 0, f"stop.sh must exit 0 when stop_hook_active is true (got {code})")
    suite.log_pass("Stop hook enforcement", "exit 0 loop protection, exit 2 prevents premature stop")


def test_model_registry_and_lifecycle(suite: TestSuite):
    suite.log_section("6. Model Registry, sync-models, auto-improve Hook & postinstall")

    registry = json.loads((ROOT / "config" / "models.json").read_text(encoding="utf-8"))
    profiles = models.registry()["models"]
    for family in model_sync.FAMILIES:
        current = registry["families"][family]["current"]
        suite.assert_true(current in registry["models"], f"registry family '{family}' points at a listed model")
        suite.assert_true(model_sync.parse(current) == (family, tuple(registry["models"][current]["version"])),
                          f"{current}: id, family and version agree")
    for role, model_id in registry["pair"].items():
        suite.assert_true(model_id in profiles, f"registry {role} model '{model_id}' has a template profile")
    suite.assert_true(registry["pair"]["lead"] == models.default_model(), "registry lead is the default profile")
    _, upgrades, _ = model_sync.plan_registry(registry, {})
    suite.assert_true(upgrades == {}, "an offline sync changes nothing")
    _, upgrades, _ = model_sync.plan_registry(registry, {"claude-fable-9-9": {}})
    suite.assert_true(upgrades == {}, "a model id too far ahead is not trusted")
    suite.log_pass("config/models.json", f"{len(registry['models'])} models, pair {registry['pair']}")

    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    suite.assert_true(pkg["scripts"].get("postinstall") == "node bin/postinstall.js", "package.json runs postinstall")
    suite.assert_true("config/" in pkg["files"], "package.json ships config/")

    with tempfile.TemporaryDirectory(prefix="tq-forge-lifecycle-") as tmp:
        tmp = pathlib.Path(tmp)
        quiet = subprocess.run(["node", str(ROOT / "bin" / "postinstall.js")], capture_output=True, text=True,
                               env={**os.environ, "CI": "1"}, timeout=30)
        suite.assert_true(quiet.returncode == 0 and quiet.stdout == "", "postinstall is silent in CI")
        env = {key: value for key, value in os.environ.items() if key not in ("CI", "TQ_FORGE_SKIP_POSTINSTALL")}
        shown = subprocess.run(["node", str(ROOT / "bin" / "postinstall.js")], capture_output=True, text=True,
                               env={**env, "HOME": str(tmp), "USERPROFILE": str(tmp)}, timeout=30)
        suite.assert_true(shown.returncode == 0, "postinstall exits 0 without a ~/.claude folder")
        suite.assert_true("npx tq-forge auto-improve --root ~ --apply" in shown.stdout, "postinstall prints the command")
        suite.log_pass("postinstall", "exit 0, silent in CI, prints the one-line command")

        project, state = tmp / "project", tmp / "state"
        project.mkdir()
        sections = "\n".join(f"## Topic {n}\n\n" + "\n".join(f"Detail {n}.{m} of the topic, written out as a full sentence of prose." for m in range(40))
                             for n in range(4))
        (project / "CLAUDE.md").write_text(f"# Project\n\n## Rules\n\n- Use tabs.\n\n{sections}\n", encoding="utf-8")
        hook = ROOT / "templates" / "hooks" / "auto-improve-session.sh"

        def run_hook(**extra):
            env = {**os.environ, "TQ_FORGE_HOME": str(state), "TQ_FORGE_SCRIPTS": str(ROOT / "scripts"),
                   "TQ_FORGE_AUTO_ROOT": str(project), "TQ_FORGE_BLOAT_THRESHOLD": "200", **extra}
            return subprocess.run(["bash", str(hook)], input=b'{"session_id": "s"}', capture_output=True,
                                  env=env, timeout=30)

        off = run_hook(TQ_FORGE_AUTO_IMPROVE="0")
        suite.assert_true(off.returncode == 0 and not state.exists(), "hook does nothing when switched off")
        calm = run_hook(TQ_FORGE_BLOAT_THRESHOLD="999999")
        suite.assert_true(calm.returncode == 0 and (state / "auto-improve.stamp").is_file(),
                          "hook measures and stamps when under the threshold")
        suite.assert_true(not (state / "auto-improve.log").exists(), "hook starts no pass under the threshold")
        waiting = run_hook()
        suite.assert_true(not (state / "auto-improve.log").exists(), "hook waits one interval between measurements")
        fired = run_hook(TQ_FORGE_AUTO_INTERVAL="0")
        suite.assert_true(fired.returncode == 0, f"hook must exit 0 (got {fired.returncode})")
        for result in (off, calm, waiting, fired):
            suite.assert_true(result.stdout == b"", "hook prints nothing into the session context")
        deadline = time.time() + 20
        while time.time() < deadline and not (project / ".tq-forge-backup").is_dir():
            time.sleep(0.2)
        suite.assert_true((project / ".tq-forge-backup").is_dir(), "background auto-improve applied with a backup")
        log = (state / "auto-improve.log").read_text(encoding="utf-8")
        suite.assert_true("always-loaded context is" in log, "hook logs why it started a pass")
        suite.assert_true(len((project / "CLAUDE.md").read_text(encoding="utf-8").splitlines()) <= 35,
                          "CLAUDE.md is lean after the background pass")
        (state / "model-sync.json").write_text("{}", encoding="utf-8")
        os.utime(state / "model-sync.json", (time.time() + 5, time.time() + 5))
        run_hook(TQ_FORGE_BLOAT_THRESHOLD="999999")
        suite.assert_true("a new model was synced" in (state / "auto-improve.log").read_text(encoding="utf-8"),
                          "hook starts a pass after a model sync")
        time.sleep(1.5)  # let the detached pass finish before the folder is removed
    suite.log_pass("auto-improve-session hook", "silent, exit 0, threshold + interval + model-sync triggers")


def _fired(rule_id, text, model_id, **options):
    return [finding for finding in model_lint.lint(text, model_id, **options) if finding["id"] == rule_id]


def test_model_compat_lint(suite: TestSuite):
    suite.log_section("7. Model-Compatibility Lint (Fable 5.2 / Adaptive Thinking Anti-Patterns)")

    for rule_id, model_id, text, must_fire, why in lint_cases.PATTERN_CASES:
        target, _ = models.lint_target(model_id)
        fired = bool(_fired(rule_id, text, target))
        suite.assert_true(fired == must_fire,
                          f"{rule_id} on {model_id}: expected {'a finding' if must_fire else 'no finding'} for {why}")
    by_rule = {}
    for rule_id, *_ in lint_cases.PATTERN_CASES:
        by_rule[rule_id] = by_rule.get(rule_id, 0) + 1
    suite.log_pass("pattern rules", ", ".join(f"{rule} x{count}" for rule, count in sorted(by_rule.items())))

    for model_id, text, effort, must_fire, why in lint_cases.COMPLETION_CASES:
        fired = bool(_fired("M011", text, model_id, kind="subagent", effort=effort))
        suite.assert_true(fired == must_fire,
                          f"M011 on {model_id}: expected {'a finding' if must_fire else 'no finding'} for {why}")
    suite.assert_true(not _fired("M011", lint_cases.subagent(effort="medium"), lint_cases.FABLE, kind="skill"),
                      "M011 is about subagents; a skill is not checked")
    suite.log_pass("M011 missing-completion-instructions", f"{len(lint_cases.COMPLETION_CASES) + 1} cases")

    for text, penalty, why in lint_cases.STALE_ID_CASES:
        found = _fired("M012", text, lint_cases.FABLE)
        got = found[0]["penalty"] if found else None
        suite.assert_true(got == penalty, f"M012: expected penalty {penalty} for {why}, got {got}")
    suite.assert_true(bool(_fired("M012", "model: claude-3-5-sonnet-20241022", None)),
                      "M012 fires for a target the lint has no model rules for")
    suite.log_pass("M012 stale-model-id", f"{len(lint_cases.STALE_ID_CASES) + 1} cases, penalties 10 / 6 / 3")

    for description, body, must_fire, why in lint_cases.LANGUAGE_CASES:
        text = lint_cases.skill_file(description, body)
        suite.assert_true(bool(_fired("M013", text, lint_cases.FABLE, kind="skill")) == must_fire,
                          f"M013: expected {'a finding' if must_fire else 'no finding'} for {why}")
    suite.assert_true(not _fired("M013", lint_cases.skill_file(lint_cases.SILENT, "Respond in Chinese."),
                                 lint_cases.FABLE, kind="subagent"), "M013 is about skills; a subagent is not checked")
    suite.log_pass("M013 output-language-not-in-description", f"{len(lint_cases.LANGUAGE_CASES) + 1} cases")

    _assert_stale_pin_is_scored(suite)
    _assert_templates_carry_completion(suite)
    _assert_scaffold_adds_completion(suite)


def _assert_stale_pin_is_scored(suite: TestSuite):
    # A stale pinned id used to switch every model rule off. It must now cost points.
    with tempfile.TemporaryDirectory(prefix="tq-forge-lint-") as tmp:
        stale = pathlib.Path(tmp) / "stale.md"
        body = lint_cases.subagent(effort="high", extra=lint_cases.FINISHING)
        stale.write_text(body.replace("effort: high", "model: claude-sonnet-4-6\neffort: high")
                         + '\nRequest: thinking={"type": "enabled", "budget_tokens": 8000}\n', encoding="utf-8")
        report = score.evaluate(stale)
        ids = {finding["id"] for finding in report["findings"]}
        suite.assert_true(report["lint_model"] == lint_cases.SONNET,
                          "a stale pinned id is linted against its family's current model")
        suite.assert_true({"M001", "M012"} <= ids, f"stale pin + budget must both be reported, got {sorted(ids)}")
        clean = pathlib.Path(tmp) / "clean.md"
        clean.write_text(body.replace("effort: high", f"model: {lint_cases.SONNET}\neffort: high"), encoding="utf-8")
        suite.assert_true(score.evaluate(clean)["score"] > report["score"],
                          "the same file with a current id and no budget scores higher")
    suite.log_pass("stale pin is scored", "linted against the family's current model, M001 + M012 reported")


def _assert_templates_carry_completion(suite: TestSuite):
    # Every subagent template must carry completion instructions, because `--effort` can lower
    # any of them to a level at which the target model stops early.
    templates = compat_matrix.subagent_files(ROOT)
    for path in templates:
        text = path.read_text(encoding="utf-8")
        _, body, _ = frontmatter.read(text)
        suite.assert_true(model_lint.has_completion_instructions(body),
                          f"{path.name}: needs explicit completion instructions (a '# Finishing work' block)")
        for family, model_id in compat_matrix.column_models(models.generations()):
            for effort in compat_matrix.SWEEP_EFFORTS:
                suite.assert_true(not _fired("M011", text, model_id, kind="subagent", effort=effort),
                                  f"{path.name}: M011 fires on {family} at {effort}")
    suite.log_pass("subagent templates", f"{len(templates)} templates carry completion instructions at every effort")


def _assert_scaffold_adds_completion(suite: TestSuite):
    with tempfile.TemporaryDirectory(prefix="tq-forge-scaffold-") as tmp:
        for alias, effort, expected in (("fable", "medium", True), ("sonnet", "low", True),
                                        ("haiku", "low", True), ("opus", "low", False), ("sonnet", "medium", False)):
            name = f"agent-{alias}-{effort}"
            with contextlib.redirect_stdout(io.StringIO()):
                code = scaffold.main(["scaffold", "agent", "triage failing nightly builds", "--name", name,
                                      "--model", alias, "--effort", effort, "--out", tmp, "--json"])
            suite.assert_true(code == 0, f"scaffold agent --model {alias} --effort {effort} must succeed")
            text = (pathlib.Path(tmp) / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
            suite.assert_true(model_lint.has_completion_instructions(text) == expected,
                              f"scaffolded {alias} agent at {effort}: completion block expected={expected}")
            suite.assert_true(not _fired("M011", text, models.resolve(alias), kind="subagent"),
                              f"scaffolded {alias} agent at {effort} must not trip M011")
    suite.log_pass("scaffold agent", "adds the keep-working block where the model stops early")


def test_registry_capabilities(suite: TestSuite):
    suite.log_section("8. Registry Capabilities, Effort Guide & Deprecation Rules")

    registry = json.loads((ROOT / "config" / "models.json").read_text(encoding="utf-8"))
    suite.assert_true(registry["schema"] == 2, "config/models.json is schema 2")
    levels = models.effort_levels()
    # The four ids this release registers stay listed after a later sync; "current" is checked per family.
    for required in ("claude-fable-5-2", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
        suite.assert_true(required in registry["models"], f"{required} is registered")
    for family in model_sync.FAMILIES:
        current = registry["families"][family]["current"]
        suite.assert_true(models.status(current, registry)["status"] == "current", f"{current} is current")
    for model_id, entry in registry["models"].items():
        guide, caps = entry["effort_guide"], entry["capabilities"]
        for key in ("api_default", "routine", "agentic", "hardest"):
            suite.assert_true(guide[key] in levels, f"{model_id}: effort_guide.{key} is a known level")
        suite.assert_true(levels.index(guide["routine"]) <= levels.index(guide["agentic"]) <= levels.index(guide["hardest"]),
                          f"{model_id}: routine <= agentic <= hardest")
        suite.assert_true(entry["effort"] == guide["agentic"], f"{model_id}: starting effort is the agentic level")
        suite.assert_true(caps["effort_levels"] == levels, f"{model_id}: supports every effort level")
        suite.assert_true(caps["context_window"] >= 200000 and 0 < caps["max_output"] <= caps["context_window"],
                          f"{model_id}: context window and output cap are plausible")
        suite.assert_true(caps["sampling"] in ("rejected", "default-only"), f"{model_id}: sampling policy is known")
        suite.assert_true(caps["prefill"] is False, f"{model_id}: prefill is rejected")
        suite.assert_true(set(entry["prompting"]) <= set(registry["prompting_rules"]),
                          f"{model_id}: every prompting rule is described")
        # The registry and the lint must tell the same story about each model.
        family = model_lint.family(model_id)
        for rule in model_lint.RULES:
            if "registry" not in rule:
                continue
            suite.assert_true((family in rule["models"]) == (rule["registry"] in entry["prompting"]),
                              f"{model_id}: lint rule {rule['id']} and registry rule '{rule['registry']}' disagree")
        suite.assert_true(set(guide["stops_early_at"]) == set(model_lint.EARLY_STOP_EFFORTS.get(family, ())),
                          f"{model_id}: stops_early_at matches the lint's early-stop levels")
        suite.assert_true(("reasoning_extraction" in caps["refusal_categories"])
                          == ("no-reasoning-in-reply" in entry["prompting"]),
                          f"{model_id}: reasoning_extraction category and rule agree")
        suite.assert_true((caps["thinking"] == "always-on" or caps["thinking_off"] == "between_tools")
                          == ("thinking-always-on" in entry["prompting"]),
                          f"{model_id}: thinking capability and rule agree")
        suite.assert_true((not caps["forced_tool_choice"]) == ("no-forced-tool-choice" in entry["prompting"]),
                          f"{model_id}: forced tool_choice capability and rule agree")
    suite.log_pass("capabilities + effort guide", f"{len(registry['models'])} models agree with {len(model_lint.RULES)} lint rules")

    fable = registry["models"][lint_cases.FABLE]["effort_guide"]
    suite.assert_true((fable["routine"], fable["agentic"], fable["hardest"]) == ("medium", "high", "xhigh"),
                      "the current Fable's effort guide is medium / high / xhigh")
    suite.assert_true(fable["stops_early_at"] == ["low", "medium"], "the current Fable can stop early at low and medium")

    _assert_deprecation_rules(suite, registry)
    _assert_bundled_files_name_current_ids(suite)


def _assert_deprecation_rules(suite: TestSuite, registry):
    for model_id, expected in (("claude-3-5-sonnet-20241022", "retired"), ("claude-opus-4-1", "retired"),
                               ("claude-2.1", "retired"), ("claude-sonnet-4-5", "deprecated"),
                               ("claude-mythos-preview", "deprecated"), ("claude-opus-5", "superseded"),
                               ("claude-fable-5-1", "superseded"), ("claude-haiku-4-5", "superseded"),
                               (lint_cases.newer(lint_cases.FABLE), "unknown"), ("gpt-5", "unknown")):
        suite.assert_true(models.status(model_id, registry)["status"] == expected, f"{model_id} is {expected}")
    for rule in registry["deprecations"]:
        suite.assert_true(rule["status"] in ("retired", "deprecated"), "a deprecation rule is retired or deprecated")
        suite.assert_true(("id" in rule and rule.get("replacement") in registry["models"])
                          or (rule.get("family") in model_sync.FAMILIES and len(rule.get("version", [])) == 2),
                          f"deprecation rule {rule} names an id with a registered replacement, or a family version")
    suite.assert_true(model_sync.upgrade_target("claude-2.1", registry) == models.status("claude-2.1", registry)["replacement"],
                      "sync-models moves a retired id to its listed replacement")
    suite.assert_true(model_sync.upgrade_target("claude-sonnet-4-6", registry) == lint_cases.SONNET,
                      "sync-models moves a superseded id to the family's current model")
    suite.assert_true(model_sync.upgrade_target("claude-mythos-preview", registry) is None,
                      "sync-models leaves an id with two possible successors to a person")
    suite.assert_true(model_sync.upgrade_target(lint_cases.FABLE, registry) is None, "a current id is left alone")
    suite.log_pass("deprecation rules", f"{len(registry['deprecations'])} rules; retired, deprecated and superseded ids resolve")


def _assert_bundled_files_name_current_ids(suite: TestSuite):
    # No bundled file may pin or mention a model id that is behind the registry.
    scanned = 0
    for path in [*sorted((ROOT / "templates").rglob("*.md")), *sorted((ROOT / "templates").rglob("*.tmpl")),
                 *sorted((ROOT / "skills").rglob("SKILL.md"))]:
        scanned += 1
        suite.assert_true(not _fired("M012", path.read_text(encoding="utf-8"), None),
                          f"{path.relative_to(ROOT)}: names a stale model id")
    suite.log_pass("bundled files", f"{scanned} templates and skills name no stale model id")
    skills = sorted((ROOT / "skills").rglob("SKILL.md"))
    for path in skills:
        suite.assert_true(not _fired("M013", path.read_text(encoding="utf-8"), None, kind="skill"),
                          f"{path.relative_to(ROOT)}: body sets an output language its description does not name")
    suite.log_pass("bundled skills", f"{len(skills)} skills name every output language in their description")


def test_compat_matrix(suite: TestSuite):
    suite.log_section("9. Cross-Model Compatibility Matrix (docs/MODEL_COMPATIBILITY.md)")

    report = compat_matrix.build(ROOT)
    families = [model["family"] for model in report["models"]]
    suite.assert_true(families == list(compat_matrix.COLUMNS), "the matrix has one column per model family")
    suite.assert_true(len(report["skills"]) == 18, f"18 bundled skills, found {len(report['skills'])}")
    suite.assert_true(len(report["subagents"]) == 9, f"9 subagent templates, found {len(report['subagents'])}")
    suite.assert_true(len(report["base_agents"]) == 8, f"8 base agent templates, found {len(report['base_agents'])}")
    for item in report["skills"] + report["subagents"]:
        for family in families:
            suite.assert_true(item["scores"][family] >= compat_matrix.PASS_SCORE,
                              f"{item['name']}: {item['scores'][family]}/100 under {family} is below the gate")
        suite.assert_true(item["pass"] and item["dry_test"]["ok"], f"{item['name']}: must pass the matrix")
        suite.assert_true(item["min_tier"] in models.TIERS, f"{item['name']}: minimum tier is a known tier")
        suite.assert_true(item["effort"] in models.effort_levels(), f"{item['name']}: effort is a known level")
        suite.assert_true(not item["effort_sweep"], f"{item['name']}: effort sweep findings {item['effort_sweep']}")
    for item in report["subagents"]:
        suite.assert_true(item["min_tier"] == model_lint.family(item["pinned"]),
                          f"{item['name']}: minimum tier is the tier of the model it pins")
    for item in report["base_agents"]:
        suite.assert_true(not any(item["findings"].values()), f"base template {item['name']}: lint findings")
    lowest = min(min(item["scores"].values()) for item in report["skills"] + report["subagents"])
    suite.log_pass("matrix", f"27 artifacts x {len(families)} models, lowest score {lowest}/100")

    doc = ROOT / compat_matrix.DOC
    suite.assert_true(doc.is_file(), f"{compat_matrix.DOC} must exist")
    suite.assert_true(doc.read_text(encoding="utf-8") == compat_matrix.render(report),
                      f"{compat_matrix.DOC} is out of date; run `node bin/cli.js compat --write`")
    suite.assert_true(str(compat_matrix.DOC).replace("\\", "/") in (ROOT / "README.md").read_text(encoding="utf-8"),
                      "README.md links the compatibility matrix")
    suite.log_pass(str(compat_matrix.DOC), "matches the generator and is linked from README.md")


def print_summary_table(suite: TestSuite):
    print(f"\n{C_BOLD}{C_CYAN}=== Quantitative Quality Scorer Benchmarks (0–100 Scale) ==={C_RESET}")
    header = f"{'Artifact':<28} {'Kind':<10} {'Target Model':<18} {'Score':>6}  {'Dimensions':<30}"
    print(C_BOLD + header + C_RESET)
    print("-" * len(header))

    for rec in suite.benchmark_records:
        dims_str = " ".join(f"{k[:3]}:{v}" for k, v in rec["dims"].items() if not k.startswith("_"))
        color = C_GREEN if rec["score"] >= 80 else (C_YELLOW if rec["score"] >= 70 else C_RED)
        print(f"{rec['name']:<28} {rec['kind']:<10} {rec['model']:<18} {color}{rec['score']:>5}/100{C_RESET}  {dims_str:<30}")


def main():
    suite = TestSuite()
    print(f"{C_BOLD}🚀 Starting tq-forge Automated Test Suite & Scorer Benchmarks...{C_RESET}")

    try:
        test_manifests(suite)
        test_bundled_skills(suite)
        test_agent_templates(suite)
        test_dynamic_scaffolding(suite)
        test_hook_lifecycle_enforcement(suite)
        test_model_registry_and_lifecycle(suite)
        test_model_compat_lint(suite)
        test_registry_capabilities(suite)
        test_compat_matrix(suite)
    except TestFailure as e:
        print(f"\n{C_RED}❌ Test assertion failed: {e}{C_RESET}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n{C_RED}❌ Unexpected error during test run: {e}{C_RESET}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    print_summary_table(suite)

    print(f"\n{C_GREEN}{C_BOLD}🎉 ALL CHECKS PASSED: {suite.passed_tests}/{suite.total_tests} assertions passed cleanly.{C_RESET}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
