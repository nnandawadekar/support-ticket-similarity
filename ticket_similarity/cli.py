import argparse
import json
import logging
import sys
import textwrap
from pathlib import Path

from .data import DEFAULT_HISTORY, DEFAULT_NEW, REPO_ROOT, load_tickets, query_text
from .service import NONE, STRONG, SimilarityService

DEFAULT_EVAL = REPO_ROOT / "eval" / "queries.json"
LABELS = {STRONG: "STRONG MATCH", "weak_match": "POSSIBLE MATCH", NONE: "NO CONFIDENT PRECEDENT"}


def build_service(args):
    return SimilarityService(load_tickets(args.history), mode=args.mode, top_k=args.top_k)


def render(result, header=None):
    lines = []
    if header:
        lines.append(header)
    lines.append(f"  {LABELS[result.verdict]}  ({result.mode}, {result.latency_ms}ms)")
    for m in result.matches:
        lines.append(f"  [{m.confidence:.2f}] {m.ticket_id} ({m.category}, {m.created_at}) {m.subject}")
        lines.extend(textwrap.wrap(m.resolution_notes, 100, initial_indent="      fix: ", subsequent_indent="           "))
        if m.matched_terms:
            lines.append(f"      matched: {', '.join(m.matched_terms)}")
    if result.verdict == NONE and result.nearest:
        n = result.nearest
        lines.append(f"  closest was {n.ticket_id} ({n.subject}) at {n.confidence:.2f}; treat as a new issue and route to triage")
    return "\n".join(lines)


def cmd_query(args):
    service = build_service(args)
    text = " ".join(args.text) if args.text else sys.stdin.read()
    result = service.search(text)
    print(json.dumps(result.to_dict(), indent=2) if args.json else render(result))


def cmd_batch(args):
    service = build_service(args)
    results = []
    for ticket in load_tickets(args.file):
        result = service.search(query_text(ticket))
        if args.json:
            results.append({"ticket_id": ticket.get("ticket_id"), **result.to_dict()})
        else:
            print(render(result, header=f"\n{ticket.get('ticket_id')}: {ticket.get('subject')}"))
    if args.json:
        print(json.dumps(results, indent=2))


def cmd_eval(args):
    from .evaluate import format_report, load_queries, misses, run, sweep

    tickets = load_tickets(args.history)
    queries = load_queries(args.queries)
    for mode in args.modes:
        report, rows = run(tickets, queries, mode)
        print(format_report(report))
        if args.sweep:
            print(f"  sweep: {sweep(rows)}")
        for line in misses(rows):
            print(line)


def cmd_serve(args):
    from .server import serve

    serve(build_service(args), host=args.host, port=args.port)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ticket_similarity", description="Surface similar resolved support tickets.")
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY, help="historical tickets JSON")
    parser.add_argument("--mode", choices=("lexical", "hybrid"), default="lexical")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    q = sub.add_parser("query", help="find matches for free text (or stdin)")
    q.add_argument("text", nargs="*")
    q.set_defaults(func=cmd_query)

    b = sub.add_parser("batch", help="run every ticket in a JSON file")
    b.add_argument("file", type=Path, nargs="?", default=DEFAULT_NEW)
    b.set_defaults(func=cmd_batch)

    e = sub.add_parser("eval", help="retrieval + abstention metrics on a labelled query set")
    e.add_argument("--queries", type=Path, default=DEFAULT_EVAL)
    e.add_argument("--modes", nargs="+", choices=("lexical", "hybrid"), default=["lexical"])
    e.add_argument("--sweep", action="store_true", help="report the best abstain threshold")
    e.set_defaults(func=cmd_eval)

    s = sub.add_parser("serve", help="JSON HTTP API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose or args.command == "serve" else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
