import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from ticket_similarity.data import DEFAULT_HISTORY, load_tickets
from ticket_similarity.server import make_handler
from ticket_similarity.service import SimilarityService


@pytest.fixture(scope="module")
def base_url():
    service = SimilarityService(load_tickets(DEFAULT_HISTORY))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _call(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def test_health(base_url):
    status, body = _call(f"{base_url}/health")
    assert status == 200 and body["indexed"] == 40


def test_similar_with_subject_and_description(base_url):
    status, body = _call(f"{base_url}/similar", {"ticket_id": "NT-3", "subject": "Getting charged twice this month",
                                                 "description": "Two charges on the card statement."})
    assert status == 200
    assert body["ticket_id"] == "NT-3"
    assert body["matches"][0]["ticket_id"] == "T-1303"


def test_similar_validation(base_url):
    assert _call(f"{base_url}/similar", {})[0] == 400
    assert _call(f"{base_url}/similar", {"text": "chart blank", "top_k": 0})[0] == 400


def test_add_ticket_then_find_it(base_url):
    ticket = {"ticket_id": "T-2001", "subject": "Embedded iframe refuses to load", "description": "Embedded dashboard iframe blocked",
              "resolution_notes": "Added customer domain to frame-ancestors CSP."}
    assert _call(f"{base_url}/tickets", ticket)[0] == 201
    assert _call(f"{base_url}/tickets", ticket)[0] == 200
    status, body = _call(f"{base_url}/similar", {"text": "iframe embed not loading"})
    assert body["matches"][0]["ticket_id"] == "T-2001"
    assert _call(f"{base_url}/tickets", {"ticket_id": "x"})[0] == 400


def test_unknown_route(base_url):
    assert _call(f"{base_url}/nope")[0] == 404
