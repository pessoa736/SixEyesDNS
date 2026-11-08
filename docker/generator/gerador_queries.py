import base64
import csv
import hashlib
import json
import os
import random
import socket
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import dns.exception
import dns.message
import dns.query


DNS_SERVER = os.getenv("DNS_SERVER", "dnsmasq")
DNS_PORT = int(os.getenv("DNS_PORT", "53"))
QUERY_COUNT = int(os.getenv("QUERY_COUNT", "30"))
QUERY_INTERVAL = float(os.getenv("QUERY_INTERVAL", "0.2"))
LABELS_PATH = Path(os.getenv("LABELS_PATH", "/data/query_labels.csv"))
DASHBOARD_PATH = Path(
    os.getenv("DASHBOARD_PATH", "/data/dashboard/traffic_summary.json")
)
SEED = int(os.getenv("SEED", "42"))
RANDOM = random.Random(SEED)
ANOMALY_RATE = float(os.getenv("ANOMALY_RATE", "0.5"))
QUERY_TYPES = ("A", "AAAA", "CNAME", "TXT", "NS", "MX", "PTR")
SERVICES = ("web", "api", "catalog", "auth", "metrics", "mail", "cdn", "dashboard")
REGIONS = ("us-east", "us-west", "eu-west", "sa-east", "ap-south", "br-south")
ENVIRONMENTS = ("dev", "staging", "prod", "canary")
PLATFORMS = ("atlas", "brisa", "cobalto", "lumen", "nuvem", "orbita", "pulsar")
WORDS = (
    "account",
    "billing",
    "health",
    "events",
    "images",
    "login",
    "orders",
    "search",
    "session",
    "status",
    "telemetry",
)


def random_bytes(size: int = 18) -> bytes:
    return bytes(RANDOM.randrange(256) for _ in range(size))


def normal_domain(index: int) -> tuple[str, str, str, str]:
    """Gera tráfego legítimo variado, incluindo casos difíceis sintéticos."""
    service = SERVICES[index % len(SERVICES)]
    region = REGIONS[(index // len(SERVICES)) % len(REGIONS)]
    environment = ENVIRONMENTS[(index // 17) % len(ENVIRONMENTS)]
    platform = PLATFORMS[(index // 31) % len(PLATFORMS)]
    word = WORDS[(index // 43) % len(WORDS)]
    pattern = index % 8

    if pattern == 0:
        return f"{service}.{platform}.test", "normal", service, "normal"
    if pattern == 1:
        return f"{environment}.{service}.{platform}.test", "normal", service, "normal"
    if pattern == 2:
        return f"{region}.{service}.{platform}.test", "normal", service, "normal"
    if pattern == 3:
        return f"{word}.{region}.{service}.{platform}.test", "normal", service, "normal"
    if pattern == 4:
        return (
            f"v{1 + (index // 97) % 8}.{service}.{platform}.test",
            "normal",
            service,
            "normal",
        )
    if pattern == 5:
        return (
            f"node-{index % 500:03d}.{service}.{platform}.test",
            "normal",
            service,
            "normal_hard",
        )
    if pattern == 6:
        digest = hashlib.sha256(f"{SEED}:{index}".encode()).hexdigest()[:10]
        return f"{digest}.{service}.{platform}.test", "normal", service, "normal_hard"
    return (
        f"{service}-{index % 1000:03d}.{region}.{platform}.test",
        "normal",
        service,
        "normal_hard",
    )


def anomalous_domain(index: int) -> tuple[str, str, str, str]:
    """Gera somente famílias sintéticas para avaliação defensiva."""
    family = ("base32", "hex", "base64", "low_entropy", "mixed")[index % 5]
    service = SERVICES[index % len(SERVICES)]
    if family == "low_entropy":
        encoded = ("safe" * (3 + index % 4))[: 12 + index % 8]
    elif family == "mixed":
        encoded = (
            base64.b32encode(random_bytes(6)).decode("ascii").rstrip("=").lower()
            + f"-{index % 97}"
        )
    else:
        payload = random_bytes(8 + (index % 5) * 4)
        if family == "base32":
            encoded = base64.b32encode(payload).decode("ascii").rstrip("=").lower()
        elif family == "hex":
            encoded = payload.hex()
        else:
            encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    if family == "low_entropy":
        domain = f"{encoded}.{service}.tunnel.test"
    else:
        domain = f"{encoded}.tunnel.test"
    return domain, family, service, family


def send_query(domain: str, query_type: str) -> None:
    request = dns.message.make_query(domain, query_type)
    server_address = socket.gethostbyname(DNS_SERVER)
    response = dns.query.udp(request, server_address, port=DNS_PORT, timeout=3)
    response.rcode()


def write_summary(
    total_queries: int,
    labels: Counter[str],
    family_counts: Counter[str],
    families: dict[str, set[str]],
) -> None:
    payload = {
        "seed": SEED,
        "total_queries": total_queries,
        "labels": dict(labels),
        "unique_domains": len(set().union(*families.values())) if families else 0,
        "families": {
            family: {
                "queries": family_counts[family],
                "unique_domains": len(domains),
            }
            for family, domains in sorted(families.items())
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = DASHBOARD_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary_path.replace(DASHBOARD_PATH)


def main() -> None:
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    labels = Counter()
    family_counts = Counter()
    domains_by_family: defaultdict[str, set[str]] = defaultdict(set)

    with LABELS_PATH.open("w", newline="", encoding="utf-8") as labels_file:
        writer = csv.writer(labels_file)
        writer.writerow(
            (
                "sequence",
                "timestamp",
                "query",
                "query_type",
                "service",
                "family",
                "profile",
                "label",
                "seed",
            )
        )

        for index in range(QUERY_COUNT):
            query_type = RANDOM.choice(QUERY_TYPES)
            if RANDOM.random() >= ANOMALY_RATE:
                domain, family, service, profile = normal_domain(index)
                label = "normal"
            else:
                domain, family, service, profile = anomalous_domain(index)
                label = "suspeita"

            try:
                send_query(domain, query_type)
            except dns.exception.DNSException as error:
                print(f"falha={domain} erro={error}", flush=True)
                continue

            timestamp = datetime.now(timezone.utc).isoformat()
            writer.writerow(
                (index, timestamp, domain, query_type, service, family, profile, label, SEED)
            )
            labels_file.flush()
            labels[label] += 1
            family_counts[profile] += 1
            domains_by_family[profile].add(domain)
            write_summary(index + 1, labels, family_counts, domains_by_family)
            print(
                f"consulta={domain} tipo={query_type} servico={service} "
                f"familia={family} rotulo={label}",
                flush=True,
            )
            time.sleep(QUERY_INTERVAL)


if __name__ == "__main__":
    main()
