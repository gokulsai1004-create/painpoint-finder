"""
Reddit source, via public Atom feeds.

Reddit answers anonymous .json requests with 403 but still serves .rss to
anyone, so this needs no account, no key and no registration. The feeds omit
score and comment count; nothing here pretends otherwise.

Adapted from the rss_source module in reddit-mentor, which has been running
against these feeds hourly and is where the backoff numbers come from.
"""

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from html import unescape
from html.parser import HTMLParser

import requests

from . import BLOCKED, ERROR, OK, Post, Result, register

ATOM = {"a": "http://www.w3.org/2005/Atom"}
BASE = "https://www.reddit.com"

# Reddit blocks the default requests user-agent outright. Identifying the tool
# honestly is also what Reddit's own API rules ask for.
HEADERS = {"User-Agent": "painpoint-finder/0.1 (research tool; contact via GitHub)"}


class _TextExtractor(HTMLParser):
    """Collapse a post's HTML body down to readable plain text."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True
        elif tag in ("p", "br", "div", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self):
        joined = re.sub(r"\n{3,}", "\n\n", "".join(self.parts))
        return joined.strip()


# Every RSS body ends with Reddit's own furniture: "submitted by /u/name to
# r/sub [link] [comments]". Left in, it becomes evidence: a real run reported
# "appreciated submitted" as a top theme, which is the footer colliding with
# the last word of the post.
FOOTER = re.compile(
    r"\s*submitted\s+by\s*/?u/\S+.*$|\s*\[link\]\s*\[comments\]\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _html_to_text(html):
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(unescape(html))
    return FOOTER.sub("", parser.text()).strip()


def _epoch(iso):
    if not iso:
        return 0.0
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return 0.0


def _first(entry, tag):
    node = entry.find(f"a:{tag}", ATOM)
    return (node.text or "") if node is not None else ""


def _parse(xml_text):
    root = ET.fromstring(xml_text)
    posts = []

    for entry in root.findall("a:entry", ATOM):
        link = entry.find("a:link", ATOM)
        href = link.attrib.get("href", "") if link is not None else ""
        if not href:
            continue

        # Reddit's search returns communities alongside posts. A subreddit has
        # no author to talk to, so it is not a lead. Post URLs always contain
        # /comments/; community URLs never do.
        if "/comments/" not in href:
            continue

        author_node = entry.find("a:author/a:name", ATOM)
        author = author_node.text if author_node is not None else ""

        sub = ""
        cat = entry.find("a:category", ATOM)
        if cat is not None:
            sub = cat.attrib.get("label", "")

        posts.append(Post(
            source=f"reddit {sub}".strip(),
            title=unescape(_first(entry, "title")),
            body=_html_to_text(_first(entry, "content")),
            url=href,
            author=author,
            created_utc=_epoch(_first(entry, "published")),
        ))

    return posts


def _fetch(query, limit, deadline=None):
    """One search request, with backoff. Returns a Result.

    `deadline` is a time.monotonic() value this call must not run past. It is
    checked before every sleep, not just between calls: one variant's backoff
    can exceed the whole budget on its own, and a caller-level check cannot
    interrupt a sleep already in progress.

    Backoff starts small because a human is waiting. reddit-mentor can afford
    to wait out a 429 since it runs unattended on a schedule; this cannot.
    """
    url = f"{BASE}/search.rss"
    params = {"q": query, "sort": "new", "limit": min(limit, 100)}
    wait = 3

    def out_of_time():
        return deadline is not None and time.monotonic() >= deadline

    def sleep_or_give_up(seconds):
        """Sleep, unless that would run past the deadline. True if we slept."""
        if deadline is not None and time.monotonic() + seconds > deadline:
            return False
        time.sleep(seconds)
        return True

    for attempt in range(4):
        if out_of_time():
            return Result("reddit", BLOCKED, detail="out of time before request")

        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        except requests.RequestException as exc:
            if attempt == 3 or not sleep_or_give_up(wait):
                return Result("reddit", ERROR, detail=f"network: {exc}")
            wait *= 2
            continue

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else wait
            if attempt == 3 or not sleep_or_give_up(delay):
                # Either out of retries or out of time. Both mean we never
                # searched, which is the whole point of the BLOCKED status.
                return Result("reddit", BLOCKED,
                              detail="rate-limited by Reddit")
            wait *= 2
            continue

        if resp.status_code in (403, 401):
            return Result("reddit", BLOCKED,
                          detail=f"Reddit refused the request ({resp.status_code})")

        if resp.status_code >= 400:
            return Result("reddit", ERROR, detail=f"HTTP {resp.status_code}")

        try:
            posts = _parse(resp.text)
        except ET.ParseError as exc:
            # Malformed XML is not "no results" — we could not read the answer.
            return Result("reddit", ERROR, detail=f"could not parse feed: {exc}")

        return Result("reddit", OK, posts=posts, searched=len(posts))

    return Result("reddit", BLOCKED, detail="retries exhausted")


def _query_variants(query):
    """Reddit search is keyword-based, so a whole sentence matches almost nothing.

    Three shots, widest last: the distinctive words together, then the two most
    distinctive as a phrase, then the single strongest term. Longest first means
    a precise hit wins; the fallbacks stop a specific question returning nothing
    at all.
    """
    from leads import keywords, phrases  # imported here to avoid a circular import

    terms = keywords(query)
    if not terms:
        return [query]

    # Longer words carry more meaning than short ones in practice.
    ranked = sorted(terms, key=len, reverse=True)
    pairs = phrases(query)

    variants = []

    # Phrase searches first. "extra work" as a phrase finds people describing
    # the problem; the same two words loose find anyone who mentioned either.
    for pair in pairs:
        variants.append(f'"{pair}"')

    # Then the distinctive subject word alongside each phrase, so results are
    # about the right people doing the right thing.
    if ranked and pairs:
        variants.append(f'{ranked[0]} "{pairs[-1]}"')

    if len(ranked) >= 3:
        variants.append(" ".join(ranked[:3]))
    if len(ranked) >= 2:
        variants.append(" ".join(ranked[:2]))
    variants.append(ranked[0])

    seen, out = set(), []
    for v in variants:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


# Whole-source deadline. Without it the empty case is the slowest: no results
# means no early exit, so every variant runs and every retry backs off, and the
# answer "nobody has this problem" - the most valuable one this tool gives -
# takes minutes to arrive. A partial search reported honestly beats a complete
# one nobody waited for.
DEADLINE_SECONDS = 45


def search(query, limit=100):
    """Search Reddit for people talking about a problem.

    Runs several keyword variants and merges them, because one phrasing of a
    natural-language question routinely returns nothing while a slightly wider
    one returns plenty. A thin result here would read as "nobody has this
    problem", which is exactly the false answer this tool exists to avoid.
    """
    merged = {}
    statuses = []
    searched = 0
    deadline = time.monotonic() + DEADLINE_SECONDS
    ran_out_of_time = False

    for variant in _query_variants(query):
        if time.monotonic() >= deadline:
            ran_out_of_time = True
            break

        result = _fetch(variant, limit, deadline=deadline)
        statuses.append(result)
        if result.usable:
            searched += result.searched
            for post in result.posts:
                merged.setdefault(post.url, post)
        if len(merged) >= limit:
            break

    if merged:
        return Result("reddit", OK, posts=list(merged.values()), searched=searched)

    # Nothing merged. Whether that means "no posts" or "never got to look"
    # depends on how the attempts failed, and the difference matters.
    if any(r.status == BLOCKED for r in statuses):
        detail = next(r.detail for r in statuses if r.status == BLOCKED)
        return Result("reddit", BLOCKED, detail=detail)
    if statuses and all(r.status == ERROR for r in statuses):
        return Result("reddit", ERROR, detail=statuses[0].detail)

    if ran_out_of_time:
        # Searched some phrasings, ran out of time before the rest. An empty
        # result here is genuinely inconclusive and must not read as "nobody
        # has this problem".
        return Result("reddit", BLOCKED, searched=searched,
                      detail=f"ran out of time after {DEADLINE_SECONDS}s "
                             f"({len(statuses)} of {len(_query_variants(query))} "
                             f"phrasings tried)")

    return Result("reddit", OK, posts=[], searched=searched)


register("reddit", search)
