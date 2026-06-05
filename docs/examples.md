# Examples

A few intents and what tq-forge does with them.

## 1. A morning digest skill

```
/tq-forge a skill that summarizes my open GitHub PRs every morning
```

- **Classified:** skill (procedural — "a skill that…").
- **Slug:** `github-pr-digest`.
- **Output:** `~/.tq-forge/sandbox/forged-skills/github-pr-digest/SKILL.md` with a
  numbered procedure (`gh pr list ...`), pitfalls, and verification.
- **Promote:** `/tq-forge-promote github-pr-digest` → live as `/github-pr-digest`.

## 2. A research agent

```
/tq-forge-agent a researcher that vets vendors before we sign contracts
```

- **Kind prompt:** defaults to `researcher`.
- **Slug:** `vendor-vetting`.
- **Output:** a 5-file agent under `~/.tq-forge/sandbox/forged-agents/vendor-vetting/`
  — `system-prompt.md` carries the researcher persona, the rigid RESEARCH BRIEF
  output format, a NEVER block, and your `~/.tq-forge/context.md` injected where
  `{{CONTEXT}}` was.
- **Promote:** lands under `~/.claude/skills/agents/vendor-vetting/`.

## 3. Fixing a weak skill

```
/tq-forge a skill to do the thing with stuff
   🔴 skill vague-skill: 4.5/10 (needs_work)
      specificity 4  ← weak

/tq-forge-improve vague-skill
   🔄 vague-skill — verify result  ✅ PASSED
      new avg: 7.8/10   Δ = +3.3
```

The improver rewrites **only** the weak section (here, replacing vague language
with concrete paths/tools) and leaves the rest untouched.

## 4. Finding gaps

```
/tq-forge-scan
   🔴 Gap candidates:
      1. weekly-metrics-digest
      2. invoice-reconcile
```

Then forge the ones worth automating.
