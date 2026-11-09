"""Testes do perfil normal_tranco do gerador, com o dnspython substituído por stubs."""

import csv
import importlib.util
import sys
import types
from pathlib import Path

import pytest

GENERATOR_DIR = Path(__file__).resolve().parents[1] / "docker" / "generator"
SAMPLE_DOMAINS = [f"exemplo-{number:02d}.com" for number in range(1, 13)]
RNG_COLUMNS = ("sequence", "query_type", "server", "label", "seed")


def load_generator(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, tranco: Path):
    """Importa gerador_queries.py sem rede: dns.* vira stub e a consulta é simulada."""
    dns = types.ModuleType("dns")
    for part in ("exception", "message", "query", "rcode"):
        stub = types.ModuleType(f"dns.{part}")
        setattr(dns, part, stub)
        monkeypatch.setitem(sys.modules, f"dns.{part}", stub)
    dns.exception.DNSException = type("DNSException", (Exception,), {})
    monkeypatch.setitem(sys.modules, "dns", dns)
    monkeypatch.syspath_prepend(str(GENERATOR_DIR))

    environment = {
        "QUERY_COUNT": "400",
        "SEED": "42",
        "ANOMALY_RATE": "0.5",
        "DNS_TARGETS": "127.0.0.1:70,127.0.0.2:20,127.0.0.3:10",
        "LABELS_PATH": str(tmp_path / f"{name}-labels.csv"),
        "DASHBOARD_PATH": str(tmp_path / f"{name}-dashboard.json"),
        "TRANCO_PATH": str(tranco),
        "TRANCO_LIMIT": "50",
        "TRANCO_RATE": "0.5",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    spec = importlib.util.spec_from_file_location(
        f"generator_{name}", GENERATOR_DIR / "gerador_queries.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.send_query = lambda domain, query_type, address: "NOERROR"
    module.time = types.SimpleNamespace(sleep=lambda seconds: None)
    return module


def run_generator(monkeypatch, tmp_path: Path, name: str, tranco: Path) -> list[dict[str, str]]:
    module = load_generator(monkeypatch, tmp_path, name, tranco)
    module.main()
    with module.LABELS_PATH.open(newline="", encoding="utf-8") as labels_file:
        return list(csv.DictReader(labels_file))


def write_ranking(path: Path) -> Path:
    lines = [f"{rank},{domain}" for rank, domain in enumerate(SAMPLE_DOMAINS, start=1)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_tranco_profile_does_not_change_the_rng_driven_columns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ranking = write_ranking(tmp_path / "tranco_top.csv")
    baseline = run_generator(monkeypatch, tmp_path, "baseline", tmp_path / "ausente.csv")
    with_tranco = run_generator(monkeypatch, tmp_path, "tranco", ranking)

    assert len(baseline) == len(with_tranco) == 400
    replaced = 0
    for before, after in zip(baseline, with_tranco):
        assert [before[column] for column in RNG_COLUMNS] == [
            after[column] for column in RNG_COLUMNS
        ]
        if before["query"] == after["query"]:
            assert before["profile"] == after["profile"]
            assert before["service"] == after["service"]
            continue
        replaced += 1
        assert before["label"] == "normal"
        assert before["query_type"] != "PTR"
        assert (after["profile"], after["family"], after["label"]) == (
            "normal_tranco",
            "normal",
            "normal",
        )
        assert after["query"].removesuffix(".test") in SAMPLE_DOMAINS
    normal_non_ptr = sum(
        row["label"] == "normal" and row["query_type"] != "PTR" for row in baseline
    )
    assert 0 < replaced < normal_non_ptr


def test_tranco_profile_is_deterministic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ranking = write_ranking(tmp_path / "tranco_top.csv")
    first = run_generator(monkeypatch, tmp_path, "first", ranking)
    second = run_generator(monkeypatch, tmp_path, "second", ranking)
    assert [row["query"] for row in first] == [row["query"] for row in second]


def test_absent_ranking_keeps_the_generator_silent_about_tranco(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = run_generator(monkeypatch, tmp_path, "baseline", tmp_path / "ausente.csv")
    assert "tranco" not in capsys.readouterr().out
    assert all(row["profile"] != "normal_tranco" for row in rows)


def test_ranking_without_valid_domains_only_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ranking = tmp_path / "tranco_top.csv"
    ranking.write_text("rank,domain\nsem,formato\n", encoding="utf-8")
    rows = run_generator(monkeypatch, tmp_path, "invalid", ranking)
    assert "tranco_aviso=" in capsys.readouterr().out
    assert all(row["profile"] != "normal_tranco" for row in rows)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
