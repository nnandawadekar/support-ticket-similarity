"""Synthetic scale test: grows the seed corpus by recombining real sentences/tags, then times index build and queries."""
import argparse
import random
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ticket_similarity.data import DEFAULT_HISTORY, DEFAULT_NEW, load_tickets, query_text  # noqa: E402
from ticket_similarity.service import SimilarityService  # noqa: E402


def synth(seed, n, rng):
    subjects = [t["subject"] for t in seed]
    descriptions = [t["description"] for t in seed]
    resolutions = [t["resolution_notes"] for t in seed]
    tags = sorted({tag for t in seed for tag in t["tags"]})
    for i in range(n):
        yield {
            "ticket_id": f"S-{i}",
            "category": rng.choice(seed)["category"],
            "subject": rng.choice(subjects),
            "description": f"{rng.choice(descriptions)} {rng.choice(descriptions)}",
            "resolution_notes": rng.choice(resolutions),
            "tags": rng.sample(tags, 3),
            "status": "resolved",
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", type=int, nargs="+", default=[10_000, 55_000, 165_000])
    parser.add_argument("--queries", type=int, default=200)
    args = parser.parse_args()

    rng = random.Random(7)
    seed = load_tickets(DEFAULT_HISTORY)
    probes = [query_text(t) for t in load_tickets(DEFAULT_NEW)] + [f"{t['subject']}\n{t['description']}" for t in seed]

    print(f"{'tickets':>9} {'build_s':>8} {'mem_mb':>7} {'p50_ms':>7} {'p95_ms':>7} {'p99_ms':>7}")
    for size in args.sizes:
        tracemalloc.start()
        started = time.perf_counter()
        service = SimilarityService(list(synth(seed, size, rng)))
        build = time.perf_counter() - started
        mem = tracemalloc.get_traced_memory()[1] / 1e6
        tracemalloc.stop()

        timings = []
        for _ in range(args.queries):
            q = rng.choice(probes)
            t0 = time.perf_counter()
            service.search(q)
            timings.append((time.perf_counter() - t0) * 1000)
        timings.sort()
        p = lambda pct: timings[min(len(timings) - 1, int(pct * len(timings)))]  # noqa: E731
        print(f"{size:>9} {build:>8.1f} {mem:>7.0f} {statistics.median(timings):>7.1f} {p(0.95):>7.1f} {p(0.99):>7.1f}")


if __name__ == "__main__":
    main()
