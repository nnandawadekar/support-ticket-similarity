# Support Ticket Similarity Assistant

**What I built:** a Python service that, given a new support ticket, returns the most similar **resolved** past tickets with their resolution notes, and says *"no confident precedent"* instead of guessing when nothing is close enough. It has a CLI and a JSON HTTP API. The default mode is BM25F lexical retrieval using only the standard library; an optional hybrid mode adds MiniLM sentence embeddings fused with RRF. An evaluation harness measures ranking and abstention.

**Design document:** [`SOLUTION_DESIGN.pdf`](SOLUTION_DESIGN.pdf), with the Markdown source in [`SOLUTION_DESIGN.md`](SOLUTION_DESIGN.md). It covers the problem, assumptions, the architecture diagram (Figure 1), evidence, trade-offs and next steps.

## Requirement → file map

| Requirement (from the brief) | Where it is met |
|---|---|
| Show similar past tickets + how they were resolved | `ticket_similarity/service.py` (`SimilarityService.search`), `ticket_similarity/lexical.py` |
| Define what "similar" means; avoid misleading matches | `service.py` thresholds and verdicts (`strong_match` / `weak_match` / `no_match`); design §2 |
| Text normalisation (synonyms, phrases, stemming) | `ticket_similarity/text.py` |
| Optional AI bonus: semantic similarity | `ticket_similarity/semantic.py` + RRF fusion in `service.py` (`--mode hybrid`) |
| End-to-end flow for a new ticket | `ticket_similarity/cli.py` (`query`, `batch`), `ticket_similarity/server.py` (`POST /similar`) |
| Growing volume: add tickets without a rebuild | `POST /tickets` → `SimilarityService.add` (in-memory) |
| Scale assumptions (55k → 220k tickets, p95 < 300 ms) | `scripts/benchmark.py`; results under "Scale evidence" below |
| Evidence that it works | `ticket_similarity/evaluate.py`, `eval/queries.json`, `tests/` |
| Assumptions, trade-offs, future work | `SOLUTION_DESIGN.pdf` §2, §5, §6; this README "Trade-offs" and "Gaps" |

## Key files (read these first)

1. `ticket_similarity/service.py`: the public seam: validation, ranking, RRF fusion, thresholds, verdict
2. `ticket_similarity/lexical.py`: BM25F inverted index and IDF-coverage confidence
3. `ticket_similarity/text.py`: tokenizer: phrase canonicalisation, synonyms, stopwords, light stemmer
4. `ticket_similarity/semantic.py`: optional embedding index (exact cosine)
5. `ticket_similarity/server.py`: stdlib JSON HTTP API (`/health`, `/similar`, `/tickets`)
6. `ticket_similarity/evaluate.py`: hit@k, MRR, abstention metrics and threshold sweep
7. `ticket_similarity/cli.py`, `ticket_similarity/data.py`: commands and data loading
8. `tests/test_service.py`, `tests/test_lexical.py`, `tests/test_server.py`, `tests/test_evaluate.py`, `tests/test_hybrid.py`

Supporting files: `tests/test_text.py`, `tests/test_cli.py`, `scripts/benchmark.py`, `eval/queries.json` (34 labelled dev queries), `starter_kit/data/*.json` (the provided seed data, needed to run).

## Key assumptions (details and rationale: design §2)

- **"Similar"** means a comparable symptom with a plausibly reusable fix, not merely the same category. Only resolved tickets with resolution notes are searched.
- **History volume:** about 55k tickets (one year at 150/day), growing by up to 165k next year (3x volume), so about 220k in total. These are planning assumptions to confirm with the customer.
- **Response time:** p95 under 300 ms, so suggestions appear when the ticket opens.
- **Precision over recall:** no match is a valid answer. The supplied Snowflake ticket (NT-4), which has no real precedent, returns `NO CONFIDENT PRECEDENT` and is routed to triage.
- English text, no attachments, a single trusted process (no auth yet).

## How to run

Python ≥ 3.10. Lexical mode has no dependencies. Run from the repository root:

```bash
python3 -m ticket_similarity batch                         # the supplied new_tickets_example.json
python3 -m ticket_similarity query "charged twice on my card this month"
python3 -m ticket_similarity eval --sweep                  # retrieval + abstention metrics
python3 -m ticket_similarity serve --port 8000             # then:
curl -s localhost:8000/similar -d '{"subject":"Chart shows nothing","description":"empty, no bars"}'
```

Hybrid mode: `pip install -r requirements-semantic.txt`, then add `--mode hybrid` (the first run downloads MiniLM, about 90 MB).

## How to test

```bash
python3 -m pip install pytest
python3 -m pytest -q          # hybrid tests auto-skip if sentence-transformers is absent
```

Last verified 2026-11-09: **94 passed**, with hybrid tests running against a cached MiniLM model.

Development-set results (34 hand-written queries, **not** a held-out benchmark): both modes rank the right precedent first for 26/26. After thresholds, lexical shows it for 25/26 and hybrid for 26/26. Both abstain correctly on 7/8 no-fix queries.

## Trade-offs

- **Lexical first, embeddings optional, no LLM.** BM25F is explainable, dependency-free and fast. Hybrid helps vocabulary mismatch but adds a model and still makes false matches. An LLM is not needed for retrieval.
- **Precision over recall.** Weak or unrelated matches are hidden (`no_match`), because a misleading precedent is worse than none. Some useful weak precedents are lost as a result.
- **In-memory index, rebuilt from JSON.** It keeps scope small, but `POST /tickets` additions are lost on restart. Persisted search (e.g. OpenSearch + vector store) is the planned step before about 165k tickets.
- **Replaced the starter `ticket_utils.py` overlap scorer.** It has no field weighting or abstention, so it cannot say "no match". The provided data is used unchanged.
- **Exact search, not ANN.** It is simple and correct at prototype scale. ANN would only be chosen after benchmarking real histories.

## Gaps and known limitations

- The eval set is small and written by me: the thresholds are smoke-tested, not calibrated. NT-1 (undelivered reset email) is still falsely accepted as a weak match in both modes.
- Confidence is a heuristic, not a probability. Short queries are noisier (`test_short_queries_are_noisier_than_full_tickets`).
- No persistence, auth, rate limiting, multi-tenancy or PII scrubbing. English only; simple suffix stemmer; no recency weighting.
- Scale numbers are for sequential lexical calls on synthetic data. Hybrid scale and concurrent load are not measured.
- Not built: helpdesk sidebar/webhook integration, agent feedback capture, LLM fix summary (see design §6).

## What I'd do next (priority order)

1. Capture agent feedback ("helped" / "not relevant") to get real labels and a held-out set, then recalibrate thresholds.
2. Integrate with the helpdesk sidebar via webhooks (`POST /similar` on ticket created, `POST /tickets` on ticket solved).
3. Persist the index (e.g. OpenSearch + vector store), and add auth, PII controls and tenant isolation.
4. Handle recency and "fix shipped" freshness, and group duplicates.
5. Optional LLM one-line fix summary, shown only on `strong_match` and always reviewed by an agent.

---

# Reference details

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

The evaluator distinguishes raw retrieval from displayed results, and computes strong precision from the first displayed match. It reports `n/a` if there are no strong predictions. The sweep preserves candidate availability: empty retrievals always abstain, even at threshold zero, while a real zero-confidence candidate remains eligible at zero. It also reports counts of queries without candidates.

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

## Postman API scenarios (repository only; not in the submission ZIP)

Import [`postman/support-ticket-similarity.postman_collection.json`](postman/support-ticket-similarity.postman_collection.json) and select the [lexical](postman/local-lexical.postman_environment.json) or [hybrid](postman/local-hybrid.postman_environment.json) environment. There are **158 requests and 843 assertions per complete run** covering the supplied examples, all seed subjects, development paraphrases, novelty, validation and incremental ingestion.

Start a dedicated lexical test server with `python3 -m ticket_similarity serve --port 8002` (or hybrid on port 8001), then run the collection once in order. A full run changes the in-memory count from 40 to 45; restart the server before repeating it. Known retrieval limitations are explicitly labelled rather than counted as relevance successes. See the [import/run guide](postman/README.md), [case catalog](postman/CASES.md) and [verification receipt](postman/verification.json). The sweep regression is exercised by `python -m pytest tests/test_evaluate.py -q`; evaluation is a CLI command, not an HTTP endpoint.

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

Rebuild the design PDF (text plus the embedded architecture figure) from `SOLUTION_DESIGN.md` after editing it, then build the submission ZIP:

```bash
python -m pip install '.[docs]'
python scripts/render_design.py
python scripts/package_submission.py      # writes dist/support-ticket-similarity-submission.zip
```

The diagram source is `architecture.json`. Its PNG export is embedded in the PDF as a raster picture. The PNG/HTML exports, Postman assets and authoring scripts stay in the repository and are left out of the ZIP.
