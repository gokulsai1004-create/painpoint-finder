"""
The Stack Exchange network, not just Stack Overflow.

This is the answer to the tool's worst structural weakness: four of its five
sources were tech-shaped, so a cement plant manager, a nurse or a lab
researcher got thin results and a coverage warning, while a developer got
hundreds of posts. Their complaints exist. They are just not on Hacker News.

Stack Exchange runs 365 sites on one API. Engineering, Law, Medical Sciences,
Academia, Aviation, Chemistry, Personal Finance, Project Management - all with
the same anonymous access as Stack Overflow, and all full of people describing
a specific problem in detail, because that is the only kind of post the format
allows.

The Workplace deserves its own mention. It is job, colleague, client and
management problems across every industry at once, which is exactly the
material the other sources cannot reach.

Replaces the stackoverflow source, which is now just one site among these.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor
from html import unescape
import re

import requests

from . import BLOCKED, ERROR, OK, Post, Result, register

API = "https://api.stackexchange.com/2.3/search/advanced"

HEADERS = {"User-Agent": "painpoint-finder/0.1 (research tool)"}

# Anonymous access allows 300 requests per IP per day, reset at UTC midnight.
# One search costs one request per site, or two where the narrow query finds
# nothing and it widens - so roughly 8 to 16 per search, or about 20 searches a
# day before this source starts refusing. That is enough to try the tool and
# not enough to develop against it, which is exactly how it was exhausted
# repeatedly while this was being built.
#
# A free registered key raises the ceiling to 10,000 a day. It needs no account
# on this side and nothing is sent with it beyond the search itself; the tool
# works without one and simply has less room. Optional by design, like
# fastembed: no key, no account, no sign-up is a promise worth keeping for the
# default path.
#
#     set STACKEXCHANGE_KEY=...        (Windows)
#     export STACKEXCHANGE_KEY=...     (macOS / Linux)
#
# Get one at https://stackapps.com/apps/oauth/register
KEY = os.environ.get("STACKEXCHANGE_KEY", "").strip()

# Below this the source says so, rather than letting the next search fail with
# no warning. Silence about a budget you are about to run out of is the same
# failure as silence about a blocked search.
QUOTA_WARNING = 30

# Chosen for breadth of industry rather than volume. Ordered by how much ground
# each covers that the other sources do not: The Workplace first because it
# spans every industry, Stack Overflow last because Hacker News and GitHub
# already cover software heavily.
SITES = [
    "workplace",        # any job: clients, managers, colleagues, scope, pay
    "engineering",      # mechanical, civil, industrial, manufacturing
    "medicalsciences",  # clinical and health
    "law",              # contracts, disputes, compliance
    "academia",         # research, funding, supervision
    "pm",               # project management, delivery, scope
    "money",            # personal finance, invoicing, tax
    "stackoverflow",    # software
]

# The anonymous quota is 300 requests/day across everything hitting this IP.
# One request per site means a search costs len(SITES); the deadline stops a
# slow run from spending the budget on sites it will not reach in time.
DEADLINE_SECONDS = 25
PER_REQUEST_TIMEOUT = 8

BLOCK_TAG = re.compile(r"</?(p|br|li|blockquote|pre)[^>]*>", re.IGNORECASE)
TAGS = re.compile(r"<[^>]+>")


def _strip_html(fragment):
    """Bodies come back as rendered HTML. Keep paragraph breaks so best_quote()
    still has real sentences to split on; drop everything else."""
    if not fragment:
        return ""
    with_breaks = BLOCK_TAG.sub("\n", fragment)
    return unescape(TAGS.sub("", with_breaks)).strip()


def _search_site(site, search_text, limit, deadline):
    """Query one site. Returns (posts, status, detail)."""
    remaining = deadline - time.monotonic()
    if remaining <= 1:
        return [], "skipped", "out of time"

    try:
        resp = requests.get(
            API,
            params={
                "order": "desc",
                "sort": "relevance",
                "q": search_text,
                "site": site,
                "filter": "withbody",
                "pagesize": min(limit, 100),
                **({"key": KEY} if KEY else {}),
            },
            headers=HEADERS,
            timeout=min(PER_REQUEST_TIMEOUT, remaining),
        )
    except requests.RequestException as exc:
        return [], ERROR, f"{site}: network: {exc}"

    # Status code BEFORE parsing. Stack Exchange throttles in two different
    # shapes: a soft one that returns HTTP 200 with a JSON error_id, and a hard
    # one that returns HTTP 429 carrying an HTML "Too Many Requests" page. The
    # HTML never parses as JSON, so checking the body first reported the hard
    # throttle as "could not parse response" - an ERROR, which reads like a
    # broken parser and, worse, never reaches the cache fallback in
    # sources.run(). Same bug the web source had with DuckDuckGo's HTTP 202.
    if resp.status_code == 429:
        return [], BLOCKED, f"{site}: rate-limited (HTTP 429)"

    try:
        payload = resp.json()
    except ValueError:
        return [], ERROR, f"{site}: could not parse response"

    # Stack Exchange reports throttling and bad requests inside a 200 body, not
    # only via status code. An error_id here means we never actually searched,
    # whatever the HTTP status says.
    if "error_id" in payload:
        message = payload.get("error_message", "unknown error")
        if payload.get("error_name") == "throttle_violation":
            return [], BLOCKED, f"{site}: {message}"
        return [], ERROR, f"{site}: {message}"

    if resp.status_code >= 400:
        return [], ERROR, f"{site}: HTTP {resp.status_code}"

    remaining_quota = payload.get("quota_remaining")

    posts = []
    for item in payload.get("items", []):
        owner = item.get("owner") or {}
        posts.append(Post(
            source=f"stackexchange {site}",
            title=unescape(item.get("title", "")),
            body=_strip_html(item.get("body", "")),
            url=item.get("link", ""),
            # Present-and-null for deleted users; see the note in github.py.
            author=owner.get("display_name") or "",
            created_utc=float(item.get("creation_date") or 0),
            replies=int(item.get("answer_count") or 0),
        ))

    if isinstance(remaining_quota, int) and remaining_quota <= QUOTA_WARNING:
        return posts, OK, f"quota low: {remaining_quota} requests left today"
    return posts, OK, ""


def search(query, limit=100):
    """Search across the Stack Exchange network for people describing a problem."""
    from leads import keywords  # local import avoids a circular import

    terms = keywords(query)
    ranked = sorted(terms, key=len, reverse=True)

    # Stack Exchange ANDs every term, and these are small sites. Measured:
    # "understaffed burnout hospital nurses" returns nothing on The Workplace,
    # "burnout understaffed" returns results, and "understaffed" alone returns
    # the best ones - "How to convince management that our department is
    # understaffed". Two terms first, then one, because narrow-then-widen finds
    # the precise hit when it exists without reporting zero when it does not.
    attempts = []
    if len(ranked) >= 2:
        attempts.append(" ".join(ranked[:2]))
    if ranked:
        attempts.append(ranked[0])
    if not attempts:
        attempts = [query]

    deadline = time.monotonic() + DEADLINE_SECONDS

    def _one_site(site):
        """Try the attempts against a single site, narrowest first."""
        reached, found, why = False, [], None
        for search_text in attempts:
            posts, status, detail = _search_site(site, search_text, limit, deadline)
            if status == OK:
                reached = True
                found.extend(posts)
                if posts:
                    break  # a narrower hit is better; do not widen further
            else:
                why = (status, detail)
                break
        return site, reached, found, why

    # Eight sites in sequence made this the slowest source by far, and every
    # request is independent waiting on the network. Threads turn the total
    # from the sum into the slowest one.
    with ThreadPoolExecutor(max_workers=len(SITES)) as pool:
        outcomes = list(pool.map(_one_site, SITES))

    merged = {}
    blocked, errors, searched_sites = [], [], []

    # Merged in SITES order rather than completion order, so results do not
    # reshuffle between runs purely because the network was faster today.
    for site, reached, found, why in outcomes:
        if reached:
            searched_sites.append(site)
            for post in found:
                merged.setdefault(post.url, post)
        if why:
            status, detail = why
            (blocked if status == BLOCKED else errors).append(detail)

    if merged or searched_sites:
        # Reached at least one site. Partial coverage is honest coverage: the
        # detail names what was and was not searched.
        detail = ""
        if blocked or errors:
            detail = f"searched {len(searched_sites)}/{len(SITES)} sites"
        return Result("stackexchange", OK, posts=list(merged.values()),
                      searched=len(merged), detail=detail)

    # Nothing reached at all. Whether that is "refused" or "broke" changes what
    # the user should conclude, so the distinction survives to the top.
    if blocked:
        return Result("stackexchange", BLOCKED, detail="; ".join(blocked[:2]))
    if errors:
        return Result("stackexchange", ERROR, detail="; ".join(errors[:2]))
    return Result("stackexchange", BLOCKED,
                  detail=f"ran out of time after {DEADLINE_SECONDS}s")


register("stackexchange", search)
