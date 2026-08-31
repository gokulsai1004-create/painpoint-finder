"""
General web search, via DuckDuckGo's HTML endpoint.

This is the fallback that exists so no query ever returns a false zero. A
biotech researcher whose pain lives on protocols.io and in conference
abstracts would get nothing from Reddit and nothing from Hacker News, and
"nothing" would read as "nobody has this problem" — which is the single worst
answer this tool can give.

Deliberately lower fidelity, and honest about it. A search result is a page,
not a person: results are marked `contactable=False` so nothing tries to draft
a reply to an article nobody will read.
"""

import html
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

from . import BLOCKED, ERROR, OK, Post, Result, register

ENDPOINT = "https://html.duckduckgo.com/html/"

# The HTML endpoint refuses obvious bot user-agents. Identifying as a normal
# browser is what makes it answer at all.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}

DEADLINE_SECONDS = 20

# The tell that we were refused, in the page body. DuckDuckGo serves a 202 - a
# SUCCESS code - with a "bots use DuckDuckGo too" modal instead of an error
# status, which is why this was landing in the layout-changed branch and being
# reported as ERROR. It is a refusal, and only BLOCKED reaches the cache
# fallback in sources.run().
THROTTLE_MARKERS = ("anomaly-modal", "anomaly.js", "cc=botnet")

# Measured against the live endpoint: two searches succeed, then every request
# is refused for minutes. Each attempt spends quota whether it succeeds or not,
# so retrying inside one search does not recover it - it just makes the NEXT
# search fail too. One attempt, honest status, and let the cache cover the gap.
COOLDOWN_SECONDS = 15 * 60
COOLDOWN_FILE = Path(__file__).resolve().parent.parent / ".cache" / "web-cooldown"

RESULT_LINK = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
SNIPPET = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.S)
TAGS = re.compile(r"<[^>]+>")

# Paid placements. They come back through the same result__a class as organic
# hits, and they are the last thing this tool should surface: an advert is
# somebody selling INTO the pain, the same reason job adverts and product
# launches are ranked down. Their hrefs also point at a click-tracking redirect
# rather than the real page, so the URL shown would not be where the user lands.
AD_HREF = re.compile(r"(duckduckgo\.com/y\.js|[?&]ad_(domain|provider|type)=)",
                     re.IGNORECASE)


def _clean(fragment):
    return html.unescape(TAGS.sub("", fragment)).strip()


def _cooling_down():
    """Seconds left on the cooldown, or 0. Persisted to a file because each run
    is a fresh process: an in-memory flag would forget between searches, which
    is exactly when it matters."""
    try:
        left = COOLDOWN_SECONDS - (time.time() - COOLDOWN_FILE.stat().st_mtime)
    except OSError:
        return 0
    return int(left) if left > 0 else 0


def _start_cooldown():
    try:
        COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOLDOWN_FILE.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass  # a cooldown we cannot record is not worth failing a search over


def _throttled(resp):
    """Refused rather than broken. The distinction decides whether the user is
    told 'nothing out there' or 'we never actually looked'."""
    if resp.status_code in (202, 403, 429):
        return True
    return any(m in resp.text for m in THROTTLE_MARKERS)


def _real_url(href):
    """DuckDuckGo wraps results in a redirect; unwrap it to the real page."""
    if href.startswith("//duckduckgo.com/l/") or "/l/?uddg=" in href:
        query = urlparse(href if href.startswith("http") else "https:" + href).query
        target = parse_qs(query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return href


def _domain(url):
    try:
        return urlparse(url).netloc.replace("www.", "")
    except ValueError:
        return "web"


def _parse(page, limit):
    """Turn a results page into posts."""
    links = RESULT_LINK.findall(page)
    snippets = [_clean(s) for s in SNIPPET.findall(page)]

    if not links and "result__a" not in page:
        # A real layout change, now that refusals are caught above. ERROR rather
        # than BLOCKED: this will not fix itself on a cooldown, it wants a human.
        return Result("web", ERROR,
                      detail="no results block in response (page layout changed?)")

    posts = []
    for i, (href, title_html) in enumerate(links):
        if AD_HREF.search(href):
            continue
        url = _real_url(href)
        posts.append(Post(
            source=f"web {_domain(url)}",
            title=_clean(title_html),
            body=snippets[i] if i < len(snippets) else "",
            url=url,
            author="",
            # Search results carry no date and no author. Treating them as
            # people to message would be a lie; they are evidence that the
            # topic exists, nothing more.
            created_utc=0.0,
            contactable=False,
        ))
        if len(posts) >= limit:
            break

    return Result("web", OK, posts=posts, searched=len(posts))


def search(query, limit=100):
    """Search the open web for pages discussing a problem."""
    left = _cooling_down()
    if left:
        # Spending a request now would refresh the block and buy nothing. Say so
        # in the same words as a live refusal, so the user reads one situation
        # rather than two, and so the cache fallback still fires.
        return Result("web", BLOCKED,
                      detail=f"on cooldown after being throttled "
                             f"({left // 60}m {left % 60}s left)")

    try:
        resp = requests.post(ENDPOINT, data={"q": query}, headers=HEADERS,
                             timeout=DEADLINE_SECONDS)
    except requests.RequestException as exc:
        return Result("web", ERROR, detail=f"network: {exc}")

    if _throttled(resp):
        _start_cooldown()
        return Result("web", BLOCKED,
                      detail=f"DuckDuckGo throttled the request "
                             f"(HTTP {resp.status_code}); backing off "
                             f"{COOLDOWN_SECONDS // 60}m")

    if resp.status_code >= 400:
        return Result("web", ERROR, detail=f"HTTP {resp.status_code}")

    return _parse(resp.text, limit)


register("web", search)
