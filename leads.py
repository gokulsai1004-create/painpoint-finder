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
# Job adverts drown any query about manual, industrial or shift work. A
# warehouse search returned "Forklift drivers" from r/houstonjobs as the top
# person to reply to, and the surrounding themes were "apply description",
# "per hour", "company date" - a corpus of adverts, not of problems.
#
# Someone hiring is not someone hurting. Same reasoning as the promo penalty:
# the poster is advertising past the pain, not describing it.
JOB_MARKERS = re.compile(
    # Bracketed tags. Reddit convention, and what automated job-board bots use:
    # both top leads for a warehouse query were titled "[HIRING] a Warehouse
    # Forklift Truck Driver". Matched outside the \b group because brackets are
    # not word characters.
    r"(\[\s*(hiring|for hire|job|jobs|recruiting|vacancy)\s*\]"
    # Formal postings
    r"|\b(now hiring|we'?re hiring|is hiring|are hiring|job description|"
    r"apply (now|online|here|today)|per hour|\$\d+\s*(/|per\s)\s*(hr|hour)|"
    r"hourly (pay|rate|wage)|full[- ]time|part[- ]time|send (your )?resume|"
    r"submit (your )?resume|job (id|posting|opening|title)|position available|"
    r"shifts? available|competitive (pay|salary|benefits)|"
    r"equal opportunity employer|benefits include"
    # Informal recruitment, which is what actually slipped through. A real post
    # read "we are in dire need of good forklift drivers ... if anyone is
    # interested" - no formal phrasing anywhere, and it ranked first.
    r"|if (anyone|you|you'?re|somebody|someone)\s+(is\s+|are\s+)?interested"
    r"|anyone\s+(is\s+)?interested"
    r"|in (dire |urgent )?need of(\s+\w+){0,3}\s+"
    r"(drivers?|workers?|staff|operators?|techs?|technicians?|hands?)"
    r"|dm me if|hit me up if|pm me if"
    r"|looking (for|to hire)(\s+\w+){0,3}\s+"
    r"(drivers?|workers?|staff|operators?|technicians?|candidates?|employees?))\b)",
    re.IGNORECASE,
)

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

    if JOB_MARKERS.search(post.text()):
        points -= 70

    # A post with no content describes no problem. Photo and link shares carry
    # a title and an empty body, and they keep surfacing as top leads for
    # physical-world queries: a cement kiln photo on r/pics, forklift machines
    # on a photography sub. Both matched perfectly and said nothing.
    #
    # Scaled rather than a cutoff, because a genuinely short cry for help
    # ("Client won't pay, what do I do?") is still a real person.
    substance = len(post.text().strip())
    if substance < SUBSTANCE_CHARS:
        points -= int(50 * (1 - substance / SUBSTANCE_CHARS))

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

# Below this much text, a post is almost always a photo or link share rather
# than someone describing a problem. Real complaints run to paragraphs; the two
# worst false leads this tool produced were 17 and 27 characters long.
SUBSTANCE_CHARS = 140

# A post with no body needs a title long enough to carry the problem on its
# own. Set above the two real false leads ("Cement Plant Kiln" at 17,
# "Warehouse forklift machines" at 27) and below a title that genuinely states
# a problem ("Client refuses to pay me and my dad for over 2 months of work"
# at 61).
BARE_TITLE_CHARS = 45

# How many candidates get the expensive semantic question. Comfortably more
# than anyone asks for (-n defaults to 5) so the reranker can still reorder
# meaningfully, small enough that a search stays under a minute.
RERANK_CANDIDATES = 40


def is_stale(post):
    if not post.created_utc:
        # No date at all. Web results are already non-contactable; anything
        # else undated cannot be judged, so treat it as evidence not a lead.
        return True
    return (time.time() - post.created_utc) / 86400 > MAX_LEAD_AGE_DAYS


def is_thin(post):
    """A photo or link share: nothing written, nothing to reply to.

    The two worst false leads this tool produced were exactly this shape -
    "Cement Plant Kiln" on r/pics and "Warehouse forklift machines" on a
    photography sub. Both matched their query perfectly and described nothing,
    because the content was an image.

    The signal is an EMPTY BODY with a SHORT title, not a short total. A
    title-only post can still be a real complaint if the title carries it:
    "Client refuses to pay me and my dad for over 2 months of work" says
    everything needed. "Cement Plant Kiln" says nothing. Length of the title is
    what separates them.

    A score penalty was the wrong tool for this. Semantic reranking weights
    topic at 65%, and a photo OF the subject is topically perfect, so any
    deduction washes out. This is the same question staleness asks: is there a
    person here to have a conversation with?
    """
    if post.body.strip():
        return False
    return len(post.title.strip()) < BARE_TITLE_CHARS


# Two posts by the same person this close together are one cross-post, whatever
# the titles say.
CROSSPOST_WINDOW_SECONDS = 30 * 60

# How much of a title must overlap, as a fraction of all the distinctive words
# in both, before two posts by one author count as the same thing. Measured on
# the real case: "How much freedom does your school give students" and "How much
# freedom does ur school / university give you?" share 0.71, while "Cement Plant
# Kiln shutdown" and "Cement kiln maintenance problem" share 0.20.
TITLE_SAME_RATIO = 0.6

# Within the cross-post window the bar drops, because posting twice in half an
# hour is itself evidence. It does not drop to zero: a person can have two
# genuinely different problems in one sitting, and collapsing those deletes a
# real lead the user never finds out existed.
TITLE_SAME_RATIO_NEARBY = 0.35


def _already_seen(post, seen):
    """Has this person already been surfaced?

    Matching on (author, exact title) was not enough. A real run returned
    "How much freedom does your school give students" and "How much freedom
    does ur school / university give you?" as two separate leads - same author,
    same question, reworded for a second subreddit. Messaging the same person
    twice is the fastest way to look like a bot.

    Titles are compared by their distinctive words rather than their exact text,
    so a reword does not read as a new person, and the bar for "same thing"
    drops when the two posts are minutes apart.

    Deliberately not collapsing every same-author post inside the window: an
    over-eager rule here deletes a real lead silently, while an under-eager one
    shows a duplicate the user can see and skip.
    """
    author = post.author.strip().lower()
    if not author:
        # No author to be duplicated. Fall back to the URL so identical pages
        # from two sources still collapse.
        key = ("", post.url)
        if key in seen:
            return True
        seen.add(key)
        return False

    for prior_author, prior_words, prior_time in list(seen):
        if prior_author != author:
            continue
        nearby = abs(post.created_utc - prior_time) <= CROSSPOST_WINDOW_SECONDS
        threshold = TITLE_SAME_RATIO_NEARBY if nearby else TITLE_SAME_RATIO
        # Jaccard rather than raw overlap - counting shared words alone called
        # "Cement Plant Kiln" and "Cement kiln maintenance problem" the same
        # post, because two words matched out of five distinct ones.
        words = _title_words(post.title)
        if words and prior_words:
            overlap = len(words & prior_words) / len(words | prior_words)
            if overlap >= threshold:
                return True

    seen.add((author, _title_words(post.title), post.created_utc))
    return False


def _title_words(title):
    """A title reduced to its distinctive words, as a frozen set."""
    words = re.findall(r"[a-z']+", title.lower())
    return frozenset(w for w in words if w not in STOPWORDS and len(w) > 2)


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
            points, hits = score(post, terms, pairs)
            if points >= min_score:
                # Deduped only among posts that actually qualify. Checking
                # earlier would let a person's junk post claim their slot and
                # hide their good one.
                if _already_seen(post, seen):
                    continue
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

        # Rerank a shortlist, not everything. Embedding runs on CPU and costs
        # real time per post: adding Stack Exchange pushed a single search to
        # over 850 posts, and the tool spent minutes embedding all of them to
        # choose five. Keyword scores are cheap and good enough to decide which
        # candidates deserve the expensive question, so only the best ones get
        # asked. The rest keep their keyword score and rank below, which is
        # where they were heading anyway.
        scored.sort(key=lambda x: -x["score"])
        shortlist = scored[:RERANK_CANDIDATES]

        sims = semantic.similarities(query, [s["post"].text() for s in shortlist])
        if sims is not None:
            top = max(s["score"] for s in shortlist)
            for entry, sim in zip(shortlist, sims):
                entry["similarity"] = sim
                entry["keyword_score"] = entry["score"]
                entry["score"] = semantic.blend(entry["score"], sim, top)
                entry["reranked"] = True

            # Reranked entries now score on a 0-1000 scale while the tail is
            # still on the raw keyword scale. Push the tail below them so the
            # two scales cannot interleave and produce a nonsense order.
            floor = min(e["score"] for e in shortlist)
            for entry in scored[RERANK_CANDIDATES:]:
                entry["score"] = min(entry["score"], floor - 1)

    scored.sort(key=lambda x: -x["score"])

    # People first, always. A page is evidence the topic exists; a person is
    # someone who can answer you, and answers are the point.
    #
    # Two ways to fail that promise: no author to reply to, or an author who
    # posted so long ago they will never see it. Both become evidence instead.
    people, pages = [], []
    for entry in scored:
        post_obj = entry["post"]
        stale, thin = is_stale(post_obj), is_thin(post_obj)

        if post_obj.contactable and not stale and not thin:
            people.append(entry)
        else:
            # Record WHY, because the reason changes what the reader does with
            # it: an old post still proves the problem existed, a photo proves
            # almost nothing.
            if post_obj.contactable:
                entry["why_not_lead"] = "too old" if stale else "nothing written"
            pages.append(entry)

    return people[:limit], pages[:limit], terms
