"""
Hacker News, via the public Algolia search API.

No key, no account, no rate limit worth worrying about — the opposite of
Reddit in every way that matters here.

Searches comments as well as stories, and comments are the better half: a
story is usually someone announcing a thing, while a comment is usually
someone reacting to it, and reacting is where the complaints live.
"""

import time

import requests

from . import ERROR, OK, Post, Result, register

API = "https://hn.algolia.com/api/v1/search"
ITEM = "https://news.ycombinator.com/item?id="

HEADERS = {"User-Agent": "painpoint-finder/0.1 (research tool)"}


def _fetch(query, tags, limit, deadline):
    """One Algolia query. Returns (posts, error_detail)."""
    if time.monotonic() >= deadline:
        return [], "out of time"

    try:
        resp = requests.get(
            API,
            params={"query": query, "tags": tags, "hitsPerPage": min(limit, 100)},
            headers=HEADERS,
            timeout=15,
        )
    except requests.RequestException as exc:
        return [], f"network: {exc}"

    if resp.status_code >= 400:
        return [], f"HTTP {resp.status_code}"

    try:
        hits = resp.json().get("hits", [])
    except ValueError as exc:
        # Malformed JSON is not "no results" — we could not read the answer.
        return [], f"could not parse response: {exc}"

    posts = []
    for hit in hits:
        # A story carries its text in story_text; a comment in comment_text.
        body = hit.get("comment_text") or hit.get("story_text") or ""
        title = hit.get("title") or hit.get("story_title") or ""

        # A comment has no title of its own. Falling back to the story title
        # keeps the display honest about what thread it came from.
        if not title and body:
            title = body.strip().split("\n")[0][:90]

        object_id = hit.get("objectID")
        if not object_id:
            continue

        posts.append(Post(
            source="hackernews",
            title=title,
            body=body,
            url=f"{ITEM}{object_id}",
            author=hit.get("author") or "",
            created_utc=float(hit.get("created_at_i") or 0),
            replies=int(hit.get("num_comments") or 0),
        ))

    return posts, ""


DEADLINE_SECONDS = 30


def search(query, limit=100):
    """Search HN stories and comments for people describing a problem."""
    from leads import keywords  # local import avoids a circular import

    terms = keywords(query)
    # Algolia treats the query as a bag of words and ANDs them, so a whole
    # sentence returns almost nothing. The distinctive words do better.
    search_text = " ".join(sorted(terms, key=len, reverse=True)[:4]) or query

    deadline = time.monotonic() + DEADLINE_SECONDS
    merged = {}
    errors = []

    for tags in ("comment", "story"):
        posts, err = _fetch(search_text, tags, limit, deadline)
        if err:
            errors.append(f"{tags}: {err}")
            continue
        for post in posts:
            merged.setdefault(post.url, post)

    if merged:
        return Result("hackernews", OK, posts=list(merged.values()),
                      searched=len(merged))

    if errors:
        return Result("hackernews", ERROR, detail="; ".join(errors))

    return Result("hackernews", OK, posts=[], searched=0)


register("hackernews", search)
