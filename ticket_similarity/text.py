import re

STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before being below between both
but by can could did do does doing down during each every few for from further had has have having he her here hers
him his how i if in into is it its itself just me more most my no nor not now of off on once only or other our out
over own same she should so some such than that the their them then there these they this those through to too under
until up very was we were what when where which while who whom why will with would you your yours
customer customers user users hour hours ago says said report reports reported notice notices noticed seems
someone still even completely just get gets getting
""".split())

# Ordered: multi-word phrases are collapsed before tokenizing so "log in" and "login" land on the same term.
PHRASES = [
    (re.compile(r"\blog(?:s|ged|ging)?[\s-]?in\b|\bsign(?:s|ed|ing)?[\s-]?in\b|\blogon\b"), "login"),
    (re.compile(r"\btwo[\s-]?factor\b|\b2[\s-]?step\b|\b2-fa\b"), "2fa"),
    (re.compile(r"\bsingle sign[\s-]?on\b"), "sso"),
    (re.compile(r"\be-mail\b"), "email"),
    (re.compile(r"\btim(?:es|ed|ing) out\b|\btime-?outs?\b"), "timeout"),
    (re.compile(r"\bread[\s-]only\b"), "viewer"),
    (re.compile(r"\btoo many requests\b"), "rate limit"),
]

SYNONYMS = {
    "mfa": "2fa", "otp": "2fa", "totp": "2fa",
    "signin": "login",
    "pw": "password", "passwd": "password",
    "graph": "chart", "graphs": "chart", "plot": "chart", "donut": "chart",
    "empty": "blank",
    "sluggish": "slow", "laggy": "slow",
}

TOKEN_RE = re.compile(r"[a-z0-9]+")
CONTRACTION_RE = re.compile(r"n't\b")
POSSESSIVE_RE = re.compile(r"'s\b")
NO_STRIP_ENDINGS = ("ss", "us", "is")
KEEP_DOUBLE = set("lsz")


def stem(word):
    if len(word) <= 3 or word.isdigit() or word.endswith(NO_STRIP_ENDINGS):
        return word
    for suffix, replacement in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if word.endswith(suffix):
            base = word[: -len(suffix)] + replacement
            if len(base) >= 3:
                word = base
                break
    if len(word) > 4 and word.endswith("e"):
        word = word[:-1]
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in KEEP_DOUBLE and word[-1] not in "aeiou":
        word = word[:-1]
    return word


def tokenize(text):
    text = (text or "").lower().replace("’", "'")
    text = CONTRACTION_RE.sub(" not", text.replace("can't", "cannot").replace("won't", "will not"))
    text = POSSESSIVE_RE.sub("", text)
    for pattern, replacement in PHRASES:
        text = pattern.sub(replacement, text)
    tokens = []
    for raw in TOKEN_RE.findall(text):
        raw = SYNONYMS.get(raw, raw)
        if raw in STOPWORDS:
            continue
        if raw.isdigit() and len(raw) != 3:
            continue
        if len(raw) < 2:
            continue
        tokens.append(stem(raw))
    return tokens
