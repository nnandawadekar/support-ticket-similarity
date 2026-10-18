import threading
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field

from .data import is_indexable
from .lexical import LexicalIndex

STRONG, WEAK, NONE = "strong_match", "weak_match", "no_match"
RRF_K = 60
CANDIDATE_POOL = 50


@dataclass(frozen=True)
class Thresholds:
    strong: float
    weak: float


# Calibrated on eval/queries.json; see `python -m ticket_similarity eval --sweep`.
DEFAULT_THRESHOLDS = {
    "lexical": Thresholds(strong=0.45, weak=0.20),
    "hybrid": Thresholds(strong=0.55, weak=0.35),
}


@dataclass
class Match:
    ticket_id: str
    subject: str
    category: str
    resolution_notes: str
    created_at: str
    confidence: float
    signals: dict
    matched_terms: list = field(default_factory=list)


@dataclass
class SimilarityResult:
    verdict: str
    matches: list
    nearest: Match | None
    mode: str
    latency_ms: float

    def to_dict(self):
        return asdict(self)


class SimilarityService:
    def __init__(self, tickets=(), mode="lexical", top_k=3, thresholds=None, semantic_index=None):
        if mode not in DEFAULT_THRESHOLDS:
            raise ValueError(f"unknown mode {mode!r}")
        if type(top_k) is not int or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        self.mode = mode
        self.top_k = top_k
        self.thresholds = thresholds or DEFAULT_THRESHOLDS[mode]
        self.tickets = []
        self.lexical = LexicalIndex()
        self.semantic = None
        if mode == "hybrid":
            from .semantic import SemanticIndex
            self.semantic = semantic_index or SemanticIndex()
        self._lock = threading.RLock()
        self._ids = set()
        self.add_many(tickets)

    def add_many(self, tickets):
        with self._lock:
            fresh = []
            seen_ids = self._ids.copy()
            for ticket in tickets:
                if not isinstance(ticket, Mapping):
                    raise ValueError("tickets must be objects")
                if not is_indexable(ticket):
                    continue
                ticket_id = ticket.get("ticket_id")
                if type(ticket_id) is int:
                    ticket_id = str(ticket_id)
                if not isinstance(ticket_id, str) or not ticket_id:
                    raise ValueError("resolved tickets must have a non-empty string or integer ticket_id")
                tags = ticket.get("tags")
                if tags is not None and (
                    not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags)
                ):
                    raise ValueError("ticket tags must be a list of strings")
                if ticket_id in seen_ids:
                    continue
                seen_ids.add(ticket_id)
                fresh.append(ticket if ticket["ticket_id"] == ticket_id else {**ticket, "ticket_id": ticket_id})
            if self.semantic is not None:
                self.semantic.add_many(fresh)
            for t in fresh:
                self.tickets.append(t)
                self._ids.add(t["ticket_id"])
                self.lexical.add(t)
            return len(fresh)

    def add(self, ticket):
        return self.add_many([ticket]) == 1

    def search(self, text, top_k=None):
        started = time.perf_counter()
        top_k = self.top_k if top_k is None else top_k
        if type(top_k) is not int or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        with self._lock:
            ranked = self._rank(text)
        matches = [m for m in ranked if m.confidence >= self.thresholds.weak][:top_k]
        nearest = max(ranked, key=lambda m: m.confidence) if ranked else None
        best = nearest.confidence if nearest else 0.0
        if best >= self.thresholds.strong:
            verdict = STRONG
        elif best >= self.thresholds.weak:
            verdict = WEAK
        else:
            verdict = NONE
        return SimilarityResult(
            verdict=verdict,
            matches=matches,
            nearest=nearest,
            mode=self.mode,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    def _rank(self, text):
        lexical_hits = self.lexical.search(text, k=CANDIDATE_POOL)
        lex = {h.doc_id: h for h in lexical_hits}
        if self.semantic is None:
            return [self._match(h.doc_id, h.coverage, {"bm25f": round(h.score, 3), "coverage": round(h.coverage, 3)}, h.matched_terms)
                    for h in lexical_hits]

        dense = dict(self.semantic.search(text, k=CANDIDATE_POOL))
        lex_rank = {h.doc_id: r for r, h in enumerate(lexical_hits)}
        dense_rank = {d: r for r, d in enumerate(dense)}
        fused = {}
        for doc_id in lex_rank.keys() | dense_rank.keys():
            fused[doc_id] = sum(1 / (RRF_K + ranks[doc_id] + 1) for ranks in (lex_rank, dense_rank) if doc_id in ranks)

        out = []
        for doc_id in sorted(fused, key=lambda d: (-fused[d], d)):
            hit = lex.get(doc_id)
            coverage = hit.coverage if hit else 0.0
            cosine = dense.get(doc_id, 0.0)
            confidence = 0.5 * coverage + 0.5 * max(cosine, 0.0)
            signals = {"rrf": round(fused[doc_id], 4), "coverage": round(coverage, 3), "cosine": round(cosine, 3)}
            out.append(self._match(doc_id, confidence, signals, hit.matched_terms if hit else []))
        return out

    def _match(self, doc_id, confidence, signals, matched_terms):
        t = self.tickets[doc_id]
        return Match(
            ticket_id=t["ticket_id"],
            subject=t.get("subject", ""),
            category=t.get("category", ""),
            resolution_notes=t.get("resolution_notes", ""),
            created_at=t.get("created_at", ""),
            confidence=round(confidence, 3),
            signals=signals,
            matched_terms=matched_terms,
        )
