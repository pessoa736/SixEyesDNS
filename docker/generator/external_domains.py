"""Fonte opcional de domínios populares para o gerador, sem dependências externas.

Lê um ranking local no formato ``rank,domain`` (por exemplo, um recorte do
arquivo do Tranco baixado manualmente), valida os nomes e escolhe domínios por
hash de ``(seed, index)``, sem consumir o ``random.Random`` do gerador. Os
nomes só viram texto de consultas ``.test`` dentro do laboratório; nenhuma
consulta sai para a Internet.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections.abc import Sequence
from pathlib import Path

# Tamanho máximo do domínio externo; com ".test" cabe com folga nos 64 caracteres
# da janela de tokens do modelo.
MAX_DOMAIN_LENGTH = 48
HOSTNAME = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*")
HASH_SPACE = 2**64


def normalize_external_domain(raw: str) -> str | None:
    """Normaliza um nome do ranking; devolve None se for inválido ou longo demais."""
    domain = raw.strip().rstrip(".").lower()
    if not domain or len(domain) > MAX_DOMAIN_LENGTH or not HOSTNAME.fullmatch(domain):
        return None
    return domain


def load_external_domains(path: Path | str, limit: int) -> list[str]:
    """Lê até ``limit`` domínios válidos e únicos, em ordem de rank.

    Linhas inválidas (rank não numérico, nome fora do padrão de hostname ou
    maior que ``MAX_DOMAIN_LENGTH``) e domínios repetidos são descartados.
    Arquivo ausente ou ``limit`` não positivo devolvem lista vazia.
    """
    file_path = Path(path)
    if limit <= 0 or not file_path.is_file():
        return []

    entries: list[tuple[int, str]] = []
    with file_path.open(newline="", encoding="utf-8-sig", errors="replace") as ranking:
        for row in csv.reader(ranking):
            if len(row) < 2:
                continue
            try:
                rank = int(row[0])
            except ValueError:
                continue
            domain = normalize_external_domain(row[1])
            if rank >= 1 and domain:
                entries.append((rank, domain))

    entries.sort(key=lambda entry: entry[0])
    domains: list[str] = []
    seen: set[str] = set()
    for _, domain in entries:
        if domain in seen:
            continue
        seen.add(domain)
        domains.append(domain)
        if len(domains) == limit:
            break
    return domains


def _hash_value(seed: int, index: int, purpose: str) -> int:
    digest = hashlib.sha256(f"{seed}:{index}:{purpose}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def is_external_index(seed: int, index: int, rate: float) -> bool:
    """Decide por hash se a consulta ``index`` usa um domínio externo (fração ``rate``)."""
    return _hash_value(seed, index, "rate") < rate * HASH_SPACE


def pick_external_domain(domains: Sequence[str], seed: int, index: int) -> str:
    """Escolhe um domínio de forma determinística por ``(seed, index)``, sem RNG."""
    if not domains:
        raise ValueError("A lista de domínios externos está vazia")
    return domains[_hash_value(seed, index, "pick") % len(domains)]
