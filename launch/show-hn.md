TITLE  (pick one — HN caps titles at 80 characters)

  A. Show HN: Painpoint Finder – who actually has the problem you want to solve
  B. Show HN: A research tool that says "could not search" instead of "no results"
  C. Show HN: Find people who have the problem, not just the problem

  Recommended: A. It says what the tool does. B is the most distinctive and the
  most HN-flavoured, but someone skimming cannot tell what it is.

URL

  https://github.com/gokulsai1004-create/painpoint-finder

BODY  (post as the first comment, immediately after submitting)

I'm 15, in Hyderabad. In July I had a startup idea, built a prototype in an
afternoon, then spent four days gathering 992 real posts about the problem it
was meant to solve. Seven of them were about my idea. 879 were about money
problems instead. The idea died in four days rather than six months, and that
was the most useful thing I did all week.

But I still couldn't talk to anyone. My question post was auto-removed by a
karma filter, LinkedIn is closed to under-16s, and a Slack community never
finished registering me. Four days of good data, zero conversations.

So this is the tool I wanted. You describe what you want to build, in your own
words. It searches Reddit, Hacker News, the Stack Exchange network, GitHub
issues and the open web, then gives you three things:

- how loud the problem actually is, as a ratio — "7 of 963", not "7 matches"
- the people already building it, pulled out into their own section
- a few people you could reply to today, with a drafted opener that quotes them

It never sends anything. It drafts, you edit, you post it yourself. That's a
permanent constraint rather than a missing feature: the version that sends
fifty messages is a spam cannon.

The decision I'd most like feedback on. A source that searched and found
nothing, and a source that was rate-limited and never looked, both return zero
posts — and they mean opposite things. Collapsing them would let this tool tell
someone their real problem is imaginary, which is the worst thing it could do.
So the distinction lives in the type, and a blocked source prints COULD NOT
SEARCH, never "no results".

Getting that right took most of the work. DuckDuckGo throttles by returning
HTTP 202 — a success code — carrying an HTML page. Stack Exchange does it with
a 429 carrying a different HTML page. Both parse as "the parser is broken" if
you check the body before the status, and both did, in my code, until this week.

What it does not do: it does not know whether your idea is good. MODERATE means
3.8% of what it read was about your thing. It isn't a verdict on you. And
neither ranking mode can represent negation — "not getting paid" and "getting
paid" are opposite problems with identical keywords, and the embedding model
scores them 0.906 similar, higher than anything else I tested. So it warns you
rather than pretending.

No API key, no account, nothing to sign up for. Semantic reranking runs locally
through fastembed if you have it, keyword-only if you don't.

    pip install requests
    python find.py "your problem, in your own words"

Happy to answer anything.


-------------------------------------------------------------------------
BEFORE YOU POST

  [ ] python test_painpoint.py           -> expect 107 passing
  [ ] python find.py "client refuses to pay for revisions" -n 3
        -> confirm all five sources say "searched", not "COULD NOT SEARCH"
  [ ] open the repo on GitHub, check the README renders (tables, code block)

TIMING

  Tuesday 1 September, 7:00pm IST  =  9:30am US Eastern  =  6:30am US Pacific

AFTER YOU POST

  - Stay at the laptop for 2-3 hours. Show HN lives or dies on whether the
    author answers comments. Ten thoughtful replies beat a better project
    with none.
  - Never ask anyone for upvotes, anywhere, including your own accounts.
    HN detects it and will kill the post outright.
  - Expect the "why not just use ChatGPT / Exa / SerpAPI" comment. The answer
    is the one above: no key, no account, and it tells you when it could not
    look. Say it plainly, don't get defensive.
  - If someone asks how you handle rate limits, that is the library idea
    arriving on its own. Answer it properly.
