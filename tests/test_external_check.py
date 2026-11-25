"""Testes do teste de estresse com nomes reais (``source.external_check``)."""

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

from source import external_check
from source.external_check import (
    FIELDS,
    MODES,
    lab_zones,
    read_ranking,
    run_check,
    swap_tld,
)
from source.scoring import read_rows

GENERATOR_MODULE = (
    Path(__file__).resolve().parents[1] / "docker" / "generator" / "external_domains.py"
)

MESSY_RANKING = [
    "2,b.com",
    "1,A.com.",
    "3,a.com",
    "x,sem-rank.com",
    "4,under_score.com",
    f"5,{'a' * 49}.com",
    "6,ok-name.net",
    "7",
    "8,-leading.com",
    "9,xn--bcher-kva.example",
]


def write_ranking(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def generator_loader():
    spec = importlib.util.spec_from_file_location("external_domains", GENERATOR_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_external_domains


def test_read_ranking_orders_by_rank_dedupes_and_drops_invalid(tmp_path: Path) -> None:
    ranking = write_ranking(tmp_path / "top.csv", MESSY_RANKING)
    assert read_ranking(ranking, 100) == [
        "a.com",
        "b.com",
        "ok-name.net",
        "xn--bcher-kva.example",
    ]
    assert read_ranking(ranking, 2) == ["a.com", "b.com"]


def test_read_ranking_skip_selects_the_names_after_the_first_ones(tmp_path: Path) -> None:
    ranking = write_ranking(
        tmp_path / "top.csv", [f"{rank},site{rank}.com" for rank in range(1, 11)]
    )
    assert read_ranking(ranking, 3, skip=4) == ["site5.com", "site6.com", "site7.com"]
    assert read_ranking(ranking, 100, skip=8) == ["site9.com", "site10.com"]
    # skip=N sobre o ranking equivale ao que o gerador (limit=N) NÃO usa.
    used = set(generator_loader()(ranking, 4))
    assert not used & set(read_ranking(ranking, 100, skip=4))


def test_read_ranking_rejects_a_bad_limit_and_an_empty_ranking(tmp_path: Path) -> None:
    ranking = write_ranking(tmp_path / "top.csv", MESSY_RANKING)
    with pytest.raises(ValueError, match="inteiro positivo"):
        read_ranking(ranking, 0)
    with pytest.raises(ValueError, match="negativo"):
        read_ranking(ranking, 5, skip=-1)
    with pytest.raises(ValueError, match="depois de pular"):
        read_ranking(ranking, 5, skip=99)
    empty = write_ranking(tmp_path / "vazio.csv", ["x,nada.com", "sem virgula"])
    with pytest.raises(ValueError, match="Nenhum domínio válido"):
        read_ranking(empty, 10)


def test_read_ranking_applies_the_same_rule_as_the_generator(tmp_path: Path) -> None:
    ranking = write_ranking(tmp_path / "top.csv", MESSY_RANKING)
    load_external_domains = generator_loader()
    for limit in (1, 3, 100):
        assert read_ranking(ranking, limit) == load_external_domains(ranking, limit)


def test_lab_zones_come_from_normals_skip_reverse_names_and_are_deterministic() -> None:
    rows = [
        {"label": "normal", "query": "a.api.orbita"},
        {"label": "normal", "query": "b.web.orbita"},
        {"label": "normal", "query": "c.mail.lumen"},
        {"label": "normal", "query": "102.0.30.172.in-addr.arpa"},
        {"label": "normal", "query": "semponto"},
        {"label": "suspeita", "query": "xyz.tunnel"},
    ]
    assert lab_zones(rows) == ["orbita", "lumen"]
    assert lab_zones(rows, count=1) == ["orbita"]
    assert lab_zones(rows) == lab_zones(list(reversed(rows)))
    with pytest.raises(ValueError, match="não tem domínios normais"):
        lab_zones([{"label": "suspeita", "query": "xyz.tunnel"}])


def test_swap_tld_replaces_only_the_last_label_and_cycles_the_zones() -> None:
    assert swap_tld(["hulu.com", "bbc.co.uk", "a.b.net"], ["atlas", "brisa"]) == [
        "hulu.atlas",
        "bbc.co.brisa",
        "a.b.atlas",
    ]


def test_check_reports_three_sets_with_consistent_counts(
    trained_models: dict[str, Path], minimal_splits: Path
) -> None:
    ranking = [f"site{index}.com" for index in range(1, 31)]
    table = run_check(trained_models["lexical"], "lexical", ranking, minimal_splits)

    assert [row["set"] for row in table] == ["ranking", "ranking_lab_zone", "test_normals"]
    test = read_rows(minimal_splits / "test.csv")
    unique_normals = len({row["query"] for row in test if row["label"] == "normal"})
    assert table[0]["rows"] == table[1]["rows"] == len(ranking)
    assert table[2]["rows"] == unique_normals
    for row in table:
        assert row["system"] == "lexical"
        assert 0 <= row["flagged"] <= row["rows"]
        assert row["rate"] == pytest.approx(row["flagged"] / row["rows"])
    # O limiar é o do checkpoint, o mesmo nos três conjuntos.
    assert len({row["threshold"] for row in table}) == 1


def test_cli_writes_only_aggregates_and_never_the_ranking_names(
    trained_models: dict[str, Path],
    minimal_splits: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = [f"unicorn{index}.example" for index in range(1, 21)]
    ranking = write_ranking(
        tmp_path / "top.csv", [f"{rank},{name}" for rank, name in enumerate(names, 1)]
    )
    output = tmp_path / "saida" / "external_check.csv"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "external_check",
            "--ranking", str(ranking),
            "--limit", "10",
            "--splits-dir", str(minimal_splits),
            "--models-dir", str(trained_models["lexical"].parent),
            "--output", str(output),
        ],
    )
    external_check.main()

    text = output.read_text(encoding="utf-8")
    assert "unicorn" not in text and "example" not in text
    with output.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert tuple(rows[0]) == FIELDS
    assert len(rows) == len(MODES) * 3
    assert {row["rows"] for row in rows if row["set"] == "ranking"} == {"10"}


def test_cli_explains_how_to_get_a_missing_ranking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys, "argv", ["external_check", "--ranking", str(tmp_path / "ausente.csv")]
    )
    with pytest.raises(SystemExit, match="data/external/README.md"):
        external_check.main()
