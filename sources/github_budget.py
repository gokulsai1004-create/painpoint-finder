"""
One request budget, shared by both GitHub sources.

GitHub's search rate limit is **10 requests per minute per IP**, and it is not
per endpoint: `/search/issues` and `/search/repositories` draw on the same
allowance. The two sources did not know about each other, so one search spent
up to four requests between them and three searches inside a minute — normal
while somebody is refining a query, which is exactly when caching says people
hit limits — blinded both at once.

Blinding both is the expensive failure. The issue source finds people
describing a problem inside a project; the repository source finds who already
shipped it. Losing them together removes the competition section entirely,
which is the one thing this tool does that others do not.

So they share a counter. When the budget is gone a source returns BLOCKED with
a reason naming the other one, rather than spending a request that will be
refused anyway and reporting an empty search.

Thread-safe because run_all() fans the sources out across threads, so both can
be spending at the same instant.
"""

import threading
import time
from collections import deque

# GitHub's documented anonymous search limit. Left one below the real ten: the
# tool is a guest on a free endpoint, and the spare request is worth more as
# headroom than as one extra result.
PER_MINUTE = 9

WINDOW_SECONDS = 60

_lock = threading.Lock()
_spent = deque()  # monotonic timestamps of requests made in the current window


def _prune(now):
    while _spent and now - _spent[0] >= WINDOW_SECONDS:
        _spent.popleft()


def try_spend():
    """Claim one request. False when the shared budget is gone."""
    with _lock:
        now = time.monotonic()
        _prune(now)
        if len(_spent) >= PER_MINUTE:
            return False
        _spent.append(now)
        return True


def seconds_until_free():
    """How long until at least one request is available again."""
    with _lock:
        now = time.monotonic()
        _prune(now)
        if len(_spent) < PER_MINUTE:
            return 0
        return max(0, int(WINDOW_SECONDS - (now - _spent[0])) + 1)


def note_response(resp):
    """Trust GitHub's own accounting over ours where it is available.

    The header is authoritative: it knows about requests this process did not
    make - another tool on the same network, an earlier run - which a local
    counter cannot see. When it says zero, the window is spent whatever we
    think.
    """
    try:
        remaining = int(resp.headers.get("X-RateLimit-Remaining", ""))
    except (TypeError, ValueError):
        return
    if remaining <= 0:
        with _lock:
            now = time.monotonic()
            _prune(now)
            while len(_spent) < PER_MINUTE:
                _spent.append(now)


def reset():
    """Test hook: forget the window."""
    with _lock:
        _spent.clear()
