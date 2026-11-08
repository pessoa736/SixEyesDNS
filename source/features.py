"""Fonte única de verdade: normalização, vocabulário, tokenização e atributos.

Os 42 atributos numéricos do modelo são somente lexicais (6 escalares e 36
frequências de caracteres). ``label``, ``family``, ``query_type``, ``seed``,
IP e cliente são metadados e nunca entram na matriz de entrada.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np


CHARACTERS = tuple("abcdefghijklmnopqrstuvwxyz0123456789")
TOKEN_CHARACTERS = tuple("abcdefghijklmnopqrstuvwxyz0123456789-_.")
PAD = "<PAD>"
UNK = "<UNK>"
VOCABULARY = (PAD, UNK) + TOKEN_CHARACTERS
TOKEN_TO_INDEX = {token: index for index, token in enumerate(VOCABULARY)}
MAX_LENGTH = 64
LAB_SUFFIXES = (".test", ".example", ".invalid")
SCALAR_FEATURES = (
    "total_length",
    "entropy",
    "digit_ratio",
    "label_count",
    "max_label_length",
    "alphanumeric_ratio",
)
QUERY_TYPES = ("A", "AAAA", "CNAME", "TXT", "NS", "MX", "PTR")
FAMILIES = ("normal", "base32", "hex", "base64")
QUERY_TYPE_COLUMNS = tuple(f"is_{query_type}" for query_type in QUERY_TYPES)
FAMILY_COLUMNS = tuple(f"is_family_{family}" for family in FAMILIES)
FEATURE_COLUMNS = SCALAR_FEATURES + tuple(
    f"char_freq_{character}" for character in CHARACTERS
)
DATASET_CATEGORICAL_COLUMNS = QUERY_TYPE_COLUMNS + FAMILY_COLUMNS
METADATA_COLUMNS = (
    "label",
    "family",
    "query_type",
    "seed",
    "profile",
    "server",
    "sequence",
    "timestamp",
    "ip",
    "client",
    "cliente",
)
LOG_FEATURES = {"total_length", "label_count", "max_label_length"}
VALID_DOMAIN = re.compile(r"^[a-z0-9._-]+$")

_METADATA_LEAK = set(FEATURE_COLUMNS) & set(METADATA_COLUMNS)
if _METADATA_LEAK:
    raise AssertionError(f"Metadados na lista de features: {sorted(_METADATA_LEAK)}")


def normalize_domain(domain: str) -> str:
    """Remove a zona de laboratório e normaliza um nome de domínio."""
    normalized = domain.strip().rstrip(".").lower()
    for suffix in LAB_SUFFIXES:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def shannon_entropy(value: str) -> float:
    """Calcula a entropia de Shannon dos caracteres."""
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def extract_features(
    domain: str, query_type: str | None = None, family: str | None = None
) -> dict[str, float | int | str]:
    """Extrai atributos do domínio e indicadores categóricos conhecidos."""
    normalized = normalize_domain(domain)
    if not normalized or not VALID_DOMAIN.fullmatch(normalized):
        raise ValueError(f"Domínio vazio ou inválido: {domain!r}")

    labels = [label for label in normalized.split(".") if label]
    character_counts = Counter(normalized)
    length = len(normalized)
    digit_count = sum(character_counts[digit] for digit in "0123456789")
    alphanumeric_count = sum(
        character_counts[character] for character in "abcdefghijklmnopqrstuvwxyz0123456789"
    )

    features: dict[str, float | int | str] = {
        "query": normalized,
        "total_length": length,
        "entropy": shannon_entropy(normalized),
        "digit_ratio": digit_count / length,
        "label_count": len(labels),
        "max_label_length": max((len(label) for label in labels), default=0),
        "alphanumeric_ratio": alphanumeric_count / length,
    }
    for character in CHARACTERS:
        features[f"char_freq_{character}"] = character_counts[character] / length
    for known_type, column in zip(QUERY_TYPES, QUERY_TYPE_COLUMNS):
        features[column] = int(query_type == known_type)
    for known_family, column in zip(FAMILIES, FAMILY_COLUMNS):
        features[column] = int(family == known_family)
    return features


def encode_domain(domain: str, max_length: int = MAX_LENGTH) -> np.ndarray:
    """Tokeniza um domínio normalizado na ordem canônica do vocabulário."""
    normalized = normalize_domain(domain)[:max_length]
    encoded = np.full(max_length, TOKEN_TO_INDEX[PAD], dtype=np.int64)
    for column, character in enumerate(normalized):
        encoded[column] = TOKEN_TO_INDEX.get(character, TOKEN_TO_INDEX[UNK])
    return encoded


def transform_features(rows: list[dict[str, str]]) -> np.ndarray:
    """Converte linhas CSV em uma matriz na ordem canônica dos atributos.

    Falha explicitamente se alguma feature estiver ausente da linha; metadados
    nunca são derivados nem aceitos como entrada.
    """

    def value(row: dict[str, str], column: str) -> float:
        if column not in row:
            raise ValueError(f"Feature ausente na linha: {column}")
        return float(row[column])

    values = np.asarray(
        [[value(row, column) for column in FEATURE_COLUMNS] for row in rows],
        dtype=np.float32,
    )
    for index, column in enumerate(FEATURE_COLUMNS):
        if column in LOG_FEATURES:
            values[:, index] = np.log1p(values[:, index])
    return values
