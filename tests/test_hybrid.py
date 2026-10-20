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


def test_hybrid_malformed_batch_does_not_mutate_either_index(hybrid):
    before = len(hybrid.tickets)
    good = {"ticket_id": "BATCH-GOOD", "subject": "invoice address", "resolution_notes": "fixed"}
    with pytest.raises(ValueError, match="description"):
        hybrid.add_many([good, {**good, "ticket_id": "BATCH-BAD", "description": [1]}])
    assert len(hybrid.tickets) == len(hybrid.lexical) == len(hybrid.semantic) == before
    assert "BATCH-GOOD" not in hybrid._ids


def test_hybrid_blank_query_does_not_suggest_a_fix(hybrid):
    result = hybrid.search(" \n ")
    assert result.verdict == NONE and result.matches == [] and result.nearest is None


def test_hybrid_evaluation_preserves_blank_query_abstention(hybrid):
    from ticket_similarity.evaluate import score_run

    row = score_run(hybrid, [{"id": "blank", "text": " \n ", "relevant": []}])[0]
    assert row["has_candidates"] is False
    assert row["ranked"] == row["returned"] == []
    assert row["verdict"] == NONE
