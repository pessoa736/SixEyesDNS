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
import dns.rcode

from external_domains import (
    is_external_index,
    load_external_domains,
    pick_external_domain,
)


DNS_PORT = int(os.getenv("DNS_PORT", "53"))
QUERY_COUNT = int(os.getenv("QUERY_COUNT", "10000"))
QUERY_INTERVAL = float(os.getenv("QUERY_INTERVAL", "0.01"))
LABELS_PATH = Path(os.getenv("LABELS_PATH", "/data/query_labels.csv"))
DASHBOARD_PATH = Path(
    os.getenv("DASHBOARD_PATH", "/data/dashboard/traffic_summary.json")
)
SEED = int(os.getenv("SEED", "42"))
RANDOM = random.Random(SEED)
ANOMALY_RATE = float(os.getenv("ANOMALY_RATE", "0.5"))
# Ranking local opcional (rank,domain); sem o arquivo o perfil normal_tranco fica desligado.
TRANCO_PATH = Path(os.getenv("TRANCO_PATH", "/external/tranco_top.csv"))
TRANCO_LIMIT = int(os.getenv("TRANCO_LIMIT", "2000"))
TRANCO_RATE = float(os.getenv("TRANCO_RATE", "0.15"))

# Tipos de consulta ponderados: normais lembram tráfego real (A/AAAA dominam),
# anomalias concentram-se em TXT/CNAME como em túneis DNS.
NORMAL_QUERY_TYPES = ("A", "AAAA", "MX", "NS", "CNAME", "TXT", "PTR")
NORMAL_QUERY_WEIGHTS = (55, 20, 6, 4, 6, 5, 4)
ANOMALY_QUERY_TYPES = ("TXT", "CNAME", "A", "AAAA", "MX", "NS")
ANOMALY_QUERY_WEIGHTS = (45, 20, 20, 5, 5, 5)
TIMELINE_MAX_MINUTES = 120
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
# Temas de entretenimento do laboratorio: memes classicos e Jujutsu Kaisen.
MEMES = (
    "doge",
    "pepe",
    "nyancat",
    "trollface",
    "rickroll",
    "harambe",
    "shrek",
    "grumpycat",
    "stonks",
    "distracted-bf",
    "drakeposting",
    "womanyelling",
    "surprised-pikachu",
    "thisisfine",
    "gigachad",
    "sus-amogus",
)
JJK = (
    "gojo",
    "sukuna",
    "itadori",
    "megumi",
    "nobara",
    "nanami",
    "toji",
    "geto",
    "mahito",
    "jogo",
    "hanami",
    "choso",
    "yuta",
    "maki",
    "panda",
    "inumaki",
    "hakari",
    "kashimo",
    "kenjaku",
    "miwa",
    "todo",
    "mai",
    "kamo",
    "mechamaru",
)
JJK_TERMS = (
    "domain-expansion",
    "cursed-energy",
    "hollow-purple",
    "limitless",
    "black-flash",
    "malevolent-shrine",
    "infinity",
    "binding-vow",
    "cursed-technique",
    "reverse-cursed",
    "ten-shadows",
    "ratio-technique",
)
MEME_WORDS = (
    "meme",
    "memes",
    "shitpost",
    "dank",
    "viral",
    "clip",
    "gif",
    "reaction",
    "lore",
    "wiki",
    "fanart",
    "clipes",
)


def random_bytes(size: int = 18) -> bytes:
    return bytes(RANDOM.randrange(256) for _ in range(size))


def parse_targets() -> list[tuple[str, str, int]]:
    """Lê DNS_TARGETS no formato "nome:peso,nome:peso" e resolve os hosts."""
    raw = os.getenv("DNS_TARGETS", "").strip()
    if not raw:
        raw = f"{os.getenv('DNS_SERVER', 'dnsmasq')}:1"
    targets = []
    for item in raw.split(","):
        name, _, weight = item.partition(":")
        name = name.strip()
        if not name:
            continue
        address = socket.gethostbyname(name)
        targets.append((name, address, max(1, int(weight or "1"))))
    if not targets:
        raise ValueError("DNS_TARGETS não define nenhum servidor válido")
    return targets


def pick_target(targets: list[tuple[str, str, int]]) -> tuple[str, str]:
    """Escolhe um servidor DNS pelo peso configurado."""
    name, address, _ = RANDOM.choices(
        targets, weights=[target[2] for target in targets], k=1
    )[0]
    return name, address


def normal_domain(index: int) -> tuple[str, str, str, str]:
    """Gera tráfego legítimo variado, incluindo casos difíceis sintéticos."""
    service = SERVICES[index % len(SERVICES)]
    region = REGIONS[(index // len(SERVICES)) % len(REGIONS)]
    environment = ENVIRONMENTS[(index // 17) % len(ENVIRONMENTS)]
    platform = PLATFORMS[(index // 31) % len(PLATFORMS)]
    word = WORDS[(index // 43) % len(WORDS)]
    meme = MEMES[(index // 13) % len(MEMES)]
    meme_word = MEME_WORDS[(index // 7) % len(MEME_WORDS)]
    character = JJK[(index // 11) % len(JJK)]
    term = JJK_TERMS[(index // 19) % len(JJK_TERMS)]
    pattern = index % 16

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
    if pattern == 7:
        return (
            f"{service}-{index % 1000:03d}.{region}.{platform}.test",
            "normal",
            service,
            "normal_hard",
        )
    if pattern == 8:
        return (
            f"{word}-{index % 200:02d}.{environment}.{platform}.test",
            "normal",
            service,
            "normal_hard",
        )
    if pattern == 9:
        return (
            f"assets-{index % 64:02x}.{service}.{platform}.test",
            "normal",
            service,
            "normal_hard",
        )
    if pattern == 10:
        return (
            f"{meme}-{index % 40:02d}.{meme_word}.test",
            "normal",
            "memes",
            "normal_meme",
        )
    if pattern == 11:
        return (
            f"{meme_word}-{index % 60:02d}.{meme}.test",
            "normal",
            "memes",
            "normal_meme",
        )
    if pattern == 12:
        return (
            f"{character}-{index % 24:02d}.jjk.test",
            "normal",
            "jjk",
            "normal_jjk",
        )
    if pattern == 13:
        return f"{term}.{character}.jjk.test", "normal", "jjk", "normal_jjk"
    if pattern == 14:
        return (
            f"{character}-{index % 90:02d}.{region}.jjk.test",
            "normal",
            "jjk",
            "normal_jjk",
        )
    return (
        f"{meme}.{environment}.{platform}.test",
        "normal",
        "memes",
        "normal_meme",
    )


def reverse_name(index: int) -> tuple[str, str, str, str]:
    """Gera consulta reversa PTR para IPs do laboratório."""
    if index % 4 == 0:
        host = 100 + index % 100
    else:
        host = 2 + index % 14
    return f"{host}.0.30.172.in-addr.arpa", "normal", "rede", "normal_reverse"


def external_name(domains: list[str], index: int) -> tuple[str, str, str, str]:
    """Usa um nome do ranking local como texto de uma consulta normal `.test`."""
    domain = pick_external_domain(domains, SEED, index)
    return f"{domain}.test", "normal", "tranco", "normal_tranco"


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


def send_query(domain: str, query_type: str, address: str) -> str:
    request = dns.message.make_query(domain, query_type)
    response = dns.query.udp(request, address, port=DNS_PORT, timeout=3)
    return dns.rcode.to_text(response.rcode())


def write_summary(
    total_queries: int,
    labels: Counter[str],
    family_counts: Counter[str],
    families: dict[str, set[str]],
    server_counts: Counter[str],
    type_counts: Counter[str],
    rcode_counts: Counter[str],
    failures: Counter[str],
    timeline: dict[str, Counter[str]],
    targets: list[tuple[str, str, int]],
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
        "servers": dict(server_counts),
        "query_types": dict(type_counts),
        "rcodes": dict(rcode_counts),
        "failures": dict(failures),
        "targets": [
            {"name": name, "address": address, "weight": weight}
            for name, address, weight in targets
        ],
        "timeline": [
            {
                "minute": minute,
                "queries": sum(counts.values()),
                "normal": counts.get("normal", 0),
                "suspeita": counts.get("suspeita", 0),
            }
            for minute, counts in sorted(timeline.items())
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = DASHBOARD_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary_path.replace(DASHBOARD_PATH)


def main() -> None:
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    targets = parse_targets()
    external_domains = load_external_domains(TRANCO_PATH, TRANCO_LIMIT)
    if external_domains:
        print(
            f"tranco_dominios={len(external_domains)} tranco_taxa={TRANCO_RATE}",
            flush=True,
        )
    elif TRANCO_PATH.is_file():
        print(f"tranco_aviso=sem dominios validos em {TRANCO_PATH}", flush=True)
    labels = Counter()
    family_counts = Counter()
    domains_by_family: defaultdict[str, set[str]] = defaultdict(set)
    server_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    rcode_counts: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    timeline: defaultdict[str, Counter[str]] = defaultdict(Counter)

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
                "server",
            )
        )

        for index in range(QUERY_COUNT):
            if RANDOM.random() >= ANOMALY_RATE:
                label = "normal"
                query_type = RANDOM.choices(
                    NORMAL_QUERY_TYPES, weights=NORMAL_QUERY_WEIGHTS, k=1
                )[0]
                if query_type == "PTR":
                    domain, family, service, profile = reverse_name(index)
                elif external_domains and is_external_index(
                    SEED, index, TRANCO_RATE
                ):
                    domain, family, service, profile = external_name(
                        external_domains, index
                    )
                else:
                    domain, family, service, profile = normal_domain(index)
            else:
                label = "suspeita"
                query_type = RANDOM.choices(
                    ANOMALY_QUERY_TYPES, weights=ANOMALY_QUERY_WEIGHTS, k=1
                )[0]
                domain, family, service, profile = anomalous_domain(index)

            server_name, server_address = pick_target(targets)
            try:
                rcode = send_query(domain, query_type, server_address)
            except (dns.exception.DNSException, OSError) as error:
                failures[server_name] += 1
                print(
                    f"falha={domain} servidor={server_name} erro={error}",
                    flush=True,
                )
                continue

            timestamp = datetime.now(timezone.utc)
            writer.writerow(
                (
                    index,
                    timestamp.isoformat(),
                    domain,
                    query_type,
                    service,
                    family,
                    profile,
                    label,
                    SEED,
                    server_name,
                )
            )
            labels_file.flush()
            labels[label] += 1
            family_counts[profile] += 1
            domains_by_family[profile].add(domain)
            server_counts[server_name] += 1
            type_counts[query_type] += 1
            rcode_counts[rcode] += 1
            minute = timestamp.replace(second=0, microsecond=0).isoformat()
            timeline[minute][label] += 1
            while len(timeline) > TIMELINE_MAX_MINUTES:
                del timeline[min(timeline)]
            write_summary(
                index + 1,
                labels,
                family_counts,
                domains_by_family,
                server_counts,
                type_counts,
                rcode_counts,
                failures,
                timeline,
                targets,
            )
            print(
                f"consulta={domain} tipo={query_type} servidor={server_name} "
                f"servico={service} familia={family} rotulo={label} rcode={rcode}",
                flush=True,
            )
            time.sleep(QUERY_INTERVAL * RANDOM.uniform(0.5, 1.5))


if __name__ == "__main__":
    main()
