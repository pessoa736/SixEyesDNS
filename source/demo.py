"""Reproduz logs DNS e classifica cada consulta com um autoencoder treinado.

O replay não usa rótulos, não recalibra o limiar e não depende do Docker. O
pré-processamento, o scaler, o score e o limiar são exatamente os do treino.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

if __package__:
    from .features import FEATURE_COLUMNS, MAX_LENGTH, extract_features
    from .process_raw import LogEntry, normalize_name, parse_log_line
    from .scoring import (
        LoadedModel,
        aggregate_reconstruction_errors,
        encode_domains,
        load_checkpoint,
        numeric_tensor,
        reconstruction_errors,
    )
else:
    from features import FEATURE_COLUMNS, MAX_LENGTH, extract_features
    from process_raw import LogEntry, normalize_name, parse_log_line
    from scoring import (
        LoadedModel,
        aggregate_reconstruction_errors,
        encode_domains,
        load_checkpoint,
        numeric_tensor,
        reconstruction_errors,
    )


# O dnsmasq não grava o ano. O replay preserva a ordem do arquivo e não usa o
# timestamp para decidir nada; 2000 é bissexto e aceita inclusive 29 de fevereiro.
REPLAY_WINDOWS = (
    (
        datetime(2000, 1, 1, tzinfo=timezone.utc),
        datetime(2000, 12, 31, 23, 59, 59, tzinfo=timezone.utc),
    ),
)
DEFAULT_MODEL_DIR = Path("results/autoencoder-hybrid")
CHARACTER_BLOCK = 8


@dataclass(frozen=True, slots=True)
class ReplayQuery:
    """Uma consulta do log e sua linha de features, sem rótulo de origem."""

    line_number: int
    entry: LogEntry
    features: dict[str, str]


def query_from_domain(domain: str, query_type: str = "A") -> ReplayQuery:
    """Converte uma consulta manual na mesma representação usada no replay."""
    entry = LogEntry(
        source="manual",
        timestamp=datetime(2000, 1, 1, tzinfo=timezone.utc),
        client="-",
        query=normalize_name(domain),
        query_type=query_type.strip().upper(),
    )
    extracted = extract_features(entry.query, query_type=entry.query_type)
    features = {column: str(value) for column, value in extracted.items()}
    return ReplayQuery(line_number=1, entry=entry, features=features)


def read_replay(path: Path, limit: int | None = None) -> list[ReplayQuery]:
    """Lê consultas dnsmasq/BIND9/Unbound na ordem do arquivo, ignorando ruído."""
    if limit is not None and limit <= 0:
        raise ValueError("--limit precisa ser um inteiro positivo")

    queries = []
    with path.open(encoding="utf-8", errors="replace") as log_file:
        for line_number, line in enumerate(log_file, start=1):
            entry = parse_log_line(line, REPLAY_WINDOWS)
            if entry is None:
                continue
            try:
                extracted = extract_features(entry.query, query_type=entry.query_type)
            except ValueError as error:
                raise ValueError(f"{path}: linha {line_number}: {error}") from error
            features = {column: str(value) for column, value in extracted.items()}
            queries.append(ReplayQuery(line_number, entry, features))
            if limit is not None and len(queries) == limit:
                break

    if not queries:
        raise ValueError(f"Nenhuma consulta DNS reconhecida em {path}")
    return queries


def score_queries(loaded: LoadedModel, queries: list[ReplayQuery]) -> list[dict[str, Any]]:
    """Calcula score e explicações com uma única inferência por lote."""
    if not queries:
        raise ValueError("O replay precisa conter ao menos uma consulta")

    rows = [query.features for query in queries]
    characters = encode_domains(rows)
    numeric = numeric_tensor(rows, loaded.scaler)
    character_errors, feature_errors = reconstruction_errors(
        loaded.model, characters, numeric, loaded.mode
    )
    components = aggregate_reconstruction_errors(
        characters, character_errors, feature_errors
    )
    scores = loaded.combine(*components)
    threshold = float(loaded.checkpoint["threshold"])

    results = []
    for index, query in enumerate(queries):
        normalized = str(query.features["query"])
        analyzed = normalized[:MAX_LENGTH]
        suspicious = bool(scores[index] > threshold)
        character_map = []
        if loaded.mode != "semantic":
            character_map = [
                {
                    "position": position,
                    "character": character,
                    "error": float(character_errors[index, position]),
                }
                for position, character in enumerate(analyzed)
            ]
        top_attributes = []
        if feature_errors.shape[1]:
            order = np.argsort(feature_errors[index])[::-1][:3]
            top_attributes = [
                {
                    "attribute": FEATURE_COLUMNS[attribute],
                    "error": float(feature_errors[index, attribute]),
                }
                for attribute in order
            ]
        results.append(
            {
                "line": query.line_number,
                "source": query.entry.source,
                "client": query.entry.client,
                "query_type": query.entry.query_type,
                "query": query.entry.query,
                "normalized_query": normalized,
                "analyzed_query": analyzed,
                "score": float(scores[index]),
                "suspicious": suspicious,
                "classification": "suspeita" if suspicious else "normal",
                "text_error": float(components[0][index]),
                "numeric_error": float(components[1][index]),
                "character_errors": character_map,
                "top_attributes": top_attributes,
            }
        )
    return results


def build_report(
    loaded: LoadedModel,
    queries: list[ReplayQuery],
    model_dir: Path,
    replay: str,
    limit: int | None = None,
) -> dict[str, Any]:
    """Monta o relatório comum ao CLI e à interface web, sem recalibrar nada."""
    results = score_queries(loaded, queries)
    suspicious_count = sum(result["suspicious"] for result in results)
    return {
        "model_dir": str(model_dir),
        "replay": replay,
        "mode": loaded.mode,
        "score_formula": loaded.checkpoint["score_formula"],
        "threshold": float(loaded.checkpoint["threshold"]),
        "limit": limit,
        "query_count": len(results),
        "suspicious_count": suspicious_count,
        "normal_count": len(results) - suspicious_count,
        "results": results,
    }


def run_replay(
    model_dir: Path, replay_path: Path, limit: int | None = None
) -> dict[str, Any]:
    """Carrega o checkpoint e devolve um relatório serializável do replay."""
    queries = read_replay(replay_path, limit=limit)
    loaded = load_checkpoint(model_dir)
    return build_report(loaded, queries, model_dir, str(replay_path), limit)


def format_character_map(
    character_errors: list[dict[str, Any]], block_size: int = CHARACTER_BLOCK
) -> list[str]:
    """Formata a CE por posição em blocos legíveis em um terminal monoespaçado."""
    lines = ["    Mapa de erro por caractere (entropia cruzada, em nats):"]
    for start in range(0, len(character_errors), block_size):
        block = character_errors[start : start + block_size]
        lines.append(
            "    posição   "
            + "".join(f"{item['position']:^8d}" for item in block).rstrip()
        )
        lines.append(
            "    caractere "
            + "".join(f"{item['character']:^8}" for item in block).rstrip()
        )
        lines.append(
            "    CE        "
            + "".join(f"{item['error']:^8.4f}" for item in block).rstrip()
        )
    return lines


def format_text_report(report: dict[str, Any]) -> str:
    """Apresenta o replay sem esconder o limiar nem os componentes do score."""
    lines = [
        f"Modelo: {report['mode']} | checkpoint: {report['model_dir']}",
        f"Score: {report['score_formula']}",
        f"Limiar P99 da validação: {report['threshold']:.6f}",
        f"Replay: {report['replay']} | consultas analisadas: {report['query_count']}",
        "",
    ]
    for index, result in enumerate(report["results"], start=1):
        comparison = ">" if result["suspicious"] else "<="
        lines.extend(
            [
                f"[{index:02d}] {result['classification'].upper()} | "
                f"score={result['score']:.6f} {comparison} limiar={report['threshold']:.6f}",
                f"     origem={result['source']} linha={result['line']} "
                f"cliente={result['client']} tipo={result['query_type']}",
                f"     consulta={result['query']}",
                f"     normalizado={result['analyzed_query']}",
                f"     erro lexical={result['text_error']:.6f} | "
                f"erro numérico={result['numeric_error']:.6f}",
            ]
        )
        if result["character_errors"]:
            lines.extend(format_character_map(result["character_errors"]))
        else:
            lines.append(
                "    Mapa de caracteres indisponível: o modo semântico não reconstrói texto."
            )
        if result["top_attributes"]:
            attributes = ", ".join(
                f"{item['attribute']}={item['error']:.4f}"
                for item in result["top_attributes"]
            )
            lines.append(f"    Maiores erros por atributo: {attributes}")
        lines.append("")
    query_label = "consulta" if report["query_count"] == 1 else "consultas"
    suspicious_label = "suspeita" if report["suspicious_count"] == 1 else "suspeitas"
    normal_label = "normal" if report["normal_count"] == 1 else "normais"
    lines.append(
        f"Resumo: {report['query_count']} {query_label} | "
        f"{report['suspicious_count']} {suspicious_label} | "
        f"{report['normal_count']} {normal_label}"
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replay",
        type=Path,
        required=True,
        help="log gravado do dnsmasq, BIND9 ou Unbound; os formatos podem ser misturados",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=DEFAULT_MODEL_DIR,
        help=f"diretório com model.pt (padrão: {DEFAULT_MODEL_DIR})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="analisa somente as N primeiras consultas reconhecidas",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="imprime o relatório completo em JSON em vez do texto da apresentação",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        report = run_replay(args.model_dir, args.replay, limit=args.limit)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        else:
            print(format_text_report(report))
    except (ValueError, OSError) as error:
        raise SystemExit(f"Erro: {error}") from error


if __name__ == "__main__":
    main()
