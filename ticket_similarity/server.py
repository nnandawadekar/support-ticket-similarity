import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .data import query_text

log = logging.getLogger("ticket_similarity.server")
MAX_BODY = 64 * 1024


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TicketSimilarity/0.1"

        def log_message(self, fmt, *args):
            log.info("%s %s", self.address_string(), fmt % args)

        def _send(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                length = 0
            elif not raw_length.isascii() or not raw_length.isdigit():
                raise ValueError("invalid Content-Length") from None
            else:
                length = int(raw_length)
            if length > MAX_BODY:
                raise ValueError("payload too large")
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            return payload

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"status": "ok", "mode": service.mode, "indexed": len(service.tickets)})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            try:
                payload = self._body()
            except (ValueError, json.JSONDecodeError) as exc:
                return self._send(400, {"error": str(exc)})

            if self.path == "/similar":
                text = payload.get("text")
                if text is not None and not isinstance(text, str):
                    return self._send(400, {"error": "'text' must be a string"})
                text = text or query_text(payload)
                if not text:
                    return self._send(400, {"error": "provide 'text' or 'subject'/'description'"})
                top_k = payload.get("top_k")
                if top_k is not None and (type(top_k) is not int or not 1 <= top_k <= 20):
                    return self._send(400, {"error": "top_k must be an integer in [1, 20]"})
                result = service.search(text, top_k=top_k)
                return self._send(200, {"ticket_id": payload.get("ticket_id"), **result.to_dict()})

            if self.path == "/tickets":
                missing = [k for k in ("ticket_id", "subject", "description", "resolution_notes") if not payload.get(k)]
                if missing:
                    return self._send(400, {"error": f"missing fields: {', '.join(missing)}"})
                invalid = [k for k in ("subject", "description", "resolution_notes") if not isinstance(payload[k], str)]
                if type(payload["ticket_id"]) not in (str, int):
                    invalid.insert(0, "ticket_id")
                if invalid:
                    return self._send(400, {"error": f"fields must be strings: {', '.join(invalid)}"})
                tags = payload.get("tags")
                if tags is not None and (
                    not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags)
                ):
                    return self._send(400, {"error": "tags must be a list of strings"})
                added = service.add(payload)
                return self._send(201 if added else 200, {"indexed": added, "total": len(service.tickets)})

            self._send(404, {"error": "not found"})

    return Handler


def serve(service, host="127.0.0.1", port=8000):
    httpd = ThreadingHTTPServer((host, port), make_handler(service))
    log.info("serving %d tickets (%s) on http://%s:%d", len(service.tickets), service.mode, host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
