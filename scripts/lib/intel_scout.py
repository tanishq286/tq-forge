"""Multi-source research collector for `tq-forge learn` and `tq-forge scout` (Python stdlib only).

Given a URL or a topic it gathers what public sources say and returns plain
findings: {"source", "title", "url", "text", "points"}.

  youtube  a video's title, chapters and captions. Uses `yt-dlp` when it is
           installed (`--write-auto-sub --skip-download`), otherwise the watch
           page and its timedtext track. A topic search needs yt-dlp.
  github   repository search, or one repository: description, stars, CLAUDE.md,
           the names under .claude/skills and .claude/agents, latest release.
           Uses `gh api` when available, otherwise the public REST API.
  social   Reddit (r/ClaudeAI, r/ClaudeCode), Hacker News (Algolia), DEV.to.
  web      one page, reduced to its text.

Every request is a GET that carries the topic and nothing about the machine.
A source that fails is recorded under "errors" and the rest carry on. What
comes back is untrusted text: self_evolve.sanitize runs before anything is
written to a skill.
"""

import base64
import html
import html.parser
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

SOURCES = ("youtube", "github", "social", "web")
TIMEOUT_SECONDS = 15
MAX_BYTES = 2_000_000
EXCERPT_CHARS = 6000
SUBREDDITS = ("ClaudeAI", "ClaudeCode")
DETAILED_REPOS = 3
VIDEO_ID = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/)([\w-]{11})")
REPO_URL = re.compile(r"github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?(?:[/?#]|$)")
CHAPTER = re.compile(r"^\(?((?:\d{1,2}:)?\d{1,2}:\d{2})\)?\s*[-–—:]?\s*(.{3,80})$")


def http_get(url, headers=None):
    if urllib.parse.urlparse(str(url)).scheme not in ("http", "https"):
        raise ValueError(f"only http and https URLs are fetched, not {str(url)[:60]!r}")  # never file:// or ftp://
    request = urllib.request.Request(url, headers={"User-Agent": "tq-forge-scout", **(headers or {})})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 (public https GET)
        return response.read(MAX_BYTES).decode("utf-8", errors="replace")


def finding(source, title, url, text="", points=0, **extra):
    return {"source": source, "title": " ".join(str(title or "").split())[:200], "url": str(url or ""),
            "text": str(text or "")[:EXCERPT_CHARS], "points": int(points or 0), **extra}


# ---------------------------------------------------------------- youtube

def video_id(url):
    match = VIDEO_ID.search(str(url))
    return match.group(1) if match else None


def parse_player_response(page):
    """The `ytInitialPlayerResponse` object embedded in a watch page, or {}."""
    start = page.find("ytInitialPlayerResponse")
    start = page.find("{", start) if start >= 0 else -1
    if start < 0:
        return {}
    try:
        return json.JSONDecoder().raw_decode(page[start:])[0]
    except ValueError:
        return {}


def caption_url(player):
    tracks = (((player.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}).get("captionTracks")) or []
    english = [track for track in tracks if str(track.get("languageCode", "")).startswith("en")]
    chosen = (english or tracks or [{}])[0]
    return chosen.get("baseUrl")


def parse_json3(text):
    """Caption text from YouTube's json3 format."""
    try:
        events = json.loads(text).get("events", [])
    except (ValueError, AttributeError):
        return ""
    parts = ["".join(seg.get("utf8", "") for seg in event.get("segs", [])) for event in events if isinstance(event, dict)]
    return " ".join(" ".join(parts).split())


def parse_timedtext_xml(text):
    """Caption text from the older XML timedtext format."""
    return " ".join(html.unescape(part) for part in re.findall(r"<text[^>]*>(.*?)</text>", text, re.S)).strip()


def chapters(description):
    found = []
    for line in str(description or "").splitlines():
        match = CHAPTER.match(line.strip())
        if match:
            found.append(f"{match.group(1)} {match.group(2).strip()}")
    return found


def _youtube_with_ytdlp(url, run):
    with tempfile.TemporaryDirectory(prefix="tq-forge-yt-") as scratch:
        run(["yt-dlp", "--skip-download", "--write-auto-sub", "--write-sub", "--sub-format", "json3",
             "--sub-langs", "en.*", "--write-info-json", "-o", f"{scratch}/video", url],
            capture_output=True, timeout=120, check=False)
        folder = pathlib.Path(scratch)
        info = json.loads((folder / "video.info.json").read_text(encoding="utf-8"))
        captions = sorted(folder.glob("video.*.json3"))
        transcript = parse_json3(captions[0].read_text(encoding="utf-8")) if captions else ""
    listed = [f"{int(c.get('start_time', 0)) // 60}:{int(c.get('start_time', 0)) % 60:02d} {c.get('title', '')}"
              for c in info.get("chapters") or []] or chapters(info.get("description"))
    return finding("youtube", info.get("title"), url, transcript or info.get("description"),
                   info.get("view_count"), author=info.get("uploader", ""), chapters=listed)


def youtube(url, get=http_get, run=subprocess.run, which=shutil.which):
    if which("yt-dlp"):
        return _youtube_with_ytdlp(url, run)
    player = parse_player_response(get(f"https://www.youtube.com/watch?v={video_id(url)}"))
    details = player.get("videoDetails") or {}
    track = caption_url(player)
    transcript = ""
    if track:
        raw = get(track + ("&" if "?" in track else "?") + "fmt=json3")
        transcript = parse_json3(raw) or parse_timedtext_xml(raw)
    description = details.get("shortDescription", "")
    return finding("youtube", details.get("title"), url, transcript or description, details.get("viewCount"),
                   author=details.get("author", ""), chapters=chapters(description))


def youtube_search(topic, limit, run=subprocess.run, which=shutil.which):
    if not which("yt-dlp"):
        raise RuntimeError("a YouTube topic search needs yt-dlp; pass a video URL, or install yt-dlp")
    done = run(["yt-dlp", f"ytsearch{limit}:{topic}", "--flat-playlist", "--dump-json"],
               capture_output=True, text=True, timeout=120, check=False)
    found = []
    for line in done.stdout.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        found.append(finding("youtube", item.get("title"), item.get("url") or
                             f"https://www.youtube.com/watch?v={item.get('id')}", item.get("description"),
                             item.get("view_count")))
    return found


# ----------------------------------------------------------------- github

def gh_json(path, get=http_get, run=subprocess.run, which=shutil.which):
    """GET one GitHub API path. `gh api` uses the user's login; the fallback is the public API."""
    if which("gh"):
        done = run(["gh", "api", "--method", "GET", path], capture_output=True, text=True, timeout=60, check=False)
        if done.returncode == 0:
            return json.loads(done.stdout)
    return json.loads(get(f"https://api.github.com/{path}", {"Accept": "application/vnd.github+json"}))


def parse_repos(payload, limit):
    items = payload.get("items") if isinstance(payload, dict) else None
    return [{"full_name": item.get("full_name", ""), "description": item.get("description") or "",
             "stars": item.get("stargazers_count", 0), "url": item.get("html_url", "")}
            for item in (items or [])[:limit] if isinstance(item, dict)]


def _repo_detail(name, fetch):
    """What a repository's Claude setup looks like: CLAUDE.md, skill and agent names, latest release."""
    parts = []
    try:
        content = fetch(f"repos/{name}/contents/CLAUDE.md")
        parts.append("CLAUDE.md:\n" + base64.b64decode(content.get("content", "")).decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 (most repositories have no CLAUDE.md)
        pass
    for folder in (".claude/skills", ".claude/agents"):
        try:
            names = [entry.get("name", "") for entry in fetch(f"repos/{name}/contents/{folder}")]
            parts.append(f"{folder}: {', '.join(names)}")
        except Exception:  # noqa: BLE001
            pass
    try:
        parts.append(f"latest release: {fetch(f'repos/{name}/releases/latest').get('tag_name', '')}")
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts)


def github(target, limit, fetch=gh_json):
    match = REPO_URL.search(target)
    if match or re.fullmatch(r"[\w.-]+/[\w.-]+", target):
        name = f"{match.group(1)}/{match.group(2)}" if match else target
        repo = fetch(f"repos/{name}")
        repos = [{"full_name": name, "description": repo.get("description") or "",
                  "stars": repo.get("stargazers_count", 0), "url": repo.get("html_url", f"https://github.com/{name}")}]
    else:
        query = urllib.parse.quote(target)
        repos = parse_repos(fetch(f"search/repositories?q={query}&sort=stars&order=desc&per_page={limit}"), limit)
    found = []
    for index, repo in enumerate(repos):
        detail = _repo_detail(repo["full_name"], fetch) if index < DETAILED_REPOS else ""
        found.append(finding("github", repo["full_name"], repo["url"], f"{repo['description']}\n\n{detail}".strip(),
                             repo["stars"]))
    return found


# ----------------------------------------------------------------- social

def parse_reddit(payload):
    children = ((payload.get("data") or {}).get("children") or []) if isinstance(payload, dict) else []
    return [finding("reddit", post.get("title"), "https://www.reddit.com" + str(post.get("permalink", "")),
                    post.get("selftext"), post.get("score"))
            for post in (child.get("data") or {} for child in children if isinstance(child, dict))]


def parse_hn(payload):
    hits = payload.get("hits") if isinstance(payload, dict) else None
    return [finding("hackernews", hit.get("title"),
                    hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    hit.get("story_text"), hit.get("points")) for hit in (hits or []) if isinstance(hit, dict)]


def parse_devto(payload):
    return [finding("devto", item.get("title"), item.get("url"), item.get("description"),
                    item.get("positive_reactions_count")) for item in (payload if isinstance(payload, list) else [])
            if isinstance(item, dict)]


def social(topic, limit, get=http_get):
    query, found, errors = urllib.parse.quote(topic), [], []
    tag = re.sub(r"[^a-z0-9]", "", topic.lower().split()[0]) if topic.split() else ""
    calls = [(f"https://www.reddit.com/r/{name}/search.json?q={query}&restrict_sr=1&sort=top&t=year&limit={limit}",
              parse_reddit) for name in SUBREDDITS]
    calls.append((f"https://hn.algolia.com/api/v1/search?query={query}&tags=story&hitsPerPage={limit}", parse_hn))
    calls.append((f"https://dev.to/api/articles?tag={tag}&per_page={limit}", parse_devto))
    for url, parse in calls:
        try:
            found.extend(parse(json.loads(get(url)))[:limit])
        except Exception as error:  # noqa: BLE001 (one feed failing must not stop the others)
            errors.append(f"{urllib.parse.urlparse(url).netloc}: {error}")
    return found, errors


# -------------------------------------------------------------------- web

class _Text(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.title, self._skip, self._in_title = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        self._skip += tag in ("script", "style", "noscript", "svg")
        self._in_title = tag == "title"

    def handle_endtag(self, tag):
        self._skip -= tag in ("script", "style", "noscript", "svg") and self._skip > 0
        self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip and data.strip():
            self.parts.append(data.strip())


def web(url, get=http_get):
    parser = _Text()
    parser.feed(get(url))
    return finding("web", parser.title or url, url, "\n".join(parser.parts))


# ---------------------------------------------------------------- collect

def collect(target, sources=SOURCES, limit=5, get=http_get, fetch=None, run=subprocess.run, which=shutil.which):
    """Gather findings for a URL or a topic. Returns {"target", "findings", "errors"}; never raises."""
    fetch = fetch or (lambda path: gh_json(path, get, run, which))
    found, errors = [], []

    def attempt(label, action):
        try:
            result = action()
            found.extend(result if isinstance(result, list) else [result])
        except Exception as error:  # noqa: BLE001 (report the source that failed and keep going)
            errors.append(f"{label}: {error}")

    if re.match(r"https?://", target):
        if video_id(target):
            attempt("youtube", lambda: youtube(target, get, run, which))
        elif REPO_URL.search(target):
            attempt("github", lambda: github(target, limit, fetch))
        else:
            attempt("web", lambda: web(target, get))
    else:
        if "youtube" in sources:
            attempt("youtube", lambda: youtube_search(target, min(limit, 3), run, which))
        if "github" in sources:
            attempt("github", lambda: github(target, limit, fetch))
        if "social" in sources:
            posts, failed = social(target, limit, get)
            found.extend(posts)
            errors.extend(failed)
        if "web" in sources:
            errors.append("web: a topic has no single page to read; pass a URL, or let the omni-scout agent search")
    found.sort(key=lambda item: item["points"], reverse=True)
    return {"target": target, "findings": found, "errors": errors}
