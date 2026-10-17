import pytest

from ticket_similarity.text import stem, tokenize


@pytest.mark.parametrize("variants", [
    ("charge", "charged", "charges", "charging"),
    ("sync", "syncs", "syncing"),
    ("log", "logged", "logging"),
    ("duplicate", "duplicates", "duplicated"),
    ("arrive", "arrives", "arrived"),
])
def test_stem_conflates_inflections(variants):
    assert len({stem(v) for v in variants}) == 1


def test_stem_leaves_short_and_ss_words():
    assert stem("sso") == "sso"
    assert stem("access") == "access"
    assert stem("status") == "status"


@pytest.mark.parametrize("phrase", ["log in", "logged in", "sign-in", "Signed in", "login", "logon"])
def test_login_phrases_collapse(phrase):
    assert tokenize(phrase) == ["login"]


def test_two_factor_variants():
    assert tokenize("two-factor") == tokenize("MFA") == tokenize("2FA") == ["2fa"]


def test_timeout_variants():
    assert tokenize("times out") == tokenize("timed out") == tokenize("timeout") == ["timeout"]


def test_contractions_and_possessives_do_not_leak_fragments():
    tokens = tokenize("The customer's email hasn't arrived and we can't log in")
    assert "hasn" not in tokens and "t" not in tokens and "can" not in tokens
    assert {"email", "arriv", "login"} <= set(tokens)


def test_stopwords_and_noise_numbers_dropped_but_status_codes_kept():
    tokens = tokenize("The API returns a 500 error after 2 days for 15 users")
    assert "500" in tokens
    assert "2" not in tokens and "15" not in tokens
    assert "the" not in tokens and "users" not in tokens


def test_tokenize_handles_none_and_empty():
    assert tokenize(None) == []
    assert tokenize("   ") == []
