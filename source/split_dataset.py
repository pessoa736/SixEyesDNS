#!/usr/bin/env python3
"""Divide o dataset processado sem repetir domínios entre os conjuntos."""

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--validation-ratio", type=float, default=0.15)
    parser.add_argument(
        "--holdout-family",
        help="Família de anomalia separada integralmente para o teste, "
        "medindo generalização para um tipo nunca visto no treino/validação",
    )
    return parser.parse_args()


def read_dataset(input_path: Path) -> tuple[list[str], dict[str, list[dict[str, str]]]]:
    with input_path.open(newline="", encoding="utf-8") as dataset_file:
        reader = csv.DictReader(dataset_file)
        if not reader.fieldnames or "query" not in reader.fieldnames or "label" not in reader.fieldnames:
            raise ValueError("O dataset precisa das colunas query e label")

        groups: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in reader:
            groups[row["query"]].append(row)

    for query, rows in groups.items():
        labels = {row["label"] for row in rows}
        if len(labels) != 1:
            raise ValueError(f"O domínio {query} possui mais de um rótulo")

    return reader.fieldnames, groups


def split_groups(
    groups: list[list[dict[str, str]]],
    train_ratio: float,
    validation_ratio: float,
    randomizer: random.Random,
) -> dict[str, list[dict[str, str]]]:
    randomizer.shuffle(groups)
    total = len(groups)
    train_end = int(total * train_ratio)
    if train_ratio > 0 and total >= 3:
        train_end = max(1, train_end)
    validation_count = int(total * validation_ratio)
    if validation_ratio > 0 and total >= 3:
        validation_count = max(1, validation_count)
    validation_end = train_end + validation_count
    validation_end = min(validation_end, total - 1) if total > 1 else total

    return {
        "train": [row for group in groups[:train_end] for row in group],
        "validation": [row for group in groups[train_end:validation_end] for row in group],
        "test": [row for group in groups[validation_end:] for row in group],
    }


def write_split(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as split_file:
        writer = csv.DictWriter(split_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def assert_disjoint_splits(splits: dict[str, list[dict[str, str]]]) -> None:
    """Falha se algum domínio aparecer em mais de um split."""
    split_names_by_domain: dict[str, set[str]] = defaultdict(set)
    for split_name, rows in splits.items():
        for row in rows:
            split_names_by_domain[row["query"]].add(split_name)

    overlaps = sorted(
        (domain, sorted(names))
        for domain, names in split_names_by_domain.items()
        if len(names) > 1
    )
    if overlaps:
        examples = ", ".join(
            f"{domain!r} em {'/'.join(names)}" for domain, names in overlaps[:5]
        )
        raise ValueError(
            f"{len(overlaps)} domínio(s) aparecem em mais de um split "
            f"(vazamento entre treino, validação e teste); exemplos: {examples}"
        )


def split_summary(rows: list[dict[str, str]]) -> dict[str, object]:
    """Resume linhas e domínios únicos por split, classe e família."""

    def count_by(column: str) -> dict[str, dict[str, int]]:
        counts: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            counts[row.get(column, "")].append(row["query"])
        return {
            value: {"rows": len(queries), "domains": len(set(queries))}
            for value, queries in sorted(counts.items())
        }

    by_label = count_by("label")
    return {
        "rows": len(rows),
        "domains": len({row["query"] for row in rows}),
        "normal": sum(row["label"] == "normal" for row in rows),
        "suspeita": sum(row["label"] == "suspeita" for row in rows),
        "by_label": by_label,
        "by_family": count_by("family"),
    }


def main() -> None:
    args = parse_args()
    if not 0 < args.train_ratio < 1 or not 0 < args.validation_ratio < 1:
        raise ValueError("As proporções precisam estar entre 0 e 1")
    if args.train_ratio + args.validation_ratio >= 1:
        raise ValueError("As proporções de treino e validação devem deixar espaço para teste")

    fieldnames, groups = read_dataset(args.input)
    randomizer = random.Random(args.seed)
    normal_groups = []
    anomaly_groups = []
    holdout_groups = []

    for rows in groups.values():
        if rows[0]["label"] == "normal":
            normal_groups.append(rows)
        elif args.holdout_family and rows[0].get("family") == args.holdout_family:
            holdout_groups.append(rows)
        else:
            anomaly_groups.append(rows)

    if args.holdout_family and not holdout_groups:
        families = sorted(
            {rows[0].get("family", "") for rows in groups.values() if rows[0]["label"] != "normal"}
        )
        raise ValueError(
            f"Família de holdout {args.holdout_family!r} ausente no dataset; "
            f"disponíveis: {families}"
        )

    normal_splits = split_groups(
        normal_groups, args.train_ratio, args.validation_ratio, randomizer
    )
    anomaly_splits = split_groups(anomaly_groups, 0.0, 0.5, randomizer)
    holdout_rows = [row for group in holdout_groups for row in group]
    splits = {
        "train": normal_splits["train"],
        "validation": normal_splits["validation"] + anomaly_splits["validation"],
        "test": normal_splits["test"] + anomaly_splits["test"] + holdout_rows,
    }
    assert_disjoint_splits(splits)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "seed": args.seed,
        "input": str(args.input),
        "holdout_family": args.holdout_family,
        "splits": {},
    }
    for split_name, rows in splits.items():
        randomizer.shuffle(rows)
        write_split(args.output_dir / f"{split_name}.csv", fieldnames, rows)
        summary["splits"][split_name] = split_summary(rows)

    with (args.output_dir / "summary.json").open("w", encoding="utf-8") as summary_file:
        json.dump(summary, summary_file, ensure_ascii=False, indent=2)

    print(json.dumps(summary["splits"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
