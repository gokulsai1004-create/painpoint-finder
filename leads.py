"""
Turning raw posts into leads: people worth talking to, and something to say.

Two jobs here. Rank the posts by how likely it is that this person actually has
the problem, and draft an opener that quotes them rather than pitching at them.

The drafting is deliberately template-based for now. A model would write better
prose, but the shape matters more than the prose: lead with their words, ask one
question, do not sell. A template enforces that shape every single time, which
a model has to be persuaded into.
"""

import re
import time

# Words that carry no signal about whether a post matches a problem.
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "for", "with", "without", "to", "of",
    "in", "on", "at", "is", "are", "was", "were", "be", "been", "being", "it",
    "its", "this", "that", "these", "those", "i", "my", "me", "we", "our",
    "you", "your", "they", "their", "not", "no", "do", "does", "did", "have",
    "has", "had", "can", "could", "would", "should", "will", "just", "get",
    "got", "as", "if", "so", "than", "then", "about", "from", "by", "up",
}

# Someone describing a problem happening TO them is a better lead than someone
# writing a guide about it. These are the phrases that separate the two.
FIRST_PERSON = re.compile(
    r"\b(i|my|we|our)\b.{0,40}\b(problem|issue|struggl|stuck|lost|losing|"
    r"can't|cannot|hate|tired|frustrat|annoy|worried|scared|help)",
    re.IGNORECASE,
)

# Advice content dressed as experience. Ranked down, not excluded, because the
# line is genuinely blurry and a false exclusion loses a real person.
ADVICE_MARKERS = re.compile(
    r"\b(\d+\s+(tips|ways|lessons|things)|ultimate guide|how to |thread:|"
    r"bookmark this|here's what i learned)\b",
    re.IGNORECASE,
)

# Someone launching a product mentions the pain in order to sell against it.
# They are not a lead - they are a competitor. This costs a real lead
# occasionally (people do build things because they felt the pain), which is
# why it is a heavy penalty rather than an exclusion.
PROMO_MARKERS = re.compile(
    r"\b(built (a|an|this|my)|i made|i built|made a|launching|just launched|"
    r"feedback wanted|check out my|introducing|my (new )?(tool|app|saas|product)|"
    r"free tool|beta testers|show hn)\b",
    re.IGNORECASE,
)


def keywords(query):
    """The words from a query that actually carry meaning."""
    words = re.findall(r"[a-z']+", query.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


# Words common enough that matching them says nothing about the topic. Not
# stopwords - they are meaningful in a query - but a post containing "work" is
# not thereby about your problem.
COMMON = {
    "work", "working", "job", "jobs", "time", "money", "paid", "pay", "paying",
    "getting", "people", "make", "making", "need", "want", "help", "good",
    "bad", "new", "old", "extra", "more", "much", "problem", "issue", "use",
    "using", "used", "way", "ways", "thing", "things", "day", "days", "year",
}


# Words that flip a query's meaning. Keyword matching cannot represent them:
# "not getting paid" and "getting paid" reduce to the same terms, which are
# opposite problems. Detected so the tool can say so rather than quietly
# returning the inverse of what was asked.
NEGATIONS = re.compile(
    r"\b(not|never|without|cant|can't|cannot|won't|wont|didn't|didnt|"
    r"doesn't|doesnt|no longer|refuse[ds]?|fail(ed|s|ing)?|unable)\b",
    re.IGNORECASE,
)


def has_negation(query):
    return bool(NEGATIONS.search(query))


def phrases(query):
    """Adjacent word pairs from the query, stopwords removed but order kept.

    "not getting paid for extra work" gives "getting paid" and "extra work".
    Loose keywords find the subject; pairs find the problem. Without this a
    query about unpaid work matches any post that says "work" and "paid" in
    different paragraphs about different things.
    """
    words = re.findall(r"[a-z']+", query.lower())
    kept = [w for w in words if w not in STOPWORDS and len(w) > 2]
    return [f"{a} {b}" for a, b in zip(kept, kept[1:])]


def essential(terms):
    """The terms a post must contain to be about this topic at all.

    A query for "freelancers not getting paid for extra work" is ABOUT
    freelancers. A car-lease post matching "getting, paid, extra, work" is not
    a lead, however many common words it hits. The distinctive words are the
    subject; the rest are grammar.
    """
    distinctive = [t for t in terms if t not in COMMON]
    return distinctive or terms  # never leave a query with nothing required


def score(post, terms, pairs=()):
    """How likely is it that this person has the problem, 0 upward.

    Deliberately simple and inspectable. Every point is explainable to the user,
    which matters more than accuracy here: a lead you do not understand is a
    lead you will not act on.
    """
    text = post.text().lower()
    hits = [t for t in terms if t in text]
    if not hits:
        return 0, []

    # Gate first. Without a distinctive term this post is about something else,
    # no matter how many common words line up.
    required = essential(terms)
    if not any(t in text for t in required):
        return 0, []

    # Rare words are worth far more than common ones. Matching "freelancers"
    # says what the post is about; matching "work" says almost nothing.
    points = sum(20 if t not in COMMON else 3 for t in hits)

    # A phrase match is worth more than both its words separately, because word
    # order is most of what separates "getting paid" from a post that happens to
    # contain "paid" and "getting" in unrelated sentences.
    matched_pairs = [p for p in pairs if p in text]
    points += len(matched_pairs) * 45

    # A title match means the problem is what the post is ABOUT, not a passing
    # mention buried in paragraph nine.
    title = post.title.lower()
    points += sum(15 if t not in COMMON else 2 for t in terms if t in title)

    if FIRST_PERSON.search(post.text()):
        points += 25

    if ADVICE_MARKERS.search(post.text()):
        points -= 20

    if PROMO_MARKERS.search(post.text()):
        points -= 60

    # Recency matters, but it must never outrank relevance: someone from six
    # months ago with the exact problem beats someone from this minute without
    # it. Capped low for that reason.
    age_days = max((time.time() - (post.created_utc or 0)) / 86400, 0)
    if age_days < 400:
        points += int(12 * (0.5 ** (age_days / 45)))

    return points, hits


def best_quote(post, terms):
    """The sentence from their post that best shows they have the problem.

    Returned verbatim, because the whole point of the draft is that it quotes
    them. Paraphrasing someone back at them is how you sound like a bot.
    """
    text = re.sub(r"\s+", " ", post.text()).strip()
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)

    best, best_hits = "", 0
    for s in sentences:
        s = s.strip()
        if not (25 <= len(s) <= 220):
            continue
        hits = sum(1 for t in terms if t in s.lower())
        if hits > best_hits:
            best, best_hits = s, hits

    return best


def age_label(created_utc):
    if not created_utc:
        return "unknown age"
    hours = (time.time() - created_utc) / 3600
    if hours < 1:
        return "just now"
    if hours < 48:
        return f"{int(hours)}h ago"
    days = hours / 24
    if days < 60:
        return f"{int(days)}d ago"
    return f"{int(days / 30)}mo ago"


def draft(post, terms):
    """An opener that quotes them and asks one question.

    Three rules, encoded in the template so they cannot be forgotten:
    open with their words, ask exactly one thing, sell nothing.
    """
    quote = best_quote(post, terms)

    if quote:
        opener = f'You said: "{quote}"\n\n'
    else:
        # No clean sentence to quote. Name the post instead of pretending.
        opener = f'Read your post about {post.title.strip()[:80]}.\n\n'

    return (
        opener
        + "Curious about one thing, and I'm asking rather than selling: "
        + "how long had this been going on before it got bad enough to post about? "
        + "And did anything you tried actually help?"
    )


# A lead is someone who might answer you. Past a certain age they will not:
# they solved it, moved on, or abandoned the account. A real run for a heavy
# industry query returned a photo posted to r/pics 113 months ago as the top
# "person you can reply to", which is the tool promising something it cannot
# deliver. Old posts are still evidence the problem exists, so they are moved
# to the evidence list rather than dropped.
MAX_LEAD_AGE_DAYS = 550  # about eighteen months


def is_stale(post):
    if not post.created_utc:
        # No date at all. Web results are already non-contactable; anything
        # else undated cannot be judged, so treat it as evidence not a lead.
        return True
    return (time.time() - post.created_utc) / 86400 > MAX_LEAD_AGE_DAYS


def rank(results, query, limit=10, min_score=1, semantic_on=True):
    """All sources' posts, best leads first.

    Deduped on author plus title, not URL: a cross-post to five subreddits is
    five URLs and one person. Showing them five times would waste four of the
    leads and make the tool look broken.
    """
    terms = keywords(query)
    pairs = phrases(query)
    scored = []
    seen = set()

    for result in results:
        if not result.usable:
            continue
        for post in result.posts:
            fingerprint = (post.author.lower(), post.title.strip().lower())
            if fingerprint in seen:
                continue

            points, hits = score(post, terms, pairs)
            if points >= min_score:
                seen.add(fingerprint)
                scored.append({
                    "post": post,
                    "score": points,
                    "matched": hits,
                    "quote": best_quote(post, terms),
                    # A page has nobody to reply to, so drafting one would be
                    # theatre. Left empty rather than faked.
                    "draft": draft(post, terms) if post.contactable else "",
                    "age": age_label(post.created_utc),
                })

    # Rerank on meaning where it is available. Keyword scores decide WHICH
    # posts are candidates; the embedding decides which of them are actually
    # about the same thing. Every false positive this tool produced - a car
    # lease, a wrestling thread, a care client refusing dentures - shared words
    # with the query and nothing else.
    if semantic_on and scored:
        import semantic

        sims = semantic.similarities(query, [s["post"].text() for s in scored])
        if sims is not None:
            top = max(s["score"] for s in scored)
            for entry, sim in zip(scored, sims):
                entry["similarity"] = sim
                entry["keyword_score"] = entry["score"]
                entry["score"] = semantic.blend(entry["score"], sim, top)
                entry["reranked"] = True

    scored.sort(key=lambda x: -x["score"])

    # People first, always. A page is evidence the topic exists; a person is
    # someone who can answer you, and answers are the point.
    #
    # Two ways to fail that promise: no author to reply to, or an author who
    # posted so long ago they will never see it. Both become evidence instead.
    people, pages = [], []
    for entry in scored:
        post_obj = entry["post"]
        if post_obj.contactable and not is_stale(post_obj):
            people.append(entry)
        else:
            entry["stale"] = post_obj.contactable  # a person, just too old
            pages.append(entry)

    return people[:limit], pages[:limit], terms
