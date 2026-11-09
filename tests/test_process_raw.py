"""Testes do alinhamento entre logs DNS e rótulos do gerador, com dados sintéticos."""

import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from source.features import extract_features
from source.process_raw import LogEntry, parse_log_line, process

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = "172.30.0.6"
RESOLVER = "172.30.0.4"
DHCP = "172.30.0.5"
START = datetime(2031, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
WINDOW = (START - timedelta(minutes=5), START + timedelta(minutes=5))
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
LABEL_COLUMNS = (
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
METADATA_COLUMNS = ["query_type", "family", "profile", "label", "seed"]
LOG_FILES = {"dnsmasq": "dnsmasq.log", "bind9": "queries.log", "resolver": "unbound.log"}


def make_label(
    sequence: int,
    query: str,
    server: str = "dnsmasq",
    query_type: str = "A",
    label: str = "normal",
    family: str = "normal",
    profile: str = "normal",
    start: datetime = START,
) -> dict[str, str]:
    """Rótulo sintético gravado 0,5 s depois do segundo cheio, como o gerador faz."""
    moment = start + timedelta(seconds=sequence, milliseconds=500)
    return {
        "sequence": str(sequence),
        "timestamp": moment.isoformat(),
        "query": query,
        "query_type": query_type,
        "service": "web",
        "family": family,
        "profile": profile,
        "label": label,
        "seed": "42",
        "server": server,
    }


def base_labels(start: datetime = START) -> list[dict[str, str]]:
    """Seis rótulos nos três servidores, com uma consulta repetida e nomes mistos."""
    return [
        make_label(0, "web.atlas.test", "resolver", start=start),
        make_label(1, "dev.api.atlas.test", "dnsmasq", "AAAA", start=start),
        make_label(2, "Abc123.tunnel.test", "bind9", "TXT", "suspeita", "base32", "base32", start),
        make_label(3, "web.atlas.test", "resolver", start=start),
        make_label(
            4, "100.0.30.172.in-addr.arpa", "bind9", "PTR", profile="normal_reverse", start=start
        ),
        make_label(5, "node-001.web.atlas.test", "dnsmasq", profile="normal_hard", start=start),
    ]


def dnsmasq_line(moment: datetime, query: str, query_type: str, client: str) -> str:
    month = MONTH_NAMES[moment.month - 1]
    return (
        f"{month} {moment.day:2d} {moment:%H:%M:%S} dnsmasq[1]: "
        f"query[{query_type}] {query} from {client}"
    )


def bind9_line(moment: datetime, query: str, query_type: str, client: str) -> str:
    month = MONTH_NAMES[moment.month - 1]
    stamp = f"{moment.day:02d}-{month}-{moment.year} {moment:%H:%M:%S}"
    return (
        f"{stamp}.{moment.microsecond // 1000:03d} "
        f"queries: client @0x7f8e631e60e0 {client}#40586 ({query}): "
        f"query: {query} IN {query_type} + (172.30.0.3)"
    )


def unbound_lines(moment: datetime, query: str, query_type: str, client: str) -> list[str]:
    epoch = int(moment.timestamp())
    return [
        f"[{epoch}] unbound[1:0] info: {client} {query}. {query_type} IN",
        f"[{epoch}] unbound[1:0] info: {client} {query}. {query_type} IN NOERROR 0.000000 1 91",
    ]


def evidence(
    label: dict[str, str], client: str = GENERATOR, shift: float = 0.0
) -> list[tuple[str, str]]:
    """Linhas que o servidor-alvo registraria 0,2 s antes do rótulo."""
    moment = datetime.fromisoformat(label["timestamp"]) + timedelta(seconds=shift - 0.2)
    query, query_type, server = label["query"], label["query_type"], label["server"]
    if server == "dnsmasq":
        return [(server, dnsmasq_line(moment, query, query_type, client))]
    if server == "bind9":
        return [(server, bind9_line(moment, query, query_type, client))]
    return [(server, line) for line in unbound_lines(moment, query, query_type, client)]


def write_labels(path: Path, labels: list[dict[str, str]], columns=LABEL_COLUMNS) -> Path:
    with path.open("w", newline="", encoding="utf-8") as labels_file:
        writer = csv.DictWriter(labels_file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(labels)
    return path


def write_logs(directory: Path, lines: list[tuple[str, str]]) -> list[Path]:
    """Grava um log por servidor, com mensagens de inicialização que devem ser ignoradas."""
    noise = {
        "dnsmasq": ["Jun 15 11:00:00 dnsmasq[1]: started, version 2.90 cachesize 150"],
        "bind9": ["15-Jun-2031 11:00:00.100 zoneload: zone test/IN: loaded serial 2026110801"],
        "resolver": [f"[{int(START.timestamp()) - 3600}] unbound[1:0] info: start of service"],
    }
    paths = []
    for server, name in LOG_FILES.items():
        content = noise[server] + [line for owner, line in lines if owner == server]
        path = directory / name
        path.write_text("\n".join(content) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def build_inputs(
    directory: Path,
    labels: list[dict[str, str]],
    extra_lines: list[tuple[str, str]] | None = None,
    skip_sequences: set[int] | None = None,
) -> tuple[list[Path], Path]:
    skipped = skip_sequences or set()
    lines = [
        pair
        for label in labels
        if int(label["sequence"]) not in skipped
        for pair in evidence(label)
    ]
    log_paths = write_logs(directory, lines + (extra_lines or []))
    return log_paths, write_labels(directory / "query_labels.csv", labels)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as dataset_file:
        return list(csv.DictReader(dataset_file))


def run_alignment(tmp_path: Path, labels: list[dict[str, str]], **kwargs):
    log_paths, labels_path = build_inputs(
        tmp_path,
        labels,
        extra_lines=kwargs.pop("extra_lines", None),
        skip_sequences=kwargs.pop("skip_sequences", None),
    )
    output = tmp_path / "processed" / "dataset.csv"
    report = process(log_paths, [labels_path], output, **kwargs)
    return report, output


def test_parse_dnsmasq_line_normalizes_name_and_infers_year() -> None:
    entry = parse_log_line(
        "Jun 15 12:00:03 dnsmasq[1]: query[AAAA] Dev.Api.Atlas.test. from 172.30.0.6", [WINDOW]
    )
    assert entry == LogEntry(
        source="dnsmasq",
        timestamp=datetime(2031, 6, 15, 12, 0, 3, tzinfo=timezone.utc),
        client=GENERATOR,
        query="dev.api.atlas.test",
        query_type="AAAA",
    )


def test_parse_bind9_line_keeps_milliseconds_and_client() -> None:
    line = bind9_line(
        datetime(2031, 6, 15, 12, 0, 3, 333000, tzinfo=timezone.utc),
        "Staging.API.atlas.test.",
        "TXT",
        GENERATOR,
    )
    entry = parse_log_line(line, [])
    assert entry == LogEntry(
        source="bind9",
        timestamp=datetime(2031, 6, 15, 12, 0, 3, 333000, tzinfo=timezone.utc),
        client=GENERATOR,
        query="staging.api.atlas.test",
        query_type="TXT",
    )


def test_parse_bind9_line_without_client_pointer() -> None:
    line = (
        "15-Jun-2031 12:00:03.333 queries: client 172.30.0.6#40586 (x.atlas.test): "
        "query: x.atlas.test IN A +"
    )
    entry = parse_log_line(line, [])
    assert entry is not None
    assert (entry.client, entry.query, entry.query_type) == (GENERATOR, "x.atlas.test", "A")


def test_parse_unbound_accepts_only_the_query_line() -> None:
    query, response = unbound_lines(
        datetime(2031, 6, 15, 12, 0, 3, tzinfo=timezone.utc), "Web.Atlas.test", "A", GENERATOR
    )
    entry = parse_log_line(query, [])
    assert entry == LogEntry(
        source="unbound",
        timestamp=datetime(2031, 6, 15, 12, 0, 3, tzinfo=timezone.utc),
        client=GENERATOR,
        query="web.atlas.test",
        query_type="A",
    )
    assert parse_log_line(response, []) is None


@pytest.mark.parametrize(
    "line",
    [
        "Jun 15 12:00:03 dnsmasq[1]: started, version 2.90 cachesize 150",
        "Jun 15 12:00:03 dnsmasq[1]: reply web.atlas.test is 172.30.0.11",
        "15-Jun-2031 12:00:03.100 zoneload: zone test/IN: loaded serial 2026110801",
        "[1938000000] unbound[1:0] notice: init module 0: validator",
        "[1938000000] unbound[1:0] info: server stats for thread 0: 10 queries",
        "",
    ],
)
def test_parse_ignores_lines_that_are_not_queries(line: str) -> None:
    assert parse_log_line(line, [WINDOW]) is None


def test_dnsmasq_year_follows_the_window_across_new_year() -> None:
    windows = [
        (
            datetime(2026, 12, 31, 23, 59, 50, tzinfo=timezone.utc),
            datetime(2027, 1, 1, 0, 0, 10, tzinfo=timezone.utc),
        )
    ]
    before = parse_log_line(
        "Dec 31 23:59:55 dnsmasq[1]: query[A] a.atlas.test from 172.30.0.6", windows
    )
    after = parse_log_line(
        "Jan  1 00:00:03 dnsmasq[1]: query[A] a.atlas.test from 172.30.0.6", windows
    )
    assert before.timestamp == datetime(2026, 12, 31, 23, 59, 55, tzinfo=timezone.utc)
    assert after.timestamp == datetime(2027, 1, 1, 0, 0, 3, tzinfo=timezone.utc)


def test_dnsmasq_line_outside_every_window_stays_outside() -> None:
    entry = parse_log_line(
        "Jan  3 08:00:00 dnsmasq[1]: query[A] a.atlas.test from 172.30.0.6", [WINDOW]
    )
    assert entry is not None
    assert not WINDOW[0] <= entry.timestamp <= WINDOW[1]


def test_dnsmasq_leap_day_requires_a_leap_year() -> None:
    line = "Feb 29 12:00:00 dnsmasq[1]: query[A] a.atlas.test from 172.30.0.6"
    leap = [
        (
            datetime(2028, 2, 29, 11, 0, 0, tzinfo=timezone.utc),
            datetime(2028, 2, 29, 13, 0, 0, tzinfo=timezone.utc),
        )
    ]
    common = [
        (
            datetime(2027, 3, 1, 11, 0, 0, tzinfo=timezone.utc),
            datetime(2027, 3, 1, 13, 0, 0, tzinfo=timezone.utc),
        )
    ]
    assert parse_log_line(line, leap).timestamp == datetime(2028, 2, 29, 12, tzinfo=timezone.utc)
    assert parse_log_line(line, common) is None


def test_each_label_produces_one_row_in_sequence_order(tmp_path: Path) -> None:
    report, output = run_alignment(tmp_path, base_labels())
    rows = read_rows(output)
    assert [row["query"] for row in rows] == [
        "web.atlas",
        "dev.api.atlas",
        "abc123.tunnel",
        "web.atlas",
        "100.0.30.172.in-addr.arpa",
        "node-001.web.atlas",
    ]
    assert [row["profile"] for row in rows] == [
        "normal",
        "normal",
        "base32",
        "normal",
        "normal_reverse",
        "normal_hard",
    ]
    assert report["labels_total"] == 6
    assert report["rows_written"] == 6
    assert report["labels_without_log"] == 0
    assert report["matched_by_server"] == {"bind9": 2, "dnsmasq": 2, "resolver": 2}


def test_output_schema_is_features_plus_metadata(tmp_path: Path) -> None:
    _, output = run_alignment(tmp_path, base_labels())
    rows = read_rows(output)
    reference_header = list(extract_features("web.atlas.test", query_type="A", family="normal"))
    expected = reference_header + METADATA_COLUMNS
    assert list(rows[0]) == expected
    anomaly = rows[2]
    assert (
        anomaly["query_type"],
        anomaly["family"],
        anomaly["profile"],
        anomaly["label"],
        anomaly["seed"],
    ) == ("TXT", "base32", "base32", "suspeita", "42")
    reference = extract_features("Abc123.tunnel.test", query_type="TXT", family="base32")
    assert float(anomaly["entropy"]) == pytest.approx(reference["entropy"])
    assert anomaly["is_TXT"] == "1"
    assert anomaly["is_family_base32"] == "1"


def test_rows_follow_sequence_even_if_the_file_is_shuffled(tmp_path: Path) -> None:
    labels = base_labels()
    shuffled = [labels[index] for index in (3, 0, 5, 1, 4, 2)]
    _, output = run_alignment(tmp_path, shuffled)
    assert [row["query"] for row in read_rows(output)] == [
        extract_features(label["query"])["query"] for label in labels
    ]


def test_log_format_is_detected_per_line_in_a_single_file(tmp_path: Path) -> None:
    labels = base_labels()
    log_paths, labels_path = build_inputs(tmp_path, labels)
    mixed = tmp_path / "mixed.log"
    mixed.write_text(
        "".join(path.read_text(encoding="utf-8") for path in log_paths), encoding="utf-8"
    )
    report = process([mixed], [labels_path], tmp_path / "out" / "dataset.csv")
    assert report["rows_written"] == 6


def test_lines_from_other_runs_in_the_log_are_ignored_and_counted(tmp_path: Path) -> None:
    labels = base_labels()
    previous_run = [pair for label in labels for pair in evidence(label, shift=-3600)]
    report, output = run_alignment(tmp_path, labels, extra_lines=previous_run)
    assert len(read_rows(output)) == 6
    lines = report["log_lines"]
    assert lines["parsed"] == {"bind9": 4, "dnsmasq": 4, "unbound": 4}
    assert lines["outside_window"] == {"bind9": 2, "dnsmasq": 2, "unbound": 2}
    assert lines["extra_in_window"] == {"bind9": 0, "dnsmasq": 0, "unbound": 0}


def test_lines_from_other_clients_are_counted_and_never_used(tmp_path: Path) -> None:
    labels = base_labels()
    forwarded = [pair for label in labels for pair in evidence(label, client=RESOLVER)]
    dhcp = [("resolver", unbound_lines(START, "web.atlas.test", "A", DHCP)[0])]
    report, output = run_alignment(tmp_path, labels, extra_lines=forwarded + dhcp)
    assert len(read_rows(output)) == 6
    lines = report["log_lines"]
    assert lines["other_clients"] == {"bind9": 2, "dnsmasq": 2, "unbound": 3}
    assert lines["other_clients_by_ip"] == {DHCP: 1, RESOLVER: 6}
    assert lines["extra_in_window"] == {"bind9": 0, "dnsmasq": 0, "unbound": 0}


def test_other_client_lines_are_not_evidence(tmp_path: Path) -> None:
    labels = base_labels()
    forwarded_only = evidence(labels[1], client=RESOLVER)
    log_paths, labels_path = build_inputs(
        tmp_path, labels, extra_lines=forwarded_only, skip_sequences={1}
    )
    with pytest.raises(ValueError, match="1 de 6 rótulo"):
        process(log_paths, [labels_path], tmp_path / "out" / "dataset.csv")


def test_client_ip_option_selects_the_generator_lines(tmp_path: Path) -> None:
    labels = base_labels()
    lines = [pair for label in labels for pair in evidence(label, client="10.9.9.9")]
    log_paths = write_logs(tmp_path, lines)
    labels_path = write_labels(tmp_path / "query_labels.csv", labels)
    output = tmp_path / "out" / "dataset.csv"
    with pytest.raises(ValueError, match="6 de 6 rótulo"):
        process(log_paths, [labels_path], output)
    report = process(log_paths, [labels_path], output, client_ip="10.9.9.9")
    assert report["client_ip"] == "10.9.9.9"
    assert report["rows_written"] == 6


def test_extra_lines_inside_the_window_are_only_counted(tmp_path: Path) -> None:
    labels = base_labels()
    duplicate = evidence(labels[1])
    unlabeled = evidence(make_label(2, "failed.atlas.test", "bind9"))
    report, output = run_alignment(tmp_path, labels, extra_lines=duplicate + unlabeled)
    assert len(read_rows(output)) == 6
    assert report["log_lines"]["extra_in_window"] == {"bind9": 1, "dnsmasq": 1, "unbound": 0}
    assert report["log_lines"]["outside_window"] == {"bind9": 0, "dnsmasq": 0, "unbound": 0}


def test_one_log_line_confirms_only_one_label(tmp_path: Path) -> None:
    labels = [
        make_label(0, "web.atlas.test", "resolver"),
        make_label(1, "web.atlas.test", "resolver"),
    ]
    log_paths, labels_path = build_inputs(tmp_path, labels, skip_sequences={1})
    with pytest.raises(ValueError, match="1 de 2 rótulo"):
        process(log_paths, [labels_path], tmp_path / "out" / "dataset.csv")


@pytest.mark.parametrize("strict_sequence", [False, True], ids=["tolerant", "strict"])
def test_concatenated_labels_with_repeated_sequence_fail(
    tmp_path: Path, strict_sequence: bool
) -> None:
    concatenated = base_labels() + base_labels(start=START + timedelta(hours=1))
    log_paths, labels_path = build_inputs(tmp_path, concatenated)
    with pytest.raises(ValueError, match="sequence repetida.*concatenadas"):
        process(
            log_paths,
            [labels_path],
            tmp_path / "out" / "dataset.csv",
            strict_sequence=strict_sequence,
        )


@pytest.mark.parametrize("strict_sequence", [False, True], ids=["tolerant", "strict"])
def test_labels_with_decreasing_timestamps_fail(tmp_path: Path, strict_sequence: bool) -> None:
    labels = base_labels()
    later = START + timedelta(hours=1)
    for index in range(3, 6):
        labels[index]["timestamp"] = (later - timedelta(seconds=index)).isoformat()
    log_paths, labels_path = build_inputs(tmp_path, labels)
    with pytest.raises(ValueError, match="timestamp decrescente"):
        process(
            log_paths,
            [labels_path],
            tmp_path / "out" / "dataset.csv",
            strict_sequence=strict_sequence,
        )


def test_negative_sequence_fails(tmp_path: Path) -> None:
    labels = base_labels()
    labels[0]["sequence"] = "-1"
    log_paths, labels_path = build_inputs(tmp_path, labels)
    with pytest.raises(ValueError, match="linha 2: sequence negativa: -1"):
        process(log_paths, [labels_path], tmp_path / "out" / "dataset.csv")


def test_sequence_gap_is_tolerated_and_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    labels = [label for label in base_labels() if label["sequence"] != "3"]
    report, output = run_alignment(tmp_path, labels)
    assert [row["query"] for row in read_rows(output)] == [
        "web.atlas",
        "dev.api.atlas",
        "abc123.tunnel",
        "100.0.30.172.in-addr.arpa",
        "node-001.web.atlas",
    ]
    (run,) = report["runs"]
    assert (run["first_sequence"], run["last_sequence"], run["sequence_gaps"]) == (0, 5, 1)
    assert report["sequence_gaps"] == 1
    assert report["strict_sequence"] is False
    assert (report["labels_total"], report["rows_written"]) == (5, 5)
    assert "lacunas=1 (consultas que falharam no gerador)" in capsys.readouterr().out


def test_gaps_at_the_start_of_the_sequence_are_counted(tmp_path: Path) -> None:
    labels = base_labels()[2:]
    report, _ = run_alignment(tmp_path, labels)
    (run,) = report["runs"]
    assert (run["first_sequence"], run["last_sequence"], run["sequence_gaps"]) == (2, 5, 2)


def test_strict_sequence_rejects_gaps(tmp_path: Path) -> None:
    labels = [label for label in base_labels() if label["sequence"] != "3"]
    log_paths, labels_path = build_inputs(tmp_path, labels)
    output = tmp_path / "out" / "dataset.csv"
    with pytest.raises(ValueError, match="sequence não contígua: esperado 3, encontrado 4"):
        process(log_paths, [labels_path], output, strict_sequence=True)
    assert not output.exists()

    leading_gap = write_labels(tmp_path / "leading.csv", base_labels()[2:])
    with pytest.raises(ValueError, match="esperado 0, encontrado 2"):
        process(log_paths, [leading_gap], output, strict_sequence=True)


def test_strict_sequence_accepts_a_contiguous_file(tmp_path: Path) -> None:
    report, _ = run_alignment(tmp_path, base_labels(), strict_sequence=True)
    assert report["strict_sequence"] is True
    assert report["sequence_gaps"] == 0
    assert report["rows_written"] == 6


def test_log_line_of_a_failed_query_is_only_counted_as_extra(tmp_path: Path) -> None:
    labels = base_labels()
    failed = labels.pop(1)
    report, output = run_alignment(tmp_path, labels, extra_lines=evidence(failed))
    assert len(read_rows(output)) == 5
    assert report["sequence_gaps"] == 1
    assert report["log_lines"]["extra_in_window"] == {"bind9": 0, "dnsmasq": 1, "unbound": 0}


@pytest.mark.parametrize(
    "conflict",
    [
        {"label": "suspeita"},
        {"profile": "normal_hard"},
        {"family": "base32"},
    ],
)
def test_conflicting_labels_for_the_same_query_fail(
    tmp_path: Path, conflict: dict[str, str]
) -> None:
    labels = base_labels()
    labels.append({**make_label(6, "web.atlas.test", "resolver"), **conflict})
    log_paths, labels_path = build_inputs(tmp_path, labels)
    with pytest.raises(ValueError, match="Casamento ambíguo.*web.atlas.test"):
        process(log_paths, [labels_path], tmp_path / "out" / "dataset.csv")


def test_same_query_with_another_type_is_not_a_conflict(tmp_path: Path) -> None:
    labels = base_labels()
    labels.append(make_label(6, "web.atlas.test", "resolver", "TXT"))
    report, _ = run_alignment(tmp_path, labels)
    assert report["rows_written"] == 7


def test_label_without_log_evidence_fails(tmp_path: Path) -> None:
    log_paths, labels_path = build_inputs(tmp_path, base_labels(), skip_sequences={4})
    output = tmp_path / "out" / "dataset.csv"
    with pytest.raises(ValueError, match="1 de 6 rótulo.*sequence=4 servidor=bind9"):
        process(log_paths, [labels_path], output)
    assert not output.exists()


def test_missing_labels_are_tolerated_up_to_max_missing_ratio(tmp_path: Path) -> None:
    labels = base_labels()
    log_paths, labels_path = build_inputs(tmp_path, labels, skip_sequences={4})
    output = tmp_path / "out" / "dataset.csv"
    with pytest.raises(ValueError, match="acima do máximo permitido"):
        process(log_paths, [labels_path], output, max_missing_ratio=0.1)
    report = process(log_paths, [labels_path], output, max_missing_ratio=0.2)
    assert report["rows_written"] == 5
    assert report["labels_without_log"] == 1
    assert report["matched_by_server"] == {"bind9": 1, "dnsmasq": 2, "resolver": 2}
    assert "100.0.30.172.in-addr.arpa" not in {row["query"] for row in read_rows(output)}


def test_missing_log_file_is_reported_in_the_error(tmp_path: Path) -> None:
    labels = base_labels()
    log_paths, labels_path = build_inputs(tmp_path, labels)
    only_dnsmasq = [path for path in log_paths if path.name == LOG_FILES["dnsmasq"]]
    expected_message = r"Nenhuma consulta foi lida dos logs \['bind9', 'unbound'\]"
    with pytest.raises(ValueError, match=expected_message):
        process(only_dnsmasq, [labels_path], tmp_path / "out" / "dataset.csv")


def test_tolerance_limits_how_early_a_log_line_may_be(tmp_path: Path) -> None:
    label = make_label(0, "web.atlas.test", "dnsmasq")
    early = evidence(label, shift=-8)
    log_paths, labels_path = build_inputs(tmp_path, [label], extra_lines=early, skip_sequences={0})
    output = tmp_path / "out" / "dataset.csv"
    with pytest.raises(ValueError, match="1 de 1 rótulo"):
        process(log_paths, [labels_path], output)
    assert process(log_paths, [labels_path], output, tolerance_seconds=10)["rows_written"] == 1


def test_log_line_after_the_label_is_not_evidence(tmp_path: Path) -> None:
    label = make_label(0, "web.atlas.test", "dnsmasq")
    late = evidence(label, shift=3)
    log_paths, labels_path = build_inputs(tmp_path, [label], extra_lines=late, skip_sequences={0})
    with pytest.raises(ValueError, match="1 de 1 rótulo"):
        process(log_paths, [labels_path], tmp_path / "out" / "dataset.csv", tolerance_seconds=60)


def test_missing_required_column_fails(tmp_path: Path) -> None:
    labels = base_labels()
    log_paths, _ = build_inputs(tmp_path, labels)
    columns = [column for column in LABEL_COLUMNS if column not in {"server", "profile"}]
    labels_path = write_labels(tmp_path / "old_labels.csv", labels, columns)
    with pytest.raises(ValueError, match="colunas obrigatórias ausentes.*profile, server"):
        process(log_paths, [labels_path], tmp_path / "out" / "dataset.csv")


def test_unknown_server_fails(tmp_path: Path) -> None:
    labels = base_labels()
    labels[1]["server"] = "powerdns"
    log_paths, labels_path = build_inputs(tmp_path, labels)
    with pytest.raises(ValueError, match="servidor desconhecido 'powerdns'"):
        process(log_paths, [labels_path], tmp_path / "out" / "dataset.csv")


def test_empty_labels_file_fails(tmp_path: Path) -> None:
    log_paths, labels_path = build_inputs(tmp_path, [])
    with pytest.raises(ValueError, match="sem registros"):
        process(log_paths, [labels_path], tmp_path / "out" / "dataset.csv")


def test_invalid_options_fail(tmp_path: Path) -> None:
    log_paths, labels_path = build_inputs(tmp_path, base_labels())
    output = tmp_path / "out" / "dataset.csv"
    with pytest.raises(ValueError, match="entre 0 e 1"):
        process(log_paths, [labels_path], output, max_missing_ratio=1.5)
    with pytest.raises(ValueError, match="negativo"):
        process(log_paths, [labels_path], output, tolerance_seconds=-1)


def test_each_labels_file_is_validated_as_its_own_run(tmp_path: Path) -> None:
    first = base_labels()
    second = base_labels(start=START + timedelta(hours=1))
    first_path = write_labels(tmp_path / "first.csv", first)
    second_path = write_labels(tmp_path / "second.csv", second)
    lines = [pair for label in first + second for pair in evidence(label)]
    log_paths = write_logs(tmp_path, lines)
    output = tmp_path / "out" / "dataset.csv"
    report = process(log_paths, [first_path, second_path], output)
    assert report["rows_written"] == 12
    assert [run["rows_written"] for run in report["runs"]] == [6, 6]
    assert report["runs"][1]["first_label"] == second[0]["timestamp"]
    assert report["log_lines"]["outside_window"] == {"bind9": 0, "dnsmasq": 0, "unbound": 0}
    assert len(read_rows(output)) == 12


def test_sequence_gaps_are_reported_per_run(tmp_path: Path) -> None:
    first = base_labels()
    second = [
        label for label in base_labels(start=START + timedelta(hours=1)) if label["sequence"] != "4"
    ]
    first_path = write_labels(tmp_path / "first.csv", first)
    second_path = write_labels(tmp_path / "second.csv", second)
    lines = [pair for label in first + second for pair in evidence(label)]
    report = process(
        write_logs(tmp_path, lines), [first_path, second_path], tmp_path / "out" / "dataset.csv"
    )
    assert [run["sequence_gaps"] for run in report["runs"]] == [0, 1]
    assert [(run["first_sequence"], run["last_sequence"]) for run in report["runs"]] == [
        (0, 5),
        (0, 5),
    ]
    assert report["sequence_gaps"] == 1


def test_overlapping_runs_fail(tmp_path: Path) -> None:
    log_paths, labels_path = build_inputs(tmp_path, base_labels())
    with pytest.raises(ValueError, match="se sobrepõem no tempo"):
        process(log_paths, [labels_path, labels_path], tmp_path / "out" / "dataset.csv")


def test_alignment_handles_new_year_rollover(tmp_path: Path) -> None:
    start = datetime(2026, 12, 31, 23, 59, 58, tzinfo=timezone.utc)
    labels = [
        make_label(index, f"node-{index:03d}.web.atlas.test", start=start) for index in range(5)
    ]
    report, _ = run_alignment(tmp_path, labels)
    assert report["rows_written"] == 5
    assert report["log_lines"]["outside_window"] == {"bind9": 0, "dnsmasq": 0, "unbound": 0}


def test_report_has_the_expected_fields(tmp_path: Path) -> None:
    labels = base_labels()
    report_path = tmp_path / "reports" / "custom.json"
    report, output = run_alignment(tmp_path, labels, report_path=report_path)
    assert not (output.parent / "alignment.json").exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved == report
    assert saved["client_ip"] == GENERATOR
    assert saved["tolerance_seconds"] == 5.0
    assert saved["strict_sequence"] is False
    assert saved["sequence_gaps"] == 0
    first = datetime.fromisoformat(labels[0]["timestamp"])
    last = datetime.fromisoformat(labels[-1]["timestamp"])
    (run,) = saved["runs"]
    assert (run["first_sequence"], run["last_sequence"], run["sequence_gaps"]) == (0, 5, 0)
    assert run["window_start"] == (first - timedelta(seconds=5)).isoformat()
    assert run["window_end"] == (last + timedelta(seconds=1)).isoformat()
    assert saved["log_lines"]["parsed"] == {"bind9": 2, "dnsmasq": 2, "unbound": 2}
    assert set(saved["log_lines"]) == {
        "parsed",
        "other_clients",
        "other_clients_by_ip",
        "outside_window",
        "extra_in_window",
    }


def test_report_defaults_to_alignment_json_next_to_the_output(tmp_path: Path) -> None:
    report, output = run_alignment(tmp_path, base_labels())
    assert json.loads((output.parent / "alignment.json").read_text(encoding="utf-8")) == report


def run_cli(arguments: list[object], as_script: bool = False) -> subprocess.CompletedProcess:
    entry = (
        [str(REPO_ROOT / "source" / "process_raw.py")]
        if as_script
        else ["-m", "source.process_raw"]
    )
    return subprocess.run(
        [sys.executable, *entry, *map(str, arguments)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("as_script", [False, True], ids=["module", "script"])
def test_cli_writes_dataset_and_default_report(tmp_path: Path, as_script: bool) -> None:
    log_paths, labels_path = build_inputs(tmp_path, base_labels())
    output = tmp_path / "out" / "dataset.csv"
    result = run_cli(
        ["--log", *log_paths, "--labels", labels_path, "--output", output], as_script=as_script
    )
    assert result.returncode == 0, result.stderr
    assert "linhas escritas: 6" in result.stdout
    assert len(read_rows(output)) == 6
    saved = json.loads((output.parent / "alignment.json").read_text(encoding="utf-8"))
    assert saved["rows_written"] == 6


def test_cli_fails_with_clear_message_and_nonzero_exit(tmp_path: Path) -> None:
    log_paths, labels_path = build_inputs(tmp_path, base_labels(), skip_sequences={1})
    output = tmp_path / "out" / "dataset.csv"
    arguments = ["--log", *log_paths, "--labels", labels_path, "--output", output]
    result = run_cli(arguments)
    assert result.returncode != 0
    assert "Erro:" in result.stderr
    assert "sem linha no log do servidor-alvo" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()

    tolerant = run_cli([*arguments, "--max-missing-ratio", "0.2"])
    assert tolerant.returncode == 0, tolerant.stderr
    assert len(read_rows(output)) == 5


def test_cli_tolerates_sequence_gaps_unless_strict(tmp_path: Path) -> None:
    labels = [label for label in base_labels() if label["sequence"] != "3"]
    log_paths, labels_path = build_inputs(tmp_path, labels)
    output = tmp_path / "out" / "dataset.csv"
    arguments = ["--log", *log_paths, "--labels", labels_path, "--output", output]

    strict = run_cli([*arguments, "--strict-sequence"])
    assert strict.returncode != 0
    assert "Erro:" in strict.stderr
    assert "sequence não contígua" in strict.stderr
    assert "Traceback" not in strict.stderr
    assert not output.exists()

    tolerant = run_cli(arguments)
    assert tolerant.returncode == 0, tolerant.stderr
    assert "Sequence 0..5" in tolerant.stdout
    assert "lacunas=1 (consultas que falharam no gerador)" in tolerant.stdout
    saved = json.loads((output.parent / "alignment.json").read_text(encoding="utf-8"))
    assert (saved["sequence_gaps"], saved["strict_sequence"]) == (1, False)
    assert len(read_rows(output)) == 5


def test_cli_accepts_report_client_and_tolerance_options(tmp_path: Path) -> None:
    labels = base_labels()
    lines = [pair for label in labels for pair in evidence(label, client="10.9.9.9", shift=-7)]
    log_paths = write_logs(tmp_path, lines)
    labels_path = write_labels(tmp_path / "query_labels.csv", labels)
    output = tmp_path / "out" / "dataset.csv"
    report_path = tmp_path / "reports" / "alignment.json"
    result = run_cli(
        [
            "--log", *log_paths,
            "--labels", labels_path,
            "--output", output,
            "--report", report_path,
            "--client-ip", "10.9.9.9",
            "--tolerance-seconds", "10",
        ]
    )
    assert result.returncode == 0, result.stderr
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["client_ip"] == "10.9.9.9"
    assert saved["tolerance_seconds"] == 10.0
    assert not (output.parent / "alignment.json").exists()


def build_script_inputs(tmp_path: Path) -> tuple[Path, Path]:
    normals = [make_label(index, f"node-{index:03d}.web.atlas.test") for index in range(40)]
    anomalies = [
        make_label(
            40 + index,
            f"{index:02d}x{'abcdefghij'[index % 10]}k{index * 7:03d}q.tunnel.test",
            "dnsmasq",
            "TXT",
            "suspeita",
            "base32",
            "base32",
        )
        for index in range(40)
    ]
    log_paths, labels_path = build_inputs(tmp_path, normals + anomalies)
    return log_paths[0], labels_path


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash indisponível")
def test_process_data_script_aligns_then_splits(tmp_path: Path) -> None:
    dnsmasq_log, labels_path = build_script_inputs(tmp_path)
    output = tmp_path / "processed" / "dataset.csv"
    splits = tmp_path / "processed" / "splits"
    result = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts" / "data" / "process-data.sh"),
            str(dnsmasq_log),
            str(labels_path),
            str(output),
            str(splits),
        ],
        env={**os.environ, "PYTHON_BIN": sys.executable, "SEED": "42"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((output.parent / "alignment.json").read_text(encoding="utf-8"))
    assert report["rows_written"] == 80
    assert (splits / "summary.json").exists()
    split_files = {path.name for path in splits.glob("*.csv")}
    assert split_files == {"train.csv", "validation.csv", "test.csv"}


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash indisponível")
def test_process_data_script_stops_when_alignment_fails(tmp_path: Path) -> None:
    labels = [make_label(0, "web.atlas.test", "resolver")]
    log_paths, labels_path = build_inputs(tmp_path, labels)
    dnsmasq_log = next(path for path in log_paths if path.name == LOG_FILES["dnsmasq"])
    splits = tmp_path / "processed" / "splits"
    result = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "scripts" / "data" / "process-data.sh"),
            str(dnsmasq_log),
            str(labels_path),
            str(tmp_path / "processed" / "dataset.csv"),
            str(splits),
        ],
        env={**os.environ, "PYTHON_BIN": sys.executable},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "sem linha no log do servidor-alvo" in result.stderr
    assert not splits.exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
