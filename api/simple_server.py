"""No-dependency HTTP API for local demos."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import service


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self.reply(service.health())
            return
        if path.startswith("/simulations/") and path.endswith("/events"):
            run_id = path.split("/")[2]
            self.reply(service.get_events(run_id))
            return
        if path.startswith("/simulations/") and "/agents/" in path and path.endswith("/trace"):
            parts = path.split("/")
            self.reply(service.get_agent_trace(parts[2], parts[4]))
            return
        if path.startswith("/simulations/"):
            self.reply(service.get_simulation(path.split("/")[2]))
            return
        if path.startswith("/experiments/") and path.endswith("/comparison"):
            self.reply(service.get_experiment_comparison(path.split("/")[2]))
            return
        self.reply({"error": "not found", "path": path}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        payload = self.read_json()
        if path == "/scenarios/validate":
            self.reply(service.validate_scenario(payload))
            return
        if path == "/simulations/run":
            self.reply(service.run_simulation(payload))
            return
        if path == "/experiments/run":
            self.reply(service.run_experiment(payload))
            return
        self.reply({"error": "not found", "path": path}, status=404)

    def read_json(self) -> dict:
        length = int(self.headers.get("content-length", "0"))
        if not length:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def reply(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    host = os.environ.get("HONGCE_API_HOST", "127.0.0.1")
    port = int(os.environ.get("HONGCE_API_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"HongCe API listening on http://{host}:{port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
