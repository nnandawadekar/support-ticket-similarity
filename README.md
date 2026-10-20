# Support Ticket Similarity Assistant

Given a new support ticket, returns the most similar **resolved** tickets and how they were fixed. When nothing in the history is close enough, it says so instead of guessing. Design rationale, assumptions and trade-offs: [`SOLUTION_DESIGN.md`](SOLUTION_DESIGN.md) ([PDF](SOLUTION_DESIGN.pdf)). Interactive architecture diagram: [`architecture.html`](architecture.html) (open in a browser). The original brief: [`case-study-brief.md`](case-study-brief.md).

## Quickstart

The default (lexical) mode is pure standard library, Python ≥ 3.10:

```bash
python3 -m ticket_similarity batch                       # runs starter_kit/data/new_tickets_example.json
python3 -m ticket_similarity query "charged twice on my card this month"
python3 -m ticket_similarity eval --sweep                # retrieval + abstention metrics
```

Hybrid mode (BM25F + sentence embeddings) and tests:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-semantic.txt pytest
python -m ticket_similarity --mode hybrid batch            # first hybrid use downloads MiniLM (~90 MB)
python -m ticket_similarity eval --modes lexical hybrid --sweep
python -m pytest -q                                      # hybrid tests auto-skip if sentence-transformers is absent
```

Example output:

```
NT-3: Getting charged twice this month
  STRONG MATCH  (lexical, 0.1ms)
  [0.75] T-1303 (billing, 2025-10-28) Charged twice for the same billing cycle
      fix: A retry mechanism for a previously failed payment double-charged after the original
           payment actually succeeded on the processor's side. Refunded the duplicate charge and
           added idempotency keys to the retry logic.
      matched: charg, twic, card, statement, two, singl, monthly, payment

NT-4: Our data warehouse integration with Snowflake is failing
  NO CONFIDENT PRECEDENT  (lexical, 0.29ms)
  closest was T-1102 (Sync job stuck at 'in progress' for 2 days) at 0.15; treat as a new issue and route to triage
```

## CLI

```
python -m ticket_similarity [--history PATH] [--mode lexical|hybrid] [--top-k N] [--json] <command>

  query TEXT...          free text, or read from stdin
  batch [FILE]           every ticket in a {"tickets"|"new_tickets": [...]} JSON file
  eval [--modes ...] [--sweep] [--queries PATH]
  serve [--host H] [--port P]
```

## HTTP API

```bash
python -m ticket_similarity serve --port 8000
```

| Method | Path | Body | Notes |
|---|---|---|---|
| `GET` | `/health` | – | mode and indexed count |
| `POST` | `/similar` | `{"subject", "description"}` or `{"text"}`, optional `ticket_id`, `top_k` (1–20) | what a helpdesk `ticket.created` webhook would call |
| `POST` | `/tickets` | a resolved ticket (`ticket_id`, `subject`, `description`, `resolution_notes`, …) | incremental index; `201` added, `200` already indexed or not resolved |

```bash
curl -s localhost:8000/similar -d '{"subject":"Chart shows nothing for the revenue tab","description":"empty, no bars"}'
```

```json
{
  "ticket_id": null,
  "verdict": "strong_match",
  "matches": [
    {"ticket_id": "T-1201", "subject": "Revenue chart shows blank instead of bars", "category": "render",
     "resolution_notes": "A recent filter combination produced a zero-row result set, ...", "created_at": "2025-10-08",
     "confidence": 0.59, "signals": {"bm25f": 9.734, "coverage": 0.59},
     "matched_terms": ["chart", "show", "revenu", "blank", "bar"]},
    {"ticket_id": "T-1204", "subject": "Custom date range filter not updating chart", "confidence": 0.208, "...": "..."}
  ],
  "nearest": {"ticket_id": "T-1201", "...": "..."},
  "mode": "lexical",
  "latency_ms": 0.13
}
```

`verdict` is one of `strong_match`, `weak_match` or `no_match`, and describes the **first displayed match**. `matches` retains BM25F/RRF order after filtering at the weak threshold and limiting to `top_k`. A higher-confidence candidate further down the ranking cannot upgrade that first match's verdict. `nearest` is the first displayed match, or the top raw retrieval candidate if no match qualifies; it is `null` when there are no candidates.

Confidence is a heuristic, not a probability that the fix applies. A weak match is related evidence to investigate, not a diagnosis. In hybrid mode, a candidate missing from either top-50 signal pool receives zero for that signal.

All indexed text fields must be strings; tags must be a list of strings (or omitted/null). Integer IDs, including zero, are normalized to strings. Malformed ticket batches are rejected before indexing; tickets without a status are treated as resolved, so a real helpdesk importer must map its statuses. Unresolved tickets and blank resolution notes are not indexed. The API returns validation errors as JSON with status 400.

## Layout

```
ticket_similarity/
  text.py       tokenizer: phrase canonicalisation, synonyms, stopwords, light stemmer
  lexical.py    BM25F inverted index + IDF-coverage confidence
  semantic.py   optional sentence-transformers index (exact cosine)
  service.py    fusion (RRF), thresholds, verdicts, incremental adds; the one public seam
  server.py     stdlib ThreadingHTTPServer JSON API
  evaluate.py   hit@k / MRR / abstention metrics + threshold sweep
  cli.py
eval/queries.json        34 development queries (26 precedents, 8 without a reusable fix)
scripts/benchmark.py     synthetic scale test (10k / 55k / 165k tickets)
tests/                   pytest suite (tokenizer, index, service, HTTP, hybrid)
starter_kit/             provided data + starter utility (unchanged)
```

## Current results

Run `python -m ticket_similarity eval --modes lexical hybrid --sweep`. This is a hand-written development smoke set, used during implementation, **not a held-out benchmark**.

| Metric | lexical | hybrid |
|---|---|---|
| Raw hit@1 / hit@3 / MRR, before threshold filtering | 1.00 / 1.00 / 1.00 | 1.00 / 1.00 / 1.00 |
| Correct first displayed match, on 26 positives | 25/26 | 26/26 |
| No-precedent queries correctly abstained, on 8 negatives | 7/8 | 7/8 |
| Precedents wrongly abstained | 1/26 | 0/26 |
| Precision of the first displayed match on strong verdicts | 18/18 | 24/24 |

**Known false acceptance:** NT-1 describes an undelivered password-reset email. T-1001 describes a password rejected after the reset email arrived; its password-case workaround does not address email delivery. Both modes return this as a weak related match. NT-1 is therefore labelled negative, rather than inflating the success rate by treating related vocabulary as a reusable resolution. Lexical also abstains on P-04 (session expiry). Both modes correctly abstain on the supplied Snowflake ticket.

Initial policy thresholds (weak / strong) are lexical **0.20 / 0.45** and hybrid **0.35 / 0.55**. They were checked on this smoke set, not independently calibrated. `--sweep` searches weak thresholds from 0 to 1 in 0.01 steps, maximizes in-sample balanced accuracy, and reports a suggestion without changing defaults. On the current labels it suggests lexical 0.35 and hybrid 0.52; both would abstain on all 8 negatives but retain only 24/26 positives. Strong thresholds are policy choices, not outputs of the sweep. Collect independent labels before adjusting either tier.

The evaluator distinguishes raw retrieval from displayed results, and computes strong precision from the first displayed match. It reports `n/a` if there are no strong predictions.

## Scale evidence

```bash
python3 scripts/benchmark.py --sizes 10000 55000 165000 --queries 200
```

Measured on 2026-10-20, macOS 27.0.1, arm64, Python 3.13.3:

| Tickets | Lexical p50 / p95 / p99 | Build | Peak traced build allocation |
|---|---|---|---|
| 10k | 8.0 / 10.8 / 12.1 ms | 2.3 s | 88 MB |
| 55k | 53.8 / 76.6 / 83.8 ms | 13.5 s | 481 MB |
| 165k | 179.8 / 243.4 / 253.2 ms | 39.7 s | 1,461 MB |

Build time includes synthetic corpus generation and index construction under `tracemalloc`. Memory is **peak traced Python allocation during that build**, not total process RSS. Queries run sequentially in the same process after indexing; timings exclude HTTP, queueing and model work. Random seed is 7, with 200 sampled queries per size. Recombined seed sentences create dense postings; this stresses lexical retrieval but is not a guaranteed production worst case. Data length, hardware and concurrency can all change results. Hybrid scale performance has not been established by this script; the former isolated dense timing and million-vector claims are not used as capacity evidence.

Planning assumptions: up to 55k existing resolved tickets, then up to 165k additional tickets over a year at 3x today's daily volume, about 220k total. Move to persisted search **before approaching 165k retained tickets**, and load-test the actual hardware and burst workload against the p95 < 300 ms service target. The table is an experiment, not a production capacity guarantee.

## Known limitations / not handled

- **The eval set is mine and small.** Thresholds are calibrated on 34 queries I wrote after reading the data, so treat the metrics as a smoke test, not a benchmark.
- **Confidence does not establish a shared root cause.** Short lexical queries can clear the weak threshold on common words (see `test_short_queries_are_noisier_than_full_tickets`). Send subject + description for context; hybrid is an option to evaluate, not a guarantee against false matches. NT-1 remains a false acceptance in both modes.
- **The index is in memory**, rebuilt from JSON at startup; tickets added via `POST /tickets` are lost on restart. The measurements above are for sequential lexical calls only; use the migration checkpoint in §5 of the design doc.
- No auth, rate limiting, multi-tenancy or PII scrubbing on the HTTP API.
- English only. The stemmer is a deliberately simple suffix stripper, not Porter/Snowball.
- No recency weighting: an old workaround for a since-fixed bug ranks the same as a current fix.
- The hybrid model is downloaded from Hugging Face on first use. Set `TICKET_SIM_MODEL` to point at a local path for offline or air-gapped deploys.

## What I'd do next

In priority order: agent feedback capture (helped / not relevant) to get real labels → helpdesk sidebar integration via webhooks → persisted index → recency and "fix shipped" handling → LLM one-line fix summary gated on `strong_match`. Details are in `SOLUTION_DESIGN.md` §6.

## Verification and demo

```bash
python3 -m ticket_similarity batch
python3 -m ticket_similarity eval --sweep
python3 -m pip install pytest
python3 -m pytest -q                             # lexical-only setup skips hybrid tests
# With the semantic dependencies installed and model already cached:
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest -q
```

Run from the repository root. The offline flags prevent Hugging Face metadata/network checks when the model is cached; they do not install or download missing files. Installing `sentence-transformers` alone does not make hybrid tests offline-ready: the first hybrid invocation also needs the model weights.

For the panel demo: show NT-2/NT-3 and their resolutions, NT-4 abstention, then NT-1 as a weak related result whose fix does not transfer. Show `eval --sweep` and explain the precision/recall trade-off and the limits of development labels. The implementation and design make no claim that suggested resolutions are automatically safe to apply.

Rebuild the two-page PDF from its Markdown source after editing it:

```bash
python -m pip install '.[docs]'
python scripts/render_design.py
```

The architecture source is `architecture.json`; its interactive and PNG exports accompany the design.
