# painpoint-finder

**Describe the thing you want to build. Find out who actually has the problem,
who already built it, and who you can talk to today.**

You have an idea. Before you spend six months on it you want three answers: is
this problem real, has somebody already solved it, and can I speak to one of
these people this afternoon.

Type the idea in your own words. It searches six public sources, tells you how
loud the problem actually is, pulls out the people already building it, and
hands you a drafted opener for the ones worth talking to.

```
python find.py "i wanna build a tool that helps small restaurant owners manage their staff rotas"
```

```
That reads like an idea, not a problem.
  you asked : "i wanna build a tool that helps small restaurant owners manage their staff rotas"
  I searched: "helps small restaurant owners manage their staff rotas"

  People in pain do not use your words. They never write
  "I need an app for this" - they write the complaint. You
  will get better leads searching what THEY would type.

COVERAGE: PARTIAL
  searched github (100 posts)   searched hackernews (22 posts)
  searched reddit (194 posts)   searched web (10 posts)
  COULD NOT SEARCH stackexchange - too many requests from this IP

  Some sources could not be searched. Treat a low count as
  incomplete rather than as an answer.

==============================================================================
VERDICT: MODERATE signal
  12 of 316 posts matched (3.8%)
  match quality: 0.68 (4 recent enough to reply to)
  3.8% of posts matched. Enough to be worth a conversation.

  What the other posts are about instead:
      25  social media       10  landing pages
      13  love hear           9  online presence
      10  graphic design      9  cash flow
==============================================================================

3 ALREADY BUILDING THIS - your competition:

  [1] Issue #11 - [feat] Employee Module - assign and manage restaurant staff
      github Ashutosh-negi07/Plato - 10d ago
  [2] [Beta] FastQRMenu - looking for restaurant owners to test updating a menu
      reddit r/alphaandbetausers - 4d ago
  [3] Launch HN: Boostly (YC S22) - SMS marketing for restaurants
      hackernews - 48mo ago

3 PERSON/PEOPLE you can reply to, best first:

[1] Restaurant owners/managers - curious how you handle scheduling
    reddit r/restaurant - 3h ago - by /u/Forsaken_Internet774

    --- draft reply (edit before sending) ---
    You said: "Restaurant owners/managers - curious how you handle scheduling
    I work at a restaurant, and our manager has mentioned how much of a
    headache it can be dealing with availability, schedule changes, and
    call-outs."

    Curious about one thing, and I'm asking rather than selling: how long had
    this been going on before it got bad enough to post about? And did
    anything you tried actually help?
```

That is a real run, not a mock-up.

## Use it inside Claude Code

```
/painpoint i wanna build a tool that helps restaurant owners manage rotas
```

```bash
git clone https://github.com/gokulsai1004-create/painpoint-finder.git
cp -r painpoint-finder/skill/painpoint ~/.claude/skills/
```

The CLI below is the same code and works on its own. The skill exists because
**reading the output is the hard part**: the coverage line has to be read before
the verdict, the verdict is a ratio rather than a judgement, the competition
section usually matters more than the leads, and the classifier prints the words
behind each call so you can overrule it. A person skims all of that and reads
the leads. The skill makes Claude read it in order and say the uncomfortable
parts out loud — that a partially blocked search proves nothing, that MODERATE
is not permission, that a rival with 3,400 stars changes the plan.

It refuses to send anything, exactly like the tool does.

See [skill/](skill/) for details.

## What it does not claim

**It does not know whether your idea is good.** It knows how many people in
six searchable places are describing your problem right now, and it shows you
the arithmetic. `MODERATE` means 3.8% of what it read was about your thing — it
does not mean go, and `WEAK` does not mean stop.

More importantly, it tells you what it **could not see**. If a source was
rate-limited it says `COULD NOT SEARCH`, never `no results`, because those two
look identical and mean opposite things. A tool that quietly reported silence
from a search it never ran would talk someone out of a real idea, and that is
the worst thing this could do.

The coverage line is not a disclaimer. It is the most important line in the
output.

## Why it rewrites your query

Searching an idea verbatim finds **other builders**, because they are the only
people who use a builder's words. Measured: the query
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
3 ALREADY BUILDING THIS - your competition:

  [1] psmux/psmux - 3400 stars
      github-repo psmux/psmux - 1d ago
      flagged by: "a shipped repository"
  [2] [Beta] FastQRMenu - looking for restaurant owners to test updating a menu
      reddit r/alphaandbetausers - 4d ago
      flagged by: "[Beta]"
  [3] Launch HN: Boostly (YC S22) - SMS marketing for restaurants
      hackernews - 48mo ago
      flagged by: "Launch HN"

  Each shows the words that flagged it. If one looks wrong, it is wrong -
  treat that person as a lead and write to them.

  Not leads, and not nothing. Read what they built and what people say back
  to them - that is the fastest free research you will get. If several exist
  and none has taken the market, the interesting question is why.
```

**Every entry shows the words that flagged it.** No regex closes the set of
ways English says "I built a thing", so this classifier will always be wrong
sometimes — a bare `my startup` used to catch founders *asking for help*, which
is precisely the person the tool exists to find. Printing the evidence does not
shrink that tail; it changes who has to live with it. A reader who sees
`flagged by: "I got tired of"` can tell in a second the call was wrong and write
to that person anyway.

Same principle the scoring follows: a judgement you cannot inspect is a
judgement you cannot overrule.

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
| GitHub issues | Someone saying what a tool they *already use* cannot do | no |
| GitHub repos | **Who already shipped it**, sorted by stars | no |
| Web (DuckDuckGo) | Fallback so no query ever returns a false zero | no |

The repository search was added the hard way. Searching for *"a tmux-like
multi-pane terminal tool for Windows"* returned four competitors and missed
**psmux** — 3,400 stars, actively developed, with documentation for that exact
use case — because issue search can see complaints *inside* a project but never
the project itself, and psmux had never filed an issue describing itself. Six
real rivals, invisible, while the verdict said MODERATE about a space that is
comprehensively taken.

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
