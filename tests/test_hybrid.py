import pytest

pytest.importorskip("sentence_transformers")

from ticket_similarity.data import DEFAULT_HISTORY, DEFAULT_NEW, load_tickets, query_text  # noqa: E402
from ticket_similarity.service import NONE, SimilarityService  # noqa: E402


@pytest.fixture(scope="module")
def hybrid():
    return SimilarityService(load_tickets(DEFAULT_HISTORY), mode="hybrid")


def test_hybrid_handles_vocabulary_mismatch(hybrid):
    result = hybrid.search("terminated staff member can still get into the product after we disabled them")
    assert result.matches[0].ticket_id == "T-1502"
    assert {"rrf", "coverage", "cosine"} <= result.matches[0].signals.keys()


def test_hybrid_abstains_on_snowflake(hybrid):
    nt4 = next(t for t in load_tickets(DEFAULT_NEW) if t["ticket_id"] == "NT-4")
    assert hybrid.search(query_text(nt4)).verdict == NONE


def test_hybrid_incremental_add_updates_dense_index(hybrid):
    before = len(hybrid.semantic)
    hybrid.add({"ticket_id": "T-3001", "subject": "Looker embed shows permission denied", "description": "x",
                "resolution_notes": "Re-shared the model with the service account."})
    assert len(hybrid.semantic) == before + 1 == len(hybrid.tickets)
