import json
import os
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


TRAFFIC_PATH = Path(
    os.getenv("TRAFFIC_PATH", "/data/dashboard/backend_traffic.json")
)
LOCK = threading.Lock()
COUNTERS = Counter()
TOTAL_LATENCY_MS = Counter()
SERVICES = {
    "/catalog": ("catalog", ["normal-domain", "synthetic-telemetry", "test-fixture"]),
    "/auth/session": ("auth", ["session-valid", "session-renewed"]),
    "/events/ingest": ("events", ["accepted"]),
    "/search": ("search", ["normal-result", "cached-result"]),
    "/metrics": ("metrics", ["cpu", "memory", "requests"]),
}


def write_snapshot() -> None:
    with LOCK:
        by_service = {}
        for key, count in COUNTERS.items():
            if not key.startswith("route:"):
                continue
            _, service, route = key.split(":", 2)
            by_service.setdefault(service, {"requests": 0, "routes": {}})
            by_service[service]["requests"] += count
            by_service[service]["routes"][route] = {
                "requests": count,
                "average_latency_ms": round(
                    TOTAL_LATENCY_MS[f"{service}:{route}"] / count, 2
                ),
            }
        snapshot = {
            "total_requests": sum(
                count for key, count in COUNTERS.items() if key.startswith("route:")
            ),
            "applications": dict(
                (key.removeprefix("app:"), count)
                for key, count in COUNTERS.items()
                if key.startswith("app:")
            ),
            "services": by_service,
            "errors": COUNTERS["errors"],
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    TRAFFIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = TRAFFIC_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    temporary_path.replace(TRAFFIC_PATH)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        started = time.perf_counter()
        path = urlparse(self.path).path.removeprefix("/api")
        application = self.headers.get("X-Synthetic-Application", "unknown")
        service_data = SERVICES.get(path)
        if path == "/health":
            payload = {"status": "ok", "service": "fake-services"}
            self.send_json(payload, application, "/health", "health", started)
            return
        if service_data is None:
            with LOCK:
                COUNTERS["errors"] += 1
            self.send_error(404)
            write_snapshot()
            return
        service, items = service_data
        self.send_json(
            {"service": service, "items": items},
            application,
            path,
            service,
            started,
        )

    def send_json(
        self,
        payload: dict[str, object],
        application: str,
        route: str,
        service: str,
        started: float,
    ) -> None:
        latency_ms = (time.perf_counter() - started) * 1000
        with LOCK:
            COUNTERS[f"app:{application}"] += 1
            COUNTERS[f"route:{service}:{route}"] += 1
            TOTAL_LATENCY_MS[f"{service}:{route}"] += latency_ms
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        write_snapshot()

    def log_message(self, format: str, *args: object) -> None:
        return


write_snapshot()
ThreadingHTTPServer(("0.0.0.0", 8081), Handler).serve_forever()
