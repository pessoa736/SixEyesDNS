import os
import random
import time
from urllib.request import Request, urlopen


SERVICE_HOST = os.getenv("SERVICE_HOST", "fake-services")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8081"))
REQUEST_INTERVAL = float(os.getenv("REQUEST_INTERVAL", "0.5"))
RANDOM = random.Random(int(os.getenv("TRAFFIC_SEED", "42")))
APPLICATIONS = {
    "web-frontend": ("/catalog", "/search", "/auth/session"),
    "event-worker": ("/events/ingest", "/metrics"),
    "monitor-agent": ("/health", "/metrics", "/catalog"),
}


def main() -> None:
    endpoints = [endpoint for values in APPLICATIONS.values() for endpoint in values]
    while True:
        application = RANDOM.choice(tuple(APPLICATIONS))
        endpoint = RANDOM.choice(APPLICATIONS[application])
        request = Request(
            f"http://{SERVICE_HOST}:{SERVICE_PORT}{endpoint}",
            headers={"X-Synthetic-Application": application},
        )
        try:
            with urlopen(request, timeout=3) as response:
                print(
                    f"application={application} endpoint={endpoint} "
                    f"status={response.status}",
                    flush=True,
                )
        except OSError as error:
            print(f"application={application} endpoint={endpoint} error={error}", flush=True)
        time.sleep(REQUEST_INTERVAL)


if __name__ == "__main__":
    main()
