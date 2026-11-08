"""Testes de determinismo, vocabulário e ausência de metadados nas features."""

import numpy as np
import pytest

from source.features import (
    FEATURE_COLUMNS,
    METADATA_COLUMNS,
    TOKEN_TO_INDEX,
    VOCABULARY,
    encode_domain,
    extract_features,
    normalize_domain,
    transform_features,
)


def test_feature_count_is_42() -> None:
    assert len(FEATURE_COLUMNS) == 42


def test_no_metadata_in_features() -> None:
    assert not set(FEATURE_COLUMNS) & set(METADATA_COLUMNS)
    for column in FEATURE_COLUMNS:
        assert not column.startswith("is_"), f"indicador categórico: {column}"


def test_normalize_domain_removes_lab_suffix() -> None:
    assert normalize_domain("Web.Atlas.TEST.") == "web.atlas"
    assert normalize_domain("web.atlas.test") == "web.atlas"


def test_extract_features_is_deterministic() -> None:
    first = extract_features("node-042.web.atlas.test", query_type="A", family="normal")
    second = extract_features("node-042.web.atlas.test", query_type="A", family="normal")
    assert first == second


def test_encode_domain_is_deterministic_and_padded() -> None:
    first = encode_domain("web.atlas.test")
    second = encode_domain("web.atlas.test")
    assert np.array_equal(first, second)
    assert first.dtype == np.int64
    assert first[0] == TOKEN_TO_INDEX["w"]
    assert first[-1] == TOKEN_TO_INDEX["<PAD>"]
    assert len(VOCABULARY) == 41


def test_transform_features_rejects_missing_column() -> None:
    with pytest.raises(ValueError, match="Feature ausente"):
        transform_features([{"query": "web.atlas", "label": "normal"}])


def test_transform_features_ignores_metadata_columns() -> None:
    row = extract_features("web.atlas.test", query_type="TXT", family="normal")
    row["label"] = "suspeita"
    row["seed"] = "42"
    matrix = transform_features([row])
    assert matrix.shape == (1, 42)
    reference = extract_features("web.atlas.test", query_type="A", family="normal")
    assert np.allclose(matrix[0], transform_features([reference])[0])
