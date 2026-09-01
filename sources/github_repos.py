"""
GitHub repositories: the people who already shipped it.

The existing github source searches ISSUES, which finds someone saying what a
tool they already use cannot do - a good lead. It cannot find the tool itself.

That gap was found the hard way. A search for "a tmux-like multi-pane terminal
tool for windows" returned four competitors, none of them psmux - the 3,400-star
project that owns that space, actively developed, with documentation for the
exact use case being searched. A repository search finds it as the first result.
It also found openwong2kim/wmux at 365 stars doing precisely the niche the
search was about. Six real competitors, invisible to a source that only reads
issues, because none of them had filed an issue describing themselves.

Every result here is a product someone shipped, so leads.is_builder() treats
this source as competition unconditionally rather than sniffing for launch
language in the description.

Sorted by stars, because "who owns this space" is the question being asked, and
the answer is almost never the newest repo.
"""

import time

import requests

from . import BLOCKED, ERROR, OK, Post, Result, register
from . import github_budget

API = "https://api.github.com/search/repositories"

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "painpoint-finder/0.1 (research tool)",
}

TIMEOUT = 12

# Anonymous search is 10 requests/minute. One request per search is the budget.
PER_PAGE = 15

# A repo with no stars at all is somebody's weekend folder, not your
# competition. Low enough to catch a serious project that launched last week.
MIN_STARS = 2


def _epoch(stamp):
    if not stamp:
        return 0.0
    try:
        from datetime import datetime
        return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").timestamp()
    except (ValueError, TypeError):
        return 0.0


def _terms(query):
    """The words a competitor would have put in their own description."""
    from leads import SOLUTION_WORDS, keywords
    terms = keywords(query)
    # "tool", "app", "platform" describe what YOU would build. Every third repo
    # on GitHub says "tool", so they cannot narrow anything.
    return [t for t in terms if t not in SOLUTION_WORDS] or terms


def _attempts(terms):
    """Query variants, best guess first.

    GitHub matches repository name, description and topics - NOT the README -
    and ANDs every term, so a long query matches nothing: "terminal windows
    multi pane tool" returned zero while that space actually held six rivals.

    No single heuristic is reliable, which is why there are three. Ranking by
    word LENGTH - what this did first - is actively wrong: it chose "terminal
    windows multi" and threw away "tmux", the one word that identified the
    space. Subject-plus-qualifier finds it; two-longest works when the subject
    is a long word; the bare subject is the last resort.
    """
    tries = []
    if len(terms) >= 2:
        tries.append(f"{terms[0]} {terms[-1]}")          # subject + qualifier
        tries.append(" ".join(sorted(terms, key=len, reverse=True)[:2]))
    if terms:
        tries.append(terms[0])
    seen, unique = set(), []
    for t in tries:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique or [" "]


def _relevance(name, description, terms):
    """How many of the query's words this repo actually claims.

    The merge needs this because a broad attempt drags in noise - searching
    "tmux windows" surfaces every Windows terminal app ever written, and only
    the ones echoing several of your words are really in your space.
    """
    haystack = f"{name} {description}".lower()
    return sum(1 for t in terms if t in haystack)


def search(query, limit=100):
    """Find repositories that already do the thing being described."""
    terms = _terms(query)
    merged, reached = {}, False

    for search_text in _attempts(terms):
        # Each widening attempt costs a request from the allowance the issue
        # source is also drawing on. Stop rather than starve it: a narrower
        # answer beats blinding both halves of the competition section.
        if not github_budget.try_spend():
            if merged:
                break
            return Result("github-repos", BLOCKED,
                          detail=f"GitHub search budget shared with github "
                                 f"is spent; free in "
                                 f"{github_budget.seconds_until_free()}s")

        try:
            resp = requests.get(
                API,
                params={"q": search_text, "sort": "stars", "order": "desc",
                        "per_page": min(limit, PER_PAGE)},
                headers=HEADERS, timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            return Result("github-repos", ERROR, detail=f"network: {exc}")

        github_budget.note_response(resp)

        # Anonymous search rate limiting arrives as a 403 carrying the reset
        # header, which is a refusal and not a break - the same distinction the
        # rest of this tool is built around.
        if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
            return Result("github-repos", BLOCKED, detail="GitHub search rate limit")
        if resp.status_code == 429:
            return Result("github-repos", BLOCKED, detail="rate-limited (HTTP 429)")
        if resp.status_code >= 400:
            return Result("github-repos", ERROR, detail=f"HTTP {resp.status_code}")

        try:
            payload = resp.json()
        except ValueError:
            return Result("github-repos", ERROR, detail="could not parse response")

        reached = True
        for post in _to_posts(payload):
            merged.setdefault(post.url, post)
        # Enough genuinely on-topic hits: stop spending requests.
        if sum(1 for p in merged.values()
               if _relevance(p.title, p.body, terms) >= 2) >= 5:
            break

    if not reached:
        return Result("github-repos", BLOCKED, detail="no attempt completed")

    scored = [(_relevance(p.title, p.body, terms), p.replies, p)
              for p in merged.values()]
    # Two words in common means the same space; one means it shares a platform.
    # Fall back to one only when nothing clears the higher bar.
    keep = [s for s in scored if s[0] >= 2] or [s for s in scored if s[0] >= 1]
    keep.sort(key=lambda s: (-s[0], -s[1]))
    posts = [p for _, _, p in keep[:limit]]
    return Result("github-repos", OK, posts=posts, searched=len(posts))


def _to_posts(payload):
    posts = []
    for item in payload.get("items", []):
        stars = int(item.get("stargazers_count") or 0)
        if stars < MIN_STARS:
            continue
        name = item.get("full_name", "")
        posts.append(Post(
            source=f"github-repo {name}",
            # Stars in the title because that is the whole signal: one rival
            # with 3,400 stars means something very different from six with two.
            title=f"{name} - {stars} stars",
            body=item.get("description") or "",
            url=item.get("html_url", ""),
            author=(item.get("owner") or {}).get("login") or "",
            created_utc=_epoch(item.get("pushed_at")),
            replies=stars,
            # A repository is a product, not a person in pain. Never a lead.
            contactable=False,
        ))
    return posts


register("github-repos", search)
