import heapq
import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from .data import field_text
from .text import tokenize

FIELD_WEIGHTS = {"subject": 3.0, "tags": 2.0, "description": 1.0, "resolution_notes": 0.4}
FIELD_B = {"subject": 0.3, "tags": 0.0, "description": 0.75, "resolution_notes": 0.75}


@dataclass
class LexicalHit:
    doc_id: int
    score: float
    coverage: float
    matched_terms: list


class LexicalIndex:
    """BM25F, scored term-at-a-time off an inverted index: cost is sum of posting lengths for the query terms."""

    def __init__(self, k1=1.2, field_weights=None, field_b=None):
        self.k1 = k1
        weights = field_weights or FIELD_WEIGHTS
        b = field_b or FIELD_B
        self.fields = list(weights)
        self.weights = [weights[f] for f in self.fields]
        self.b = [b[f] for f in self.fields]
        self.doc_len = []
        self.total_len = [0] * len(self.fields)
        self.postings = defaultdict(dict)

    def __len__(self):
        return len(self.doc_len)

    def add(self, ticket):
        doc_id = len(self.doc_len)
        lengths = []
        for fi, field in enumerate(self.fields):
            tokens = tokenize(field_text(ticket, field))
            lengths.append(len(tokens))
            self.total_len[fi] += len(tokens)
            for term, tf in Counter(tokens).items():
                self.postings[term].setdefault(doc_id, []).append((fi, tf))
        self.doc_len.append(lengths)
        return doc_id

    def df(self, term):
        return len(self.postings.get(term, ()))

    def idf(self, term):
        n = len(self)
        df = self.df(term)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query, k=10):
        terms = list(dict.fromkeys(tokenize(query)))
        if not terms or not len(self):
            return []
        n = len(self)
        idf = {t: self.idf(t) for t in terms}
        idf_mass = sum(idf.values())
        base = [1 - b for b in self.b]
        slope = [b * n / total if total else 0.0 for b, total in zip(self.b, self.total_len)]
        weights, k1, doc_len = self.weights, self.k1, self.doc_len

        scores = defaultdict(float)
        mass = defaultdict(float)
        for term in terms:
            plist = self.postings.get(term)
            if not plist:
                continue
            term_idf = idf[term]
            for doc_id, entries in plist.items():
                lengths = doc_len[doc_id]
                wtf = 0.0
                for fi, tf in entries:
                    wtf += weights[fi] * tf / (base[fi] + slope[fi] * lengths[fi])
                scores[doc_id] += term_idf * wtf / (k1 + wtf)
                mass[doc_id] += term_idf

        top = heapq.nlargest(k, scores.items(), key=lambda kv: (kv[1], -kv[0]))
        return [
            LexicalHit(doc_id, score, mass[doc_id] / idf_mass, [t for t in terms if doc_id in self.postings.get(t, ())])
            for doc_id, score in top
        ]
