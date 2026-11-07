"""Extração e transformação dos atributos lexicais e do tipo DNS."""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np


CHARACTERS = tuple("abcdefghijklmnopqrstuvwxyz0123456789")
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
FEATURE_COLUMNS = (
    SCALAR_FEATURES
    + tuple(f"char_freq_{character}" for character in CHARACTERS)
    + QUERY_TYPE_COLUMNS
)
DATASET_CATEGORICAL_COLUMNS = QUERY_TYPE_COLUMNS + FAMILY_COLUMNS
LOG_FEATURES = {"total_length", "label_count", "max_label_length"}
VALID_DOMAIN = re.compile(r"^[a-z0-9._-]+$")


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


def transform_features(rows: list[dict[str, str]]) -> np.ndarray:
    """Converte linhas CSV em uma matriz na ordem canônica dos atributos."""

    def value(row: dict[str, str], column: str) -> float:
        if column in row:
            return float(row[column])
        if column in QUERY_TYPE_COLUMNS:
            return float(row.get("query_type") == column.removeprefix("is_"))
        if column in FAMILY_COLUMNS:
            family = column.removeprefix("is_family_")
            return float(row.get("family") == family)
        return float(row[column])

    values = np.asarray(
        [[value(row, column) for column in FEATURE_COLUMNS] for row in rows],
        dtype=np.float32,
    )
    for index, column in enumerate(FEATURE_COLUMNS):
        if column in LOG_FEATURES:
            values[:, index] = np.log1p(values[:, index])
    return values
