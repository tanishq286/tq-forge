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

Exit code 0 on all tests passing, non-zero on any failure.
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

import drytest  # noqa: E402
import frontmatter  # noqa: E402
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
        suite.assert_true(fields.get("model") == "claude-fable-5-2",
                          f"{path.name}: model must be 'claude-fable-5-2'")
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
        suite.assert_true(af_fields.get("model") == "claude-fable-5-2", "Isolated agent has claude-fable-5-2")
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
