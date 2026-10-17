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
pip install -r requirements-semantic.txt pytest          # first run downloads all-MiniLM-L6-v2 (~90 MB)
python -m ticket_similarity --mode hybrid batch
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

`verdict` is one of `strong_match`, `weak_match` or `no_match`. `matches` only contains results at or above the weak threshold. `nearest` is always the top candidate, for transparency.

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
eval/queries.json        34 labelled queries (27 with a precedent, 7 novel)
scripts/benchmark.py     synthetic scale test (10k / 55k / 165k tickets)
tests/                   pytest suite (tokenizer, index, service, HTTP, hybrid)
starter_kit/             provided data + starter utility (unchanged)
```

## Current results

| | lexical | hybrid |
|---|---|---|
| hit@1 / MRR | 1.00 / 1.00 | 1.00 / 1.00 |
| novel tickets abstained | 7/7 | 7/7 |
| precedents wrongly abstained | 1/27 | 0/27 |
| confidence margin, precedent vs novel | 0.02 | 0.11 |

Lexical p95 is 74 ms at 55k tickets and 232 ms at 165k on a synthetic worst case (`python3 scripts/benchmark.py`). See the design doc for how to read these numbers.

## Known limitations / not handled

- **The eval set is mine and small.** Thresholds are calibrated on 34 queries I wrote after reading the data, so treat the metrics as a smoke test, not a benchmark.
- **Lexical confidence is fragile on very short queries.** A 4–5 word query can clear the weak threshold on two common words (see `test_short_queries_are_noisier_than_full_tickets`). Hybrid mode, or sending subject + description as the API expects, avoids this.
- **The index is in memory**, rebuilt from JSON at startup; tickets added via `POST /tickets` are lost on restart. Fine up to ~165k tickets (~40 s build, ~1.4 GB); beyond that see §5 of the design doc.
- No auth, rate limiting, multi-tenancy or PII scrubbing on the HTTP API.
- English only. The stemmer is a deliberately simple suffix stripper, not Porter/Snowball.
- No recency weighting: an old workaround for a since-fixed bug ranks the same as a current fix.
- The hybrid model is downloaded from Hugging Face on first use. Set `TICKET_SIM_MODEL` to point at a local path for offline or air-gapped deploys.

## What I'd do next

In priority order: agent feedback capture (helped / not relevant) to get real labels → helpdesk sidebar integration via webhooks → persisted index → recency and "fix shipped" handling → LLM one-line fix summary gated on `strong_match`. Details are in `SOLUTION_DESIGN.md` §6.
