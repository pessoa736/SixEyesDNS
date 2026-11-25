"""Perfis sintéticos do gerador: vocabulário, anomalias e normais difíceis.

Tudo aqui é determinístico: as anomalias recebem o ``random.Random`` do
gerador e os normais derivam de ``(seed, index)``. Nenhum nome sai do
laboratório; as zonas existem só como texto de consultas ``.test``.

As anomalias **não** carregam um sufixo fixo. A zona do túnel sai de um conjunto
que mistura nomes parecidos com a infraestrutura normal e zonas próprias do
atacante, para que o detector não separe as classes só por um trecho conhecido
do nome (o antigo ``.tunnel`` aparecia em 100% das suspeitas).
"""

from __future__ import annotations

import base64
import hashlib
import random

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
# Ferramentas de infraestrutura: aparecem pouco no tráfego normal, o que cria
# uma cauda longa de palavras legítimas raras.
RARE_WORDS = (
    "grafana", "kibana", "jenkins", "registry", "vault", "gitlab", "nexus",
    "sonar", "prometheus", "consul", "ldap", "vpn", "wiki", "backup", "printer",
    "ntp", "smtp", "imap", "proxy", "sso", "jira", "confluence", "bitbucket",
    "artifactory", "harbor", "traefik", "keycloak", "minio", "rabbitmq", "redis",
    "kafka", "zookeeper", "elastic", "logstash", "nagios", "zabbix", "bastion",
    "gateway", "ingress", "sentry",
)
# Zonas "próprias" do atacante: palavras plausíveis que os normais não usam.
ATTACKER_ZONES = (
    "syncfeed", "edgecache", "pixelmetrics", "datapipe", "updatehub",
    "cloudhelper", "mailrelay", "assetsync", "logship", "statuspulse",
    "cdnbridge", "metricsink",
)
# Palavras de um túnel por dicionário: se misturam ao vocabulário normal.
DICTIONARY_WORDS = WORDS + (
    "update", "cache", "static", "media", "assets", "config", "report", "sync",
    "queue", "stream", "profile", "token", "refresh", "index", "archive", "node",
)
ANOMALY_FAMILIES = (
    "base32",
    "hex",
    "base64",
    "low_entropy",
    "mixed",
    "dictionary",
    "short",
)
ZONE_KINDS = ("mimic", "mimic_region", "own")
ZONE_WEIGHTS = (40, 30, 30)
LOW_ENTROPY_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


def random_bytes(rng: random.Random, size: int) -> bytes:
    return bytes(rng.randrange(256) for _ in range(size))


def b32(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii").rstrip("=").lower()


def maybe_split(rng: random.Random, text: str, threshold: int) -> list[str]:
    """Divide um payload longo em duas etiquetas, como os túneis reais fazem."""
    if len(text) > threshold and rng.random() < 0.5:
        cut = len(text) // 2
        return [text[:cut], text[cut:]]
    return [text]


def tunnel_zone(rng: random.Random) -> str:
    """Zona do túnel: imita a infraestrutura normal ou usa um nome próprio."""
    kind = rng.choices(ZONE_KINDS, weights=ZONE_WEIGHTS, k=1)[0]
    service = rng.choice(SERVICES)
    platform = rng.choice(PLATFORMS)
    if kind == "mimic":
        return f"{service}.{platform}"
    if kind == "mimic_region":
        return f"{rng.choice(REGIONS)}.{service}.{platform}"
    return rng.choice(ATTACKER_ZONES)


def payload_labels(rng: random.Random, family: str) -> list[str]:
    """Etiquetas de payload da família pedida, sem a zona do túnel."""
    if family == "base32":
        return maybe_split(rng, b32(random_bytes(rng, 8 + rng.randrange(5) * 4)), 26)
    if family == "hex":
        return maybe_split(rng, random_bytes(rng, 8 + rng.randrange(5) * 4).hex(), 32)
    if family == "base64":
        data = random_bytes(rng, 8 + rng.randrange(5) * 4)
        return maybe_split(rng, base64.urlsafe_b64encode(data).decode().rstrip("="), 26)
    if family == "mixed":
        return [b32(random_bytes(rng, 6)) + f"-{rng.randrange(97)}"]
    if family == "low_entropy":
        # Dados com muito padding viram uma sequência repetitiva; o padrão sai
        # sorteado, para a família não colapsar em poucos domínios.
        pattern = "".join(rng.choices(LOW_ENTROPY_ALPHABET, k=rng.randint(1, 4)))
        return [(pattern * 24)[: rng.randint(12, 24)]]
    if family == "dictionary":
        words = rng.choices(DICTIONARY_WORDS, k=rng.randint(3, 6))
        return ["-".join(words)[:60]]
    if family == "short":
        return [b32(random_bytes(rng, rng.randint(4, 6)))]
    raise ValueError(f"Família de anomalia desconhecida: {family}")


def anomalous_domain(rng: random.Random, index: int) -> tuple[str, str, str, str]:
    """Anomalia sintética para avaliação defensiva: (domínio, família, serviço, perfil)."""
    family = ANOMALY_FAMILIES[index % len(ANOMALY_FAMILIES)]
    service = SERVICES[index % len(SERVICES)]
    labels = [*payload_labels(rng, family), tunnel_zone(rng), "test"]
    return ".".join(labels), family, service, family


def rare_word_domain(index: int) -> tuple[str, str, str, str]:
    """Nome legítimo com uma ferramenta de infraestrutura pouco frequente."""
    word = RARE_WORDS[(index // 5) % len(RARE_WORDS)]
    platform = PLATFORMS[(index // 3) % len(PLATFORMS)]
    service = SERVICES[index % len(SERVICES)]
    if (index // 7) % 2 == 0:
        return f"{word}.{platform}.test", "normal", service, "normal"
    environment = ENVIRONMENTS[(index // 11) % len(ENVIRONMENTS)]
    return f"{word}-{index % 30:02d}.{environment}.{platform}.test", "normal", service, "normal"


def cdn_id_domain(seed: int, index: int) -> tuple[str, str, str, str]:
    """Id de distribuição de CDN: alta entropia, base32 e legítimo."""
    digest = hashlib.sha256(f"cdn:{seed}:{index}".encode()).digest()
    label = "d" + b32(digest[:9])[:13]
    platform = PLATFORMS[(index // 31) % len(PLATFORMS)]
    return f"{label}.cdn.{platform}.test", "normal", "cdn", "normal_hard"


def uuid_like_domain(seed: int, index: int) -> tuple[str, str, str, str]:
    """Identificador de sessão ou instância em hexadecimal, legítimo."""
    digest = hashlib.sha256(f"uuid:{seed}:{index}".encode()).hexdigest()
    service = SERVICES[index % len(SERVICES)]
    platform = PLATFORMS[(index // 29) % len(PLATFORMS)]
    return (
        f"{digest[:8]}-{digest[8:12]}.{service}.{platform}.test",
        "normal",
        service,
        "normal_hard",
    )
