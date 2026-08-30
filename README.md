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
pip install requests
py -3 find.py "your problem, in your own words"
```

Python 3.9+. One dependency. **No API key, no account, no sign-up** — every
source is public and anonymous.

## What it searches

| Source | What you get | Key needed |
|---|---|---|
| Reddit | People describing problems, via public RSS | no |
| Hacker News | Stories **and comments** — comments are where complaints live | no |
| Web (DuckDuckGo) | Fallback so no query ever returns a false zero | no |

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

## What it will not do

**It never sends anything.** It surfaces a handful of leads and drafts
something you must read, edit and post yourself. No bulk, no automation, no
auto-posting. The version that sends fifty messages is a spam cannon; the
version that helps you write one good reply is useful. That is a design
constraint, not a missing feature, and it is not coming.

## Known limitation

**Ranking is keyword-based, so it cannot represent negation.** `not getting
paid` and `getting paid` reduce to identical terms and are opposite problems.
The tool warns you when your query contains a negation and suggests rephrasing
positively — `unpaid revisions` works far better than `not paid for revisions`.

Semantic ranking fixes this properly. It needs a model API key, which is the
next thing on the list.

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

Sources worth adding: Stack Overflow, GitHub issues, app-store reviews,
G2/Capterra, Upwork job posts (someone *paying* to fix a problem is the
strongest signal there is), and SBIR solicitations for anything defence or
government adjacent.

## Tests

```
py -3 test_painpoint.py
```

22 tests, all offline — a test that needs Reddit to be up is a test that fails
for reasons that are not bugs.

## Licence

MIT. See LICENSE.
