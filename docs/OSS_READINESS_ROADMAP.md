# 15-Day Claude for Open Source Application Sprint

**Owner:** tq-forge maintainer  
**Sprint:** 17–31 November 2026 (15 calendar days)  
**Goal:** Prepare and submit the strongest truthful application to Anthropic's Claude for Open Source program within 10–15 days, if the application form is open. This is an application-readiness sprint, not a promise of approval.

> Important: Anthropic's listed thresholds measure existing ecosystem impact, including activity over the preceding 12 months. We cannot legitimately manufacture 500 dependent repositories, 100 dependent packages, 200,000 monthly downloads, 100 upstream merged PRs, 20 external contributors, or an OpenSSF criticality score of 0.4 in 15 days. Anthropic explicitly invites maintainers who do not quite meet a threshold to apply and explain the ecosystem value. We will use that route honestly if appropriate.

## 1. What we are applying for

Anthropic's official program currently advertises six months of Claude Ultra for selected open-source contributors. The published application asks for the GitHub repository, evidence of reach/impact, and how the subscription will be used.

Official page: https://claude.com/contact-sales/claude-for-oss

Published eligibility routes include:
- Maintainer/library author: 500+ dependent repositories, 100+ dependent packages, or 200,000+ combined monthly downloads across registries.
- Core contributor: listed committer/maintainer on a recognized foundation or language project.
- Active contributor: 100+ PRs merged into repositories the applicant does not own in the preceding 12 months.
- Community builder: 20+ unique external contributors with merged PRs to a maintained repository in the preceding 12 months.
- Critical infrastructure: maintained repository with OpenSSF criticality score 0.4+.

These are alternative routes, not a checklist to fake. Approval remains Anthropic's decision.

## 2. Current project positioning

tq-forge should be presented narrowly and accurately:

**A focused open-source toolkit for creating, validating, optimizing, and evaluating Claude Code skills and subagents.**

Existing strengths visible in the repository:
- Published npm CLI and reusable skill/agent templates.
- Deterministic static scoring and context optimization.
- Automated tests and GitHub Actions CI.
- MIT license, security policy, contribution guide, and code of conduct.
- Draft PRs for installer/security hardening (#4) and deterministic evaluation (#5).
- A documented evaluation foundation that explicitly does not claim to execute agents itself.

Current gaps:
- Early-stage project; public adoption and dependency thresholds have not yet been verified.
- No proof yet of 20 external merged contributors or 100 upstream merged PRs.
- Recorded-result evaluation is not a real execution adapter.
- Draft PRs are not merged product capabilities.
- The security hardening work still identifies follow-up requirements such as DNS pinning.

Do not call tq-forge critical infrastructure, claim unverified users/downloads, or present draft work as released.

## 3. The 15-day execution plan

### Day 1 — Verify eligibility and collect baseline

- Inspect Anthropic's live application page and terms.
- Record the maintainer's actual GitHub contribution history over the last 12 months.
- Record npm downloads using public registry data for the actual package and a clearly stated date range.
- Check whether GitHub shows dependent repositories/packages; capture only verifiable counts.
- Check the OpenSSF criticality score only if the project has a published score.
- Make an evidence table with links and timestamps.

**Deliverable:** one-page eligibility matrix showing each criterion as met, not met, or unverified.

### Days 2–3 — Repository credibility pass

- Review draft PR #4 for destructive install/uninstall behavior, safe backups, symlink handling, atomic writes, URL validation, redirect handling, and DNS-rebinding limitations.
- Review draft PR #5 for test coverage, result schema validation, and honest claims about recorded-run evaluation.
- Run the full GitHub Actions workflow on candidate branches and fix reproducible failures.
- Do not merge a security change merely to meet the deadline; resolve critical review findings first.
- Check that README claims match shipped behavior and clearly label benchmark fixtures as fixtures.

**Deliverable:** reviewed PRs, green CI where verified, and a short known-limitations section.

### Days 4–5 — Improve the project's proof

- Add a concise architecture diagram and a five-minute quick-start that a new contributor can reproduce.
- Add a real end-to-end example using a bounded Claude Code task only if it can be safely executed and verified.
- If a runtime execution adapter is not ready, document the evaluation harness accurately as a recorded-run evaluator; do not invent live benchmark outcomes.
- Publish one small, reproducible benchmark with environment, task definitions, commands, raw results, and limitations.
- Add an example showing how a user creates, scores, and validates a skill.

**Deliverable:** a reviewer can install tq-forge and independently reproduce one useful workflow.

### Days 6–7 — External validation

- Invite a small number of relevant developers to test the documented workflow.
- Ask for actionable feedback, not endorsements.
- Fix onboarding defects and documentation issues.
- Open clearly scoped issues for genuine missing capabilities.
- Welcome and review external PRs promptly; never ask people to submit artificial PRs for a count.

**Deliverable:** attributable feedback and, if it happens organically, genuine external contributions.

### Days 8–9 — Application evidence package

Prepare:
1. Repository URL and concise project summary.
2. Actual npm download stats and measurement window.
3. GitHub stars, forks, releases, issues and merged PR activity with date captured.
4. Verified downstream dependencies or users, if any.
5. Security policy, CI workflow, test evidence and known limitations.
6. One reproducible demonstration and benchmark report.
7. Maintainer's actual role and contribution history.
8. Specific plan for using Claude Ultra to improve tq-forge.

**Deliverable:** evidence notes with no unsupported claims.

### Days 10–11 — Draft the application

Answer the form's questions directly:
- **Project reach and impact:** explain the developer problem, target users, what tq-forge does, current verified adoption, and why this fills a gap in the Claude Code ecosystem.
- **How the subscription will be used:** describe a concrete six-month engineering plan: secure lifecycle, runtime execution adapter, reliable agent evaluations, docs, external contributor support, and maintenance.
- **Other info:** acknowledge the project's stage and explain why the work matters even if it does not yet meet a numeric threshold.

Do not say that six months of access is guaranteed. Do not use inflated claims like “industry standard,” “widely adopted,” or “production critical” without independent evidence.

### Days 12–13 — Independent review

- Ask one experienced open-source developer to challenge the application narrative and evidence.
- Verify every number and link again.
- Remove any statement that cannot be substantiated.
- Check that all draft PRs are described as drafts, not shipped features.
- Re-check Anthropic's live terms and form.

**Deliverable:** final, evidence-checked application.

### Days 14–15 — Submit and follow up

- Submit the official application if the form is open and the answers are truthful.
- Save the submission confirmation and a copy of the exact answers.
- Watch the GitHub repository and email for requests for clarification.
- Continue the engineering roadmap while the application is reviewed.

**Deliverable:** application submitted, or a written reason to wait if a critical fact remains unverified.

## 4. Application draft

### Project reach and impact

tq-forge is an MIT-licensed open-source toolkit focused on the lifecycle of Claude Code skills and subagents. It helps developers scaffold reusable agent instructions, apply deterministic static quality checks, optimize project context, and validate recorded agent-run outcomes. The repository includes a CLI, templates, automated tests, CI, contribution guidance, and a security policy.

The project is early-stage, and we are deliberately not overstating its adoption. We are collecting verifiable package and GitHub metrics and improving the reliability of installation, evaluation, and contributor workflows. The ecosystem gap we are addressing is the lack of a simple, reproducible workflow for creating and maintaining high-quality Claude Code skills and subagents, with explicit safety checks and measurable evaluation.

### How I will use Claude Ultra

I will use Claude Ultra as an engineering multiplier to maintain and improve tq-forge over the next six months. The priorities are to complete installer and network-security hardening, build a safely sandboxed Claude Code execution adapter, expand reproducible evaluation suites, improve documentation and onboarding, review community contributions, and maintain compatibility as Claude Code evolves. I will publish implementation changes, tests, benchmark methodology, limitations, and release notes so that the work is reviewable by the open-source community.

### Optional context

I am an early-stage independent maintainer building tq-forge as a focused tool for the Claude Code ecosystem. I understand that the project may not yet meet every numerical adoption threshold. I am applying under the program's invitation for maintainers whose projects provide ecosystem value even when they do not quite fit a listed threshold. All adoption and contribution metrics will be reported exactly as verifiable.

**Important:** use this draft only after replacing claims with the verified Day 1 evidence. Do not submit invented download counts, users, dependent repositories, contributors, benchmark results, or merged PRs.

## 5. Day 1 evidence checklist

- [ ] Confirm current program wording and application availability.
- [ ] Capture npm package downloads for a stated date range.
- [ ] Capture GitHub repository metrics and release history.
- [ ] Review actual maintainer PR history for the last 12 months.
- [ ] Check for verified dependents and external contributors.
- [ ] Check OpenSSF criticality only if a score exists.
- [ ] Mark every eligibility route met / not met / unverified.
- [ ] Save dated links/screenshots or API exports as evidence.

## 6. Official links

- Anthropic Claude for Open Source: https://claude.com/contact-sales/claude-for-oss
- tq-forge repository: https://github.com/tanishq286/tq-forge
- Existing hardening PR #4: https://github.com/tanishq286/tq-forge/pull/4
- Existing evaluation PR #5: https://github.com/tanishq286/tq-forge/pull/5

**Success for this sprint means a credible application submitted within 15 days—not guaranteed acceptance.**
