# painpoint-finder

**Find the people who have the problem, not just the problem.**

You have an idea. Before you spend six months on it, you want to know whether
anyone actually has the problem — and if they do, you want to talk to one of
them today.

Every tool in this space stops at a report. This one ends at a person and
something to say to them.

```
py -3 find.py "client refuses to pay for revisions"
```

```
COVERAGE: MEDIUM
  searched hackernews (6 posts)
  searched reddit (194 posts)
  searched web (10 posts)

==============================================================================
VERDICT: MODERATE signal
  4 of 210 posts matched (1.9%)
  1.9% of posts matched. That is thin.

  What the other posts are about instead:
      14  finding clients
      11  raising rates
       9  chasing invoices
==============================================================================

1 PERSON YOU CAN REPLY TO

[1] Client refuses to pay me and my dad for over 2 months of work
    reddit r/legaladvice - 7d ago - by /u/Tiny_Ad3757
    https://www.reddit.com/r/legaladvice/comments/1vvq96h/...

    --- draft reply (edit before sending) ---
    You said: "Client refuses to pay me and my dad for over 2 months of work"

    Curious about one thing, and I'm asking rather than selling: how long had
    this been going on before it got bad enough to post about? And did
    anything you tried actually help?

2 PAGE(S) about this - evidence, not people
  No drafts for these: a page has nobody to reply to.
```

## Why it exists

I had a startup idea, built a prototype in an afternoon, then spent four days
gathering 992 real posts about the problem. Seven of them were about my idea.
Two hundred and eighty-four were about something else entirely.

That killed the idea in four days instead of six months, and it was the most
useful thing I did all week.

But I still could not talk to anyone. My question post was auto-removed on a
karma filter. The Slack community would not finish registering me. LinkedIn is
closed to under-16s. Four days of perfect data, zero conversations.

**Finding the pain is solved. Reaching the person is not.** That gap is what
this tool is for.

## Install

```
git clone <this repo>
cd painpoint-finder
pip install requests fastembed   # fastembed optional, improves ranking
py -3 find.py "your problem, in your own words"
```

Python 3.9+. One dependency. **No API key, no account, no sign-up** — every
source is public and anonymous.

## What it searches

| Source | What you get | Key needed |
|---|---|---|
| Reddit | People describing problems, via public RSS | no |
| Hacker News | Stories **and comments** — comments are where complaints live | no |
| Stack Overflow | Developers stuck on a real problem, via the public API | no |
| Web (DuckDuckGo) | Fallback so no query ever returns a false zero | no |

## Ranking

Optional but recommended:

```
pip install fastembed
```

Keyword matching finds posts containing your words. It cannot tell that a post
about a care client refusing to wear *dentures* is not about a client refusing
to pay an *invoice* — both contain "client" and "refuses". A small model
running **on your own machine** can, because it places text by meaning.

Measured against this tool's own false positives, for the query *"freelance
client refuses to pay for revisions"*:

| post | keyword rank | with reranking |
|---|---|---|
| Real "client won't pay" post | 1 | **1** |
| Care client refusing dentures | **2** | 4 |
| Car lease financing | **1** | 5 |
| Wrestling thread | **1** | 6 |

No key, no account, no network after the first run. Skipped automatically if
`fastembed` is not installed, or explicitly with `--no-semantic`.

## The three ideas it is built on

**A blocked search is not an empty search.** If Reddit rate-limits us, the tool
says `COULD NOT SEARCH`, never `no results`. Those two things look identical
and mean opposite things, and confusing them would let this tool tell someone
their real problem is imaginary. That distinction lives in the type system, not
in a comment.

**The ratio is the answer, not the count.** Seven matches sounds promising
until you learn it was seven out of nine hundred and sixty-three. The verdict
prints before the leads for that reason.

**A page is not a person.** A Reddit thread has an author who can answer you; a
blog post does not. Results are split, and pages explicitly get no draft
reply — writing an opener for an article nobody reads would be theatre.

## Caching

Rate limits are what you actually hit while refining a query: you rerun a
search five times adjusting the wording, and the fifth gets refused. When a
source is blocked, results from a recent identical search are used instead —
and always labelled:

```
COVERAGE: MEDIUM (PARTLY CACHED)
  reddit: CACHED from 12 minutes ago (194 posts) - live search was refused
```

Cached runs mark the verdict line too. A stale answer presented as fresh is
worse than no answer. Failures are never cached, and an `ERROR` never falls
back — only a rate limit does, because an error might mean the source changed
shape and serving old data would hide a real break.

## What it will not do

**It never sends anything.** It surfaces a handful of leads and drafts
something you must read, edit and post yourself. No bulk, no automation, no
auto-posting. The version that sends fifty messages is a spam cannon; the
version that helps you write one good reply is useful. That is a design
constraint, not a missing feature, and it is not coming.

## Known limitation: negation

**Neither ranking mode can represent negation.** `not getting paid` and
`getting paid` are opposite problems, and both approaches treat them as nearly
the same thing. Keywords reduce them to identical terms. Embeddings are worse
than you would expect here — measured, the model rates *"getting paid for extra
work"* as the **closest** match to *"not getting paid for extra work"*, at
0.906, higher than any other candidate tested. That is a documented weakness of
the technique, not a bug in this tool.

So the warning stays. When your query contains a negation the tool says so and
suggests rephrasing positively: `unpaid revisions` works far better than `not
paid for revisions`.

## Adding a source

A source takes a query and returns a `Result`. That is the whole contract:

```python
from . import OK, BLOCKED, Post, Result, register

def search(query, limit=100):
    ...
    return Result("mysource", OK, posts=[...], searched=n)

register("mysource", search)
```

Return `BLOCKED` if you could not look, `ERROR` if something broke, `OK` with
an empty list if you looked and found nothing. Getting that right is the only
thing the rest of the tool depends on.

Sources worth adding: GitHub issues, app-store reviews, G2/Capterra, Upwork job
posts (someone *paying* to fix a problem is the strongest signal there is), and
SBIR solicitations for anything defence or government adjacent.

## Tests

```
py -3 test_painpoint.py
```

35 tests, all offline — a test that needs Reddit to be up is a test that fails
for reasons that are not bugs.

## Licence

MIT. See LICENSE.
