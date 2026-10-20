import json
import math
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
    shown_hit_at_1: float
    false_abstain: float
    novel_detected: float
    strong_precision: float | None
    strong_predictions: int
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
        ranked = service._rank(q["text"]) if q["text"].strip() else []
        rows.append({
            "id": q["id"],
            "relevant": set(q["relevant"]),
            "ranked": [m.ticket_id for m in ranked[:10]],
            "returned": [m.ticket_id for m in result.matches],
            "top_conf": max((m.confidence for m in ranked), default=0.0),
            "has_candidates": bool(ranked),
            "verdict": result.verdict,
            "latency": result.latency_ms,
        })
    return rows


def summarize(rows, mode):
    if not rows:
        raise ValueError("evaluation needs at least one query")
    pos = [r for r in rows if r["relevant"]]
    neg = [r for r in rows if not r["relevant"]]
    ranks = [_rank_of(r["ranked"], r["relevant"]) for r in pos]
    strong = [r for r in rows if r["verdict"] == STRONG]
    latencies = sorted(r["latency"] for r in rows)
    return EvalReport(
        mode=mode,
        positives=len(pos),
        novel=len(neg),
        hit_at_1=sum(1 for k in ranks if k == 1) / len(pos) if pos else 0.0,
        hit_at_3=sum(1 for k in ranks if k and k <= 3) / len(pos) if pos else 0.0,
        mrr=sum(1 / k for k in ranks if k) / len(pos) if pos else 0.0,
        shown_hit_at_1=sum(bool(r["returned"]) and r["returned"][0] in r["relevant"] for r in pos) / len(pos) if pos else 0.0,
        false_abstain=sum(1 for r in pos if r["verdict"] == NONE) / len(pos) if pos else 0.0,
        novel_detected=sum(1 for r in neg if r["verdict"] == NONE) / len(neg) if neg else 1.0,
        strong_precision=(sum(1 for r in strong if r["returned"] and r["returned"][0] in r["relevant"]) / len(strong)) if strong else None,
        strong_predictions=len(strong),
        p50_ms=statistics.median(latencies),
        p95_ms=latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))],
    )


def sweep(rows, lo=0.0, hi=1.0, step=0.01):
    """Suggest a weak threshold; this is in-sample analysis, not calibration of strong."""
    if not all(math.isfinite(v) for v in (lo, hi, step)) or not 0 <= lo <= hi <= 1 or step <= 0:
        raise ValueError("sweep needs 0 <= lo <= hi <= 1 and a finite positive step")
    pos = [r for r in rows if r["relevant"]]
    neg = [r for r in rows if not r["relevant"]]
    if not pos or not neg:
        raise ValueError("threshold sweep needs both precedent and novel queries")
    best = None
    for index in range(math.floor((hi - lo) / step + 1e-9) + 1):
        t = round(lo + index * step, 10)
        # An empty retrieval always abstains, even at zero. It is distinct from
        # an available candidate whose actual confidence happens to be zero.
        tpr = sum(r["has_candidates"] and r["top_conf"] >= t for r in pos) / len(pos)
        tnr = sum(not r["has_candidates"] or r["top_conf"] < t for r in neg) / len(neg)
        bal = (tpr + tnr) / 2
        if best is None or bal > best[1]:
            best = (t, bal, tpr, tnr)
    return {"threshold": best[0], "balanced_accuracy": round(best[1], 3), "recall_on_precedent": round(best[2], 3), "novel_detected": round(best[3], 3),
            "pos_conf_min": round(min(r["top_conf"] for r in pos), 3),
            "neg_conf_max": round(max(r["top_conf"] for r in neg), 3),
            "precedents_without_candidates": sum(not r["has_candidates"] for r in pos),
            "novel_without_candidates": sum(not r["has_candidates"] for r in neg)}


def run(tickets, queries, mode, thresholds=None):
    service = SimilarityService(tickets, mode=mode, thresholds=thresholds)
    rows = score_run(service, queries)
    return summarize(rows, mode), rows


def format_report(report):
    precision = "n/a" if report.strong_precision is None else f"{report.strong_precision:.3f}"
    return (
        f"mode={report.mode}  positives={report.positives}  novel={report.novel}\n"
        f"  raw hit@1={report.hit_at_1:.3f}  hit@3={report.hit_at_3:.3f}  MRR={report.mrr:.3f}\n"
        f"  shown_hit@1={report.shown_hit_at_1:.3f}  novel_detected={report.novel_detected:.3f}  false_abstain={report.false_abstain:.3f}\n"
        f"  strong_precision={precision}  strong_predictions={report.strong_predictions}\n"
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
