"""Synthetic scale test: grows the seed corpus by recombining real sentences/tags, then times index build and queries."""
import argparse
import platform
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
    if any(size < 1 for size in args.sizes) or args.queries < 1:
        parser.error("sizes and queries must be positive")

    rng = random.Random(7)
    seed = load_tickets(DEFAULT_HISTORY)
    probes = [query_text(t) for t in load_tickets(DEFAULT_NEW)] + [f"{t['subject']}\n{t['description']}" for t in seed]

    print(f"platform={platform.platform()} machine={platform.machine()} python={platform.python_version()}", flush=True)
    print(f"mode=lexical seed=7 queries_per_size={args.queries} concurrency=1 memory=peak_traced_build_MB", flush=True)
    print("Synthetic recombinations stress dense postings; not a guaranteed production worst case. HTTP and hybrid are not measured.", flush=True)
    print(f"{'tickets':>9} {'build_s':>8} {'mem_mb':>7} {'p50_ms':>7} {'p95_ms':>7} {'p99_ms':>7}", flush=True)
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
        print(f"{size:>9} {build:>8.1f} {mem:>7.0f} {statistics.median(timings):>7.1f} {p(0.95):>7.1f} {p(0.99):>7.1f}", flush=True)
        del service


if __name__ == "__main__":
    main()
