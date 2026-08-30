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
    """One thing somebody wrote, from any source."""
    source: str
    title: str
    body: str
    url: str
    author: str = ""
    created_utc: float = 0.0
    replies: int = 0

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

    @property
    def usable(self):
        return self.status == OK


_REGISTRY = {}


def register(name, fn):
    """Add a source. `fn(query, limit) -> Result`."""
    _REGISTRY[name] = fn


def available():
    return sorted(_REGISTRY)


def run(name, query, limit=100):
    """Run one source, converting an unexpected crash into an ERROR Result.

    A source that raises must not take the whole search down with it — the
    other sources may still have something useful, and a partial answer with
    honest coverage beats no answer.
    """
    fn = _REGISTRY[name]
    try:
        return fn(query, limit)
    except Exception as exc:  # noqa: BLE001 - deliberate boundary
        return Result(source=name, status=ERROR, detail=f"{type(exc).__name__}: {exc}")


def run_all(query, limit=100, only=None):
    names = [n for n in available() if not only or n in only]
    return [run(n, query, limit) for n in names]
