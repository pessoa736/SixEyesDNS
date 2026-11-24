"""Testes do replay offline com os três formatos de log e checkpoints mínimos."""

import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from source.demo import format_text_report, read_replay, run_replay, score_queries
from source.scoring import load_checkpoint

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_LOG = REPO_ROOT / "scripts" / "demo" / "replay-example.txt"
DNSMASQ_NORMAL = (
    "Nov 20 10:00:00 dnsmasq[41]: query[A] Staging.Api.Orbita.test. "
    "from 172.30.0.6"
)
DNSMASQ_ANOMALY = (
    "Nov 20 10:00:01 dnsmasq[41]: query[TXT] aaj4pccnvdeac.tunnel.test "
    "from 172.30.0.6"
)
BIND9_LINE = (
    "20-Nov-2026 10:00:02.125 queries: client @0x7f8e631e60e0 "
    "172.30.0.6#53000 (web.atlas.test): query: web.atlas.test IN A + (172.30.0.3)"
)
UNBOUND_LINE = "[1795168803] unbound[1:0] info: 172.30.0.6 docs.brisa.test. A IN"
UNBOUND_RESPONSE = (
    "[1795168803] unbound[1:0] info: 172.30.0.6 docs.brisa.test. A IN "
    "NOERROR 0.000000 1 91"
)


def write_log(path: Path, lines: list[str] | None = None) -> Path:
    content = lines or [DNSMASQ_NORMAL, DNSMASQ_ANOMALY]
    path.write_text("\n".join(content) + "\n", encoding="utf-8")
    return path


def test_read_replay_detects_formats_and_ignores_noise(tmp_path: Path) -> None:
    path = write_log(
        tmp_path / "mixed.txt",
        [
            "Nov 20 09:59:59 dnsmasq[41]: started, version 2.90 cachesize 150",
            DNSMASQ_NORMAL,
            BIND9_LINE,
            UNBOUND_LINE,
            UNBOUND_RESPONSE,
        ],
    )
    queries = read_replay(path)
    assert [query.entry.source for query in queries] == ["dnsmasq", "bind9", "unbound"]
    assert [query.line_number for query in queries] == [2, 3, 4]
    assert [query.features["query"] for query in queries] == [
        "staging.api.orbita",
        "web.atlas",
        "docs.brisa",
    ]
    assert [query.entry.query_type for query in queries] == ["A", "A", "A"]
    assert "label" not in queries[0].features
    assert "client" not in queries[0].features


def test_read_replay_honors_limit_and_rejects_empty_input(tmp_path: Path) -> None:
    path = write_log(tmp_path / "limited.txt", [DNSMASQ_NORMAL, BIND9_LINE])
    assert len(read_replay(path, limit=1)) == 1
    with pytest.raises(ValueError, match="inteiro positivo"):
        read_replay(path, limit=0)
    empty = write_log(tmp_path / "empty.txt", ["not a DNS query"])
    with pytest.raises(ValueError, match="Nenhuma consulta DNS reconhecida"):
        read_replay(empty)


def test_versioned_example_is_offline_and_covers_all_sources() -> None:
    queries = read_replay(EXAMPLE_LOG)
    assert len(queries) == 9
    assert {query.entry.source for query in queries} == {"dnsmasq", "bind9", "unbound"}
    assert all(str(query.features["query"]).endswith(".test") is False for query in queries)
    with (REPO_ROOT / "data" / "processed" / "splits" / "test.csv").open(
        newline="", encoding="utf-8"
    ) as test_file:
        test_domains = {row["query"] for row in csv.DictReader(test_file)}
    assert {query.features["query"] for query in queries} <= test_domains


@pytest.mark.parametrize("mode", ["lexical", "semantic", "hybrid"])
def test_scores_and_explanations_use_the_shared_pipeline(
    mode: str, trained_models: dict[str, Path], tmp_path: Path
) -> None:
    path = write_log(tmp_path / f"{mode}.txt")
    queries = read_replay(path)
    loaded = load_checkpoint(trained_models[mode])
    results = score_queries(loaded, queries)
    expected = loaded.score([query.features for query in queries])
    threshold = float(loaded.checkpoint["threshold"])

    assert len(results) == len(queries) == 2
    for index, result in enumerate(results):
        assert result["score"] == pytest.approx(expected[index], rel=1e-5, abs=1e-6)
        assert result["suspicious"] == (result["score"] > threshold)
        assert result["classification"] == (
            "suspeita" if result["suspicious"] else "normal"
        )
        if mode == "semantic":
            assert result["character_errors"] == []
            assert len(result["top_attributes"]) == 3
        else:
            assert len(result["character_errors"]) == len(result["analyzed_query"])
        if mode == "lexical":
            assert result["top_attributes"] == []


def test_text_report_shows_threshold_score_and_character_map(
    trained_models: dict[str, Path], tmp_path: Path
) -> None:
    path = write_log(tmp_path / "report.txt")
    report = run_replay(trained_models["hybrid"], path)
    text = format_text_report(report)
    assert report["query_count"] == 2
    assert report["suspicious_count"] + report["normal_count"] == 2
    assert "Limiar P99 da validação" in text
    assert "Mapa de erro por caractere" in text
    assert "erro lexical=" in text and "erro numérico=" in text
    assert "Resumo: 2 consultas" in text
    single = run_replay(trained_models["hybrid"], path, limit=1)
    assert "Resumo: 1 consulta |" in format_text_report(single)


def run_cli(arguments: list[object], as_script: bool = False) -> subprocess.CompletedProcess:
    entry = (
        [str(REPO_ROOT / "source" / "demo.py")]
        if as_script
        else ["-m", "source.demo"]
    )
    return subprocess.run(
        [sys.executable, *entry, *map(str, arguments)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("as_script", [False, True], ids=["module", "script"])
def test_cli_emits_complete_json(
    as_script: bool, trained_models: dict[str, Path], tmp_path: Path
) -> None:
    path = write_log(tmp_path / "cli.txt")
    result = run_cli(
        [
            "--replay",
            path,
            "--model-dir",
            trained_models["hybrid"],
            "--limit",
            1,
            "--json",
        ],
        as_script=as_script,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["query_count"] == 1
    assert report["limit"] == 1
    assert len(report["results"][0]["character_errors"]) == len(
        report["results"][0]["analyzed_query"]
    )


def test_cli_reports_an_empty_log_without_traceback(tmp_path: Path) -> None:
    path = write_log(tmp_path / "noise.txt", ["not a DNS query"])
    result = run_cli(["--replay", path, "--model-dir", "unused"])
    assert result.returncode != 0
    assert "Erro:" in result.stderr
    assert "Nenhuma consulta DNS reconhecida" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash indisponível")
def test_demo_wrapper_uses_the_versioned_example_and_json(
    trained_models: dict[str, Path]
) -> None:
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "demo" / "demo.sh"), "--json"],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHON_BIN": sys.executable,
            "MODEL_DIR": str(trained_models["hybrid"]),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["query_count"] == 9
    assert report["replay"] == "scripts/demo/replay-example.txt"
    assert {item["source"] for item in report["results"]} == {
        "dnsmasq",
        "bind9",
        "unbound",
    }
