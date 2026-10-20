import pytest

from ticket_similarity.data import DEFAULT_HISTORY, DEFAULT_NEW, load_tickets, query_text
from ticket_similarity.service import NONE, STRONG, SimilarityService, Thresholds


@pytest.fixture(scope="module")
def history():
    return load_tickets(DEFAULT_HISTORY)


@pytest.fixture(scope="module")
def service(history):
    return SimilarityService(history)


@pytest.fixture(scope="module")
def new_tickets():
    return {t["ticket_id"]: t for t in load_tickets(DEFAULT_NEW)}


def test_loads_full_seed_set(history, service):
    assert len(history) == 40
    assert len(service.tickets) == 40
    assert len({t["ticket_id"] for t in history}) == 40


@pytest.mark.parametrize("new_id, expected", [("NT-2", "T-1201"), ("NT-3", "T-1303")])
def test_example_tickets_surface_their_precedent(service, new_tickets, new_id, expected):
    result = service.search(query_text(new_tickets[new_id]))
    assert result.verdict != NONE
    assert result.matches[0].ticket_id == expected


def test_snowflake_ticket_abstains_but_reports_nearest(service, new_tickets):
    result = service.search(query_text(new_tickets["NT-4"]))
    assert result.verdict == NONE
    assert result.matches == []
    assert result.nearest is not None and result.nearest.confidence < service.thresholds.weak


def test_missing_reset_email_has_only_a_weak_related_result(service, new_tickets):
    # Related history exists, but no seed fix addresses an undelivered reset email.
    # Preserve this known false acceptance rather than calling it a true precedent.
    result = service.search(query_text(new_tickets["NT-1"]))
    assert result.verdict == "weak_match"
    assert result.matches[0].ticket_id == "T-1001"


def test_strong_verdict_for_near_duplicate(service):
    result = service.search("Charged twice for the same billing cycle")
    assert result.verdict == STRONG
    assert result.matches[0].ticket_id == "T-1303"


def test_top_k_and_threshold_filtering(history):
    svc = SimilarityService(history, top_k=2, thresholds=Thresholds(strong=0.9, weak=0.0))
    assert len(svc.search("dashboard slow").matches) == 2
    assert len(svc.search("dashboard slow", top_k=5).matches) == 5


def test_unresolved_and_duplicate_tickets_are_not_indexed(history):
    svc = SimilarityService(history)
    assert not svc.add({"ticket_id": "T-9", "subject": "x", "description": "y", "resolution_notes": "", "status": "resolved"})
    assert not svc.add({"ticket_id": "T-10", "subject": "x", "description": "y", "resolution_notes": "z", "status": "open"})
    assert not svc.add(history[0])
    assert len(svc.tickets) == 40


def test_short_queries_are_noisier_than_full_tickets(service, new_tickets):
    assert service.search(query_text(new_tickets["NT-4"])).verdict == NONE
    assert service.search("Snowflake warehouse integration connection error").verdict != NONE


def test_incremental_add_makes_new_precedent_searchable(history, new_tickets):
    svc = SimilarityService(history)
    query = query_text(new_tickets["NT-4"])
    assert svc.search(query).verdict == NONE
    svc.add({
        "ticket_id": "T-1801", "category": "sync", "status": "resolved",
        "subject": "Snowflake integration fails with connection error",
        "description": "New Snowflake warehouse sync fails to connect.",
        "resolution_notes": "Customer's Snowflake network policy blocked our egress IPs; allowlisted them.",
        "tags": ["snowflake", "integration", "network"],
    })
    result = svc.search(query)
    assert result.matches[0].ticket_id == "T-1801"
    assert result.verdict != NONE


def test_verdict_agrees_with_returned_matches(service):
    # T-1501 tops BM25F on a subject hit for "member"; T-1502 explains more of the query via "terminated".
    result = service.search("terminated staff member can still get into the product")
    assert result.matches, "a match above the weak threshold was returned"
    assert result.verdict != NONE
    assert result.nearest.confidence == max(m.confidence for m in result.matches)


def test_unknown_mode_rejected(history):
    with pytest.raises(ValueError):
        SimilarityService(history, mode="magic")


@pytest.mark.parametrize("top_k", [0, -1, True])
def test_search_rejects_invalid_top_k(service, top_k):
    with pytest.raises(ValueError, match="top_k"):
        service.search("dashboard slow", top_k=top_k)


def test_constructor_rejects_invalid_top_k(history):
    with pytest.raises(ValueError, match="top_k"):
        SimilarityService(history, top_k=0)


def test_add_many_deduplicates_ids_within_batch(history):
    service = SimilarityService(history)
    ticket = {
        "ticket_id": "T-3001",
        "subject": "New precedent",
        "description": "A reproducible issue",
        "resolution_notes": "Applied the fix.",
    }
    assert service.add_many([ticket, ticket]) == 1
    assert len(service.tickets) == 41


def test_add_rejects_unhashable_ticket_id(history):
    service = SimilarityService(history)
    ticket = {
        "ticket_id": ["T-3001"],
        "subject": "New precedent",
        "description": "A reproducible issue",
        "resolution_notes": "Applied the fix.",
    }
    with pytest.raises(ValueError, match="ticket_id"):
        service.add(ticket)


def test_integer_ticket_ids_are_accepted_as_strings(history):
    service = SimilarityService(history)
    ticket = {"ticket_id": 1001, "subject": "Kiosk printer offline", "description": "Receipt printer drops off the network",
              "resolution_notes": "Pinned the printer to a static IP."}
    assert service.add(ticket)
    assert service.search("receipt printer offline").matches[0].ticket_id == "1001"
    assert ticket["ticket_id"] == 1001
    assert not service.add({**ticket, "ticket_id": "1001"})


@pytest.mark.parametrize("bad_id", [True, 0.5, ""])
def test_non_integer_non_string_ticket_ids_rejected(history, bad_id):
    service = SimilarityService(history)
    with pytest.raises(ValueError, match="ticket_id"):
        service.add({"ticket_id": bad_id, "subject": "s", "description": "d", "resolution_notes": "r"})


@pytest.mark.parametrize("name, value", [
    ("subject", ["bad", 1]), ("description", ["bad", 1]),
    ("resolution_notes", {"fix": "bad"}), ("category", []),
    ("created_at", 123), ("status", None), ("tags", [123]),
])
def test_malformed_batch_is_rejected_before_any_index_changes(history, name, value):
    svc = SimilarityService(history)
    good = {"ticket_id": "GOOD", "subject": "unicorn zoology", "description": "unique issue",
            "resolution_notes": "Correct fix", "tags": ["unique"]}
    bad = {**good, "ticket_id": "BAD", name: value}
    with pytest.raises(ValueError, match=name):
        svc.add_many([good, bad])
    assert len(svc.tickets) == len(svc.lexical) == 40
    assert svc._ids == {t["ticket_id"] for t in history}
    assert svc.add(good)
    match = svc.search("unicorn zoology").matches[0]
    assert match.ticket_id == "GOOD" and match.resolution_notes == "Correct fix"


def test_index_owns_ticket_fields_and_tags():
    ticket = {"ticket_id": "A", "subject": "unicorn zoology", "resolution_notes": "Correct fix", "tags": ["unique"]}
    svc = SimilarityService([ticket])
    ticket.update(ticket_id="B", resolution_notes="Wrong fix")
    ticket["tags"].append("mutated")
    match = svc.search("unicorn zoology").matches[0]
    assert match.ticket_id == "A" and match.resolution_notes == "Correct fix"
    assert svc.tickets[0]["tags"] == ["unique"]


@pytest.mark.parametrize("top_k", [1, 3])
def test_hidden_or_lower_ranked_confidence_does_not_upgrade_first_match(top_k):
    svc = SimilarityService([
        {"ticket_id": "A", "subject": "invoice address", "resolution_notes": "fixed"},
        {"ticket_id": "B", "subject": "other issue", "resolution_notes": "invoice address export permission timeout"},
        {"ticket_id": "C", "subject": "other issue", "description": "export permission timeout", "resolution_notes": "fixed"},
    ])
    result = svc.search("invoice address export permission timeout", top_k=top_k)
    assert result.verdict == "weak_match"
    assert result.nearest == result.matches[0]
    assert result.matches[0].ticket_id == "A"
    assert result.matches[0].confidence == 0.4


def test_blank_resolution_is_not_indexed_and_query_types_are_validated(service):
    assert not SimilarityService().add({"ticket_id": "A", "resolution_notes": "  \n"})
    with pytest.raises(ValueError, match="query text"):
        service.search(["invoice"])
    assert service.search(" \n ").verdict == NONE
