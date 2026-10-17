"""
Small utility module provided as an optional starting point for the
support-ticket similarity case study.

Feel free to use, modify, replace, or ignore this entirely -- it is not
guaranteed to be complete or bug-free. It exists only so you don't have to
write basic data-loading and tokenizing helpers from scratch.
"""
import json
import re


def load_tickets(path):
    """Load a list of ticket dicts from a JSON file shaped like data/tickets.json."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tickets", data.get("new_tickets", []))


def normalize_text(text):
    """Lowercase, strip punctuation, and split into a set of word tokens."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return set(text.split())


def keyword_overlap_score(tokens_a, tokens_b):
    """Naive keyword-overlap similarity between two token sets, in [0, 1]."""
    if not tokens_a:
        return 0.0
    shared = tokens_a & tokens_b
    return len(shared) / len(tokens_a)


def find_top_matches(new_ticket_text, historical_tickets, top_n=3):
    """Rank historical tickets by keyword overlap with new_ticket_text."""
    new_tokens = normalize_text(new_ticket_text)
    scored = []
    for ticket in historical_tickets:
        ticket_text = ticket.get("subject", "") + " " + ticket.get("description", "")
        ticket_tokens = normalize_text(ticket_text)
        score = keyword_overlap_score(new_tokens, ticket_tokens)
        scored.append((ticket, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_n]
