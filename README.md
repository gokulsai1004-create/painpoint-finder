# painpoint-finder

**Find the people who have the problem, not just the problem.**

You have an idea. Before you spend six months on it, you want to know whether
anyone actually has the problem — and if they do, you want to talk to one of
them today.

Every tool in this space stops at a report. This one ends at a person and
something to say to them.

```
python find.py "client refuses to pay for revisions"
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

## You will type an idea. The people in pain will not.

Whoever reaches for this tool has an *idea* — that is why they came. But the
people with the problem never use a builder's words. Nobody writes *"I need an
app for this"*; they write the complaint.

So searching your idea verbatim finds **other builders**. Measured: the query
*"i wanna build a startup that helps students find internships"* returned two
people asking what to build next — matched on the words "wanna" and "build" —
and a feature request on somebody's intern-hackathon repo. Three leads, zero
sufferers, and a `WEAK` verdict that would have talked someone out of a real
idea.

The tool now searches the problem inside the idea, and says so:

```
That reads like an idea, not a problem.
  you asked : "i wanna build a tool that helps small restaurant owners manage their staff rotas"
  I searched: "helps small restaurant owners manage their staff rotas"

  People in pain do not use your words. They never write
  "I need an app for this" - they write the complaint. You
  will get better leads searching what THEY would type.
```

It deliberately does **not** claim to have understood you. Stripping "i wanna
build a tool that" is honest string work; turning a feature back into a
complaint is not, so it tells you to do that part yourself.

## Who is already building it

The same search that finds your customers finds your competitors, because they
post about the same problem in the same places. Handing you those under the
heading *"people you can reply to"* wastes the slot — and offering to draft one
a sympathetic *"how long has this been going on?"* is an embarrassing thing to
send someone who is selling the cure.

They get their own section, printed **before** the leads, because a reader who
has started drafting replies has stopped deciding:

```
4 ALREADY BUILDING THIS - your competition:

  [1] Issue #11 - [feat] Employee Module - assign and manage restaurant staff
      github Ashutosh-negi07/Plato - 10d ago
  [2] [Beta] FastQRMenu - looking for restaurant owners to test updating a menu
      reddit r/alphaandbetausers - 4d ago
  [3] If you already know restaurant owners, I'm testing a 30% recurring affiliate
      reddit r/passive_income - 4d ago
  [4] Launch HN: Boostly (YC S22) - SMS marketing for restaurants
      hackernews - 48mo ago

  Not leads, and not nothing. Read what they built and what people say back
  to them - that is the fastest free research you will get. If several exist
  and none has taken the market, the interesting question is why.
```

If *every* match is a builder, the verdict says so in those words — **"no
customers found, only rivals"** — rather than the misleading "nothing recent
enough to reply to". The space is not quiet. It is taken.

Detection is deliberately narrow: a plain bug report stays a lead, because
someone whose tool is broken is genuinely in pain.

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
git clone https://github.com/gokulsai1004-create/painpoint-finder.git
cd painpoint-finder
pip install requests fastembed   # fastembed optional, improves ranking
python find.py "your problem, in your own words"
```

Python 3.9+. One required dependency. **No API key, no account, no sign-up** —
every source is public and anonymous.

If `python` runs Python 2 on your machine, use `python3`. On Windows, `py -3`
also works. If `pip` is missing, try `python -m pip`.

First run with `fastembed` installed downloads a ~50MB model once, which takes
a minute. Every run after that is offline. Skip it entirely with
`--no-semantic` if you would rather not.

## What it searches

| Source | What you get | Key needed |
|---|---|---|
| Reddit | People describing problems, via public RSS | no |
| Hacker News | Stories **and comments** — comments are where complaints live | no |
| Stack Exchange | 8 sites at once: The Workplace, Engineering, Law, Medical Sciences, Academia, Project Management, Money, Stack Overflow | no |
| GitHub issues | Someone saying what a tool they *already use* cannot do — and, sorted out separately, the people building your idea | no |
| Web (DuckDuckGo) | Fallback so no query ever returns a false zero | no |

GitHub issues are worth calling out. A forum complaint is someone annoyed; a
filed issue is someone who installed the thing, hit the wall, and cared enough
to write it down against the project. The gap between what a tool does and what
someone needed is sitting in the open.

## Industries outside tech

Reddit, Hacker News and GitHub all skew heavily toward software, so early
versions gave a developer hundreds of posts and a nurse or a plant engineer a
coverage warning. Their complaints exist. They are just not on Hacker News.

Stack Exchange fixes most of that. It runs 365 sites on one API, and this
searches eight of them chosen for breadth rather than volume — **The Workplace**
above all, which is client, manager, colleague and scope problems across every
industry at once.

The difference is not subtle. Searching *"nurses burnout understaffed hospital
shifts"* returned nothing usable before and now surfaces *"How to convince
management that our department is understaffed"* — a real person with the exact
problem.

Still thin for genuinely niche B2B: heavy industry, defence procurement,
specialist manufacturing. Those complaints live in trade publications and
tender documents, and no source here reads those yet. The tool says so rather
than guessing — see the coverage line.

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

## The ideas it is built on

**A blocked search is not an empty search.** If Reddit rate-limits us, the tool
says `COULD NOT SEARCH`, never `no results`. Those two things look identical
and mean opposite things, and confusing them would let this tool tell someone
their real problem is imaginary. That distinction lives in the type system, not
in a comment.

**The ratio is the answer, not the count.** Seven matches sounds promising
until you learn it was seven out of nine hundred and sixty-three. The verdict
prints before the leads for that reason.

**A competitor is not a customer.** Someone launching the thing you were
going to launch posts about the same problem in the same places. They are
separated out and never drafted a reply, because the finding *"three people
already shipped this"* changes your next move more than one more complaint
would.

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

Sources worth adding: app-store reviews, G2/Capterra, Upwork job
posts (someone *paying* to fix a problem is the strongest signal there is), and
SBIR solicitations for anything defence or government adjacent.

## Tests

```
python test_painpoint.py
```

47 tests, all offline — a test that needs Reddit to be up is a test that fails
for reasons that are not bugs.

## Licence

MIT. See LICENSE.
