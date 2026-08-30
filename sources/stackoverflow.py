"""
Stack Overflow, via the public Stack Exchange API.

No key, no account, no sign-up: the anonymous quota (300 requests/day, shared
across every unauthenticated tool hitting this IP) is fine for a handful of
searches. Covers ground none of the other sources touch — a developer stuck on
a real problem describes it in a question, not a Reddit post or a Show HN.

Only questions are searchable this way, not answers. That is a limit of the
public API, not a choice: there is no full-text search across answer bodies
without a signed-in session.
"""

import re
import time
from html import unescape

import requests

from . import BLOCKED, ERROR, OK, Post, Result, register

API = "https://api.stackexchange.com/2.3/search/advanced"

HEADERS = {"User-Agent": "painpoint-finder/0.1 (research tool)"}

DEADLINE_SECONDS = 20

BLOCK_TAG = re.compile(r"</?(p|br|li|blockquote|pre)[^>]*>", re.IGNORECASE)
TAGS = re.compile(r"<[^>]+>")


def _strip_html(fragment):
    """Question bodies come back as rendered HTML. Keep the paragraph breaks
    so best_quote() still has real sentences to split on; drop everything
    else."""
    if not fragment:
        return ""
    with_breaks = BLOCK_TAG.sub("\n", fragment)
    return unescape(TAGS.sub("", with_breaks)).strip()


def search(query, limit=100):
    """Search Stack Overflow questions for people describing a problem."""
    from leads import keywords  # local import avoids a circular import

    terms = keywords(query)
    # Same reasoning as the Hacker News source: the API treats a whole
    # sentence as a strict phrase far more often than it treats it as a bag
    # of words, so a handful of distinctive terms finds more than the raw
    # question does.
    search_text = " ".join(sorted(terms, key=len, reverse=True)[:4]) or query

    try:
        resp = requests.get(
            API,
            params={
                "order": "desc",
                "sort": "relevance",
                "q": search_text,
                "site": "stackoverflow",
                "filter": "withbody",
                "pagesize": min(limit, 100),
            },
            headers=HEADERS,
            timeout=DEADLINE_SECONDS,
        )
    except requests.RequestException as exc:
        return Result("stackoverflow", ERROR, detail=f"network: {exc}")

    try:
        payload = resp.json()
    except ValueError as exc:
        # Malformed JSON is not "no results" — we could not read the answer.
        return Result("stackoverflow", ERROR,
                      detail=f"could not parse response: {exc}")

    # The Stack Exchange API reports throttling and bad requests inside a 200
    # response body, not just via HTTP status — an error_id here means we
    # never actually searched, whatever the status code says.
    if "error_id" in payload:
        message = payload.get("error_message", "unknown error")
        if payload.get("error_name") == "throttle_violation" or resp.status_code == 502:
            return Result("stackoverflow", BLOCKED, detail=message)
        return Result("stackoverflow", ERROR,
                      detail=f"{payload.get('error_name', 'error')}: {message}")

    if resp.status_code == 429:
        return Result("stackoverflow", BLOCKED, detail="rate-limited by Stack Exchange")

    if resp.status_code >= 400:
        return Result("stackoverflow", ERROR, detail=f"HTTP {resp.status_code}")

    posts = []
    for item in payload.get("items", []):
        owner = item.get("owner") or {}
        posts.append(Post(
            source="stackoverflow",
            title=unescape(item.get("title", "")),
            body=_strip_html(item.get("body", "")),
            url=item.get("link", ""),
            author=owner.get("display_name", ""),
            created_utc=float(item.get("creation_date") or 0),
            replies=int(item.get("answer_count") or 0),
        ))

    return Result("stackoverflow", OK, posts=posts, searched=len(posts))


register("stackoverflow", search)
