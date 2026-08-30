"""
A short-lived cache of successful searches.

Only used when a source comes back BLOCKED. Rate limits are the failure you
actually hit while iterating on a query — you rerun a search five times
refining the wording, and the fifth one gets refused. Falling back to results
from twenty minutes ago turns a dead run into a usable one.

Cached results are ALWAYS labelled. A stale answer presented as fresh is worse
than no answer, because the whole point of this tool is being honest about the
strength of its own evidence.
"""

import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from sources import OK, Post, Result

CACHE_DIR = Path(__file__).parent / ".cache"

# Long enough to cover a burst of query refinements, short enough that nobody
# makes a decision on genuinely stale evidence.
TTL_SECONDS = 30 * 60

# The cache is a convenience, not a store. Bounded so a long session cannot
# quietly fill a disk.
MAX_ENTRIES = 200


def _key(source, query):
    """Filename-safe key, unique per query.

    Hashed rather than slugified. The obvious approach - lowercase, replace
    punctuation, truncate to a sane filename length - collides: two long
    queries sharing their first 80 characters map to one file, and the second
    search silently receives the first one's posts labelled as cached. That is
    the tool handing someone results for a search they never ran.

    A readable prefix is kept so the cache directory can still be eyeballed,
    but the hash is what makes the key unique.
    """
    normalised = " ".join(query.lower().split())
    digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]
    hint = "".join(c if c.isalnum() else "_" for c in normalised)[:40]
    return f"{source}__{hint}__{digest}.json"


def _path(source, query):
    return CACHE_DIR / _key(source, query)


def save(result, query):
    """Store a successful result. Failures are never cached — caching a
    rate-limit would mean serving the failure back for the next 30 minutes."""
    if not result.usable:
        return

    try:
        CACHE_DIR.mkdir(exist_ok=True)
        _prune()
        payload = {
            "saved_at": time.time(),
            "query": query,
            "source": result.source,
            "searched": result.searched,
            "posts": [asdict(p) for p in result.posts],
        }
        _path(result.source, query).write_text(
            json.dumps(payload), encoding="utf-8")
    except OSError:
        # A cache that cannot write is a cache that does nothing. It must never
        # be the reason a search fails.
        pass


def load(source, query):
    """Return (Result, age_seconds) if a fresh entry exists, else (None, 0)."""
    path = _path(source, query)
    try:
        if not path.exists():
            return None, 0
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, 0

    age = time.time() - payload.get("saved_at", 0)
    if age > TTL_SECONDS:
        return None, 0

    try:
        posts = [Post(**p) for p in payload.get("posts", [])]
    except TypeError:
        # Written by an older version with different fields. Treat as a miss
        # rather than crashing on someone's upgrade.
        return None, 0

    return Result(source, OK, posts=posts,
                  searched=payload.get("searched", len(posts))), age


def _prune():
    """Drop expired entries, then the oldest if still over the ceiling."""
    try:
        entries = sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return

    cutoff = time.time() - TTL_SECONDS
    for path in entries:
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass

    try:
        entries = sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for path in entries[:-MAX_ENTRIES] if len(entries) > MAX_ENTRIES else []:
            path.unlink()
    except OSError:
        pass


def age_label(seconds):
    minutes = int(seconds / 60)
    if minutes < 1:
        return "under a minute ago"
    if minutes == 1:
        return "1 minute ago"
    return f"{minutes} minutes ago"
