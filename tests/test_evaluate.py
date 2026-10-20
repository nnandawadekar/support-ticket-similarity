import pytest

from ticket_similarity.evaluate import format_report, score_run, summarize, sweep
from ticket_similarity.service import SimilarityService, Thresholds


def test_precision_scores_the_displayed_match_after_threshold_filtering():
    svc = SimilarityService([
        {"ticket_id": "A", "subject": "invoice address", "resolution_notes": "fixed"},
        {"ticket_id": "B", "subject": "other issue", "resolution_notes": "invoice address export permission timeout"},
        {"ticket_id": "C", "subject": "other issue", "description": "export permission timeout", "resolution_notes": "fixed"},
    ], thresholds=Thresholds(strong=0.9, weak=0.5))
    rows = score_run(svc, [{"id": "Q", "text": "invoice address export permission timeout", "relevant": ["B"]}])
    report = summarize(rows, "lexical")
    assert report.hit_at_1 == 0.0
    assert report.shown_hit_at_1 == report.strong_precision == 1.0
    assert report.strong_predictions == 1


def test_no_strong_predictions_reports_undefined_precision():
    rows = score_run(SimilarityService(), [{"id": "N", "text": "novel", "relevant": []}])
    report = summarize(rows, "lexical")
    assert report.strong_predictions == 0 and report.strong_precision is None
    assert "strong_precision=n/a" in format_report(report)


@pytest.mark.parametrize("positive, negative, expected", [(0.193, 0.17, 0.18), (0.3, 0.29, 0.3)])
def test_sweep_includes_low_thresholds_and_compares_exact_grid_values(positive, negative, expected):
    rows = [{"top_conf": positive, "has_candidates": True, "relevant": {"A"}},
            {"top_conf": negative, "has_candidates": True, "relevant": set()}]
    result = sweep(rows)
    assert result["threshold"] == expected
    assert result["balanced_accuracy"] == 1.0


@pytest.mark.parametrize("rows", [[], [{"top_conf": 0.3, "relevant": {"A"}}]])
def test_sweep_requires_both_query_classes(rows):
    with pytest.raises(ValueError, match="both precedent and novel"):
        sweep(rows)


def test_unseen_positive_cannot_be_recalled_by_lowering_threshold_to_zero():
    svc = SimilarityService([{"ticket_id": "A", "subject": "invoice", "resolution_notes": "fixed"}])
    rows = score_run(svc, [
        {"id": "P", "text": "zyxwvut", "relevant": ["A"]},
        {"id": "N", "text": "invoice", "relevant": []},
    ])
    assert rows[0]["has_candidates"] is False
    assert rows[0]["ranked"] == []
    zero = sweep(rows, lo=0, hi=0)
    assert zero["recall_on_precedent"] == 0.0
    assert zero["balanced_accuracy"] == 0.0
    assert zero["precedents_without_candidates"] == 1


def test_missing_positive_does_not_produce_a_false_zero_threshold_recommendation():
    rows = [
        {"top_conf": 0.0, "has_candidates": False, "relevant": {"A"}},
        {"top_conf": 0.1, "has_candidates": True, "relevant": set()},
    ]
    result = sweep(rows)
    assert result["threshold"] == 0.11
    assert result["recall_on_precedent"] == 0.0
    assert result["novel_detected"] == 1.0
    assert result["balanced_accuracy"] == 0.5


@pytest.mark.parametrize("text", ["zyxwvut", "   \n"])
def test_empty_retrieval_still_abstains_at_zero_on_both_query_classes(text):
    svc = SimilarityService(thresholds=Thresholds(strong=0.45, weak=0.0))
    queries = [{"id": "P", "text": text, "relevant": ["A"]}, {"id": "N", "text": text, "relevant": []}]
    rows = score_run(svc, queries)
    assert all(not row["has_candidates"] and row["verdict"] == "no_match" for row in rows)
    result = sweep(rows, lo=0, hi=0)
    assert result["recall_on_precedent"] == 0.0
    assert result["novel_detected"] == 1.0
    assert result["novel_without_candidates"] == 1


def test_zero_confidence_candidate_is_accepted_at_zero_unlike_empty_retrieval():
    rows = [
        {"top_conf": 0.0, "has_candidates": True, "relevant": {"A"}},
        {"top_conf": 0.0, "has_candidates": False, "relevant": set()},
    ]
    result = sweep(rows, lo=0, hi=0)
    assert result["recall_on_precedent"] == result["novel_detected"] == 1.0
    assert result["balanced_accuracy"] == 1.0


@pytest.mark.parametrize("threshold", [0.0, 0.2, 0.45, 1.0])
def test_sweep_acceptance_matches_service_verdicts_at_the_same_threshold(threshold):
    svc = SimilarityService(
        [{"ticket_id": "A", "subject": "invoice", "resolution_notes": "fixed"}],
        thresholds=Thresholds(strong=1.0, weak=threshold),
    )
    rows = score_run(svc, [
        {"id": "P-found", "text": "invoice", "relevant": ["A"]},
        {"id": "P-missing", "text": "zyxwvut", "relevant": ["A"]},
        {"id": "N-found", "text": "invoice qzxjkv", "relevant": []},
        {"id": "N-missing", "text": "qzxjkv", "relevant": []},
    ])
    report = summarize(rows, "lexical")
    result = sweep(rows, lo=threshold, hi=threshold)
    assert result["recall_on_precedent"] == 1 - report.false_abstain
    assert result["novel_detected"] == report.novel_detected
