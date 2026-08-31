"""
Optional semantic reranking, running entirely on your own machine.

Keyword matching finds posts containing your words. It cannot tell that a post
about a care client refusing to wear dentures is not about a client refusing to
pay an invoice, because both contain "client" and "refuses". Embeddings can:
they place text by meaning, so an off-topic post lands far away no matter how
many words it shares.

Measured against the false positives this tool actually produced, for the query
"freelance client refuses to pay for revisions":

    keyword rank        semantic rank
    1  car lease post    5
    2  dentures post     4
    1  real payment post 1

WHAT THIS DOES NOT FIX: negation. Embedding models rate "getting paid for extra
work" as the CLOSEST match to "not getting paid for extra work" - 0.906, higher
than anything else tested. This is a known weakness of the technique, not a bug
here, and the negation warning stays because of it.

Optional by design. No key, no account, no network after the first run - but a
50MB model download is a real cost to impose on someone who just wants to try
the tool, so everything degrades to keyword-only when fastembed is absent.
"""

import math
import sys

# Small, fast, CPU-only, quantised. Good enough for ranking short posts, and
# the download is small enough that a first run is not a wait people abandon.
MODEL = "BAAI/bge-small-en-v1.5"

# Longer text dilutes the embedding: a 4000-word post averages its meaning into
# mush. The opening is where someone states their problem; the rest is
# background, and "edit: thanks everyone".
#
# Also the single biggest cost in a run. Measured over 60 real posts averaging
# 914 characters: 900 chars took 46 seconds, 300 took 19. Ranking order was
# identical at both - a genuine payment complaint, a care client refusing
# dentures and a car lease sorted the same way - so the longer window was
# buying nothing but time.
MAX_CHARS = 300

_model = None
_unavailable = False


def available():
    """Whether reranking can run, without paying the import cost to find out."""
    global _unavailable
    if _model is not None:
        return True
    if _unavailable:
        return False
    try:
        import fastembed  # noqa: F401
        return True
    except ImportError:
        _unavailable = True
        return False


def _model_is_cached():
    """Best effort: has the model already been downloaded?

    Only used to decide whether to warn about a wait. Wrong in the cautious
    direction prints one unnecessary line; wrong in the other direction is the
    silent minute this exists to prevent, so anything uncertain counts as
    not cached.
    """
    import os
    import tempfile
    from pathlib import Path

    roots = []
    for var in ("FASTEMBED_CACHE_PATH", "HF_HOME"):
        if os.environ.get(var):
            roots.append(Path(os.environ[var]))
    roots += [
        Path(tempfile.gettempdir()) / "fastembed_cache",   # fastembed's default
        Path.home() / ".cache" / "fastembed",
        Path.home() / ".cache" / "huggingface",
    ]
    for root in roots:
        try:
            if root.exists() and any(root.glob("**/*bge-small-en*")):
                return True
        except OSError:
            continue
    return False


def _load():
    """Load once, lazily. Importing fastembed alone costs a second or two, and
    a user who never reaches ranking should never pay it."""
    global _model, _unavailable
    if _model is not None:
        return _model
    if _unavailable:
        return None
    try:
        # The first run downloads ~50MB and says nothing while it does. Someone
        # trying this for the first time sees the program stop dead after the
        # search and assumes it hung - the worst possible first impression, and
        # entirely avoidable with one line. Printed to stderr so it never
        # pollutes piped output.
        if not _model_is_cached():
            print("  Downloading the ranking model (~50MB, one time). This is "
                  "the only\n  network call after the search itself - every run "
                  "after this is offline.\n  Skip it with --no-semantic.",
                  file=sys.stderr, flush=True)

        from fastembed import TextEmbedding
        _model = TextEmbedding(MODEL)
        return _model
    except Exception:  # noqa: BLE001 - download failure, no disk, corrupt cache
        # Reranking is an enhancement. It must never be why a search fails.
        _unavailable = True
        return None


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def similarities(query, texts):
    """Cosine similarity of each text to the query, 0..1.

    Returns None when reranking is unavailable, so callers can tell "could not
    rerank" from "reranked and everything scored zero" - the same distinction
    the source layer makes between blocked and empty.
    """
    if not texts:
        return []

    model = _load()
    if model is None:
        return None

    trimmed = [t[:MAX_CHARS] for t in texts]
    try:
        vectors = list(model.embed([query] + trimmed))
    except Exception:  # noqa: BLE001 - runtime failure mid-embed
        return None

    if len(vectors) != len(trimmed) + 1:
        return None

    query_vec = vectors[0]
    return [_cosine(query_vec, v) for v in vectors[1:]]


def blend(keyword_score, similarity, max_keyword):
    """Combine the two signals.

    Neither alone is right. Embeddings judge topic well and intent badly: they
    cannot see that a post is someone launching a product rather than someone
    in pain, which the keyword layer catches with its promo and advice
    penalties. So topic comes from the embedding and intent from the keywords,
    weighted toward topic because that is where the false positives came from.
    """
    if max_keyword <= 0:
        normalised_keyword = 0.0
    else:
        normalised_keyword = min(keyword_score / max_keyword, 1.0)

    # Similarities for related text cluster in roughly 0.45-0.80, so raw values
    # compress the interesting range. Stretching it makes the gap between a real
    # match and a near-miss visible in the final ordering.
    stretched = max(0.0, (similarity - 0.40) / 0.45)
    stretched = min(stretched, 1.0)

    return int(1000 * (0.65 * stretched + 0.35 * normalised_keyword))
