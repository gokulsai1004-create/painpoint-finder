"""
painpoint-finder — find the people who have the problem, not just the problem.

    python find.py "client refuses to pay for revisions"

Every other tool in this space stops at a report. This one ends at a person and
something to say to them. It never sends anything: it drafts, you edit, you post.
"""

import argparse
import io
import sys
import textwrap

# Windows consoles default to cp1252, which cannot print the em-dashes and
# smart quotes people actually use. Reconfigure rather than strip: mangling a
# quote defeats the point of quoting someone verbatim.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
elif isinstance(sys.stdout, io.TextIOWrapper):  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# One required dependency, and the failure to install it should read like a
# sentence rather than a stack trace. Someone trying this from a Show HN link
# who skipped the pip line gets a wall of red otherwise, and concludes the tool
# is broken rather than that they missed a step.
try:
    import sources
    import sources.github  # noqa: F401 - importing registers the source
    import sources.hackernews  # noqa: F401
    import sources.reddit  # noqa: F401
    import sources.stackexchange  # noqa: F401
    import sources.web  # noqa: F401
except ImportError as exc:
    missing = getattr(exc, "name", None) or "a dependency"
    print(f"\n  Missing dependency: {missing}\n", file=sys.stderr)
    print("  This tool needs one package. Install it with:\n", file=sys.stderr)
    print("      pip install requests\n", file=sys.stderr)
    print("  If pip is not found, try:  python -m pip install requests",
          file=sys.stderr)
    print("  Optional, for much better ranking:  pip install fastembed\n",
          file=sys.stderr)
    raise SystemExit(2)

from leads import has_negation, looks_like_an_idea, problem_in, rank
from verdict import explain, summarise


def coverage(results):
    """How much to trust this run.

    Reported separately from the results because zero leads means nothing until
    you know whether we were able to look. A blocked source is not evidence of
    absence, and saying otherwise would be the worst bug this tool could have.
    """
    ok = [r for r in results if r.usable]
    blocked = [r for r in results if r.status == sources.BLOCKED]
    errored = [r for r in results if r.status == sources.ERROR]

    if not ok:
        level = "NONE"
    elif blocked or errored:
        level = "PARTIAL"
    elif len(ok) == 1:
        level = "LOW"
    else:
        level = "MEDIUM"

    return level, ok, blocked, errored


def wrap(text, indent="    "):
    out = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        out.extend(textwrap.wrap(para, width=76,
                                 initial_indent=indent, subsequent_indent=indent))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(
        description="Find people currently talking about a problem.")
    ap.add_argument("query", help="the problem, in your own words")
    ap.add_argument("-n", type=int, default=5, help="how many leads (default 5)")
    ap.add_argument("--limit", type=int, default=100,
                    help="posts to pull per source (default 100)")
    ap.add_argument("--no-semantic", action="store_true",
                    help="skip meaning-based reranking (faster, less accurate)")
    args = ap.parse_args()

    # These land in list slices, where 0 and negatives quietly return nothing
    # at all rather than failing. A user who typed -n 0 by accident would read
    # that as "no leads found" and believe it.
    if args.n < 1:
        ap.error("-n must be at least 1")
    if args.limit < 1:
        ap.error("--limit must be at least 1")

    # An idea is not a problem. Someone arriving here has an idea - that is
    # why they came - but the people with the pain never use the builder's
    # words, so searching the idea verbatim finds other builders. Search the
    # problem inside it instead, and say plainly that that is what happened:
    # a tool that quietly searched the wrong thing and reported WEAK would
    # talk someone out of a real idea, which is the worst thing it could do.
    query = args.query
    if looks_like_an_idea(query):
        query = problem_in(query)
        print('\nThat reads like an idea, not a problem.')
        print(f'  you asked : "{args.query}"')
        print(f'  I searched: "{query}"\n')
        print('  People in pain do not use your words. They never write')
        print('  "I need an app for this" - they write the complaint. You')
        print('  will get better leads searching what THEY would type.\n')
    else:
        print(f'\nSearching for: "{query}"\n')

    results = sources.run_all(query, limit=args.limit)
    level, ok, blocked, errored = coverage(results)

    # Coverage first, always. It frames everything below it.
    # Staleness belongs on the headline, not only in the per-source detail.
    # These are the two lines a user actually acts on, and a run where nothing
    # was searched just now must not read identically to a live one.
    cached = [r for r in ok if r.from_cache]
    if cached and len(cached) == len(ok):
        level = f"{level} (ALL CACHED)"
    elif cached:
        level = f"{level} (PARTLY CACHED)"

    print(f"COVERAGE: {level}")
    for r in ok:
        if r.from_cache:
            # Never let a cached answer look fresh. The tool's whole claim is
            # honesty about the strength of its own evidence.
            print(f"  {r.source}: CACHED from {r.from_cache} "
                  f"({r.searched} posts) - live search was refused")
        else:
            print(f"  searched {r.source} ({r.searched} posts)")
    for r in blocked:
        print(f"  COULD NOT SEARCH {r.source} - {r.detail}")
    for r in errored:
        print(f"  FAILED {r.source} - {r.detail}")

    if level == "NONE":
        print("\nNo source could be searched, so this run tells you nothing.")
        print("It is NOT evidence that nobody has this problem. Try again later.")
        return 2

    if level == "PARTIAL":
        print("\n  Some sources could not be searched. Treat a low count as")
        print("  incomplete rather than as an answer.")

    leads, builders, pages, terms = rank(
        results, query, limit=args.n, semantic_on=not args.no_semantic)
    print(f"\nMatched on: {', '.join(terms) or '(no usable keywords)'}")

    # Say which ranking actually ran. Keyword-only ordering is noticeably
    # worse, and a user comparing two runs deserves to know why.
    reranked = any(l.get("reranked") for l in leads + pages)
    if reranked:
        print("Ranked by meaning (local model, offline)")
    elif not args.no_semantic:
        import semantic
        if not semantic.available():
            print("Ranked by keywords only - install fastembed for better "
                  "results: pip install fastembed")

    if has_negation(query):
        print("\n  WARNING: your query contains a negation (\"not\", \"without\",")
        print("  \"can't\"). This version matches keywords, which cannot tell")
        print("  \"not getting paid\" from \"getting paid\" - opposite problems,")
        print("  identical keywords. Expect some results to be the inverse of")
        print("  what you asked. Rephrasing positively helps: try \"unpaid\"")
        print("  rather than \"not paid\".")

    # The verdict goes before the leads. Seven matches reads as promising until
    # you learn it was seven out of nine hundred, and by then you have already
    # started planning what to build.
    summary = summarise(results, leads, pages, terms, builders)
    stale = " (from cached results)" if cached else ""
    print("\n" + "=" * 78)
    print(f"VERDICT: {summary['signal']} signal{stale}")
    print(f"  {summary['matched']} of {summary['searched']} posts matched "
          f"({summary['rate'] * 100:.1f}%)")
    if summary.get("quality") is not None:
        print(f"  match quality: {summary['quality']:.2f} "
              f"({summary['people']} recent enough to reply to)")
    print(wrap(explain(summary["signal"], summary["rate"], summary["searched"],
                       summary.get("caveat", "")), indent="  "))

    if summary["themes"]:
        print("\n  What the other posts are about instead:")
        for phrase, count in summary["themes"]:
            print(f"    {count:4d}  {phrase}")
        print("\n  A louder theme than yours is worth a look. This is how this")
        print("  tool's own author found his second idea after the first died.")
    print("=" * 78)

    if not leads and not builders and not pages:
        print("\nNothing found.")
        if level in ("LOW", "PARTIAL"):
            print("Coverage was thin, so this is weak evidence either way.")
        else:
            print("Nobody in the searched sources is describing this problem.")
        return 1

    if builders:
        # Before the leads, deliberately. If somebody already shipped this, that
        # changes what you do tomorrow more than one more complaint would, and a
        # reader who has already started drafting replies has stopped deciding.
        print(f"\n{len(builders)} ALREADY BUILDING THIS - your competition:\n")
        for i, b in enumerate(builders, 1):
            p = b["post"]
            print(f"  [{i}] {p.title.strip()[:70]}")
            print(f"      {p.source} - {b['age']}")
            print(f"      {p.url[:88]}")
        print("\n  Not leads, and not nothing. Read what they built and what")
        print("  people say back to them - that is the fastest free research")
        print("  you will get. If several exist and none has taken the market,")
        print("  the interesting question is why.")

    if leads:
        print(f"\n{len(leads)} PERSON/PEOPLE you can reply to, best first:\n")
        print("=" * 78)

        for i, lead in enumerate(leads, 1):
            p = lead["post"]
            print(f"\n[{i}] {p.title.strip()[:90]}")
            print(f"    {p.source} - {lead['age']} - by {p.author or 'unknown'}")
            print(f"    match: {', '.join(lead['matched'])} (score {lead['score']})")
            print(f"    {p.url}")
            print("\n    --- draft reply (edit before sending) ---")
            print(wrap(lead["draft"]))
            print("\n" + "-" * 78)
    else:
        print("\nNo people found to reply to.")
        if pages:
            print("The topic exists on the web, but nobody in the searched")
            print("communities is currently discussing it.")

    if pages:
        # Evidence the topic is real, but not someone who will answer: either a
        # page with no author, or a person who posted too long ago to reply.
        print(f"\n{len(pages)} MORE - evidence the topic is real, but not "
              f"people to message:\n")
        for i, page in enumerate(pages, 1):
            p = page["post"]
            reason = page.get("why_not_lead")
            if reason == "too old":
                why = f"too old ({page['age']})"
            elif reason == "nothing written":
                why = "nothing written - photo or link only"
            else:
                why = "no author"
            print(f"  [{i}] {p.title.strip()[:70]}")
            print(f"      {p.source} - {why}")
            print(f"      {p.url[:88]}")
        print("\n  No drafts for these: nobody would see the reply.")

    if leads:
        print("\nThis tool never sends anything. Read each draft, change it so it")
        print("sounds like you, and post it yourself.")
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nstopped.")
        sys.exit(130)
