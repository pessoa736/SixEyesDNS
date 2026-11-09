"""Alinha logs DNS aos rótulos do gerador e grava o dataset processado.

Cada rótulo confirmado vira exatamente uma linha, em ordem de ``sequence``.
Os logs (dnsmasq, BIND9 e Unbound) servem só de evidência de que o
servidor-alvo recebeu a consulta do gerador: a linha precisa ter o IP do
gerador, a mesma consulta normalizada, o mesmo tipo e um timestamp próximo ao
do rótulo. Linhas de outros clientes (como o resolvedor, que encaminha
consultas aos autoritativos), de outras execuções acumuladas no log ou
excedentes são ignoradas e apenas contadas em ``alignment.json``.

O gerador não grava rótulo de consulta que falhou, então lacunas em
``sequence`` são toleradas e reportadas; ``--strict-sequence`` as rejeita.
``sequence`` repetida ou timestamps decrescentes indicam execuções
concatenadas e sempre falham.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if __package__:
    from .features import extract_features
else:
    from features import extract_features


DEFAULT_CLIENT_IP = "172.30.0.6"
DEFAULT_TOLERANCE_SECONDS = 5.0
DEFAULT_MAX_MISSING_RATIO = 0.0
# dnsmasq e Unbound truncam o log ao segundo e o rótulo é gravado depois da
# resposta; a folga superior cobre apenas arredondamentos.
UPPER_MARGIN = timedelta(seconds=1)
REQUIRED_LABEL_COLUMNS = (
    "sequence",
    "timestamp",
    "query",
    "query_type",
    "family",
    "profile",
    "label",
    "seed",
    "server",
)
SERVER_SOURCES = {"bind9": "bind9", "dnsmasq": "dnsmasq", "resolver": "unbound"}
LOG_SOURCES = ("bind9", "dnsmasq", "unbound")
MAX_EXAMPLES = 5
MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

DNSMASQ_PATTERN = re.compile(
    r"^(?P<month>\w{3})\s+(?P<day>\d+)\s+(?P<clock>\d\d:\d\d:\d\d)\s+dnsmasq\[\d+\]:\s+"
    r"query\[(?P<qtype>[^]]+)\]\s+(?P<name>\S+)\s+from\s+(?P<client>\S+)"
)
BIND9_PATTERN = re.compile(
    r"^(?P<day>\d\d)-(?P<month>\w{3})-(?P<year>\d{4})\s+(?P<clock>\d\d:\d\d:\d\d)"
    r"(?:\.(?P<fraction>\d+))?\s+queries:.*?"
    r"client\s+(?:@\S+\s+)?(?P<client>[0-9A-Fa-f:.]+)#\d+\s+\(.*?\):\s+"
    r"query:\s+(?P<name>\S+)\s+IN\s+(?P<qtype>[A-Z0-9]+)\b"
)
# Só a linha de consulta; as de resposta têm campos depois de "IN".
UNBOUND_PATTERN = re.compile(
    r"^\[(?P<epoch>\d+)\]\s+unbound\[[^]]+\]\s+info:\s+(?P<client>[0-9A-Fa-f:.]+)\s+"
    r"(?P<name>\S+)\s+(?P<qtype>[A-Z0-9]+)\s+IN\s*$"
)

Window = tuple[datetime, datetime]


@dataclass(frozen=True, slots=True)
class LogEntry:
    """Consulta registrada por um servidor DNS."""

    source: str
    timestamp: datetime
    client: str
    query: str
    query_type: str


@dataclass(frozen=True, slots=True)
class Label:
    """Rótulo gravado pelo gerador após a resposta de uma consulta."""

    run: int
    sequence: int
    timestamp: datetime
    query: str
    query_type: str
    family: str
    profile: str
    label: str
    seed: str
    server: str

    @property
    def key(self) -> tuple[str, str]:
        return normalize_name(self.query), self.query_type.upper()

    @property
    def source(self) -> str:
        return SERVER_SOURCES[self.server]


@dataclass(frozen=True)
class LabelRun:
    """Arquivo de rótulos de uma única execução, ordenado por ``sequence``."""

    path: Path
    labels: list[Label]

    @property
    def first(self) -> datetime:
        return self.labels[0].timestamp

    @property
    def last(self) -> datetime:
        return self.labels[-1].timestamp

    @property
    def first_sequence(self) -> int:
        return self.labels[0].sequence

    @property
    def last_sequence(self) -> int:
        return self.labels[-1].sequence

    @property
    def sequence_gaps(self) -> int:
        """Números de sequence ausentes entre 0 e o último: consultas que falharam."""
        return self.last_sequence + 1 - len(self.labels)

    def window(self, tolerance: timedelta) -> Window:
        return self.first - tolerance, self.last + UPPER_MARGIN


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log",
        type=Path,
        nargs="+",
        required=True,
        help="logs do dnsmasq, BIND9 e/ou Unbound (o formato é detectado por linha)",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        nargs="+",
        required=True,
        help="um arquivo de rótulos por execução do gerador",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--client-ip",
        default=DEFAULT_CLIENT_IP,
        help="IP do gerador; só as linhas desse cliente servem de evidência",
    )
    parser.add_argument(
        "--tolerance-seconds",
        type=float,
        default=DEFAULT_TOLERANCE_SECONDS,
        help="antecedência máxima da linha de log em relação ao rótulo",
    )
    parser.add_argument(
        "--max-missing-ratio",
        type=float,
        default=DEFAULT_MAX_MISSING_RATIO,
        help="fração máxima de rótulos sem linha de log; por padrão qualquer falta falha",
    )
    parser.add_argument(
        "--strict-sequence",
        action="store_true",
        help="exige sequence contígua 0..N-1; por padrão as lacunas, que são consultas "
        "que falharam no gerador, são toleradas e reportadas",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="JSON do alinhamento (padrão: alignment.json ao lado do --output)",
    )
    return parser.parse_args()


def normalize_name(name: str) -> str:
    """Normaliza o nome para o casamento: minúsculas e sem ponto final."""
    return name.strip().rstrip(".").lower()


def parse_timestamp(value: str) -> datetime:
    """Interpreta um timestamp ISO 8601 e o converte para UTC (sem fuso = UTC)."""
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def resolve_year(
    month: int, day: int, clock: str, windows: Sequence[Window]
) -> datetime | None:
    """Infere o ano de uma linha do dnsmasq, que só registra mês, dia e hora.

    Usa o ano que coloca a linha dentro de alguma janela de execução, o que
    cobre a virada de ano. Se nenhum ano cabe, devolve um instante fora de
    todas as janelas.
    """
    hour, minute, second = (int(part) for part in clock.split(":"))
    years = sorted({bound.year for window in windows for bound in window})
    fallback = None
    for year in years:
        try:
            moment = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
        except ValueError:
            continue
        if any(start <= moment <= end for start, end in windows):
            return moment
        fallback = fallback or moment
    return fallback


def build_entry(source: str, moment: datetime, match: re.Match[str]) -> LogEntry:
    return LogEntry(
        source=source,
        timestamp=moment,
        client=match["client"],
        query=normalize_name(match["name"]),
        query_type=match["qtype"].upper(),
    )


def parse_log_line(line: str, windows: Sequence[Window]) -> LogEntry | None:
    """Reconhece a linha de consulta de um log dnsmasq, BIND9 ou Unbound.

    ``windows`` só é usado para inferir o ano das linhas do dnsmasq. Linhas de
    resposta do Unbound e demais mensagens devolvem None.
    """
    line = line.rstrip("\r\n")

    match = UNBOUND_PATTERN.match(line)
    if match:
        try:
            moment = datetime.fromtimestamp(int(match["epoch"]), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
        return build_entry("unbound", moment, match)

    match = BIND9_PATTERN.match(line)
    if match:
        month = MONTHS.get(match["month"])
        if month is None:
            return None
        hour, minute, second = (int(part) for part in match["clock"].split(":"))
        microsecond = int((match["fraction"] or "0")[:6].ljust(6, "0"))
        try:
            moment = datetime(
                int(match["year"]),
                month,
                int(match["day"]),
                hour,
                minute,
                second,
                microsecond,
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None
        return build_entry("bind9", moment, match)

    match = DNSMASQ_PATTERN.match(line)
    if match:
        month = MONTHS.get(match["month"])
        if month is None:
            return None
        moment = resolve_year(month, int(match["day"]), match["clock"], windows)
        if moment is None:
            return None
        return build_entry("dnsmasq", moment, match)

    return None


def read_log_entries(log_paths: Sequence[Path], windows: Sequence[Window]) -> list[LogEntry]:
    """Lê as consultas de todos os logs; o formato de cada linha é detectado."""
    entries = []
    for log_path in log_paths:
        with log_path.open(encoding="utf-8", errors="replace") as log_file:
            for line in log_file:
                entry = parse_log_line(line, windows)
                if entry:
                    entries.append(entry)
    return entries


def parse_label_row(path: Path, run: int, line_number: int, row: dict[str, str]) -> Label:
    values = {column: (row.get(column) or "").strip() for column in REQUIRED_LABEL_COLUMNS}
    empty = [column for column, value in values.items() if not value]
    if empty:
        raise ValueError(f"{path}: linha {line_number}: campos vazios: {', '.join(empty)}")
    try:
        sequence = int(values["sequence"])
    except ValueError as error:
        raise ValueError(
            f"{path}: linha {line_number}: sequence inválida: {values['sequence']!r}"
        ) from error
    if sequence < 0:
        raise ValueError(f"{path}: linha {line_number}: sequence negativa: {sequence}")
    try:
        timestamp = parse_timestamp(values["timestamp"])
    except ValueError as error:
        raise ValueError(
            f"{path}: linha {line_number}: timestamp inválido: {values['timestamp']!r}"
        ) from error
    if values["server"] not in SERVER_SOURCES:
        raise ValueError(
            f"{path}: linha {line_number}: servidor desconhecido {values['server']!r}; "
            f"esperado um de {sorted(SERVER_SOURCES)}"
        )
    return Label(
        run=run,
        sequence=sequence,
        timestamp=timestamp,
        query=values["query"],
        query_type=values["query_type"],
        family=values["family"],
        profile=values["profile"],
        label=values["label"],
        seed=values["seed"],
        server=values["server"],
    )


def validate_run(path: Path, labels: Sequence[Label], strict_sequence: bool = False) -> list[Label]:
    """Garante que o arquivo é uma única execução coerente; devolve por sequence.

    ``sequence`` repetida e timestamps decrescentes indicam execuções
    concatenadas e sempre falham. Lacunas em ``sequence`` são consultas que
    falharam no gerador: só falham com ``strict_sequence``.
    """
    if not labels:
        raise ValueError(f"{path}: arquivo de rótulos sem registros")

    counts = Counter(label.sequence for label in labels)
    repeated = sorted(sequence for sequence, count in counts.items() if count > 1)
    if repeated:
        raise ValueError(
            f"{path}: sequence repetida em {len(repeated)} valor(es), "
            f"ex.: {repeated[:MAX_EXAMPLES]}; o arquivo parece conter execuções concatenadas"
        )

    ordered = sorted(labels, key=lambda label: label.sequence)
    if strict_sequence:
        for position, label in enumerate(ordered):
            if label.sequence != position:
                raise ValueError(
                    f"{path}: sequence não contígua: esperado {position}, encontrado "
                    f"{label.sequence}; --strict-sequence exige 0..N-1 e o gerador não "
                    "grava rótulo de consulta que falhou"
                )

    for previous, current in zip(ordered, ordered[1:]):
        if current.timestamp < previous.timestamp:
            raise ValueError(
                f"{path}: timestamp decrescente entre sequence {previous.sequence} e "
                f"{current.sequence}; o arquivo parece conter execuções concatenadas"
            )
    return ordered


def read_label_run(path: Path, run: int, strict_sequence: bool = False) -> LabelRun:
    """Lê e valida um arquivo de rótulos, que deve conter uma única execução."""
    with path.open(newline="", encoding="utf-8") as labels_file:
        reader = csv.DictReader(labels_file)
        header = reader.fieldnames or []
        missing = [column for column in REQUIRED_LABEL_COLUMNS if column not in header]
        if missing:
            raise ValueError(
                f"{path}: colunas obrigatórias ausentes nos rótulos: {', '.join(missing)}"
            )
        labels = [parse_label_row(path, run, reader.line_num, row) for row in reader]
    return LabelRun(path=path, labels=validate_run(path, labels, strict_sequence))


def check_label_conflicts(runs: Sequence[LabelRun]) -> None:
    """Falha se a mesma consulta tiver rótulos conflitantes entre os arquivos."""
    signatures: dict[tuple[str, str], set[tuple[str, str, str]]] = defaultdict(set)
    for run in runs:
        for label in run.labels:
            signatures[label.key].add((label.label, label.family, label.profile))

    conflicts = [
        f"({query!r}, {query_type}): {sorted(options)}"
        for (query, query_type), options in sorted(signatures.items())
        if len(options) > 1
    ]
    if conflicts:
        raise ValueError(
            f"Casamento ambíguo: {len(conflicts)} consulta(s) com rótulos conflitantes "
            f"(label, family, profile); exemplos: {'; '.join(conflicts[:MAX_EXAMPLES])}"
        )


def check_runs_disjoint(runs: Sequence[LabelRun]) -> None:
    """Falha se duas execuções se sobrepõem no tempo (o gerador é único)."""
    ordered = sorted(runs, key=lambda run: run.first)
    for previous, current in zip(ordered, ordered[1:]):
        if current.first <= previous.last:
            raise ValueError(
                f"As execuções de {previous.path} e {current.path} se sobrepõem no tempo; "
                "use um arquivo de rótulos por execução, sem repetir arquivos"
            )


def align_labels(
    labels: Sequence[Label],
    entries: Sequence[LogEntry],
    client_ip: str,
    tolerance: timedelta,
) -> tuple[list[Label], list[Label], set[int]]:
    """Casa cada rótulo com uma linha do log do servidor-alvo.

    O casamento é guloso em ordem temporal por chave (fonte, consulta, tipo):
    cada rótulo consome a linha mais antiga ainda livre dentro de
    ``[timestamp - tolerância, timestamp + 1 s]``. Devolve os rótulos
    confirmados, os sem evidência e os índices das linhas consumidas.
    """
    candidates: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for index, entry in enumerate(entries):
        if entry.client == client_ip:
            candidates[(entry.source, entry.query, entry.query_type)].append(index)
    for indexes in candidates.values():
        indexes.sort(key=lambda index: entries[index].timestamp)

    cursors: dict[tuple[str, str, str], int] = defaultdict(int)
    confirmed: list[Label] = []
    missing: list[Label] = []
    used: set[int] = set()
    for label in sorted(labels, key=lambda item: (item.timestamp, item.run, item.sequence)):
        key = (label.source, *label.key)
        indexes = candidates.get(key, [])
        position = cursors[key]
        earliest = label.timestamp - tolerance
        latest = label.timestamp + UPPER_MARGIN
        while position < len(indexes) and entries[indexes[position]].timestamp < earliest:
            position += 1
        if position < len(indexes) and entries[indexes[position]].timestamp <= latest:
            used.add(indexes[position])
            confirmed.append(label)
            position += 1
        else:
            missing.append(label)
        cursors[key] = position
    return confirmed, missing, used


def count_by_source(entries: Sequence[LogEntry]) -> dict[str, int]:
    counts = Counter(entry.source for entry in entries)
    return {source: counts[source] for source in LOG_SOURCES}


def count_by_server(labels: Sequence[Label]) -> dict[str, int]:
    counts = Counter(label.server for label in labels)
    return {server: counts[server] for server in sorted(SERVER_SOURCES)}


def classify_log_lines(
    entries: Sequence[LogEntry], used: set[int], client_ip: str, windows: Sequence[Window]
) -> dict[str, Any]:
    """Conta as linhas de log por fonte e pelo motivo de não terem sido usadas."""
    others: list[LogEntry] = []
    outside: list[LogEntry] = []
    extra: list[LogEntry] = []
    for index, entry in enumerate(entries):
        if entry.client != client_ip:
            others.append(entry)
        elif index in used:
            continue
        elif any(start <= entry.timestamp <= end for start, end in windows):
            extra.append(entry)
        else:
            outside.append(entry)
    return {
        "parsed": count_by_source(entries),
        "other_clients": count_by_source(others),
        "other_clients_by_ip": dict(sorted(Counter(entry.client for entry in others).items())),
        "outside_window": count_by_source(outside),
        "extra_in_window": count_by_source(extra),
    }


def describe_runs(
    runs: Sequence[LabelRun], windows: Sequence[Window], confirmed: Sequence[Label]
) -> list[dict[str, Any]]:
    """Resume cada execução: totais, sequência, casados por servidor e janela de tempo."""
    reports = []
    for index, (run, (start, end)) in enumerate(zip(runs, windows)):
        run_confirmed = [label for label in confirmed if label.run == index]
        reports.append(
            {
                "labels": str(run.path),
                "labels_total": len(run.labels),
                "rows_written": len(run_confirmed),
                "labels_without_log": len(run.labels) - len(run_confirmed),
                "first_sequence": run.first_sequence,
                "last_sequence": run.last_sequence,
                "sequence_gaps": run.sequence_gaps,
                "matched_by_server": count_by_server(run_confirmed),
                "first_label": run.first.isoformat(),
                "last_label": run.last.isoformat(),
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
            }
        )
    return reports


def describe_missing(
    missing: Sequence[Label],
    total: int,
    parsed: dict[str, int],
    max_missing_ratio: float,
    client_ip: str,
    tolerance_seconds: float,
) -> str:
    """Monta a mensagem de falha para rótulos sem evidência no log."""
    by_server = {server: count for server, count in count_by_server(missing).items() if count}
    unread = [
        SERVER_SOURCES[server]
        for server in by_server
        if not parsed[SERVER_SOURCES[server]]
    ]
    examples = "; ".join(
        f"sequence={label.sequence} servidor={label.server} consulta={label.query} "
        f"tipo={label.query_type} em {label.timestamp.isoformat()}"
        for label in missing[:MAX_EXAMPLES]
    )
    message = (
        f"{len(missing)} de {total} rótulo(s) ({len(missing) / total:.2%}) sem linha no log do "
        f"servidor-alvo, acima do máximo permitido ({max_missing_ratio:.2%}). "
        f"Por servidor: {by_server}. Exemplos: {examples}. "
    )
    if unread:
        message += f"Nenhuma consulta foi lida dos logs {unread}; informe-os em --log. "
    return message + (
        f"Confira se os logs cobrem a execução e estão em UTC, se --client-ip ({client_ip}) "
        f"é o IP do gerador e se --tolerance-seconds ({tolerance_seconds}) basta; "
        "--max-missing-ratio tolera perdas conhecidas."
    )


def build_row(label: Label) -> dict[str, float | int | str]:
    row = extract_features(label.query, query_type=label.query_type, family=label.family)
    row.update(
        {
            "query_type": label.query_type,
            "family": label.family,
            "profile": label.profile,
            "label": label.label,
            "seed": label.seed,
        }
    )
    return row


def process(
    log_paths: Sequence[Path],
    labels_paths: Sequence[Path],
    output_path: Path,
    report_path: Path | None = None,
    client_ip: str = DEFAULT_CLIENT_IP,
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
    max_missing_ratio: float = DEFAULT_MAX_MISSING_RATIO,
    strict_sequence: bool = False,
) -> dict[str, Any]:
    """Grava o dataset com uma linha por rótulo confirmado e devolve o relatório."""
    if tolerance_seconds < 0:
        raise ValueError("--tolerance-seconds não pode ser negativo")
    if not 0 <= max_missing_ratio <= 1:
        raise ValueError("--max-missing-ratio precisa estar entre 0 e 1")
    report_path = report_path or output_path.parent / "alignment.json"
    tolerance = timedelta(seconds=tolerance_seconds)

    runs = [
        read_label_run(path, index, strict_sequence) for index, path in enumerate(labels_paths)
    ]
    check_label_conflicts(runs)
    check_runs_disjoint(runs)
    windows = [run.window(tolerance) for run in runs]

    entries = read_log_entries(log_paths, windows)
    labels = [label for run in runs for label in run.labels]
    confirmed, missing, used = align_labels(labels, entries, client_ip, tolerance)
    if len(missing) > max_missing_ratio * len(labels):
        parsed = count_by_source(entries)
        raise ValueError(
            describe_missing(
                missing, len(labels), parsed, max_missing_ratio, client_ip, tolerance_seconds
            )
        )
    if not confirmed:
        raise ValueError("Nenhum rótulo foi confirmado pelo log DNS")

    confirmed_keys = {(label.run, label.sequence) for label in confirmed}
    rows = [
        build_row(label)
        for run in runs
        for label in run.labels
        if (label.run, label.sequence) in confirmed_keys
    ]
    report = {
        "client_ip": client_ip,
        "tolerance_seconds": tolerance_seconds,
        "max_missing_ratio": max_missing_ratio,
        "strict_sequence": strict_sequence,
        "labels_total": len(labels),
        "rows_written": len(confirmed),
        "labels_without_log": len(missing),
        "sequence_gaps": sum(run.sequence_gaps for run in runs),
        "matched_by_server": count_by_server(confirmed),
        "runs": describe_runs(runs, windows, confirmed),
        "logs": [str(path) for path in log_paths],
        "log_lines": classify_log_lines(entries, used, client_ip, windows),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print_summary(report, output_path, report_path)
    return report


def print_summary(report: dict[str, Any], output_path: Path, report_path: Path) -> None:
    lines = report["log_lines"]
    matched = ", ".join(
        f"{server}={count}" for server, count in report["matched_by_server"].items()
    )
    print(
        f"Rótulos: {report['labels_total']} | linhas escritas: {report['rows_written']} | "
        f"rótulos sem log: {report['labels_without_log']}"
    )
    for run in report["runs"]:
        print(
            f"Sequence {run['first_sequence']}..{run['last_sequence']} ({run['labels']}): "
            f"lacunas={run['sequence_gaps']} (consultas que falharam no gerador)"
        )
    print(f"Casados por servidor: {matched}")
    print(
        "Linhas de log ignoradas: "
        f"outros clientes={sum(lines['other_clients'].values())}, "
        f"fora da janela={sum(lines['outside_window'].values())}, "
        f"extras na janela={sum(lines['extra_in_window'].values())}"
    )
    print(f"Dataset salvo em: {output_path}")
    print(f"Relatório de alinhamento salvo em: {report_path}")


def main() -> None:
    args = parse_args()
    try:
        process(
            args.log,
            args.labels,
            args.output,
            report_path=args.report,
            client_ip=args.client_ip,
            tolerance_seconds=args.tolerance_seconds,
            max_missing_ratio=args.max_missing_ratio,
            strict_sequence=args.strict_sequence,
        )
    except (ValueError, OSError) as error:
        raise SystemExit(f"Erro: {error}") from error


if __name__ == "__main__":
    main()
