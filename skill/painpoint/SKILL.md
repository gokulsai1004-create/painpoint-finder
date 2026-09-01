---
name: painpoint
version: 1.0.0
description: Check whether anyone actually has the problem behind an idea. Searches five public sources for people describing it right now, separates out who has already built it, and drafts an opener you edit and send yourself. No API key.
triggers:
  - is anyone actually asking for this
  - validate this idea
  - who has this problem
  - has someone already built this
  - should I build this
allowed-tools:
  - Bash
  - Read
---

# painpoint

Someone has an idea. Before they spend months on it, three questions matter:
**is the problem real, has somebody already solved it, and can I talk to one of
these people today?**

This skill answers all three from public data, with no API key and no account.

## When to use this

Use it the moment someone describes something they want to build — before
writing any code for it. That is the whole point: a search costs a minute, and
building the wrong thing costs months.

Also use it when someone asks whether an idea is "taken", who the competitors
are, or where to find users to talk to.

**Do not** use it to decide for them. It reports evidence. It does not know
whether an idea is good, and saying so is part of using it correctly.

## Setup (first run only)

The tool is a small Python program. Check whether it is already present next to
this skill, and clone it if not:

```bash
SKILL_DIR="$(dirname "$0")"   # or the directory this SKILL.md lives in
if [ ! -d "$SKILL_DIR/painpoint-finder" ]; then
  git clone --depth 1 https://github.com/gokulsai1004-create/painpoint-finder.git "$SKILL_DIR/painpoint-finder"
fi
python -c "import requests" 2>/dev/null || pip install requests
```

Optional but much better ranking — a 50MB model that runs locally, offline
after the first download:

```bash
pip install fastembed
```

If `fastembed` is missing the tool degrades to keyword-only and says so. Do not
install it without asking; it is a real download.

## Running it

```bash
python painpoint-finder/find.py "<what they want to build, in their own words>"
```

**Pass their words through unchanged.** Do not rewrite the idea into a
"better" problem statement first — the tool detects idea-shaped queries itself,
strips the builder's framing, and tells the user what it searched instead. If
you pre-translate, you hide that step from them and you will often get it wrong.

Useful flags:

- `-n 5` — how many leads to return (default 5)
- `--no-semantic` — skip the local model; faster, noticeably worse

Expect **40–70 seconds**. Say so before running it, so the wait is not a
surprise.

## Reading the output — this is the part that matters

The output has four blocks. Read them to the user in this order and do not
skip the first one.

### 1. COVERAGE — read this before anything else

```
COVERAGE: PARTIAL
  searched reddit (194 posts)
  COULD NOT SEARCH stackexchange - too many requests from this IP
```

`COULD NOT SEARCH` means that source was **refused and never looked**. It does
**not** mean nothing was there.

**This is the single most important thing to convey.** If two of five sources
were blocked, a low match count is not evidence of anything. Never summarise a
partially-blocked run as "not much interest in this" — say the search was
incomplete and offer to re-run later. Getting this wrong tells someone their
real problem is imaginary, which is the worst outcome this tool can produce.

### 2. VERDICT — a ratio, not a judgement

```
VERDICT: MODERATE signal
  12 of 316 posts matched (3.8%)
  match quality: 0.68 (4 recent enough to reply to)
```

`MODERATE` means 3.8% of what it read was about their thing. **It does not mean
go, and WEAK does not mean stop.** Report the ratio, not just the word. If
`match quality` is below about 0.62 the matches share words with the query but
are mostly about something else — say that plainly.

Themes listed under "what the other posts are about instead" are worth
surfacing. A louder theme next to a quiet one is often the more interesting
idea.

### 3. ALREADY BUILDING THIS — usually the most decision-relevant block

```
3 ALREADY BUILDING THIS - your competition:
  [1] psmux/psmux - 3400 stars
      flagged by: "a shipped repository"
```

Lead with this when it is non-empty. "Three people already shipped this"
changes what someone does tomorrow far more than one more complaint does.

Each entry shows **the words that flagged it**. The classifier has a known tail
of mistakes — if a reason looks wrong (`flagged by: "I got tired of"` on
somebody clearly in pain), say so and treat that person as a lead instead. A
judgement you cannot inspect is one you cannot overrule, which is why it prints.

### 4. PEOPLE YOU CAN REPLY TO — with a drafted opener

Real people, recent enough to answer, each with a draft that quotes them.

**The tool never sends anything, and neither do you.** Offer to help edit a
draft so it sounds like them. Never offer to post it. If the user asks you to
send it, decline and explain that outreach has to come from them — a tool that
messages fifty strangers is a spam cannon, and that constraint is deliberate.

## After the run

Suggest exactly one next step, chosen from what actually came back:

- **Competitors found** → read what they built and what people say back to
  them. If several exist and none has taken the market, ask why.
- **Real leads found** → pick one, edit the draft, send it themselves today.
- **Coverage was partial** → re-run in fifteen minutes before concluding
  anything.
- **Genuinely thin, full coverage** → look at the louder themes. That is how
  this tool's own author found his second idea after his first died.

## Honest limitations — state these when they apply

- **Negation defeats it.** "not getting paid" and "getting paid" are opposite
  problems with identical keywords, and the embedding model scores them 0.906
  similar. The tool warns on negated queries; repeat the warning rather than
  glossing over it. "unpaid invoices" works far better than "not paid".
- **Rate limits are real.** Free public endpoints refuse anonymous traffic.
  Stack Exchange allows 300 requests/day per IP and one search costs 8–16, so
  roughly 20 searches a day. Setting `STACKEXCHANGE_KEY` raises it to 10,000.
- **It does not know if the idea is good.** Say this out loud if the user
  starts treating the verdict as permission or as a refusal.
