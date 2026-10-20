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
    rows = [{"top_conf": positive, "relevant": {"A"}}, {"top_conf": negative, "relevant": set()}]
    result = sweep(rows)
    assert result["threshold"] == expected
    assert result["balanced_accuracy"] == 1.0


@pytest.mark.parametrize("rows", [[], [{"top_conf": 0.3, "relevant": {"A"}}]])
def test_sweep_requires_both_query_classes(rows):
    with pytest.raises(ValueError, match="both precedent and novel"):
        sweep(rows)
