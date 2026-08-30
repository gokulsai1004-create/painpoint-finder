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

RESULT_LINK = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
SNIPPET = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.S)
TAGS = re.compile(r"<[^>]+>")


def _clean(fragment):
    return html.unescape(TAGS.sub("", fragment)).strip()


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


def search(query, limit=100):
    """Search the open web for pages discussing a problem."""
    deadline = time.monotonic() + DEADLINE_SECONDS

    try:
        resp = requests.post(
            ENDPOINT, data={"q": query}, headers=HEADERS,
            timeout=max(5, int(deadline - time.monotonic())),
        )
    except requests.RequestException as exc:
        return Result("web", ERROR, detail=f"network: {exc}")

    if resp.status_code in (403, 429):
        # Refused or throttled. We never searched, and the status must say so
        # rather than letting an empty list read as "nothing out there".
        return Result("web", BLOCKED,
                      detail=f"DuckDuckGo refused the request ({resp.status_code})")

    if resp.status_code >= 400:
        return Result("web", ERROR, detail=f"HTTP {resp.status_code}")

    links = RESULT_LINK.findall(resp.text)
    snippets = [_clean(s) for s in SNIPPET.findall(resp.text)]

    if not links and "result__a" not in resp.text:
        # The page shape changed, or we were served something that is not a
        # results page. Either way we did not get an answer.
        return Result("web", ERROR,
                      detail="no results block in response (page layout changed?)")

    posts = []
    for i, (href, title_html) in enumerate(links[:limit]):
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

    return Result("web", OK, posts=posts, searched=len(posts))


register("web", search)
