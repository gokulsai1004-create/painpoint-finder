"""
The verdict: is this problem real, and if not, what is?

Two numbers matter. How many posts matched, and out of how many. Seven matches
sounds like something until you learn it was seven out of nine hundred and
sixty-three, at which point it is the answer to a different question.

The second half is the part that saved this project's own author a week: when
a search comes back thin, the posts that did NOT match are still evidence. They
are people in the same space talking about something else, and that something
else is usually louder than what you went looking for.

No model involved. Word frequency and pair frequency, which is enough to name
a theme even if it cannot judge one.
"""

import re
from collections import Counter

from leads import COMMON, STOPWORDS, keywords

# Words that appear in every forum post regardless of topic. Counting them
# would make "just", "like" and "know" the top three themes of everything.
NOISE = STOPWORDS | COMMON | {
    # filler and hedging
    "like", "know", "knows", "known", "think", "thinks", "really", "even",
    "also", "still", "back", "going", "maybe", "probably", "actually",
    "pretty", "very", "quite", "little", "lot", "lots", "bit", "kind", "sort",
    "always", "never", "sometimes", "often", "usually", "already", "yet",
    # question words, prepositions and quantifiers - these form the junk pairs
    "how", "why", "what", "when", "where", "who", "which", "whose",
    "out", "there", "here", "over", "under", "into", "onto", "off",
    "many", "most", "some", "any", "all", "both", "each", "few", "other",
    "another", "same", "different", "several", "enough", "less", "least",
    # third person and archaic prose - the gap that produced "his own",
    # "she her", "upon them" and "now only" as the loudest rival themes of a
    # farming search. STOPWORDS covers first and second person and stops.
    "he", "him", "his", "she", "her", "hers", "them", "theirs",
    "itself", "himself", "herself", "themselves", "upon", "now", "may",
    "only", "own", "such",
    # people-in-general
    "guys", "anyone", "someone", "somebody", "everyone", "everybody",
    "nobody", "something", "anything", "everything", "nothing", "everyones",
    # common verbs that pair with anything
    "said", "says", "say", "tell", "told", "ask", "asked", "asking", "see",
    "saw", "seen", "look", "looking", "find", "found", "try", "tried",
    "trying", "take", "taking", "took", "put", "give", "given", "gave",
    "come", "coming", "came", "went", "goes", "gone", "run", "running",
    "made", "makes", "feel", "feels", "felt", "seems", "seem", "seemed",
    "got", "gets", "keep", "keeps", "let", "lets", "start", "started",
    "stop", "stopped", "end", "ends", "read", "reading", "write", "written",
    # judgement words with no topic content
    "sure", "right", "wrong", "better", "best", "worse", "worst", "great",
    "nice", "big", "small", "long", "short", "hard", "easy", "real", "true",
    "false", "yes", "please", "thanks", "thank", "sorry",
    # platform furniture
    "post", "posted", "posts", "comment", "comments", "reddit", "sub",
    "subreddit", "thread", "edit", "update", "hi", "hello", "hey",
    "https", "http", "www", "com", "amp", "quot", "nbsp", "removed",
    "deleted", "click", "link", "https www", "one", "two", "three",
    "first", "second", "last", "next", "since", "around", "every",
}

WORD = re.compile(r"[a-z][a-z']{2,}")

# Reddit bodies carry preview image links like
# https://preview.redd.it/x.png?width=633&format=png&auto=webp
# Left in, their query-string fragments become "top themes": real runs produced
# "auto webp", "format png" and "preview redd" as the things people were
# supposedly talking about. Strip URLs before any counting.
URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def _words(text):
    text = URL.sub(" ", text)
    return [w for w in WORD.findall(text.lower()) if w not in NOISE]


def _stem(word):
    """Crudest useful stemmer: enough to see that "students" and "student" are
    the same word.

    Without this the query leaks straight back into the themes. A search for
    "students struggle" reported "student struggling" as the top thing people
    were talking about INSTEAD - 45 hits, first in the list, and it was the
    query wearing different endings.

    Deliberately not a real stemmer. This only has to collapse plurals and
    common verb endings well enough to compare two words, and a dependency
    would cost more than it is worth.
    """
    base = word
    for suffix in ("ingly", "edly", "ing", "ies", "ied", "es", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            base = word[: -len(suffix)]
            # "ies" -> "y" so "companies" and "company" agree
            if suffix in ("ies", "ied"):
                return base + "y"
            break

    # Then drop a trailing "e", or the endings disagree with each other:
    # "struggling" strips to "struggl" while "struggle" stays whole, and
    # "refuses" strips to "refus" while "refuse" stays whole. Both pairs are
    # the same word and must land on the same stem.
    if base.endswith("e") and len(base) >= 4:
        base = base[:-1]

    return base


# Above this length, two identical bodies are one piece of writing that was
# cross-posted, not two people who happened to agree.
CROSSPOST_BODY_CHARS = 200


def themes(posts, query_terms, top=6, min_count=3):
    """What the non-matching posts are actually about.

    Pairs are preferred over single words because "getting paid" says something
    and "paid" barely does. Single words fill in only when there are not enough
    pairs to be useful.
    """
    # Compared on stems, so "students" in the query also excludes "student"
    # and "struggle" also excludes "struggling". Matching on exact words let
    # the query reappear as the top alternative to itself.
    query_stems = {_stem(t) for t in query_terms}

    pair_counts = Counter()
    word_counts = Counter()

    # One story, cross-posted, must not vote twenty-one times.
    #
    # "The Fangs of Dracula XX" is 27,294 characters of vampire fiction posted
    # to twenty-one subreddits with identical text. It matched a query about
    # farmers and harvest prices because a document that long contains almost
    # any word, and then supplied the six loudest "rival themes" in the run:
    # "eyes filled", "door open", "power living". rank() dedups cross-posts,
    # but themes runs over the posts rank REJECTED, where nothing had.
    #
    # Hashed on the body rather than the URL, because the twenty-one copies are
    # twenty-one different URLs and one piece of writing.
    #
    # Only long bodies. Two people typing "same here" or "this happened to me
    # too" are two people, and collapsing them would quietly under-count the
    # agreement that makes a theme worth reading. Nobody writes the same
    # paragraph twice by coincidence.
    seen_bodies = set()

    for post in posts:
        # Repositories do not have opinions. A restaurant-rota search reported
        # "menu management", "user friendly" and "option available" as the
        # loudest rival themes - that is README and issue-template boilerplate
        # from other people's restaurant apps, and presenting it as "what
        # everyone is talking about instead" points the reader at vocabulary
        # rather than at a problem. This block exists to surface the pain
        # nobody has named yet, and only humans write that.
        if post.source.startswith("github"):  # issues and repos alike
            continue

        body = post.body.strip()
        if len(body) >= CROSSPOST_BODY_CHARS:
            fingerprint = hash(body)
            if fingerprint in seen_bodies:
                continue
            seen_bodies.add(fingerprint)

        words = _words(post.text())
        # A post repeating a word twenty times should not outvote twenty posts
        # mentioning it once, so each post contributes each term at most once.
        seen_pairs, seen_words = set(), set()

        for a, b in zip(words, words[1:]):
            # A pair containing any query word is the same topic restated, not
            # an alternative to it. "prevent scope" is not what people are
            # talking about INSTEAD of scope.
            if _stem(a) in query_stems or _stem(b) in query_stems:
                continue
            seen_pairs.add(f"{a} {b}")

        for w in words:
            if _stem(w) not in query_stems:
                seen_words.add(w)

        pair_counts.update(seen_pairs)
        word_counts.update(seen_words)

    found = [(p, n) for p, n in pair_counts.most_common(40) if n >= min_count]

    if len(found) < top:
        # Not enough repeated pairs to describe the space. Fall back to single
        # words, which are weaker but better than showing nothing.
        singles = [(w, n) for w, n in word_counts.most_common(40)
                   if n >= min_count and not any(w in p for p, _ in found)]
        found.extend(singles)

    return found[:top]


# Below this, a "match" shares words with the query but is not about the same
# thing. Calibrated against real runs: a genuine client-payment complaint scored
# 0.76, a care client refusing dentures 0.66, a car lease 0.50.
WEAK_SIMILARITY = 0.62

LEVELS = ["NONE", "WEAK", "MODERATE", "STRONG"]


def _downgrade(signal, steps=1):
    if signal not in LEVELS:
        return signal
    return LEVELS[max(0, LEVELS.index(signal) - steps)]


def summarise(results, leads, pages, terms, builders=()):
    """Everything the user needs to judge the answer, as plain data.

    Builders count as matches. They are not leads - nobody wants a pain
    interview from a stranger while they are selling the cure - but they are
    posts about this exact problem, and leaving them out would understate the
    rate AND let them leak into the themes as "what everyone is talking about
    instead". A restaurant-rota search reported "menu management" and "user
    friendly" as rival themes; that was the README vocabulary of the very
    competitors it had just found.
    """
    usable = [r for r in results if r.usable]
    total_searched = sum(r.searched for r in usable)
    matched = len(leads) + len(builders) + len(pages)

    all_posts = [p for r in usable for p in r.posts]
    matched_urls = {e["post"].url for e in list(leads) + list(builders) + list(pages)}
    unmatched = [p for p in all_posts if p.url not in matched_urls]

    # Ratio, not count. Seven means nothing without the denominator.
    rate = (matched / total_searched) if total_searched else 0.0

    if total_searched == 0:
        signal = "UNKNOWN"
    elif matched == 0:
        signal = "NONE"
    elif rate < 0.02:
        signal = "WEAK"
    elif rate < 0.08:
        signal = "MODERATE"
    else:
        signal = "STRONG"

    # Count alone is not the answer. A heavy-industry search matched 4 of 123
    # posts and reported MODERATE - "worth a conversation" - when the top result
    # was a nine-year-old photo. Quantity said yes; quality said no, and the
    # verdict only asked quantity.
    sims = [e["similarity"] for e in list(leads) + list(builders) + list(pages)
            if "similarity" in e]
    quality = None
    caveat = ""

    if sims:
        quality = sorted(sims)[len(sims) // 2]  # median, so one good hit cannot carry it
        if quality < WEAK_SIMILARITY and signal not in ("UNKNOWN", "NONE"):
            signal = _downgrade(signal)
            caveat = ("matches share words with your query but are mostly "
                      "about something else")

    # Nobody to reply to is a ceiling on how strong this can be, whatever the
    # count says. Leads are the product; pages are consolation.
    if not leads and signal in ("MODERATE", "STRONG"):
        signal = "WEAK"
        if builders:
            # A different situation entirely, and it deserves different words:
            # the space is not quiet, it is taken. Telling someone "nothing to
            # reply to" when the answer is "everyone here is a competitor"
            # would hide the finding that matters most.
            caveat = caveat or ("everyone posting about this is building it, "
                                "not living it - no customers found, only rivals")
        else:
            caveat = caveat or ("nothing recent enough to reply to - only pages "
                                "and old posts")

    return {
        "searched": total_searched,
        "matched": matched,
        "people": len(leads),
        "builders": len(builders),
        "pages": len(pages),
        "rate": rate,
        "signal": signal,
        "quality": quality,
        "caveat": caveat,
        "themes": themes(unmatched, terms) if unmatched else [],
    }


def explain(signal, rate, searched, caveat=""):
    """One honest sentence about what the number means."""
    if signal == "UNKNOWN":
        return "Nothing was searched, so there is no signal either way."
    if signal == "NONE":
        return (f"Nobody in {searched} posts is describing this. That is real "
                "evidence, though only for the places searched.")

    if signal == "WEAK":
        base = (f"{rate * 100:.1f}% of posts matched. That is thin - the same "
                "range that killed this tool's own first idea.")
    elif signal == "MODERATE":
        base = f"{rate * 100:.1f}% of posts matched. Enough to be worth a conversation."
    else:
        base = (f"{rate * 100:.1f}% of posts matched. People are actively "
                "talking about this.")

    # The downgrade reason matters more than the label. "WEAK" alone invites a
    # shrug; "WEAK because the matches are about something else" tells you your
    # query is wrong rather than your idea.
    if caveat:
        base += f" Downgraded: {caveat}."
    return base
