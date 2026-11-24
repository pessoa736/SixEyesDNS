"""Testes do controle do atalho do sufixo ``.tunnel``."""

from pathlib import Path

import pytest

from source.scoring import read_rows
from source.suffix_control import (
    normal_suffixes,
    run_control,
    swap_suffix,
)


def test_swap_keeps_only_the_payload_and_uses_the_new_suffix() -> None:
    assert swap_suffix("aaj4pccnvdeac.tunnel", "api.orbita") == "aaj4pccnvdeac.api.orbita"
    # low_entropy: o serviço entre o payload e .tunnel também sai.
    assert swap_suffix("safesafe.auth.tunnel", "api.orbita") == "safesafe.api.orbita"
    with pytest.raises(ValueError, match="não termina em .tunnel"):
        swap_suffix("staging.api.orbita", "api.orbita")


def test_normal_suffixes_come_only_from_normals_and_are_deterministic() -> None:
    rows = [
        {"label": "normal", "query": "a.api.orbita"},
        {"label": "normal", "query": "b.api.orbita"},
        {"label": "normal", "query": "c.mail.lumen"},
        {"label": "normal", "query": "102.0.30.172.in-addr.arpa"},
        {"label": "suspeita", "query": "xyz.tunnel"},
    ]
    assert normal_suffixes(rows) == ["api.orbita", "mail.lumen"]
    assert normal_suffixes(rows) == normal_suffixes(list(reversed(rows)))
    with pytest.raises(ValueError, match="não tem domínios normais"):
        normal_suffixes([{"label": "suspeita", "query": "xyz.tunnel"}])


def test_control_reports_all_four_experiments_with_consistent_counts(
    trained_models: dict[str, Path], minimal_splits: Path
) -> None:
    table = run_control(trained_models["lexical"], "lexical", minimal_splits)
    test = read_rows(minimal_splits / "test.csv")
    suspects = sum(row["label"] != "normal" for row in test)
    normals = len({row["query"] for row in test if row["label"] == "normal"})

    summary = {
        (row["experiment"], row["group"]): row for row in table
    }
    assert {experiment for experiment, _ in summary} == {
        "suspects_original",
        "suspects_normal_suffix",
        "normals_original",
        "normals_plus_tunnel",
    }
    assert summary[("suspects_original", "all")]["rows"] == suspects
    assert summary[("suspects_normal_suffix", "all")]["rows"] == suspects
    assert summary[("normals_original", "all")]["rows"] == normals
    assert summary[("normals_plus_tunnel", "all")]["rows"] == normals
    for row in table:
        rate, flagged, total = float(row["rate"]), int(row["flagged"]), int(row["rows"])
        assert 0.0 <= rate <= 1.0
        assert flagged == round(rate * total)
    families = {group for _, group in summary if group not in {"all", "normal"}}
    assert families == {"base32", "hex", "base64"}
