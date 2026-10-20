import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HISTORY = REPO_ROOT / "starter_kit" / "data" / "tickets.json"
DEFAULT_NEW = REPO_ROOT / "starter_kit" / "data" / "new_tickets_example.json"


def load_tickets(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    for key in ("tickets", "new_tickets"):
        if key in data:
            return data[key]
    raise ValueError(f"{path}: expected a list or an object with 'tickets' / 'new_tickets'")


def query_text(ticket):
    for name in ("subject", "description"):
        if name in ticket and not isinstance(ticket[name], str):
            raise ValueError(f"ticket {name} must be a string")
    return f"{ticket.get('subject', '')}\n{ticket.get('description', '')}".strip()


def field_text(ticket, field):
    value = ticket.get(field) or ""
    return " ".join(value) if isinstance(value, list) else str(value)


def is_indexable(ticket):
    return ticket.get("status", "resolved") == "resolved" and bool((ticket.get("resolution_notes") or "").strip())
