# Six-Month Open-Source Readiness Plan

**Owner:** tq-forge maintainers  
**Planning window:** 17 November 2026 – 17 May 2027  
**Primary objective:** Build a demonstrably useful, secure, adopted open-source developer tool and submit an honest application to Anthropic's Claude for Open Source program when the evidence supports it.

> This is an execution plan, not a promise of acceptance. Program eligibility and approval are decided by Anthropic. Never fabricate downloads, dependent repositories, contributors, merged pull requests, security scores, user testimonials, or benchmark results.

## 1. Program criteria and reality check

Anthropic's published Claude for Open Source criteria include one or more of the following:

- Maintainer/library author: at least 500 dependent repositories, 100 dependent packages, or 200,000 combined monthly downloads across package registries.
- Core contributor: listed committer or maintainer on a recognized foundation or language project.
- Active contributor: at least 100 pull requests merged into repositories the applicant does not own during the preceding 12 months.
- Community builder: at least 20 unique external contributors with merged pull requests to one of the applicant's repositories during the preceding 12 months.
- Critical infrastructure: a maintained repository with an OpenSSF criticality score of at least 0.4.

Anthropic says maintainers who do not quite meet a listed threshold may still apply and explain the ecosystem value of their project. Meeting a threshold is not a guarantee of approval.

**Current assessment:** tq-forge is an early-stage, owner-led project. The repository has useful foundations (CLI, tests, CI, security policy, contribution guide, and draft hardening/evaluation work), but the project must first prove real execution quality, external adoption, and community participation. Do not describe it as critical infrastructure or claim broad adoption without evidence.

## 2. Product strategy: narrow the promise, prove the outcome

For this six-month period, focus tq-forge on one credible promise:

**A safe, reproducible toolkit for creating, validating, evaluating, and maintaining Claude Code skills and subagents.**

Do not claim universal autonomous-agent orchestration until multiple runtime adapters actually execute tasks and pass the same evaluation contract.

### Product pillars

1. **Safe lifecycle:** install, update, backup, restore, uninstall, and network research must be safe by default.
2. **Execution-based evaluation:** run real agent tasks, capture tool traces and outputs, and report reproducible outcomes.
3. **Reproducibility:** versioned suites, fixed fixtures, repeated runs, documented environments, and honest limitations.
4. **Contributor usability:** simple setup, good first issues, clear contribution rules, and responsive reviews.
5. **Evidence-led adoption:** publish actual registry downloads, dependent packages/repos, releases, external PRs, and user-reported use cases.

## 3. Six-month execution schedule

### Month 1 — Stabilize the foundation (17 Nov–16 Dec 2026)

- Review and safely land the existing installer/security hardening work (draft PR #4) only after resolving review findings, including DNS-rebinding protection and cross-platform behavior.
- Rebase and review the deterministic evaluation work (draft PR #5) after its dependency is integrated; preserve its explicit limitation that recorded-result evaluation does not itself execute agents.
- Add ownership manifests and robust backup/restore tests; verify that force install and uninstall never silently destroy user customizations.
- Test supported environments in CI: Linux and macOS first; explicitly document Windows/WSL support or non-support.
- Publish a threat model and a support matrix.
- Establish a baseline metrics snapshot from public GitHub and npm data.

**Exit gate:** clean CI on supported platforms, reviewed security changes, reproducible package install/uninstall tests, no known destructive installer path.

### Month 2 — Build the real execution adapter (17 Dec 2026–16 Jan 2027)

- Implement a Claude Code runtime adapter that executes a bounded task in a disposable workspace.
- Capture task input, model/runtime version, tool calls, final output, exit status, elapsed time, token/cost metadata when available, and failure reason.
- Use explicit permissions, allowlisted tools, timeouts, output limits, and no host secrets in the sandbox.
- Define a stable, versioned run-result schema; reject incomplete or malformed records.
- Keep evaluation separate from generation so the evaluator cannot reward its own output.

**Exit gate:** end-to-end execution works on at least 10 representative tasks in a disposable environment; all results are machine-readable and replayable.

### Month 3 — Prove quality with benchmarks (17 Jan–16 Feb 2027)

- Grow a task suite to at least 30 representative tasks across skill creation, tool selection, safe file edits, error recovery, and instruction following.
- Include positive, negative, adversarial, and regression cases.
- Run each task at least 5 times where stochasticity matters; publish pass rate, variance, latency, cost where available, and failure categories.
- Add human review for semantic correctness; phrase matching and static structure scores must never be presented as proof of task success.
- Compare against a clearly documented baseline (manual workflow or another reproducible method); do not cherry-pick cases.
- Publish raw, privacy-safe benchmark artifacts and exact reproduction commands.

**Exit gate:** public benchmark report with methodology, failures, limitations, and repeatable commands—not just a headline score.

### Month 4 — External contributors and adoption (17 Feb–16 Mar 2027)

- Create a small, well-scoped issue backlog with labels: good first issue, help wanted, security, evaluation, docs.
- Add a contributor quick-start, architecture map, development setup, test instructions, release process, and maintainer response expectations.
- Run a public contributor onboarding session or asynchronous issue sprint.
- Ask users to test real workflows; collect consent-based, attributable case studies. Do not invent testimonials.
- Make at least 5 small, independently reviewable contributions easy for first-time contributors.
- Respond to issues and PRs consistently; close stale items with explanations.

**Exit gate:** first external merged PRs, documented real user feedback, and a transparent public activity record. The 20-external-contributor criterion is a stretch target, not something to manufacture.

### Month 5 — Ecosystem distribution (17 Mar–16 Apr 2027)

- Publish a stable release with signed/tagged release notes and migration guidance.
- Improve package discoverability, examples, integrations, and installation docs.
- Seek integrations with existing Claude Code skill collections, developer tooling, and agent evaluation projects through genuine upstream PRs.
- Contribute useful fixes to projects tq-forge depends on or integrates with; do not submit low-value PRs to inflate counts.
- Track npm downloads, dependent packages/repositories where available, unique external contributors, merged external PRs, release adoption, and active issue/PR health.
- Review OpenSSF Scorecard findings and fix actionable items; report the actual score and date, never imply that a badge alone proves security.

**Exit gate:** stable release, independently reproducible usage examples, measurable adoption trend, and at least one meaningful external integration or documented downstream use.

### Month 6 — Evidence package and application (17 Apr–17 May 2027)

- Recalculate the published program criteria using current, verifiable evidence.
- Prepare a concise application describing the project's purpose, users, ecosystem gap, maintainer role, security posture, adoption, contributor activity, and how Claude Max 20x will be used to maintain the project.
- Link only public evidence: repository, releases, benchmark report, package registry stats, dependent repos/packages, merged external PRs, contributor list, and OpenSSF score where relevant.
- If a published threshold is met, identify it explicitly with dated evidence.
- If no threshold is met, use the program's invitation to explain quietly important ecosystem value and apply honestly if the form remains open.
- If rejected or not yet eligible, publish the next evidence-based plan and continue building; do not game the metrics.

**Exit gate:** a complete, truthful application submitted only when the evidence is ready, or a documented reason to wait.

## 4. Monthly metrics dashboard

Record a dated snapshot at the end of every month. Use public, independently verifiable sources wherever possible.

| Metric | Baseline (record in Month 1) | Six-month direction |
|---|---:|---|
| Monthly npm downloads | TBD — measure, do not estimate | Sustained organic growth |
| Dependent repositories | TBD — verify from registry/GitHub | Toward 500 if genuine adoption supports it |
| Dependent packages | TBD — verify | Toward 100 if genuine adoption supports it |
| Unique external contributors with merged PRs (rolling 12 months) | TBD | Grow toward 20 |
| PRs merged into repos not owned by maintainer (rolling 12 months) | TBD | Meaningful upstream work; 100 is a separate high bar |
| OpenSSF criticality score | TBD | Improve only through real ecosystem adoption/importance |
| Execution benchmark tasks | 0 until adapter exists | 30+ |
| Repeated runs per stochastic task | 0 until adapter exists | 5+ |
| Supported platform CI | Record actual matrix | All declared platforms green |
| Security findings | Record reviewed findings | No unresolved critical/high findings |

Never combine downloads across registries without explaining the calculation and deduplicating where possible. Never count bot accounts as unique human contributors. Never count draft, unmerged, self-authored, or duplicate PRs as merged external contributions.

## 5. Application narrative: evidence, not hype

The application should answer:

- What developer problem does tq-forge solve that existing tools do not solve well?
- Who uses it today, and what concrete work does it help them complete?
- What evidence demonstrates dependency or ecosystem impact?
- What security and privacy controls protect users?
- What did external contributors build or improve?
- What will the maintainer accomplish with six months of Claude Max 20x that could not be done as effectively otherwise?

A credible project description should say that tq-forge is a focused Claude Code skill/subagent lifecycle and evaluation toolkit. Avoid calling it a universal agent platform, production-critical infrastructure, or autonomous execution engine until those claims are backed by shipped code and independent evidence.

## 6. Risks and guardrails

- **Threshold risk:** a young project may not reach any numerical threshold in six months. Apply honestly if the program permits, but do not budget around acceptance.
- **Benchmark gaming:** keep the suite versioned, include failures, and use human review for semantic outcomes.
- **Security overclaim:** pattern-based sanitization is not a complete prompt-injection defense; network allowlisting must bind validation to the actual connection.
- **Contributor-count gaming:** prioritize useful upstream work and genuine external contributions, not artificial PRs.
- **Scope creep:** defer broad multi-provider orchestration until the Claude Code adapter is reliable.
- **Cost risk:** prefer local deterministic tests and small bounded evaluation runs; document any paid model/API usage before running it.

## 7. Immediate next actions

1. Review and resolve draft PR #4's remaining security issues.
2. Rebase and review draft PR #5 after #4 is integrated.
3. Measure current npm/GitHub adoption and save the baseline with the measurement date.
4. Implement the Claude Code execution adapter and result schema.
5. Publish the first real execution benchmark with failures included.

## 8. Official program reference

Anthropic's Claude for Open Source program page: https://claude.com/contact-sales/claude-for-oss

Program criteria and terms may change. Re-check the official page immediately before applying.
