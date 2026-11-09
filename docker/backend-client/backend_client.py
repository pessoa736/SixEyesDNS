import os
import random
import time
from urllib.request import Request, urlopen


SERVICE_HOST = os.getenv("SERVICE_HOST", "fake-services")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8081"))
REQUEST_INTERVAL = float(os.getenv("REQUEST_INTERVAL", "0.5"))
RANDOM = random.Random(int(os.getenv("TRAFFIC_SEED", "42")))
SITES = (
    ("portal.atlas.test", ("/catalog", "/search", "/auth/session"), 35),
    ("docs.brisa.test", ("/catalog", "/search"), 25),
    ("status.cobalto.test", ("/health", "/metrics"), 15),
    ("shop.lumen.test", ("/catalog", "/auth/session", "/search"), 15),
    ("news.nuvem.test", ("/catalog", "/search"), 10),
)
APPLICATIONS = (("web-frontend", 60), ("event-worker", 25), ("monitor-agent", 15))
USER_AGENTS = (
    "synthetic-browser/1.0",
    "synthetic-mobile/1.0",
    "synthetic-worker/1.0",
)


def browse_session() -> None:
    application = RANDOM.choices(
        [item[0] for item in APPLICATIONS],
        weights=[item[1] for item in APPLICATIONS],
        k=1,
    )[0]
    site, routes, _ = RANDOM.choices(SITES, weights=[item[2] for item in SITES], k=1)[0]
    pages = RANDOM.randint(2, 6) if application == "web-frontend" else 1
    for _ in range(pages):
        endpoint = RANDOM.choice(routes)
        request = Request(
            f"http://{SERVICE_HOST}:{SERVICE_PORT}{endpoint}",
            headers={
                "X-Synthetic-Application": application,
                "X-Synthetic-Site": site,
                "User-Agent": RANDOM.choice(USER_AGENTS),
            },
        )
        try:
            with urlopen(request, timeout=3) as response:
                print(
                    f"application={application} site={site} endpoint={endpoint} "
                    f"status={response.status}",
                    flush=True,
                )
        except OSError as error:
            print(
                f"application={application} site={site} endpoint={endpoint} "
                f"error={error}",
                flush=True,
            )
        time.sleep(RANDOM.uniform(0.08, 0.7))
    time.sleep(RANDOM.uniform(0.2, 2.5) * (2 if application == "web-frontend" else 0.5))


def main() -> None:
    while True:
        browse_session()
        time.sleep(REQUEST_INTERVAL * RANDOM.uniform(0.5, 1.8))


if __name__ == "__main__":
    main()
