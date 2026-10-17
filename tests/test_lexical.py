from ticket_similarity.lexical import LexicalIndex


def _ticket(tid, subject, description="", resolution="fixed", tags=()):
    return {"ticket_id": tid, "subject": subject, "description": description, "resolution_notes": resolution, "tags": list(tags)}


def test_empty_index_and_empty_query():
    idx = LexicalIndex()
    assert idx.search("anything") == []
    idx.add(_ticket("A", "chart blank"))
    assert idx.search("") == []
    assert idx.search("the and of") == []


def test_rare_terms_outweigh_common_terms():
    idx = LexicalIndex()
    for i in range(10):
        idx.add(_ticket(f"C{i}", "dashboard issue", "dashboard problem"))
    idx.add(_ticket("RARE", "dashboard snowflake connector"))
    hits = idx.search("snowflake dashboard")
    assert idx.idf("snowflake") > idx.idf("dashboard")
    assert hits[0].doc_id == 10


def test_subject_match_beats_resolution_match():
    idx = LexicalIndex()
    idx.add(_ticket("SUBJ", "webhook retries failing"))
    idx.add(_ticket("RES", "something unrelated", resolution="added webhook retries"))
    assert idx.search("webhook retries")[0].doc_id == 0


def test_coverage_is_bounded_and_penalises_unseen_terms():
    idx = LexicalIndex()
    idx.add(_ticket("A", "invoice seat count wrong"))
    idx.add(_ticket("B", "chart blank"))
    full = idx.search("invoice seat count")[0]
    partial = idx.search("invoice seat count snowflake warehouse")[0]
    assert full.coverage == 1.0
    assert 0 < partial.coverage < full.coverage
    assert set(partial.matched_terms) == {"invoic", "seat", "count"}


def test_only_candidates_from_postings_are_scored():
    idx = LexicalIndex()
    idx.add(_ticket("A", "billing invoice"))
    idx.add(_ticket("B", "chart rendering"))
    assert [h.doc_id for h in idx.search("invoice")] == [0]


def test_ties_are_deterministic():
    idx = LexicalIndex()
    idx.add(_ticket("A", "export csv"))
    idx.add(_ticket("B", "export csv"))
    assert [h.doc_id for h in idx.search("export csv")] == [0, 1]
