#!/usr/bin/env python3
"""Serve o dashboard local e o resumo produzido pelo gerador."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


class DashboardHandler(BaseHTTPRequestHandler):
    dashboard_dir: Path
    summary_path: Path
    backend_traffic_path: Path

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_file(self.dashboard_dir / "index.html", "text/html")
        elif path == "/traffic_summary.json":
            self._send_summary()
        elif path == "/backend_traffic.json":
            self._send_json_file(self.backend_traffic_path)
        elif path == "/api/health":
            self._send_json({"status": "ok", "service": "local-dashboard"})
        else:
            self.send_error(404)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_summary(self) -> None:
        try:
            payload = json.loads(self.summary_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            payload = {
                "total_queries": 0,
                "labels": {},
                "unique_domains": 0,
                "families": {},
                "updated_at": "aguardando coleta",
            }
        except json.JSONDecodeError:
            self.send_error(503, "Resumo temporariamente indisponível")
            return
        self._send_json(payload)

    def _send_json_file(self, path: Path) -> None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            payload = {
                "total_requests": 0,
                "applications": {},
                "services": {},
                "errors": 0,
                "updated_at": "aguardando aplicações",
            }
        except json.JSONDecodeError:
            self.send_error(503, "Tráfego backend temporariamente indisponível")
            return
        self._send_json(payload)

    def _send_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--dashboard-dir", type=Path, default=Path("docker/dashboard"))
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("data/raw/dashboard/traffic_summary.json"),
    )
    parser.add_argument(
        "--backend-traffic",
        type=Path,
        default=Path("data/raw/dashboard/backend_traffic.json"),
    )
    args = parser.parse_args()

    handler = DashboardHandler
    handler.dashboard_dir = args.dashboard_dir
    handler.summary_path = args.summary
    handler.backend_traffic_path = args.backend_traffic
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Dashboard disponível em http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
