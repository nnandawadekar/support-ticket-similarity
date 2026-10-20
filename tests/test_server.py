import json
import socket
import threading
import urllib.error
import urllib.parse
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
    assert _call(f"{base_url}/similar", {"text": "chart blank", "top_k": True})[0] == 400
    assert _call(f"{base_url}/similar", {"text": 123})[0] == 400


@pytest.mark.parametrize("payload", [{"subject": []}, {"description": 123}, {"text": "  \n"}])
def test_similar_rejects_malformed_ticket_text(base_url, payload):
    assert _call(f"{base_url}/similar", payload)[0] == 400


def test_service_validation_errors_return_400_without_indexing(base_url):
    before = _call(f"{base_url}/health")[1]["indexed"]
    ticket = {"ticket_id": "BAD", "subject": "subject", "description": "description",
              "resolution_notes": "fix", "category": ["invalid"]}
    status, body = _call(f"{base_url}/tickets", ticket)
    assert status == 400 and "category" in body["error"]
    assert _call(f"{base_url}/health")[1]["indexed"] == before


def test_zero_ticket_id_is_accepted(base_url):
    ticket = {"ticket_id": 0, "subject": "zero id", "description": "valid ticket", "resolution_notes": "fix"}
    assert _call(f"{base_url}/tickets", ticket)[0] == 201


@pytest.mark.parametrize("payload", [[], "chart blank"])
def test_post_rejects_non_object_json(base_url, payload):
    assert _call(f"{base_url}/similar", payload)[0] == 400


def test_post_rejects_negative_content_length(base_url):
    port = urllib.parse.urlsplit(base_url).port
    with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
        conn.sendall(b"POST /similar HTTP/1.1\r\nHost: localhost\r\nContent-Length: -1\r\n\r\n{}")
        conn.shutdown(socket.SHUT_WR)
        response = b""
        while chunk := conn.recv(4096):
            response += chunk
    assert b"400" in response.split(b"\r\n", 1)[0]
    assert b"invalid Content-Length" in response


def test_add_ticket_then_find_it(base_url):
    ticket = {"ticket_id": "T-2001", "subject": "Embedded iframe refuses to load", "description": "Embedded dashboard iframe blocked",
              "resolution_notes": "Added customer domain to frame-ancestors CSP."}
    assert _call(f"{base_url}/tickets", ticket)[0] == 201
    assert _call(f"{base_url}/tickets", ticket)[0] == 200
    status, body = _call(f"{base_url}/similar", {"text": "iframe embed not loading"})
    assert body["matches"][0]["ticket_id"] == "T-2001"
    assert _call(f"{base_url}/tickets", {"ticket_id": "x"})[0] == 400
    invalid_ticket = {
        "ticket_id": ["T-2002"],
        "subject": "Invalid ticket identifier",
        "description": "This should be rejected",
        "resolution_notes": "It must not be indexed.",
    }
    assert _call(f"{base_url}/tickets", invalid_ticket)[0] == 400
    assert _call(f"{base_url}/tickets", {**invalid_ticket, "ticket_id": True})[0] == 400
    assert _call(f"{base_url}/tickets", {**invalid_ticket, "ticket_id": 2002})[0] == 201


def test_unknown_route(base_url):
    assert _call(f"{base_url}/nope")[0] == 404
