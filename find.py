"""
painpoint-finder — find the people who have the problem, not just the problem.

    py -3 find.py "freelancers not getting paid for extra work"

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

import sources
import sources.reddit  # noqa: F401 - importing registers the source
from leads import has_negation, rank


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
    args = ap.parse_args()

    print(f'\nSearching for: "{args.query}"\n')

    results = sources.run_all(args.query, limit=args.limit)
    level, ok, blocked, errored = coverage(results)

    # Coverage first, always. It frames everything below it.
    print(f"COVERAGE: {level}")
    for r in ok:
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

    leads, terms = rank(results, args.query, limit=args.n)
    print(f"\nMatched on: {', '.join(terms) or '(no usable keywords)'}")

    if has_negation(args.query):
        print("\n  WARNING: your query contains a negation (\"not\", \"without\",")
        print("  \"can't\"). This version matches keywords, which cannot tell")
        print("  \"not getting paid\" from \"getting paid\" - opposite problems,")
        print("  identical keywords. Expect some results to be the inverse of")
        print("  what you asked. Rephrasing positively helps: try \"unpaid\"")
        print("  rather than \"not paid\".")

    if not leads:
        print("\nNo leads found.")
        if level in ("LOW", "PARTIAL"):
            print("Coverage was thin, so this is weak evidence either way.")
        else:
            print("Nobody in the searched sources is describing this problem.")
        return 1

    print(f"\n{len(leads)} lead(s), best first:\n")
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

    print("\nThis tool never sends anything. Read each draft, change it so it")
    print("sounds like you, and post it yourself.\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nstopped.")
        sys.exit(130)
