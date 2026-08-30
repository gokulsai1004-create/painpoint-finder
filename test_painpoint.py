"""
Tests for the parts that decide what the user sees.

Everything here runs offline. The network paths are covered by asserting on
the shapes they return rather than by calling them, because a test that needs
Reddit to be up is a test that fails for reasons that are not bugs.

Run:  py -3 test_painpoint.py
"""

import unittest

import leads
import verdict
from sources import BLOCKED, ERROR, OK, Post, Result


def post(title="", body="", author="a", url="u", age_days=1, contactable=True):
    import time
    return Post(
        source="test", title=title, body=body, url=url, author=author,
        created_utc=time.time() - age_days * 86400, contactable=contactable,
    )


class TestKeywords(unittest.TestCase):

    def test_drops_stopwords_and_short_words(self):
        self.assertEqual(
            leads.keywords("the client is not paying me"),
            ["client", "paying"],
        )

    def test_phrases_are_adjacent_pairs_in_order(self):
        self.assertEqual(
            leads.phrases("client refuses to pay for revisions"),
            ["client refuses", "refuses pay", "pay revisions"],
        )

    def test_negation_detected(self):
        self.assertTrue(leads.has_negation("not getting paid"))
        self.assertTrue(leads.has_negation("client won't pay"))
        self.assertFalse(leads.has_negation("unpaid revisions"))


class TestScoring(unittest.TestCase):
    """The gate matters more than the arithmetic. A post about the wrong thing
    scoring zero is the difference between a lead and a waste of the user's
    afternoon."""

    TERMS = ["freelancers", "getting", "paid", "extra", "work"]

    def test_common_words_alone_score_nothing(self):
        # The real bug this encodes: a car-lease post matched "getting, paid,
        # extra, work" and scored 94, beating actual freelancer posts.
        car = post(title="Considering a lease",
                   body="I would be getting it paid off with extra work hours.")
        points, _ = leads.score(car, self.TERMS)
        self.assertEqual(points, 0)

    def test_distinctive_word_admits_the_post(self):
        real = post(title="Freelancers, how do you handle this",
                    body="I am a freelancer and my client wants extra work free.")
        points, hits = leads.score(real, self.TERMS)
        self.assertGreater(points, 0)
        self.assertIn("freelancers", hits)

    def test_phrase_match_outweighs_loose_words(self):
        terms = ["client", "refuses", "pay"]
        pairs = ["client refuses", "refuses pay"]
        loose = post(title="A note", body="the client and the pay and refuses")
        tight = post(title="A note", body="my client refuses to pay me")
        self.assertGreater(
            leads.score(tight, terms, pairs)[0],
            leads.score(loose, terms, pairs)[0],
        )

    def test_launch_posts_are_penalised(self):
        plain = post(title="Freelancers and unpaid work",
                     body="My client keeps asking for extra work.")
        promo = post(title="Freelancers and unpaid work",
                     body="I built a free tool for this. Feedback wanted! "
                          "My client keeps asking for extra work.")
        self.assertLess(
            leads.score(promo, self.TERMS)[0],
            leads.score(plain, self.TERMS)[0],
        )

    def test_relevance_beats_recency(self):
        # An exactly-relevant post from months ago must outrank an irrelevant
        # one from this minute, or "sort by new" quietly becomes the ranking.
        old_relevant = post(title="Freelancers not getting paid",
                            body="I am a freelancer doing extra work unpaid.",
                            age_days=120)
        new_thin = post(title="Freelancers", body="freelancers", age_days=0)
        self.assertGreater(
            leads.score(old_relevant, self.TERMS)[0],
            leads.score(new_thin, self.TERMS)[0],
        )


class TestQuoting(unittest.TestCase):

    def test_quote_is_verbatim_from_the_post(self):
        body = "Some preamble here. My client refuses to pay for the revisions."
        p = post(title="Help", body=body)
        quote = leads.best_quote(p, ["client", "refuses", "pay", "revisions"])
        self.assertIn(quote, p.text())

    def test_draft_contains_the_quote_and_asks_something(self):
        p = post(title="Help",
                 body="My client refuses to pay for the revisions I did.")
        draft = leads.draft(p, ["client", "refuses", "pay"])
        self.assertIn("client refuses to pay", draft)
        self.assertIn("?", draft)

    def test_draft_never_pitches(self):
        p = post(title="Help", body="My client refuses to pay for revisions.")
        draft = leads.draft(p, ["client", "refuses"]).lower()
        for word in ("i built", "my tool", "check out", "try it", "sign up"):
            self.assertNotIn(word, draft)


class TestRanking(unittest.TestCase):

    def _results(self, posts):
        return [Result("test", OK, posts=posts, searched=len(posts))]

    def test_crosspost_shown_once(self):
        a = post(title="Client refuses to pay", body="freelancer here", url="u1")
        b = post(title="Client refuses to pay", body="freelancer here", url="u2")
        people, _, _ = leads.rank(self._results([a, b]), "client refuses pay")
        self.assertEqual(len(people), 1)

    def test_pages_separated_from_people_and_get_no_draft(self):
        person = post(title="Client refuses to pay", body="me too", url="u1")
        page = post(title="Client refuses to pay: a guide", body="advice",
                    url="u2", contactable=False)
        people, pages, _ = leads.rank(self._results([person, page]),
                                      "client refuses pay")
        self.assertEqual(len(people), 1)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["draft"], "")
        self.assertNotEqual(people[0]["draft"], "")

    def test_blocked_source_contributes_nothing(self):
        results = [Result("test", BLOCKED, detail="rate-limited")]
        people, pages, _ = leads.rank(results, "client refuses pay")
        self.assertEqual((people, pages), ([], []))


class TestVerdict(unittest.TestCase):
    """The status distinction is the whole safety property of this tool: a
    source that could not look must never read as 'nobody has this problem'."""

    def test_blocked_is_not_usable(self):
        self.assertFalse(Result("s", BLOCKED).usable)
        self.assertFalse(Result("s", ERROR).usable)
        self.assertTrue(Result("s", OK).usable)

    def test_no_searchable_source_gives_unknown_not_none(self):
        summary = verdict.summarise([Result("s", BLOCKED, detail="x")], [], [], [])
        self.assertEqual(summary["signal"], "UNKNOWN")

    def test_zero_matches_from_a_real_search_is_none(self):
        posts = [post(title="unrelated", body="nothing here") for _ in range(50)]
        results = [Result("s", OK, posts=posts, searched=50)]
        summary = verdict.summarise(results, [], [], ["freelancers"])
        self.assertEqual(summary["signal"], "NONE")

    def test_signal_uses_the_ratio_not_the_count(self):
        # 7 matches out of 900 is weak; 7 out of 20 is strong. Same numerator.
        many = [Result("s", OK, posts=[], searched=900)]
        few = [Result("s", OK, posts=[], searched=20)]
        seven = [{"post": post(url=f"u{i}")} for i in range(7)]
        self.assertEqual(verdict.summarise(many, seven, [], [])["signal"], "WEAK")
        self.assertEqual(verdict.summarise(few, seven, [], [])["signal"], "STRONG")

    def test_explain_is_a_sentence_for_every_signal(self):
        for signal in ("UNKNOWN", "NONE", "WEAK", "MODERATE", "STRONG"):
            text = verdict.explain(signal, 0.03, 100)
            self.assertTrue(text.endswith(".") or text.endswith("]"))
            self.assertGreater(len(text), 20)


class TestThemes(unittest.TestCase):

    def test_query_words_excluded_from_themes(self):
        posts = [post(body="scope creep is ruining my margins") for _ in range(5)]
        found = verdict.themes(posts, ["scope", "creep"], min_count=2)
        for phrase, _ in found:
            self.assertNotIn("scope", phrase)
            self.assertNotIn("creep", phrase)

    def test_grammar_fragments_filtered_out(self):
        posts = [post(body="how many people know what everyone said")
                 for _ in range(5)]
        found = verdict.themes(posts, [], min_count=2)
        phrases = [p for p, _ in found]
        for junk in ("how many", "everyone said", "many people"):
            self.assertNotIn(junk, phrases)

    def test_urls_are_not_themes(self):
        # Real runs reported "auto webp", "format png" and "preview redd" as
        # what people were talking about. Those are Reddit image-link query
        # strings, not topics.
        body = ("Client wont pay. https://preview.redd.it/a.png?width=633"
                "&format=png&auto=webp and more about payment terms")
        posts = [post(body=body, url=f"u{i}") for i in range(5)]
        phrases = [p for p, _ in verdict.themes(posts, [], min_count=2)]
        for junk in ("auto webp", "format png", "preview redd", "png width"):
            self.assertNotIn(junk, phrases)

    def test_one_ranting_post_cannot_outvote_many(self):
        ranter = post(body=" ".join(["invoice dispute"] * 40))
        others = [post(body="payment terms matter") for _ in range(4)]
        found = dict(verdict.themes([ranter] + others, [], min_count=2))
        self.assertNotIn("invoice dispute", found)
        self.assertIn("payment terms", found)


class TestCache(unittest.TestCase):
    """The cache exists to rescue a rate-limited run. It must never rescue one
    by pretending stale data is fresh, and it must never cache a failure."""

    def setUp(self):
        import cache
        self.cache = cache
        self.query = f"cache test {id(self)}"

    def tearDown(self):
        for source in ("t_ok", "t_blocked", "t_error", "t_fail"):
            path = self.cache._path(source, self.query)
            if path.exists():
                path.unlink()

    def _ok(self, source):
        return Result(source, OK, posts=[post(title="T", url="u1")], searched=1)

    def test_round_trip(self):
        self.cache.save(self._ok("t_ok"), self.query)
        got, age = self.cache.load("t_ok", self.query)
        self.assertIsNotNone(got)
        self.assertEqual(len(got.posts), 1)
        self.assertLess(age, 60)

    def test_failures_are_never_cached(self):
        # Caching a rate-limit would serve the failure back for 30 minutes.
        self.cache.save(Result("t_fail", BLOCKED, detail="429"), self.query)
        got, _ = self.cache.load("t_fail", self.query)
        self.assertIsNone(got)

    def test_blocked_source_falls_back_and_is_labelled(self):
        import sources
        self.cache.save(self._ok("t_blocked"), self.query)
        sources.register("t_blocked",
                         lambda q, limit: Result("t_blocked", BLOCKED, detail="429"))
        result = sources.run("t_blocked", self.query)
        self.assertTrue(result.usable)
        # Unlabelled cached data would be the tool lying about its evidence.
        self.assertTrue(result.from_cache)

    def test_errored_source_does_not_fall_back(self):
        # An ERROR may mean the source changed shape. Serving old data would
        # hide a real break behind a stale success.
        import sources
        self.cache.save(self._ok("t_error"), self.query)
        sources.register("t_error",
                         lambda q, limit: Result("t_error", ERROR, detail="broke"))
        result = sources.run("t_error", self.query)
        self.assertFalse(result.usable)

    def test_expired_entry_is_a_miss(self):
        import json
        import time as _t
        self.cache.save(self._ok("t_ok"), self.query)
        path = self.cache._path("t_ok", self.query)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["saved_at"] = _t.time() - self.cache.TTL_SECONDS - 10
        path.write_text(json.dumps(payload), encoding="utf-8")
        got, _ = self.cache.load("t_ok", self.query)
        self.assertIsNone(got)

    def test_long_queries_do_not_collide(self):
        # The bug this encodes: an 80-character slug meant two long queries
        # sharing a prefix got one file, and the second search was handed the
        # first one's posts labelled as cached.
        base = ("freelance designers who lose money on unpaid revision rounds "
                "with difficult clients in agency work ")
        self.assertNotEqual(
            self.cache._key("reddit", base + "alpha"),
            self.cache._key("reddit", base + "beta"),
        )

    def test_punctuation_does_not_collide(self):
        self.assertNotEqual(
            self.cache._key("reddit", "client-refuses-pay"),
            self.cache._key("reddit", "client refuses pay"),
        )

    def test_query_normalised_so_spacing_and_case_share_an_entry(self):
        self.cache.save(self._ok("t_ok"), "Client  REFUSES to Pay")
        got, _ = self.cache.load("t_ok", "client refuses to pay")
        self.assertIsNotNone(got)
        self.cache._path("t_ok", "client refuses to pay").unlink()


class TestSemantic(unittest.TestCase):
    """Reranking is optional. The tool must work identically without it, and
    must never fail because of it."""

    def setUp(self):
        import semantic
        self.semantic = semantic

    def test_blend_prefers_topic_over_keyword_overlap(self):
        # The dentures post shared "client" and "refuses" with the query and
        # was ranked second. High keyword score plus low similarity must lose
        # to the reverse.
        off_topic = self.semantic.blend(keyword_score=150, similarity=0.50,
                                        max_keyword=150)
        on_topic = self.semantic.blend(keyword_score=80, similarity=0.78,
                                       max_keyword=150)
        self.assertGreater(on_topic, off_topic)

    def test_blend_handles_zero_max_without_dividing_by_zero(self):
        self.assertIsInstance(
            self.semantic.blend(0, 0.5, max_keyword=0), int)

    def test_empty_input_returns_empty_not_none(self):
        # None means "could not rerank"; [] means "nothing to rerank". Callers
        # branch on that difference.
        self.assertEqual(self.semantic.similarities("q", []), [])

    def test_ranking_works_with_semantic_disabled(self):
        results = [Result("t", OK,
                          posts=[post(title="Client refuses to pay",
                                      body="freelancer here", url="u1")],
                          searched=1)]
        people, pages, terms = leads.rank(results, "client refuses pay",
                                          semantic_on=False)
        self.assertEqual(len(people), 1)
        self.assertNotIn("reranked", people[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
