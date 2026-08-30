"""
GitHub issues, via the public search API.

Covers something none of the other sources do: a person describing what a tool
they already use cannot do. That is a stronger signal than a forum complaint,
because they installed the thing, hit the wall, and cared enough to file
against it. The gap between "what this does" and "what I needed" is written
down in the open.

No key needed, but the unauthenticated search limit is 10 requests per MINUTE,
by far the tightest of any source here. One query per run, and a refusal is
reported as BLOCKED rather than silently reading as "nobody has this problem".
"""

import time

import requests

from . import BLOCKED, ERROR, OK, Post, Result, register

API = "https://api.github.com/search/issues"

HEADERS = {
    "User-Agent": "painpoint-finder/0.1 (research tool)",
    "Accept": "application/vnd.github+json",
}

DEADLINE_SECONDS = 20

# GitHub caps search results per page at 100 regardless of what you ask for.
MAX_PER_PAGE = 100


def search(query, limit=100):
    """Search GitHub issues for people describing an unmet need."""
    from leads import keywords  # local import avoids a circular import

    terms = keywords(query)
    # GitHub ANDs every term, so a whole sentence matches almost nothing. Three
    # distinctive words is the sweet spot: fewer returns noise, more returns
    # zero. Same reasoning as the Hacker News and Stack Overflow sources.
    words = " ".join(sorted(terms, key=len, reverse=True)[:3]) or query

    # type:issue excludes pull requests. A PR is someone contributing a fix,
    # not someone describing a problem, and the two read very differently.
    q = f"{words} in:title,body type:issue"

    try:
        resp = requests.get(
            API,
            params={
                "q": q,
                "per_page": min(limit, MAX_PER_PAGE),
                "sort": "created",
                "order": "desc",
            },
            headers=HEADERS,
            timeout=DEADLINE_SECONDS,
        )
    except requests.RequestException as exc:
        return Result("github", ERROR, detail=f"network: {exc}")

    # GitHub answers a spent rate limit with 403, not 429, and says so only in
    # the body. Treating that as a generic error would hide the one failure
    # worth distinguishing: we never actually searched.
    if resp.status_code in (403, 429):
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining == "0" or resp.status_code == 429:
            reset = resp.headers.get("X-RateLimit-Reset")
            wait = ""
            if reset:
                try:
                    seconds = max(0, int(reset) - int(time.time()))
                    wait = f", resets in {seconds}s"
                except ValueError:
                    pass
            return Result("github", BLOCKED,
                          detail=f"rate-limited (10 searches/minute unauthenticated{wait})")
        return Result("github", BLOCKED, detail="GitHub refused the request (403)")

    if resp.status_code >= 400:
        return Result("github", ERROR, detail=f"HTTP {resp.status_code}")

    try:
        payload = resp.json()
    except ValueError as exc:
        # Malformed JSON is not "no results" - we could not read the answer.
        return Result("github", ERROR, detail=f"could not parse response: {exc}")

    posts = []
    for item in payload.get("items", []):
        user = item.get("user") or {}

        # An issue with no body is a title and nothing else. Keeping the title
        # as the body gives best_quote() something real to quote instead of
        # falling back to naming the post.
        body = item.get("body") or item.get("title") or ""

        # repository_url looks like https://api.github.com/repos/owner/name -
        # the last two segments name the project, which is worth showing.
        repo = ""
        repo_url = item.get("repository_url", "")
        if repo_url:
            parts = repo_url.rstrip("/").split("/")
            if len(parts) >= 2:
                repo = "/".join(parts[-2:])

        posts.append(Post(
            source=f"github {repo}".strip(),
            title=item.get("title", ""),
            body=body,
            url=item.get("html_url", ""),
            author=user.get("login", ""),
            created_utc=_epoch(item.get("created_at")),
            replies=int(item.get("comments") or 0),
        ))

    return Result("github", OK, posts=posts, searched=len(posts))


def _epoch(iso):
    """'2026-08-27T14:22:01Z' -> unix seconds."""
    if not iso:
        return 0.0
    try:
        from datetime import datetime
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").timestamp()
    except (ValueError, TypeError):
        return 0.0


register("github", search)
