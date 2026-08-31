"""
Tests for the parts that decide what the user sees.

Everything here runs offline. The network paths are covered by asserting on
the shapes they return rather than by calling them, because a test that needs
Reddit to be up is a test that fails for reasons that are not bugs.

Run:  python test_painpoint.py
"""

import sys
import time
import unittest

import leads
import verdict
from pathlib import Path

from sources import BLOCKED, ERROR, OK, Post, Result
from sources import web


_author_seq = [0]


def post(title="", body="", author=None, url="u", age_days=1, contactable=True):
    # Distinct authors by default. Sharing one author across fixtures made every
    # post look like a cross-post once author-based dedup landed.
    if author is None:
        _author_seq[0] += 1
        author = f"author{_author_seq[0]}"
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

    def test_job_adverts_are_penalised(self):
        # A warehouse query returned "Forklift drivers" from r/houstonjobs as
        # the top person to reply to. Someone hiring is not someone hurting,
        # and job boards flood any query about manual or shift work.
        terms = ["warehouse", "forklift", "drivers"]
        problem = post(title="Forklift drivers waiting hours at the dock",
                       body="Our warehouse forklift drivers wait for a dock "
                            "slot every morning and nothing moves.")
        advert = post(title="Forklift drivers",
                      body="Now hiring warehouse forklift drivers. $22 per "
                           "hour, full-time, benefits include health. Apply now.")
        self.assertLess(leads.score(advert, terms)[0],
                        leads.score(problem, terms)[0])

    def test_informal_job_adverts_are_caught(self):
        # The advert that actually slipped through had no formal phrasing at
        # all: no "now hiring", no rate, no "apply". Verbatim from r/houstonjobs.
        advert = ("Hey guys, at my company we are in dire need of good forklift "
                  "drivers that know the basic of technology, but better yet an "
                  "amazing forklift driver, this warehouse is located in "
                  "brookshire,Tx if anyone is interested.")
        self.assertTrue(leads.JOB_MARKERS.search(advert))

    def test_bracketed_hiring_tags_are_caught(self):
        # Automated job-board bots use these. Both top leads for a warehouse
        # query were titled "[HIRING] a Warehouse Forklift Truck Driver".
        for title in ("[HIRING] a Warehouse Forklift Truck Driver - Sharpak",
                      "[FOR HIRE] experienced forklift operator",
                      "[Job] Warehouse associate needed"):
            self.assertTrue(leads.JOB_MARKERS.search(title), title)

    def test_job_markers_do_not_catch_genuine_posts(self):
        # Over-matching here silently deletes real leads, which is worse than
        # letting an advert through: you never see what you lost.
        genuine = [
            "I am interested in solving this problem",
            "Looking for advice on unpaid invoices",
            "My client is looking for more revisions",
            "Our drivers wait forty minutes for a dock slot every morning",
            "I need advice about a client who refuses to pay",
        ]
        for text in genuine:
            self.assertIsNone(leads.JOB_MARKERS.search(text), text)

    def test_bodyless_photo_posts_rank_below_real_complaints(self):
        # Two real false leads: "Cement Plant Kiln" (17 chars) on r/pics and
        # "Warehouse forklift machines" (27 chars) on a photography sub. Both
        # matched the query perfectly and described nothing.
        terms = ["warehouse", "forklift", "drivers"]
        photo = post(title="Warehouse forklift machines", body="")
        real = post(title="Forklift drivers stuck waiting",
                    body="Every morning our warehouse forklift drivers wait "
                         "forty minutes for a dock slot to free up, and the "
                         "whole shift runs late because of it.")
        self.assertLess(leads.score(photo, terms)[0],
                        leads.score(real, terms)[0])

    def test_short_cry_for_help_is_not_over_penalised(self):
        # The penalty scales, so a genuinely brief but real post survives.
        terms = ["client", "pay"]
        brief = post(title="Client won't pay, what do I do?",
                     body="Three months of invoices ignored and I am stuck.")
        empty = post(title="Client pay", body="")
        self.assertGreater(leads.score(brief, terms)[0], 0)
        self.assertGreater(leads.score(brief, terms)[0],
                           leads.score(empty, terms)[0])

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



class TestIdeaShapedQueries(unittest.TestCase):
    """The query someone actually types.

    Whoever reaches for this tool has an IDEA - that is why they came. But the
    people with the pain never use a builder's words, so searching the idea
    verbatim finds other builders. A real run for "i wanna build a startup that
    helps students find internships" returned two people asking what to build
    next, matched on "wanna, build", plus a feature request on somebody's
    intern-hackathon repo. Three leads, zero sufferers, verdict WEAK.
    """

    def test_builder_framing_is_recognised(self):
        for q in ("i wanna build a startup that helps students find internships",
                  "I want to build an app for freelancers to track invoices",
                  "thinking about making a tool for nurses doing handover notes",
                  "an app for freelancers to track unpaid invoices",
                  "building a platform for cement plant maintenance teams"):
            self.assertTrue(leads.looks_like_an_idea(q), q)

    def test_a_real_complaint_is_left_alone(self):
        # The costly false positive. Rewriting a good query would search
        # something the user never asked for and never told them.
        for q in ("students cant get internships without experience",
                  "client refuses to pay for revisions",
                  "nurses are burning out from understaffed night shifts",
                  "my cement kiln shuts down every winter and nobody knows why"):
            self.assertFalse(leads.looks_like_an_idea(q), q)
            self.assertEqual(leads.problem_in(q), q)

    def test_the_problem_survives_the_strip(self):
        got = leads.problem_in(
            "i wanna build a startup that helps students find internships")
        for word in ("students", "internships"):
            self.assertIn(word, got)
        for word in ("wanna", "build", "startup"):
            self.assertNotIn(word, got)

    def test_solution_words_cannot_admit_a_post(self):
        # The exact failure: two leads scored on "wanna, build" alone. Someone
        # saying "startup" is not someone in pain.
        terms = leads.keywords(
            "i wanna build a startup that helps students find internships")
        self.assertNotIn("build", leads.essential(terms))
        self.assertNotIn("startup", leads.essential(terms))
        self.assertIn("internships", leads.essential(terms))

    def test_another_builder_no_longer_outranks_a_sufferer(self):
        terms = ["build", "startup", "students", "internships"]
        builder = post(title="Looking for my first project",
                       body="I wanna build a startup but dont know what. Any "
                            "ideas for what to build next?")
        sufferer = post(title="Cant land an internship anywhere",
                        body="Every internship wants students to already have "
                             "experience, so I cannot get the experience.")
        self.assertLess(leads.score(builder, terms)[0],
                        leads.score(sufferer, terms)[0])

    def test_a_query_of_pure_framing_still_searches(self):
        # Degrade, never break. "i wanna build an app" has no problem inside it,
        # so it is searched as written rather than as an empty string.
        q = "i wanna build an app"
        self.assertEqual(leads.problem_in(q), q)
        self.assertTrue(leads.essential(leads.keywords(q)))

class TestRanking(unittest.TestCase):

    def _results(self, posts):
        return [Result("test", OK, posts=posts, searched=len(posts))]

    def test_crosspost_shown_once(self):
        # One person, two subreddits. The author has to be spelled out here:
        # fixtures get distinct authors by default, and a crosspost is defined
        # by the author being the same.
        a = post(title="Client refuses to pay", body="freelancer here",
                 url="u1", author="same")
        b = post(title="Client refuses to pay", body="freelancer here",
                 url="u2", author="same")
        people, _, _, _ = leads.rank(self._results([a, b]), "client refuses pay")
        self.assertEqual(len(people), 1)

    def test_reworded_crosspost_shown_once(self):
        # The case that exposed the bug. One person posted the same question to
        # two subreddits minutes apart with a reworded title, and both slots in
        # the lead list went to him - the fastest way to look like a bot.
        a = post(title="How much freedom does your school give students",
                 body="I want to know how much freedom schools actually give.",
                 url="u1", author="TomZillaforLife")
        b = post(title="How much freedom does ur school / university give you?",
                 body="I want to know how much freedom schools actually give.",
                 url="u2", author="TomZillaforLife")
        people, _, _, _ = leads.rank(self._results([a, b]), "school freedom students")
        self.assertEqual(len(people), 1)

    def test_same_author_different_topic_both_kept(self):
        # The other half. Someone active in a niche posts about several distinct
        # problems, and collapsing those would silently delete real leads.
        a = post(title="Cement Plant Kiln shutdown every winter",
                 body="Our cement plant kiln shuts down and nobody can say why.",
                 url="u1", author="planthand")
        b = post(title="Cement kiln maintenance problem with the feed screw",
                 body="The feed screw on the cement kiln jams and maintenance "
                      "takes the whole line down for a day.",
                 url="u2", author="planthand")
        people, _, _, _ = leads.rank(self._results([a, b]), "cement kiln problem")
        self.assertEqual(len(people), 2)

    def test_authorless_and_authored_posts_can_coexist(self):
        # A crash, not a ranking flaw. `seen` held two key shapes - ("", url)
        # for posts with no author and (author, words, time) for posts with one
        # - and the comparison loop unpacked three values, so the first
        # authorless post followed by any authored one took down the search.
        #
        # It never fired live because the web source is the one whose posts
        # carry no author, and it was rate-limited every time this path ran.
        # A blocked source was hiding a crash.
        page = Post(source="web example.com", title="Client refuses to pay: a guide",
                    body="advice about clients who refuse to pay",
                    url="u1", author="", created_utc=time.time(), contactable=False)
        person = post(title="Client refuses to pay me",
                      body="Three months of invoices ignored and I am stuck.")
        people, _, pages, _ = leads.rank(
            [Result("test", OK, posts=[page, person], searched=2)],
            "client refuses pay", semantic_on=False)
        self.assertEqual(len(people), 1)
        self.assertEqual(len(pages), 1)

    def test_the_same_page_from_two_sources_collapses(self):
        # What the authorless branch is actually for.
        def page(source):
            return Post(source=source, title="Client refuses to pay: a guide",
                        body="advice about clients who refuse to pay",
                        url="same-url", author="", created_utc=time.time(),
                        contactable=False)
        _, _, pages, _ = leads.rank(
            [Result("test", OK, posts=[page("web a.com"), page("web b.com")],
                    searched=2)],
            "client refuses pay", semantic_on=False)
        self.assertEqual(len(pages), 1)

    def test_pages_separated_from_people_and_get_no_draft(self):
        person = post(title="Client refuses to pay", body="me too", url="u1")
        page = post(title="Client refuses to pay: a guide", body="advice",
                    url="u2", contactable=False)
        people, _, pages, _ = leads.rank(self._results([person, page]),
                                      "client refuses pay")
        self.assertEqual(len(people), 1)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["draft"], "")
        self.assertNotEqual(people[0]["draft"], "")

    def test_ancient_post_is_evidence_not_a_lead(self):
        # A real run for a heavy-industry query returned a photo posted to
        # r/pics 113 months ago as the top "person you can reply to". Nobody
        # answers a nine-year-old post.
        old = post(title="Cement Plant Kiln", body="cement kiln photo",
                   url="u1", age_days=3400)
        recent = post(title="Cement kiln maintenance problem",
                      body="our cement kiln keeps failing", url="u2",
                      age_days=20)
        people, _, pages, _ = leads.rank(self._results([old, recent]),
                                      "cement kiln maintenance",
                                      semantic_on=False)
        self.assertEqual([p["post"].url for p in people], ["u2"])
        self.assertEqual([p["post"].url for p in pages], ["u1"])
        self.assertEqual(pages[0]["why_not_lead"], "too old")

    def test_undated_post_is_not_a_lead(self):
        undated = post(title="Client refuses to pay", body="text", url="u1")
        undated.created_utc = 0
        people, _, pages, _ = leads.rank(self._results([undated]),
                                      "client refuses pay", semantic_on=False)
        self.assertEqual(people, [])
        self.assertEqual(len(pages), 1)

    def test_blocked_source_contributes_nothing(self):
        results = [Result("test", BLOCKED, detail="rate-limited")]
        people, _, pages, _ = leads.rank(results, "client refuses pay")
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

    def _entries(self, n, similarity):
        return [{"post": post(url=f"u{i}"), "similarity": similarity}
                for i in range(n)]

    def test_low_similarity_downgrades_the_signal(self):
        # A heavy-industry search matched 4 of 123 and reported MODERATE -
        # "worth a conversation" - when the top hit was a nine-year-old photo.
        # Quantity said yes, quality said no, and only quantity was asked.
        results = [Result("s", OK, posts=[], searched=100)]
        good = verdict.summarise(results, self._entries(5, 0.78), [], [])
        poor = verdict.summarise(results, self._entries(5, 0.50), [], [])
        self.assertEqual(good["signal"], "MODERATE")
        self.assertEqual(poor["signal"], "WEAK")
        self.assertIn("something else", poor["caveat"])

    def test_median_used_so_one_good_hit_cannot_carry_it(self):
        results = [Result("s", OK, posts=[], searched=100)]
        entries = self._entries(4, 0.45) + [{"post": post(url="star"),
                                             "similarity": 0.95}]
        summary = verdict.summarise(results, entries, [], [])
        self.assertLess(summary["quality"], verdict.WEAK_SIMILARITY)

    def test_no_contactable_leads_caps_the_signal(self):
        # Pages and stale posts are consolation. If nobody can be replied to,
        # the answer cannot be "worth a conversation" whatever the count says.
        results = [Result("s", OK, posts=[], searched=50)]
        summary = verdict.summarise(results, [], self._entries(10, 0.85), [])
        self.assertEqual(summary["signal"], "WEAK")
        self.assertIn("reply to", summary["caveat"])

    def test_signal_unchanged_when_no_similarity_available(self):
        # Keyword-only runs have no similarity scores. They must not be
        # downgraded for lacking data they were never going to have.
        results = [Result("s", OK, posts=[], searched=100)]
        plain = [{"post": post(url=f"u{i}")} for i in range(5)]
        summary = verdict.summarise(results, plain, [], [])
        self.assertEqual(summary["signal"], "MODERATE")
        self.assertIsNone(summary["quality"])

    def test_explain_names_the_downgrade_reason(self):
        text = verdict.explain("WEAK", 0.03, 100, caveat="matches are off-topic")
        self.assertIn("Downgraded", text)
        self.assertIn("off-topic", text)

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

    def test_query_plurals_and_verb_endings_excluded(self):
        # A real run for "students struggle" reported "student struggling" as
        # the top thing people were talking about INSTEAD - 45 hits, first in
        # the list. It was the query wearing different endings.
        posts = [post(body="student struggling with money problems", url=f"u{i}")
                 for i in range(5)]
        phrases = [p for p, _ in verdict.themes(posts, ["students", "struggle"],
                                                min_count=2)]
        for phrase in phrases:
            self.assertNotIn("student", phrase)
            self.assertNotIn("struggl", phrase)

    def test_stem_collapses_common_endings(self):
        pairs = [
            ("students", "student"),
            ("struggling", "struggle"),
            ("refuses", "refuse"),
            ("paying", "pay"),
            ("companies", "company"),
            ("revisions", "revision"),
        ]
        for a, b in pairs:
            self.assertEqual(verdict._stem(a), verdict._stem(b),
                             f"{a} and {b} should share a stem")

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


class TestSourceContract(unittest.TestCase):
    """Every source must honour the same contract, because the verdict layer
    trusts it blindly. A source that returns OK when it was actually refused
    would let the tool report 'nobody has this problem' about a search it never
    ran."""

    def _all_sources(self):
        import sources
        import sources.github  # noqa: F401
        import sources.hackernews  # noqa: F401
        import sources.reddit  # noqa: F401
        import sources.stackexchange  # noqa: F401
        import sources.web  # noqa: F401
        return sources

    def test_every_source_is_registered(self):
        sources = self._all_sources()
        for name in ("github", "hackernews", "reddit", "stackexchange", "web"):
            self.assertIn(name, sources.available())

    def test_a_raising_source_becomes_error_not_a_crash(self):
        # One broken source must not take the whole search down; the others may
        # still have something useful.
        sources = self._all_sources()

        def boom(query, limit):
            raise RuntimeError("simulated")

        sources.register("t_boom", boom)
        result = sources.run("t_boom", "anything", use_cache=False)
        self.assertEqual(result.status, ERROR)
        self.assertIn("RuntimeError", result.detail)

    def test_run_all_survives_one_bad_source(self):
        sources = self._all_sources()
        sources.register("t_bad", lambda q, l: (_ for _ in ()).throw(ValueError("x")))
        sources.register("t_good",
                         lambda q, l: Result("t_good", OK,
                                             posts=[post(url="u1")], searched=1))
        results = sources.run_all("anything", only=["t_bad", "t_good"],
                                  use_cache=False)
        statuses = {r.source: r.status for r in results}
        self.assertEqual(statuses["t_bad"], ERROR)
        self.assertEqual(statuses["t_good"], OK)


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
        people, _, pages, terms = leads.rank(results, "client refuses pay",
                                          semantic_on=False)
        self.assertEqual(len(people), 1)
        self.assertNotIn("reranked", people[0])



class TestWebSource(unittest.TestCase):
    """The fallback that exists so no query returns a false zero.

    It broke silently. DuckDuckGo throttles by serving HTTP 202 - a SUCCESS
    code - carrying a "bots use DuckDuckGo too" page, so the parser found no
    results and reported ERROR "page layout changed?". Two things were wrong
    with that: the message sent a reader looking for a bug that did not exist,
    and only BLOCKED reaches the cache fallback, so a recent good answer sat
    on disk unused.
    """

    class FakeResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    RESULT_PAGE = (
        '<div class="result results_links_deep result--ad">'
        '<a rel="nofollow" class="result__a" '
        'href="https://duckduckgo.com/y.js?ad_domain=jobrapido.com&amp;'
        'ad_provider=bingv7aa">Freelance Jobs - Apply Now</a>'
        '<a class="result__snippet">Thousands of freelance jobs.</a></div>'
        '<div class="result results_links_deep">'
        '<a class="result__a" href="//duckduckgo.com/l/?uddg='
        'https%3A%2F%2Fexample.com%2Funpaid">Client refuses to pay</a>'
        '<a class="result__snippet">What to do when a client will not pay.</a>'
        '</div>'
    )

    THROTTLE_PAGE = (
        '<html><head><title>DuckDuckGo</title></head><body>'
        '<form id="img-form" action="//duckduckgo.com/anomaly.js?sv=html'
        '&cc=botnet&ti=1788146829"></form>'
        '<div class="anomaly-modal__title">Unfortunately, bots use '
        'DuckDuckGo too.</div></body></html>'
    )

    def test_a_202_throttle_page_is_blocked_not_an_error(self):
        # The whole bug in one assertion. ERROR here means no cache fallback
        # and a user hunting for a parser bug that is not there.
        self.assertTrue(web._throttled(self.FakeResponse(202, self.THROTTLE_PAGE)))

    def test_the_marker_is_checked_as_well_as_the_status(self):
        # 202 is a success code. Trusting it alone would be guessing about an
        # endpoint that has already changed its mind once.
        self.assertTrue(web._throttled(self.FakeResponse(200, self.THROTTLE_PAGE)))

    def test_a_real_results_page_is_not_throttled(self):
        self.assertFalse(web._throttled(self.FakeResponse(200, self.RESULT_PAGE)))

    def test_adverts_are_dropped(self):
        # Adverts arrive through the same result__a class as organic hits. An
        # advert is somebody selling INTO the pain, and its href is a click
        # tracker, so the URL shown would not be where the user lands.
        result = web._parse(self.RESULT_PAGE, limit=10)
        self.assertEqual(result.status, OK)
        self.assertEqual(len(result.posts), 1)
        self.assertEqual(result.posts[0].url, "https://example.com/unpaid")
        for post in result.posts:
            self.assertNotIn("y.js", post.url)

    def test_results_are_pages_not_people(self):
        for post in web._parse(self.RESULT_PAGE, limit=10).posts:
            self.assertFalse(post.contactable)

    def test_a_genuine_layout_change_is_still_an_error(self):
        # Now that refusals are caught earlier, this branch means what it says.
        result = web._parse("<html><body>nothing familiar</body></html>", limit=10)
        self.assertEqual(result.status, ERROR)

    def test_cooldown_blocks_without_spending_a_request(self):
        # Each attempt costs quota whether it succeeds or not, so hammering a
        # throttled endpoint makes the NEXT search fail too.
        import tempfile
        original = web.COOLDOWN_FILE
        try:
            web.COOLDOWN_FILE = Path(tempfile.gettempdir()) / "pf-test-cooldown"
            web.COOLDOWN_FILE.unlink(missing_ok=True)
            self.assertEqual(web._cooling_down(), 0)
            web._start_cooldown()
            self.assertGreater(web._cooling_down(), 0)

            def explode(*a, **k):
                raise AssertionError("made a request while cooling down")

            saved = web.requests.post
            web.requests.post = explode
            try:
                result = web.search("anything", 10)
            finally:
                web.requests.post = saved
            self.assertEqual(result.status, BLOCKED)
            self.assertIn("cooldown", result.detail)
        finally:
            web.COOLDOWN_FILE.unlink(missing_ok=True)
            web.COOLDOWN_FILE = original



class TestBuilders(unittest.TestCase):
    """Someone already building this is not someone who has the problem.

    Both live runs of an idea-shaped query put a builder at the top. A student
    internships search ranked a feature request on somebody's InternHack repo
    first; a restaurant rota search ranked "[Beta] FastQRMenu - looking for
    restaurant owners to test" second. Offering those as "people you can reply
    to" wastes the slot and buries the most decision-relevant thing in the run.
    """

    def _results(self, posts):
        return [Result("test", OK, posts=posts, searched=len(posts))]

    def test_beta_launch_is_a_builder(self):
        p = post(title="[Beta] FastQRMenu - looking for restaurant owners to test",
                 body="I'm testing FastQRMenu, a browser-based menu manager "
                      "for small restaurants and cafes.")
        self.assertTrue(leads.is_builder(p))

    def test_github_feature_request_is_a_builder(self):
        p = Post(source="github Ashutosh-negi07/Plato",
                 title="[feat] Employee Module - assign and manage restaurant staff",
                 body="", url="u", author="a", created_utc=time.time())
        self.assertTrue(leads.is_builder(p))

    def test_a_bug_report_is_not_a_builder(self):
        # Someone whose tool is broken is genuinely in pain. Over-matching here
        # would silently delete the best leads GitHub has.
        p = Post(source="github acme/billing",
                 title="Billing breaks when the invoice date is null",
                 body="Our team hit this in production and lost a day.",
                 url="u", author="a", created_utc=time.time())
        self.assertFalse(leads.is_builder(p))

    def test_a_real_complaint_is_not_a_builder(self):
        p = post(title="Restaurant owners - curious how you handle scheduling",
                 body="Our manager has mentioned how much of a headache it is "
                      "dealing with availability, schedule changes and call-outs.")
        self.assertFalse(leads.is_builder(p))

    def test_builders_are_separated_from_leads(self):
        rival = post(title="Show HN: I built a rota tool for restaurants",
                     body="I built a scheduling tool for restaurant staff rotas.")
        sufferer = post(title="Restaurant staff rotas are a nightmare",
                        body="Every week I redo the restaurant staff rotas by "
                             "hand and somebody always calls out.")
        people, builders, _, _ = leads.rank(
            self._results([rival, sufferer]), "restaurant staff rotas",
            semantic_on=False)
        self.assertEqual([e["post"].url for e in builders], [rival.url])
        self.assertEqual([e["post"].url for e in people], [sufferer.url])

    def test_builders_get_no_draft(self):
        rival = post(title="Show HN: I built a rota tool for restaurants",
                     body="I built a scheduling tool for restaurant staff rotas.")
        _, builders, _, _ = leads.rank(self._results([rival]),
                                       "restaurant staff rotas", semantic_on=False)
        self.assertEqual(builders[0]["draft"], "")

    def test_builders_still_count_as_matches(self):
        # They are posts about this exact problem. Dropping them would
        # understate the rate and let them leak into the themes as "what
        # everyone is talking about instead".
        rival = post(title="Show HN: I built a rota tool for restaurants",
                     body="I built a scheduling tool for restaurant staff rotas.")
        results = self._results([rival])
        people, builders, pages, terms = leads.rank(
            results, "restaurant staff rotas", semantic_on=False)
        summary = verdict.summarise(results, people, pages, terms, builders)
        self.assertEqual(summary["matched"], 1)
        self.assertEqual(summary["builders"], 1)
        self.assertEqual(summary["themes"], [])

    def test_only_builders_cannot_read_as_strong(self):
        # Nobody to reply to is a ceiling however loud the space is.
        rivals = [post(title=f"Show HN: I built rota tool {i}",
                       body="I built a scheduling tool for restaurant staff rotas.")
                  for i in range(9)]
        results = [Result("test", OK, posts=rivals, searched=10)]
        people, builders, pages, terms = leads.rank(
            results, "restaurant staff rotas", semantic_on=False)
        self.assertEqual(people, [])
        summary = verdict.summarise(results, people, pages, terms, builders)
        self.assertNotIn(summary["signal"], ("STRONG", "MODERATE"))


    def test_innocent_posts_are_not_filed_as_competitors(self):
        # The dangerous direction. This filter began by reusing PROMO_MARKERS -
        # a soft scoring penalty, where a false positive costs a few points -
        # as a hard classifier, where a false positive deletes a lead the user
        # never learns existed. A nursing query then filed three innocent posts
        # under "your competition", one of them for the phrase "I'm testing"
        # used about hormone levels.
        innocent = [
            ("General MTF 50+ Transition Questions",
             "I am testing my hormone levels every month and my doctor said "
             "to wait before changing anything."),
            ("First night shift tomorrow",
             "I am working on nights for the first time and I am terrified."),
            ("Nurses we are understaffed every night",
             "I work nights and we made a complaint to management about it."),
            ("Client refuses to pay",
             "Three months of invoices ignored, we have made no progress."),
        ]
        for title, body in innocent:
            self.assertFalse(leads.is_builder(post(title=title, body=body)), title)

    def test_building_language_still_counts_when_a_product_is_named(self):
        # The other side of the same threshold: tightening must not blind it.
        real = [
            ("How are you handling cross-promos?",
             "I got tired of Linktree so I built a small tool for it."),
            ("I built a browser-based staff scheduler for small restaurants",
             "Where would you look for users?"),
            ("Show HN: I built a rota tool", ""),
        ]
        for title, body in real:
            self.assertTrue(leads.is_builder(post(title=title, body=body)), title)

    def test_github_issue_number_prefix_does_not_hide_a_feature_request(self):
        # GitHub titles arrive prefixed with their issue number, so an anchored
        # pattern caught only the ones whose number happened to be missing.
        # "Issue #11 - [feat] Employee Module" sat in the leads list and got a
        # drafted pain interview sent to the person building the competitor.
        for title in ("Issue #11 - [feat] Employee Module - manage staff",
                      "feat(apex): news and tools content hub",
                      "Issue #9 - feature request: bulk import"):
            p = Post(source="github x/y", title=title, body="", url="u",
                     author="a", created_utc=time.time())
            self.assertTrue(leads.is_builder(p), title)

    def test_repository_text_stays_out_of_the_themes(self):
        # A restaurant-rota search reported "menu management" and "user
        # friendly" as the loudest rival themes. That is README boilerplate
        # from competitors' repos, not people talking about a problem.
        repo = [Post(source="github a/b", title="Restaurant POS",
                     body="menu management user friendly option available "
                          "menu management user friendly option available",
                     url=f"r{i}", author="", created_utc=time.time())
                for i in range(6)]
        human = [Post(source="reddit", title="Rota headaches",
                      body="call outs ruin the week, call outs every week",
                      url=f"h{i}", author="a", created_utc=time.time())
                 for i in range(6)]
        found = verdict.themes(repo + human, ["rota"])
        flat = " ".join(phrase for phrase, _ in found)
        self.assertNotIn("menu management", flat)
        self.assertNotIn("user friendly", flat)
        self.assertIn("call outs", flat)

class TestCommandLine(unittest.TestCase):
    """Actually run main().

    Everything else here tests functions. A crash lived in find.py through a
    full green test run - rank() grew a fourth return value and the caller
    still unpacked three - because nothing exercised the program end to end.
    Unit tests cannot catch a wiring bug between two units.
    """

    def _run(self, argv, posts):
        import contextlib
        import io as _io
        import find
        import sources

        fake = [Result("test", OK, posts=posts, searched=len(posts))]
        saved_run_all, saved_argv = sources.run_all, sys.argv
        sys.argv = ["find.py"] + argv
        sources.run_all = lambda *a, **k: fake
        out = _io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                code = find.main()
        finally:
            sources.run_all, sys.argv = saved_run_all, saved_argv
        return code, out.getvalue()

    def test_a_normal_search_runs_end_to_end(self):
        code, out = self._run(
            ["client refuses to pay for revisions", "--no-semantic"],
            [post(title="Client refuses to pay for revisions",
                  body="Three months of invoices ignored and I am stuck.")])
        self.assertEqual(code, 0)
        self.assertIn("VERDICT", out)
        self.assertIn("you can reply to", out)

    def test_an_idea_shaped_query_runs_end_to_end(self):
        code, out = self._run(
            ["i wanna build a tool that helps restaurants manage staff rotas",
             "--no-semantic"],
            [post(title="Restaurant staff rotas are a nightmare",
                  body="Every week I redo the restaurant staff rotas by hand "
                       "and somebody always calls out at the last minute.")])
        self.assertEqual(code, 0)
        self.assertIn("reads like an idea", out)

    def test_builders_are_shown_as_competition_not_as_leads(self):
        code, out = self._run(
            ["restaurant staff rotas", "--no-semantic"],
            [post(title="Show HN: I built a rota tool for restaurants",
                  body="I built a scheduling tool for restaurant staff rotas.")])
        self.assertIn("ALREADY BUILDING THIS", out)
        self.assertNotIn("draft reply", out)

    def test_finding_nothing_does_not_crash(self):
        code, out = self._run(["something nobody discusses", "--no-semantic"], [])
        self.assertIn(code, (0, 1))
        self.assertIn("Nothing found", out)

    def test_every_source_blocked_says_unknown_not_none(self):
        import contextlib
        import io as _io
        import find
        import sources

        blocked = [Result("test", BLOCKED, detail="rate-limited")]
        saved_run_all, saved_argv = sources.run_all, sys.argv
        sys.argv = ["find.py", "anything", "--no-semantic"]
        sources.run_all = lambda *a, **k: blocked
        out = _io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                find.main()
        finally:
            sources.run_all, sys.argv = saved_run_all, saved_argv
        text = out.getvalue()
        self.assertNotIn("Nobody in the searched sources", text)



class TestStackExchangeThrottle(unittest.TestCase):
    """Stack Exchange throttles in two shapes, and only one used to be read
    correctly.

    Soft: HTTP 200 with a JSON error_id of throttle_violation.
    Hard: HTTP 429 carrying an HTML "Too Many Requests" page.

    The HTML never parses as JSON, and the parse was attempted before the
    status was checked, so a hard throttle came back as ERROR "could not parse
    response" - which reads like a broken parser and never reaches the cache
    fallback in sources.run(). Exactly the bug the web source had with
    DuckDuckGo's HTTP 202.
    """

    class FakeResponse:
        def __init__(self, status_code, text, payload=None):
            self.status_code = status_code
            self.text = text
            self._payload = payload

        def json(self):
            if self._payload is None:
                raise ValueError("not json")
            return self._payload

    def _search(self, resp):
        import sources.stackexchange as se
        saved = se.requests.get
        se.requests.get = lambda *a, **k: resp
        try:
            return se._search_site("workplace", "q", 10, time.monotonic() + 30)
        finally:
            se.requests.get = saved

    def test_hard_throttle_is_blocked_not_an_error(self):
        html = ("<!DOCTYPE html><html><head><title>Too Many Requests - "
                "Stack Exchange</title></head><body>slow down</body></html>")
        _, status, detail = self._search(self.FakeResponse(429, html))
        self.assertEqual(status, BLOCKED)
        self.assertIn("rate-limited", detail)

    def test_soft_throttle_is_still_blocked(self):
        payload = {"error_id": 502, "error_name": "throttle_violation",
                   "error_message": "too many requests from this IP"}
        _, status, detail = self._search(self.FakeResponse(200, "{}", payload))
        self.assertEqual(status, BLOCKED)

    def test_genuinely_unparseable_body_is_still_an_error(self):
        # The branch must not be swallowed: a 200 that is not JSON means the
        # endpoint changed shape, and that wants a human, not a cooldown.
        _, status, detail = self._search(self.FakeResponse(200, "<html>?</html>"))
        self.assertEqual(status, ERROR)

    def test_a_normal_response_still_returns_posts(self):
        payload = {"items": [{"title": "Rota trouble", "body": "<p>help</p>",
                              "link": "https://x/1", "creation_date": 1,
                              "answer_count": 2, "owner": {"display_name": "sam"}}]}
        posts, status, _ = self._search(self.FakeResponse(200, "{}", payload))
        self.assertEqual(status, OK)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].author, "sam")



class TestCodeReviewRegressions(unittest.TestCase):
    """Three bugs a pre-launch review found, all of which the suite had missed."""

    def test_a_complaint_that_starts_with_a_build_verb_is_left_alone(self):
        # The worst of the three. English uses one word for the thing you
        # intend to do and the thing happening to you, and the detector matched
        # on the verb alone: "starting a business is harder than anyone says"
        # became "is harder than anyone says" - the entire subject deleted -
        # and the WEAK verdict that followed was an artefact of the rewrite.
        for q in ("starting a business is harder than anyone says",
                  "building a rota by hand every week is killing me",
                  "making a living as a freelancer is impossible",
                  "starting a company at 15 is a legal nightmare",
                  "launching a product with no audience is brutal",
                  "creating a website for my shop took three months",
                  "making an app for my boss was the worst month of my life"):
            self.assertFalse(leads.looks_like_an_idea(q), q)
            self.assertEqual(leads.problem_in(q), q)

    def test_real_ideas_are_still_recognised(self):
        # The other half: tightening must not blind it.
        for q, must_keep in (
            ("i wanna build a startup that helps students find internships",
             "internships"),
            ("I want to build an app for freelancers to track invoices",
             "freelancers"),
            ("thinking about making a tool for nurses doing handover notes",
             "nurses"),
            ("an app for freelancers to track unpaid invoices", "invoices"),
            ("building a platform for cement plant maintenance teams", "cement"),
            ("creating an app for students to swap textbooks", "textbooks"),
        ):
            self.assertTrue(leads.looks_like_an_idea(q), q)
            self.assertIn(must_keep, leads.problem_in(q), q)

    def test_the_article_an_is_not_split_into_a_plus_n(self):
        # Regex alternation is leftmost-first, so (a|an) matched the "a" of
        # "an" and left a stray "n": the query above was rewritten to
        # "n app for freelancers to track invoices".
        got = leads.problem_in("I want to build an app for freelancers to track invoices")
        self.assertFalse(got.startswith("n "), got)

    def test_a_product_noun_must_be_the_object_of_the_building_verb(self):
        # WEAK_BUILDER accepted any product noun within 60 characters, so
        # ordinary complaints that merely mentioned software were filed as
        # competitors, got no draft, and never reached the user as leads.
        for title, body in (
            ("Client wont pay",
             "I made a complaint about the app I have to use at work."),
            ("Warehouse chaos",
             "We made a complaint to management about the tracker they forced on us."),
            ("Scheduling hell",
             "I am working on the rota every Sunday and the software we use is garbage."),
        ):
            self.assertFalse(leads.is_builder(post(title=title, body=body)), title)

    def test_real_builders_survive_the_tightening(self):
        for title, body in (
            ("How are you handling cross-promos?",
             "I got tired of Linktree so I built a small tool for it."),
            ("I built a browser-based staff scheduler for restaurants",
             "Where would you look for users?"),
            ("Show HN: I built a rota tool", ""),
        ):
            self.assertTrue(leads.is_builder(post(title=title, body=body)), title)

    def test_unnamed_product_aimed_at_an_audience_is_a_builder(self):
        # Found by re-running the live query after tightening the filter, not
        # by the suite: "UAE F&B owners, I've been building something for you"
        # sat in the leads list. The product is never named, so the direct
        # object rule cannot see it - the tell is that it is built FOR someone.
        for title in ("UAE F&B owners, I've been building something for you",
                      "I've been working on something for restaurant owners",
                      "I'm building something to fix this"):
            self.assertTrue(leads.is_builder(post(title=title)), title)

    def test_been_building_a_product_is_a_builder(self):
        # "I've been building a tool" - the progressive form skipped the verb
        # list entirely, because "been" sat between the pronoun and the verb.
        self.assertTrue(leads.is_builder(post(title="I've been building a tool for rotas")))

    def test_ordinary_speech_about_something_is_not_a_builder(self):
        # The reason "something" needs the audience phrase: without it this is
        # just how people talk, and every one of these is a person.
        for body in ("I'm working on something else at the moment and cannot help",
                     "I've been building my confidence back after the burnout",
                     "I am working on nights for the first time and I am terrified."):
            self.assertFalse(leads.is_builder(post(title="x", body=body)), body)

    def test_recruiting_testers_in_a_sentence_is_a_builder(self):
        # The fixed-width gap could not reach across six words, so "I am
        # looking for a few small-business owners or managers to test one
        # thing" sat in the leads list beside real restaurant owners.
        for text in ("I am looking for a few small-business owners or managers "
                     "to test one thing: is the signup clear?",
                     "Looking for 5 people to test whether free signup feels clear"):
            self.assertTrue(leads.is_builder(post(title="x", body=text)), text)

    def test_saying_my_startup_is_not_promotion(self):
        # Both of these were filed as competitors and lost their draft. The
        # first is a founder asking for help - a person with a problem, which
        # is the entire point of this tool. The second was a quoted comment
        # inside an AMA that merely contained the phrase.
        for title, body in (
            ("How can I grow my startup, it's in prototype stage v0.1",
             "I am building it alone and have no idea how to find users."),
            ("I Am Sam Altman, President of Y Combinator. AMA",
             "the code I've written for my startup looks as good as it needs to"),
        ):
            self.assertFalse(leads.is_builder(post(title=title, body=body)), title)

    def test_promotional_framing_still_counts(self):
        for text in ("check out my startup", "introducing my saas",
                     "sharing my side project"):
            self.assertTrue(leads.is_builder(post(title="x", body=text)), text)

    def test_the_flagging_evidence_is_returned_and_readable(self):
        # No regex closes the set of ways English says "I built a thing", so
        # this classifier will always be wrong sometimes. The honest response
        # is to print the evidence: a reader who sees flagged by "I got tired
        # of" can tell in a second that the call was wrong and treat the post
        # as a lead. A judgement you cannot inspect is one you cannot overrule.
        for title, body, expected in (
            ("Show HN: I built a rota tool", "", "Show HN"),
            ("[Beta] FastQRMenu", "looking for restaurant owners to test", "[Beta]"),
        ):
            got = leads.builder_reason(post(title=title, body=body))
            self.assertIsNotNone(got, title)
            self.assertIn(expected.lower(), got.lower())

    def test_a_lead_has_no_flagging_evidence(self):
        self.assertIsNone(leads.builder_reason(
            post(title="Client refuses to pay",
                 body="Three months of invoices ignored and I am stuck.")))

    def test_rank_attaches_the_reason_to_each_builder(self):
        rival = post(title="Show HN: I built a rota tool for restaurants",
                     body="I built a scheduling tool for restaurant staff rotas.")
        _, builders, _, _ = leads.rank(
            [Result("test", OK, posts=[rival], searched=1)],
            "restaurant staff rotas", semantic_on=False)
        self.assertTrue(builders[0]["builder_reason"])

    def test_roast_my_needs_its_object(self):
        # "PLEASE ROAST MY RESUME" from a jobs subreddit was filed as a
        # competitor. Found by auditing 565 posts across ten industries - the
        # only false positive in the set, and invisible to fixtures because
        # nobody writing them thinks of resumes.
        self.assertFalse(leads.is_builder(post(title="PLEASE ROAST MY RESUME")))
        self.assertTrue(leads.is_builder(post(title="Roast my startup idea")))
        self.assertTrue(leads.is_builder(post(title="roast my saas landing page")))

    def test_a_null_author_does_not_take_down_the_search(self):
        # GitHub and Stack Exchange return the author key present-and-null for
        # ghost/deleted accounts, and .get(key, "") only supplies the default
        # when the key is ABSENT. One such record crashed every source's
        # results, not just its own.
        p = Post(source="github x/y", title="Client refuses to pay",
                 body="Invoices ignored for months and I am stuck.",
                 url="u", author=None, created_utc=time.time())
        people, _, _, _ = leads.rank(
            [Result("test", OK, posts=[p], searched=1)],
            "client refuses pay", semantic_on=False)
        self.assertEqual(len(people), 1)

if __name__ == "__main__":
    unittest.main(verbosity=2)
