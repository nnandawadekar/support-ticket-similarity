import pytest

from ticket_similarity.cli import main


@pytest.mark.parametrize("value", ["0", "-2", "three"])
def test_top_k_must_be_positive(value, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--top-k", value, "query", "chart blank"])
    assert exc.value.code == 2
    assert "must be a positive integer" in capsys.readouterr().err


def test_query_respects_top_k(capsys):
    main(["--top-k", "1", "--json", "query", "dashboard slow to load"])
    out = capsys.readouterr().out
    assert out.count('"ticket_id"') == 2  # one match + nearest
