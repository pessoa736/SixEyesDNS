import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


SERVICE_NAME = os.getenv("SERVICE_NAME", "catalog-api")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json({"status": "ok", "service": SERVICE_NAME})
            return
        if self.path == "/api/catalog":
            self.send_json(
                {
                    "service": SERVICE_NAME,
                    "items": ["normal-domain", "synthetic-telemetry", "test-fixture"],
                }
            )
            return
        self.send_error(404)

    def send_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


ThreadingHTTPServer(("0.0.0.0", 8081), Handler).serve_forever()
