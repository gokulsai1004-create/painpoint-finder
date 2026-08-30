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
    # question words and quantifiers - these form the junk pairs
    "how", "why", "what", "when", "where", "who", "which", "whose",
    "many", "most", "some", "any", "all", "both", "each", "few", "other",
    "another", "same", "different", "several", "enough", "less", "least",
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


def _words(text):
    return [w for w in WORD.findall(text.lower()) if w not in NOISE]


def themes(posts, query_terms, top=6, min_count=3):
    """What the non-matching posts are actually about.

    Pairs are preferred over single words because "getting paid" says something
    and "paid" barely does. Single words fill in only when there are not enough
    pairs to be useful.
    """
    query_set = set(query_terms)

    pair_counts = Counter()
    word_counts = Counter()

    for post in posts:
        words = _words(post.text())
        # A post repeating a word twenty times should not outvote twenty posts
        # mentioning it once, so each post contributes each term at most once.
        seen_pairs, seen_words = set(), set()

        for a, b in zip(words, words[1:]):
            # A pair containing any query word is the same topic restated, not
            # an alternative to it. "prevent scope" is not what people are
            # talking about INSTEAD of scope.
            if a in query_set or b in query_set:
                continue
            seen_pairs.add(f"{a} {b}")

        for w in words:
            if w not in query_set:
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


def summarise(results, leads, pages, terms):
    """Everything the user needs to judge the answer, as plain data."""
    usable = [r for r in results if r.usable]
    total_searched = sum(r.searched for r in usable)
    matched = len(leads) + len(pages)

    all_posts = [p for r in usable for p in r.posts]
    matched_urls = {l["post"].url for l in leads} | {p["post"].url for p in pages}
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

    return {
        "searched": total_searched,
        "matched": matched,
        "people": len(leads),
        "pages": len(pages),
        "rate": rate,
        "signal": signal,
        "themes": themes(unmatched, terms) if unmatched else [],
    }


def explain(signal, rate, searched):
    """One honest sentence about what the number means."""
    if signal == "UNKNOWN":
        return "Nothing was searched, so there is no signal either way."
    if signal == "NONE":
        return (f"Nobody in {searched} posts is describing this. That is real "
                "evidence, though only for the places searched.")
    if signal == "WEAK":
        return (f"{rate * 100:.1f}% of posts matched. That is thin - the same "
                "range that killed this tool's own first idea.")
    if signal == "MODERATE":
        return f"{rate * 100:.1f}% of posts matched. Enough to be worth a conversation."
    return (f"{rate * 100:.1f}% of posts matched. People are actively talking "
            "about this.")
