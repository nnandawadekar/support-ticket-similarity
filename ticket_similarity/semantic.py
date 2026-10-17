import os

DEFAULT_MODEL = os.environ.get("TICKET_SIM_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def embedding_text(ticket):
    tags = ", ".join(ticket.get("tags") or [])
    return f"{ticket.get('subject', '')}. {ticket.get('description', '')} Tags: {tags}".strip()


class SemanticIndex:
    """Dense cosine search. Brute force is deliberate: at 100k tickets x 384 dims it is a ~40M-FLOP matvec."""

    def __init__(self, model_name=DEFAULT_MODEL):
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("hybrid mode needs `pip install -r requirements-semantic.txt`") from exc
        self.np = np
        self.model = SentenceTransformer(model_name)
        self.matrix = np.zeros((0, self._dimension()), dtype=np.float32)

    def _dimension(self):
        getter = getattr(self.model, "get_embedding_dimension", None) or self.model.get_sentence_embedding_dimension
        return getter()

    def __len__(self):
        return self.matrix.shape[0]

    def _encode(self, texts):
        return self.model.encode(texts, normalize_embeddings=True, batch_size=64, convert_to_numpy=True)

    def add_many(self, tickets):
        if tickets:
            self.matrix = self.np.vstack([self.matrix, self._encode([embedding_text(t) for t in tickets])])

    def add(self, ticket):
        self.add_many([ticket])

    def search(self, query, k=10):
        if not len(self):
            return []
        sims = self.matrix @ self._encode([query])[0]
        k = min(k, len(sims))
        top = self.np.argpartition(-sims, k - 1)[:k]
        return sorted(((int(i), float(sims[i])) for i in top), key=lambda pair: -pair[1])
