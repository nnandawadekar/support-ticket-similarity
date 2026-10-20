"""Build the checked-in Postman collection and case catalog with stdlib Python.

The scenario expectations are explicit; running this never calls the service to
learn expected answers. Exact-subject checks are sanity tests, not held-out eval.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "postman"
SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"

COMMON_TESTS = r'''
pm.test("Response is JSON", function () {
  pm.expect(pm.response.headers.get("Content-Type")).to.include("application/json");
});
const body = pm.response.json();
if (pm.response.code >= 400) {
  pm.test("Error explains the failure", function () {
    pm.expect(body.error).to.be.a("string").and.not.empty;
  });
}
if (pm.response.code === 200 && Array.isArray(body.matches)) {
  const thresholds = body.mode === "hybrid" ? {weak: 0.35, strong: 0.55} : {weak: 0.20, strong: 0.45};
  const request = JSON.parse(pm.variables.replaceIn(pm.request.body.raw));
  const limit = request.top_k === null || request.top_k === undefined ? 3 : request.top_k;
  pm.test("Similarity response has the public fields", function () {
    ["ticket_id", "verdict", "matches", "nearest", "mode", "latency_ms"].forEach(k => pm.expect(body).to.have.property(k));
    pm.expect(body.mode).to.equal(pm.variables.get("expectedMode"));
    pm.expect(body.latency_ms).to.be.a("number").and.at.least(0);
    pm.expect(body.matches.length).to.be.at.most(limit);
    pm.expect(["strong_match", "weak_match", "no_match"]).to.include(body.verdict);
  });
  pm.test("Every displayed match includes a usable resolution and signals", function () {
    body.matches.forEach(m => {
      ["ticket_id", "subject", "category", "resolution_notes", "created_at", "confidence", "signals", "matched_terms"].forEach(k => pm.expect(m).to.have.property(k));
      pm.expect(m.ticket_id).to.be.a("string").and.not.empty;
      pm.expect(m.resolution_notes.trim()).not.to.equal("");
      pm.expect(m.confidence).to.be.within(thresholds.weak, 1);
      pm.expect(m.matched_terms).to.be.an("array");
      pm.expect(m.signals).to.have.property("coverage");
      if (body.mode === "hybrid") {
        pm.expect(m.signals).to.have.property("rrf");
        pm.expect(m.signals).to.have.property("cosine");
      } else {
        pm.expect(m.signals).to.have.property("bm25f");
      }
    });
  });
  pm.test("Verdict and nearest agree with the first displayed match", function () {
    if (!body.matches.length) {
      pm.expect(body.verdict).to.equal("no_match");
      if (body.nearest !== null) pm.expect(body.nearest.confidence).to.be.below(thresholds.weak);
    } else {
      pm.expect(body.nearest).to.eql(body.matches[0]);
      pm.expect(body.verdict).to.equal(body.matches[0].confidence >= thresholds.strong ? "strong_match" : "weak_match");
    }
  });
}
'''.strip()


def event(kind, code):
    return {"listen": kind, "script": {"type": "text/javascript", "exec": code.strip().splitlines()}}


class Builder:
    def __init__(self):
        self.folders = []
        self.catalog = []
        self.group = None

    def folder(self, name, description):
        self.group = {"name": name, "description": description, "item": []}
        self.folders.append(self.group)
        self.catalog.append((name, description, []))

    def request(self, name, path, status=200, payload=None, *, method="POST", raw=None,
                checks="", before="", why="", expected=""):
        number = sum(len(folder[2]) for folder in self.catalog) + 1
        name = f"C{number:03d} - {name}"
        request = {"method": method, "header": [{"key": "Accept", "value": "application/json"}],
                   "url": "{{baseUrl}}" + path, "description": why}
        if method != "GET":
            request["header"].append({"key": "Content-Type", "value": "application/json"})
            request["body"] = {"mode": "raw", "raw": raw if raw is not None else json.dumps(payload, indent=2, ensure_ascii=False),
                               "options": {"raw": {"language": "json"}}}
        code = f'pm.test("Expected HTTP {status}", function () {{ pm.response.to.have.status({status}); }});\n'
        code += "const b = pm.response.json();\n" + checks
        item = {"name": name, "request": request, "event": [event("test", code)]}
        if before:
            item["event"].insert(0, event("prerequest", before))
        self.group["item"].append(item)
        self.catalog[-1][2].append((name, method, path, status, expected or why))

    def similar(self, name, payload, *, ids=None, verdict=None, checks="", why=""):
        if verdict is not None:
            js = json.dumps(verdict)
            expression = f"({js})[b.mode]" if isinstance(verdict, dict) else js
            checks += f'\npm.test("Expected verdict", function () {{ pm.expect(b.verdict).to.equal({expression}); }});'
        if ids:
            checks += '\npm.test("First match is a labelled precedent", function () { pm.expect(b.matches).not.to.be.empty; pm.expect(' + json.dumps(ids) + ').to.include(b.matches[0].ticket_id); });'
        self.request(name, "/similar", payload=payload, checks=checks, why=why,
                     expected=why or ((str(verdict) if verdict is not None else "valid similarity response") + ("; first in " + ", ".join(ids) if ids else "")))

    def invalid(self, name, path, payload=None, *, raw=None, error=None, before=""):
        checks = '' if error is None else 'pm.test("Specific validation reason", function () { pm.expect(b.error).to.include(' + json.dumps(error) + '); });'
        self.request(name, path, status=400, payload=payload, raw=raw, checks=checks, before=before,
                     why="Reject malformed input without indexing it.", expected="400; " + (error or "JSON validation error"))

    def add(self, name, ticket, added=True):
        checks = f'''pm.test("Indexed flag and total are correct", function () {{
  pm.expect(b.indexed).to.equal({str(added).lower()});
  pm.expect(b.total).to.equal(Number(pm.collectionVariables.get("expectedTotal")) + {int(added)});
}});
pm.collectionVariables.set("expectedTotal", String(b.total));'''
        self.request(name, "/tickets", status=201 if added else 200, payload=ticket, checks=checks,
                     why="Add once; duplicates and non-indexable tickets leave the count unchanged.",
                     expected=("201; indexed=true; count +1" if added else "200; indexed=false; unchanged count"))


def build():
    b = Builder()
    history = json.loads((ROOT / "starter_kit/data/tickets.json").read_text())["tickets"]
    incoming = json.loads((ROOT / "starter_kit/data/new_tickets_example.json").read_text())["new_tickets"]
    queries = json.loads((ROOT / "eval/queries.json").read_text())["queries"]
    b.folder("00 - Start here", "Start a fresh server with the 40 seed tickets. Run the complete collection once in order. A new run ID is allocated here; mutation requests run last.")
    b.request("Health and clean seed-history preflight", "/health", method="GET", checks='''pm.test("Expected server mode and 40 seed tickets", function () {
  pm.expect(b.status).to.equal("ok");
  pm.expect(b.mode).to.equal(pm.variables.get("expectedMode"));
  pm.expect(b.indexed).to.equal(40);
});
pm.collectionVariables.set("expectedTotal", String(b.indexed));''', before='pm.collectionVariables.set("runId", pm.variables.replaceIn("{{$guid}}"));',
              why="Catches a wrong port, wrong mode or a previously mutated server.", expected="200; configured mode; indexed=40")
    b.request("Unknown GET route", "/does-not-exist", method="GET", status=404, why="Unknown route returns a JSON error.")
    b.request("Unknown POST route", "/does-not-exist", payload={}, status=404, why="Unknown route returns a JSON error.")
    b.request("GET on a POST-only route", "/similar", method="GET", status=404, why="No GET similarity endpoint is implemented.")
    b.request("POST on a GET-only route", "/health", payload={}, status=404, why="Health is GET-only.")

    b.folder("01 - Customer examples", "The four supplied new tickets. NT-1 is an explicit known false acceptance, not proof of a reusable fix.")
    for ticket in incoming:
        tid = ticket["ticket_id"]
        verdict = "weak_match" if tid == "NT-1" else ("no_match" if tid == "NT-4" else "strong_match")
        ids = {"NT-1": ["T-1001"], "NT-2": ["T-1201"], "NT-3": ["T-1303"]}.get(tid)
        why = ("KNOWN LIMITATION: weak related result; password-case fix does not solve missing email." if tid == "NT-1" else
               "Novel Snowflake issue: abstain, show no matches, preserve nearest for transparency." if tid == "NT-4" else
               "Show a precedent with its original resolution for agent review.")
        b.similar(tid + ": " + ticket["subject"], ticket, ids=ids, verdict=verdict,
                  checks='pm.test("Correlation ID is echoed", function () { pm.expect(b.ticket_id).to.equal(' + json.dumps(tid) + '); });', why=why)

    b.folder("02 - Exact historical subjects", "40 exact-subject sanity checks spanning every seed category. These deliberately reuse historical wording and are not held-out retrieval evidence.")
    for ticket in history:
        b.similar(ticket["ticket_id"] + ": " + ticket["subject"], {"text": ticket["subject"]},
                  ids=[ticket["ticket_id"]], verdict="strong_match", why="Sanity: exact historical subject retrieves its own fix.")

    b.folder("03 - Development paraphrases", "The 24 hand-written P-* queries from eval/queries.json. Same labels as the CLI; P-04 is a known lexical false abstention. Related-but-different causes still need independent evaluation.")
    for q in queries:
        if not q["id"].startswith("P-"):
            continue
        checks = ''
        if q["id"] == "P-04":
            checks = 'pm.test("Known lexical miss / hybrid recovery", function () { if (b.mode === "lexical") { pm.expect(b.verdict).to.equal("no_match"); } else { pm.expect(b.matches[0].ticket_id).to.equal("T-1005"); } });'
        else:
            checks = 'pm.test("Returned precedent is relevant", function () { pm.expect(b.matches).not.to.be.empty; pm.expect(' + json.dumps(q["relevant"]) + ').to.include(b.matches[0].ticket_id); });'
        b.similar(q["id"] + ": " + q["text"].splitlines()[0], {"text": q["text"]}, checks=checks,
                  why="KNOWN LIMITATION: lexical abstains; hybrid recovers T-1005." if q["id"] == "P-04" else "Development paraphrase; first displayed ticket must have a reusable labelled fix.")

    b.folder("04 - Novelty and normalization", "No-precedent and tokenizer boundaries, including queries with no lexical candidates. Hybrid may retain a nearest dense candidate even when lexical retrieval is empty.")
    for q in queries:
        if q["id"].startswith("N-"):
            b.similar(q["id"] + ": " + q["text"].splitlines()[0], {"text": q["text"]}, verdict="no_match", why="No reusable seed fix: return matches=[] and no_match.")
    for name, text in [("Entirely unseen vocabulary", "zyxwvut qzxjkv"), ("Only punctuation", "!!! ... ???"), ("Only stopwords", "the and of")]:
        b.similar(name, {"text": text}, checks='pm.test("Lexical has no candidates", function () { if (b.mode === "lexical") { pm.expect(b.verdict).to.equal("no_match"); pm.expect(b.matches).to.eql([]); pm.expect(b.nearest).to.equal(null); } });',
                  why="Lexical: no candidates, no match, nearest=null. Dense nearest is allowed in hybrid.")
    b.similar("Uppercase normalization", {"text": "CHARGED TWICE FOR THE SAME BILLING CYCLE"}, ids=["T-1303"], verdict="strong_match")
    b.similar("MFA/two-factor normalization", {"text": "two-factor SMS verification code never arrives on phone"}, ids=["T-1003"])
    b.similar("Unicode punctuation and emoji", {"text": "Customer’s card shows duplicate charges 💳 charged twice for the same billing cycle"}, ids=["T-1303"])

    b.folder("05 - Request options", "Supported text shapes, correlation IDs, top_k boundaries and response invariants. Exact confidence and timing values are deliberately not pinned.")
    for name, payload in [
        ("Free-text body", {"text": "Charged twice for the same billing cycle"}),
        ("Subject-only body", {"subject": "Charged twice for the same billing cycle"}),
        ("Description-only body", {"description": "Charged twice for the same billing cycle"}),
        ("Empty text falls back to subject", {"text": "", "subject": "Charged twice for the same billing cycle"}),
        ("Null text falls back to subject", {"text": None, "subject": "Charged twice for the same billing cycle"}),
        ("Explicit text takes precedence", {"text": "Charged twice for the same billing cycle", "subject": "unrelated query"}),
        ("Integer correlation ID", {"text": "Charged twice for the same billing cycle", "ticket_id": 123}),
    ]:
        b.similar(name, payload, ids=["T-1303"], verdict="strong_match",
                  checks='pm.test("Correlation ID matches the request", function () { pm.expect(b.ticket_id).to.eql(' + json.dumps(payload.get("ticket_id")) + '); });')
    for limit in (1, 3, 20, None):
        b.similar(f"top_k={json.dumps(limit)}", {"text": "dashboard chart slow loading", "top_k": limit}, why="200; length respects top_k (null uses default 3); verdict follows first displayed result.")

    b.folder("06 - Similarity validation", "Each request expects a descriptive HTTP 400 JSON error. The health check after validation confirms no invalid request changed the index.")
    for name, payload, error in [
        ("Empty object", {}, "provide"), ("Empty text", {"text": ""}, "provide"),
        ("Whitespace text", {"text": "  \n\t"}, "provide"),
        ("Null text without fallback", {"text": None}, "provide"),
        ("Numeric text", {"text": 123}, "'text'"), ("Boolean text", {"text": True}, "'text'"),
        ("Array text", {"text": ["invoice"]}, "'text'"), ("Object text", {"text": {"value": "invoice"}}, "'text'"),
        ("Null subject", {"subject": None}, "subject"), ("Array subject", {"subject": []}, "subject"),
        ("Numeric description", {"description": 123}, "description"), ("Object description", {"description": {}}, "description"),
    ]:
        b.invalid(name, "/similar", payload, error=error)
    for limit in (0, -1, 21, 1.5, True, "3", [], {}):
        b.invalid("Invalid top_k=" + json.dumps(limit), "/similar", {"text": "invoice", "top_k": limit}, error="top_k")
    for name, raw in [("Malformed JSON", '{"text":'), ("Trailing comma", '{"text":"invoice",}'),
                      ("Array body", '[]'), ("String body", '"invoice"'), ("Null body", 'null'), ("Numeric body", '42')]:
        b.invalid(name, "/similar", raw=raw)
    b.invalid("Body over 64 KiB", "/similar", raw="{{oversizedBody}}", error="payload too large",
              before='pm.variables.set("oversizedBody", JSON.stringify({text: "x".repeat(65536)}));')

    b.folder("07 - Ingestion validation", "Malformed resolved tickets must not reserve an ID or shift index positions. Every failing request reuses the validation ID; the valid recovery ticket is inserted later.")
    ticket = {"ticket_id": "{{runId}}-validation", "subject": "Receipt printer offline", "description": "Printer loses connection", "resolution_notes": "Assigned a static IP"}
    for field in ("ticket_id", "subject", "description", "resolution_notes"):
        missing = {k: v for k, v in ticket.items() if k != field}
        b.invalid("Missing " + field, "/tickets", missing, error="missing fields")
    for field, value in [
        ("ticket_id", True), ("ticket_id", 1.5), ("ticket_id", []), ("ticket_id", {}),
        ("ticket_id", "   "), ("ticket_id", None),
        ("subject", ["bad", 1]), ("description", ["bad", 1]), ("resolution_notes", {"fix": "bad"}),
        ("tags", "billing"), ("tags", ["billing", 1]), ("category", []), ("created_at", 123), ("status", None),
    ]:
        b.invalid("Invalid " + field + "=" + json.dumps(value), "/tickets", {**ticket, field: value})
    b.request("Validation did not mutate index", "/health", method="GET",
              checks='pm.test("Index count is unchanged", function () { pm.expect(b.indexed).to.equal(Number(pm.collectionVariables.get("expectedTotal"))); });',
              expected="200; indexed unchanged from preflight (40)")

    b.folder("08 - Incremental ingestion workflow", "Run in order, after read-only retrieval checks. Uses a per-run UUID and checks count changes, duplicate handling, integer IDs, ignored tickets, preserved fixes and valid ingestion after rejection. Restart before another complete run.")
    snowflake = {"ticket_id": "{{runId}}-snowflake", "subject": "Snowflake warehouse connection failure",
                 "description": "Snowflake integration cannot connect because network policy blocks egress IPs",
                 "resolution_notes": "Allowlisted our egress IPs in the Snowflake network policy.", "status": "resolved", "category": "sync", "tags": ["snowflake", "network"]}
    b.add("Resolve a formerly novel Snowflake issue", snowflake)
    expected_snow = '''pm.test("New resolution is searchable", function () {
  pm.expect(b.matches[0].ticket_id).to.equal(pm.variables.replaceIn("{{runId}}-snowflake"));
  pm.expect(b.matches[0].resolution_notes).to.equal("Allowlisted our egress IPs in the Snowflake network policy.");
});'''
    b.similar("Find the newly added resolution", {"text": snowflake["subject"]}, verdict="strong_match", checks=expected_snow)
    b.add("Duplicate is not inserted", snowflake, added=False)
    b.add("Duplicate ID does not overwrite fix", {**snowflake, "resolution_notes": "THIS MUST NOT OVERWRITE THE ORIGINAL FIX"}, added=False)
    b.similar("Original fix remains after duplicate", {"text": snowflake["subject"]}, checks=expected_snow)
    b.add("Valid ticket after all rejected inputs", ticket)
    b.similar("Rejected fields did not shift later ticket IDs", {"text": "Receipt printer offline"},
              checks='pm.test("Fix belongs to correct ticket", function () { pm.expect(b.matches[0].ticket_id).to.equal(pm.variables.replaceIn("{{runId}}-validation")); pm.expect(b.matches[0].resolution_notes).to.equal("Assigned a static IP"); });')
    integer = {**ticket, "ticket_id": 0, "subject": "Kiosk receipt printer reconnects", "description": "Kiosk printer reconnect test", "tags": []}
    b.add("Integer ticket ID zero is accepted", integer)
    b.add("String ID zero is the same ticket", {**integer, "ticket_id": "0"}, added=False)
    b.similar("Integer ID is returned as a string", {"text": integer["subject"]}, ids=["0"])
    for status in ("open", "pending"):
        b.add("Ignore " + status + " ticket", {**ticket, "ticket_id": "{{runId}}-" + status, "status": status}, added=False)
    b.add("Whitespace-only resolution is ignored", {**ticket, "ticket_id": "{{runId}}-blank", "resolution_notes": "  \n"}, added=False)
    b.add("Missing status defaults to resolved", {**ticket, "ticket_id": "{{runId}}-default-status", "subject": "WiFi scanner firmware issue"})
    b.add("Null tags are accepted", {**ticket, "ticket_id": "{{runId}}-null-tags", "subject": "Label scanner reconnect", "tags": None})
    b.request("Final count and mode", "/health", method="GET", checks='''pm.test("Exactly five resolved tickets were added", function () {
  pm.expect(b.indexed).to.equal(45);
  pm.expect(b.indexed).to.equal(Number(pm.collectionVariables.get("expectedTotal")));
  pm.expect(b.mode).to.equal(pm.variables.get("expectedMode"));
});''', expected="200; indexed=45; correct mode")

    collection = {"info": {"name": "Support Ticket Similarity - Evaluator API Scenarios", "schema": SCHEMA,
                           "description": "Run once in order against a fresh 40-ticket server. Import the lexical or hybrid environment. Read postman/README.md first. Known limitations are labelled; green transport assertions are not held-out relevance evidence. The threshold sweep is CLI-only and is covered by tests/test_evaluate.py, not an invented HTTP endpoint."},
                  "variable": [{"key": "baseUrl", "value": "http://127.0.0.1:8002"}, {"key": "expectedMode", "value": "lexical"}],
                  "event": [event("prerequest", 'if (!pm.collectionVariables.get("runId")) pm.collectionVariables.set("runId", pm.variables.replaceIn("{{$guid}}"));'), event("test", COMMON_TESTS)],
                  "item": b.folders}
    OUT.mkdir(exist_ok=True)
    (OUT / "support-ticket-similarity.postman_collection.json").write_text(json.dumps(collection, indent=2, ensure_ascii=False) + "\n")
    for mode, port in (("lexical", 8002), ("hybrid", 8001)):
        env = {"id": "89d8cbad-13a3-4927-a165-" + ("6dba405d6000" if mode == "lexical" else "6dba405d6001"),
               "name": "Ticket Similarity - Local " + mode.title(), "_postman_variable_scope": "environment",
               "values": [{"key": "baseUrl", "value": f"http://127.0.0.1:{port}", "enabled": True},
                          {"key": "expectedMode", "value": mode, "enabled": True}]}
        (OUT / f"local-{mode}.postman_environment.json").write_text(json.dumps(env, indent=2) + "\n")
    lines = ["# API scenario catalog", "", "Generated by `python3 scripts/build_postman.py`. Run the collection in order on a fresh server. See [setup and interpretation](README.md).", ""]
    for name, description, cases in b.catalog:
        lines.extend(["## " + name, "", description, "", "| Case | Request | Expected outcome / purpose |", "|---|---|---|"])
        for name, method, path, status, expected in cases:
            lines.append(f"| {name.replace('|', '/')} | `{method} {path}` | HTTP {status}: {expected.replace('|', '/')} |")
        lines.append("")
    (OUT / "CASES.md").write_text("\n".join(lines))
    print(f"Built {sum(len(f['item']) for f in b.folders)} requests in {len(b.folders)} folders, with lexical and hybrid environments.")


if __name__ == "__main__":
    build()
