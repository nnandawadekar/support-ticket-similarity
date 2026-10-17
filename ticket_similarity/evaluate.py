import json
import statistics
from dataclasses import dataclass

from .service import NONE, STRONG, SimilarityService, Thresholds


@dataclass
class EvalReport:
    mode: str
    positives: int
    novel: int
    hit_at_1: float
    hit_at_3: float
    mrr: float
    false_abstain: float
    novel_detected: float
    strong_precision: float
    p50_ms: float
    p95_ms: float


def load_queries(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["queries"]


def _rank_of(ranked_ids, relevant):
    for i, tid in enumerate(ranked_ids, 1):
        if tid in relevant:
            return i
    return None


def score_run(service, queries):
    rows = []
    for q in queries:
        result = service.search(q["text"], top_k=10)
        ranked = service._rank(q["text"])
        rows.append({
            "id": q["id"],
            "relevant": set(q["relevant"]),
            "ranked": [m.ticket_id for m in ranked[:10]],
            "top_conf": max((m.confidence for m in ranked), default=0.0),
            "verdict": result.verdict,
            "latency": result.latency_ms,
        })
    return rows


def summarize(rows, mode):
    pos = [r for r in rows if r["relevant"]]
    neg = [r for r in rows if not r["relevant"]]
    ranks = [_rank_of(r["ranked"], r["relevant"]) for r in pos]
    strong = [r for r in rows if r["verdict"] == STRONG]
    latencies = sorted(r["latency"] for r in rows)
    return EvalReport(
        mode=mode,
        positives=len(pos),
        novel=len(neg),
        hit_at_1=sum(1 for k in ranks if k == 1) / len(pos),
        hit_at_3=sum(1 for k in ranks if k and k <= 3) / len(pos),
        mrr=sum(1 / k for k in ranks if k) / len(pos),
        false_abstain=sum(1 for r in pos if r["verdict"] == NONE) / len(pos),
        novel_detected=sum(1 for r in neg if r["verdict"] == NONE) / len(neg) if neg else 1.0,
        strong_precision=(sum(1 for r in strong if r["ranked"] and r["ranked"][0] in r["relevant"]) / len(strong)) if strong else 1.0,
        p50_ms=statistics.median(latencies),
        p95_ms=latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))],
    )


def sweep(rows, lo=0.20, hi=0.80, step=0.01):
    """Pick the abstain threshold maximising balanced accuracy between 'has precedent' and 'novel'."""
    pos = [r["top_conf"] for r in rows if r["relevant"]]
    neg = [r["top_conf"] for r in rows if not r["relevant"]]
    best = None
    t = lo
    while t <= hi + 1e-9:
        tpr = sum(c >= t for c in pos) / len(pos)
        tnr = sum(c < t for c in neg) / len(neg)
        bal = (tpr + tnr) / 2
        if best is None or bal > best[1]:
            best = (round(t, 2), bal, tpr, tnr)
        t += step
    return {"threshold": best[0], "balanced_accuracy": round(best[1], 3), "recall_on_precedent": round(best[2], 3), "novel_detected": round(best[3], 3),
            "pos_conf_min": round(min(pos), 3), "neg_conf_max": round(max(neg), 3)}


def run(tickets, queries, mode, thresholds=None):
    service = SimilarityService(tickets, mode=mode, thresholds=thresholds)
    rows = score_run(service, queries)
    return summarize(rows, mode), rows


def format_report(report):
    return (
        f"mode={report.mode}  positives={report.positives}  novel={report.novel}\n"
        f"  hit@1={report.hit_at_1:.3f}  hit@3={report.hit_at_3:.3f}  MRR={report.mrr:.3f}\n"
        f"  novel_detected={report.novel_detected:.3f}  false_abstain={report.false_abstain:.3f}  strong_precision={report.strong_precision:.3f}\n"
        f"  latency p50={report.p50_ms:.2f}ms  p95={report.p95_ms:.2f}ms"
    )


def misses(rows):
    out = []
    for r in rows:
        top = r["ranked"][0] if r["ranked"] else "-"
        ok = (top in r["relevant"]) if r["relevant"] else r["verdict"] == NONE
        if not ok or (r["relevant"] and r["verdict"] == NONE):
            out.append(f"  {r['id']}: top={top} conf={r['top_conf']:.3f} verdict={r['verdict']} expected={sorted(r['relevant']) or 'no_match'}")
    return out


__all__ = ["run", "sweep", "format_report", "misses", "load_queries", "Thresholds"]
