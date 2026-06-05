---
name: github-pr-digest
description: |
  Summarize your open GitHub pull requests into a single morning digest —
  grouped by repo, flagged by staleness and review state. Use when asked for
  "/github-pr-digest", "my PR digest", "what PRs are waiting on me", or "open
  PR summary".
allowed-tools:
  - Bash
  - Read
---

# /github-pr-digest — morning open-PR digest

## When to use

You start the day wanting one screen that tells you which of your open pull
requests are waiting on you, which are waiting on others, and which have gone
stale. This skill pulls open PRs via the `gh` CLI and renders a grouped digest.

## Procedure

1. **Check the gh CLI is authed.**
   ```bash
   gh auth status >/dev/null 2>&1 || { echo "Run: gh auth login"; exit 1; }
   ```

2. **Fetch open PRs authored by you across repos.**
   ```bash
   gh search prs --author "@me" --state open --json repository,title,url,updatedAt,reviewDecision,isDraft --limit 100 > /tmp/pr-digest.json
   ```

3. **Group + flag with a staleness threshold (7 days).**
   ```bash
   python3 - <<'PY'
   import json, datetime
   rows = json.load(open("/tmp/pr-digest.json"))
   now = datetime.datetime.now(datetime.timezone.utc)
   by_repo = {}
   for r in rows:
       repo = r["repository"]["nameWithOwner"]
       upd = datetime.datetime.fromisoformat(r["updatedAt"].replace("Z","+00:00"))
       stale = (now - upd).days >= 7
       flag = "DRAFT" if r["isDraft"] else (r.get("reviewDecision") or "PENDING")
       by_repo.setdefault(repo, []).append((flag, "🕒" if stale else "  ", r["title"], r["url"]))
   for repo in sorted(by_repo):
       print(f"\n## {repo}")
       for flag, stale, title, url in by_repo[repo]:
           print(f"  {stale} [{flag:<16}] {title}\n        {url}")
   print(f"\n{sum(len(v) for v in by_repo.values())} open PRs across {len(by_repo)} repos")
   PY
   ```

4. **Surface the action list.** Call out `APPROVED` PRs (ready to merge) and
   `CHANGES_REQUESTED` PRs (waiting on you) at the top of your summary.

## Pitfalls

- `gh search prs` paginates at 100; if you have more open PRs, raise `--limit`
  or filter by `--owner`.
- `reviewDecision` is `null` until at least one review exists — show it as
  `PENDING`, not an error.
- Times are UTC; the 7-day staleness flag is timezone-agnostic by design.

## Verification

- `/tmp/pr-digest.json` parses as a JSON array.
- The printed PR count matches `gh search prs --author @me --state open | wc -l`.
- Draft PRs show `DRAFT`; approved ones show `APPROVED`.

## Tags

`github` `pull-requests` `digest` `daily`
