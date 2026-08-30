"""
Source registry.

A source is anything that can answer "who is talking about this?". It takes a
query and returns a Result. That is the whole contract, and it is deliberately
small so adding a source later is one file rather than a rewrite.

The important part of Result is `status`. A source that found nothing and a
source that could not look both return zero posts, and those two things mean
opposite things:

    "I searched and nobody has this problem"      -> maybe drop the idea
    "I was rate-limited and never actually looked" -> we know nothing

Collapsing them would let this tool tell someone their real problem is
imaginary. That is the worst thing it could do, so the distinction is carried
in the type rather than left to a caller to remember.
"""

from dataclasses import dataclass, field


# Status values a source can report.
OK = "ok"            # searched successfully, whatever the count
BLOCKED = "blocked"  # rate-limited, banned, or refused; we learned nothing
ERROR = "error"      # network failure, bad response, parse failure


@dataclass
class Post:
    """One thing somebody wrote, from any source.

    `contactable` separates a person from a page. A Reddit post has an author
    you can reply to; a blog article usually does not. Drafting an opener for
    something nobody can answer would waste the user's time and make the tool
    look like it does not understand its own results.
    """
    source: str
    title: str
    body: str
    url: str
    author: str = ""
    created_utc: float = 0.0
    replies: int = 0
    contactable: bool = True

    def text(self):
        return f"{self.title}\n{self.body}"


@dataclass
class Result:
    """What one source found, and whether it was actually able to look."""
    source: str
    status: str
    posts: list = field(default_factory=list)
    detail: str = ""       # why it was blocked or errored, for the user
    searched: int = 0      # how many items were examined
    from_cache: str = ""   # set to an age label when served from cache

    @property
    def usable(self):
        return self.status == OK


_REGISTRY = {}


def register(name, fn):
    """Add a source. `fn(query, limit) -> Result`."""
    _REGISTRY[name] = fn


def available():
    return sorted(_REGISTRY)


def run(name, query, limit=100, use_cache=True):
    """Run one source, converting an unexpected crash into an ERROR Result.

    A source that raises must not take the whole search down with it — the
    other sources may still have something useful, and a partial answer with
    honest coverage beats no answer.

    A blocked source falls back to a recent cached search of the same query,
    labelled as cached. Rate limits are what you actually hit while refining a
    query, and results from twenty minutes ago beat nothing. Only BLOCKED falls
    back: an ERROR might mean the source changed shape, and serving old data
    for that would hide a real break.
    """
    fn = _REGISTRY[name]
    try:
        result = fn(query, limit)
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        result = Result(source=name, status=ERROR,
                        detail=f"{type(exc).__name__}: {exc}")

    if not use_cache:
        return result

    # Deferred because cache imports Result from this module, so a top-level
    # import would be circular. Guarded because the import resolves today only
    # by virtue of the project root being on sys.path; the moment this package
    # is installed or vendored without cache.py beside it, an unguarded import
    # would raise straight out of run() and take the whole search down instead
    # of degrading to an uncached result.
    try:
        import cache
    except ImportError:
        return result

    if result.usable:
        cache.save(result, query)
        return result

    if result.status == BLOCKED:
        cached, age = cache.load(name, query)
        if cached:
            cached.from_cache = cache.age_label(age)
            cached.detail = result.detail
            return cached

    return result


def run_all(query, limit=100, only=None, use_cache=True):
    names = [n for n in available() if not only or n in only]
    return [run(n, query, limit, use_cache=use_cache) for n in names]


