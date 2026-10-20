# Local API testing with Postman

Import [the collection](support-ticket-similarity.postman_collection.json) and choose either the [lexical environment](local-lexical.postman_environment.json) or the [hybrid environment](local-hybrid.postman_environment.json). The collection contains **158 requests, 843 assertions per complete run, and nine ordered folders**. [CASES.md](CASES.md) lists every request and its expected outcome.

## Start a fresh local server

From the repository root, in a terminal:

```bash
python3 -m ticket_similarity serve --port 8002
```

For hybrid mode, use a second terminal after installing the semantic dependencies:

```bash
.venv/bin/python -m ticket_similarity --mode hybrid serve --port 8001
```

The first hybrid use needs the MiniLM download. If weights are already cached, use `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` before the hybrid command to avoid network checks. Lexical mode has no model or third-party runtime dependency.

These environments deliberately use dedicated testing ports; the ordinary CLI server still defaults to port 8000. If a port is occupied, change `--port` and the selected environment's `baseUrl` together. Keep `expectedMode` equal to the mode actually running.

## Import and run

1. In the Postman desktop app, use **Import** and select the collection JSON and one or both environment JSON files.
2. Select **Ticket Similarity - Local Lexical** or **Ticket Similarity - Local Hybrid** in the environment selector.
3. Open the collection, choose **Run**, select all requests in their saved order, and use **one iteration**. No iteration data file, authentication or API key is required.
4. Review the post-response assertion results. The first health check requires the original **40 indexed tickets**. The final check expects **45**, after exactly five resolved tickets were added.
5. Stop the server with **Ctrl+C** and restart it before another complete collection run. This restores the seed history because ingestion is in memory. It does not change `starter_kit/data/tickets.json`.

Use the desktop app or desktop agent for localhost requests; a cloud-only runner cannot reach your computer's loopback address. The Postman [Collection Runner guide](https://learning.postman.com/latest-v-12/docs/tests-and-scripts/running-collections/intro-to-collection-runs) describes the runner controls. Scripts use [collection-scoped variables](https://learning.postman.com/docs/tests-and-scripts/write-scripts/postman-sandbox-reference/pm-variables) for the run ID and expected index count.

Read-only requests in folders 01-05 can also be sent individually against a fresh server. Run folder 08 in order after the preflight; its later requests depend on the ticket IDs and count established earlier. Folders 00-07 leave the seed history unchanged. Full runs require a restart because newly ingested tickets alter corpus frequencies and can change the later retrieval results. Running twice without a restart intentionally fails the clean-history preflight; UUIDs prevent collisions for most tickets, but the integer-ID test also uses ID zero.

## What the folders prove

| Folder | Requests | Evidence |
|---|---:|---|
| 00 - Start here | 5 | Health, expected mode, clean seed count, JSON 404s, route methods |
| 01 - Customer examples | 4 | All supplied examples, resolutions, correlation IDs, Snowflake abstention, known NT-1 limitation |
| 02 - Exact historical subjects | 40 | Each historical subject retrieves its own fix across all seed categories; sanity checks only |
| 03 - Development paraphrases | 24 | Existing development labels, including the lexical P-04 miss and hybrid recovery |
| 04 - Novelty and normalization | 12 | Novel subjects, no lexical candidates, stopwords/punctuation, case, MFA and Unicode |
| 05 - Request options | 11 | Text/subject/description inputs, fallback/precedence, correlation IDs, top_k 1/3/20/null |
| 06 - Similarity validation | 27 | Missing/invalid text, top_k types/range, malformed/non-object JSON, body-size limit |
| 07 - Ingestion validation | 19 | Required fields, invalid IDs/tags/text/metadata, unchanged index after rejected requests |
| 08 - Incremental ingestion workflow | 16 | New resolution becomes searchable, deduplication, no accidental overwrite, ID alignment after errors, integer zero, ignored unresolved tickets, status/tag defaults, final count |

Every similarity success also checks the response fields, returned resolutions, signal fields, threshold filtering, top_k limit, and agreement between the first displayed match, `nearest`, and `verdict`. Error responses must contain a descriptive JSON error. Tests do not assert exact latency or confidence values, which vary with hardware, model/runtime and corpus statistics.

**Passing this collection does not mean retrieval quality is perfect.** NT-1 deliberately asserts the current **weak related result** and is labelled a known false acceptance: the returned password-case workaround does not solve an undelivered reset email. P-04 deliberately records lexical abstention and hybrid recovery. The 40 exact-subject requests reuse indexed wording and the paraphrases are development data; neither is held-out evidence. The CLI evaluation remains the relevance/abstention report, including those misses.

The API has no batch-ingestion, threshold-setting or `/eval` endpoint. The collection does not invent them. Negative Content-Length/raw transport framing, atomic multi-ticket validation, caller mutation, and threshold-sweep behavior are covered by Python tests instead of trying to force Postman to send invalid wire framing.

## Verify the reviewer-reported sweep regression

```bash
.venv/bin/python -m pytest tests/test_evaluate.py -q
python3 -m ticket_similarity eval --sweep
```

`score_run` now records `has_candidates`. A query without candidates always abstains, including at a zero weak threshold; it cannot gain recall just by lowering the threshold. A real candidate whose score is zero remains eligible at zero. Blank queries keep the same no-candidate semantics during hybrid evaluation. Sweep output includes the counts of positive and negative queries without candidates. Regression tests also compare sweep acceptance with actual service verdicts at thresholds 0, 0.20, 0.45 and 1.0.

## Run the same collection from the terminal

With a fresh server running, use Newman 6.2.1:

```bash
npx --yes newman@6.2.1 run postman/support-ticket-similarity.postman_collection.json \
  -e postman/local-lexical.postman_environment.json

# Against a separate, fresh hybrid server:
npx --yes newman@6.2.1 run postman/support-ticket-similarity.postman_collection.json \
  -e postman/local-hybrid.postman_environment.json
```

Node.js is needed for Newman, not for the API. Its first invocation may download the runner. Use Newman's JSON/JUnit reporters when retaining results; see the [official command reference](https://learning.postman.com/docs/collections/using-newman-cli/newman-options). [verification.json](verification.json) records the checked collection/environment hashes and the results of the local lexical and hybrid runs. The full local response reports are not committed.

## Maintain the scenarios

Edit the explicit scenario definitions and assertions in `scripts/build_postman.py`, then regenerate:

```bash
python3 scripts/build_postman.py
```

The generator uses the seed subjects and development paraphrases, but never queries the service to learn expected answers. Commit the generated collection, environments and case catalog with any scenario changes, then rerun Newman against fresh servers. A saved verification receipt describes only the collection/environment hashes it records; regenerate the receipt after checking a changed collection.
