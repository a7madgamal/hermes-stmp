"""A stand-in for the phone, so the whole failure surface can be tested offline.

Deliberately dumb: a route table, a request log, and the bridge's own JSON
envelope. Anything cleverer would be a second implementation to trust.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qsl, urlsplit

Response = tuple[int, dict[str, Any] | bytes, str]


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _serve(self) -> None:  # noqa: D401 - BaseHTTPRequestHandler hook
        parsed = urlsplit(self.path)
        key = f"{self.command} {parsed.path}"
        body = b""
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            body = self.rfile.read(length)

        record = {
            "method": self.command,
            "path": parsed.path,
            "query": dict(parse_qsl(parsed.query, keep_blank_values=True)),
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": body,
        }
        self.server.requests.append(record)  # type: ignore[attr-defined]

        response = self.server.routes.get(key)  # type: ignore[attr-defined]
        if response is None:
            payload: dict[str, Any] | bytes = {
                "ok": False,
                "error": "not_found",
                "detail": f"no stub route for {key}",
            }
            status, content_type = 404, "application/json"
        else:
            status, payload, content_type = response

        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _serve
    do_POST = _serve
    do_DELETE = _serve
    do_PUT = _serve
    do_PATCH = _serve

    def log_message(self, *args, **kwargs) -> None:  # keep test output clean
        return


class StubBridge:
    """Context manager serving a fixed route table on loopback."""

    def __init__(self, routes: dict[str, Response]):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.routes = routes  # type: ignore[attr-defined]
        self.server.requests = []  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "StubBridge":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self.server.requests  # type: ignore[attr-defined]


def ok(**fields: Any) -> Response:
    return 200, {"ok": True, **fields}, "application/json"


def fail(status: int, code: str, detail: str = "refused") -> Response:
    return status, {"ok": False, "error": code, "detail": detail}, "application/json"
