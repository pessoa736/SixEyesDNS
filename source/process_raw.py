

import argparse
import csv
import math
import re
from collections import Counter, defaultdict, deque
from pathlib import Path


QUERY_PATTERN = re.compile(r"query\[[^]]+\]\s+(\S+)\s+from\s+(\S+)")
CHARACTERS = tuple("abcdefghijklmnopqrstuvwxyz0123456789")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--labels", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def read_queries(log_path: Path) -> list[dict[str, str]]:
    queries = []
    with log_path.open(encoding="utf-8") as log_file:
        for line in log_file:
            match = QUERY_PATTERN.search(line)
            if match:
                queries.append({"query": match.group(1)})
    return queries


def read_labels(labels_paths: list[Path]) -> dict[str, deque[dict[str, str]]]:
    labels_by_query: dict[str, deque[dict[str, str]]] = defaultdict(deque)
    for labels_path in labels_paths:
        with labels_path.open(newline="", encoding="utf-8") as labels_file:
            for row in csv.DictReader(labels_file):
                labels_by_query[row["query"]].append(row)
    return labels_by_query


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value.lower())
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def extract_features(domain: str) -> dict[str, float | int | str]:
    normalized = domain.rstrip(".").lower()
    labels = [label for label in normalized.split(".") if label]
    character_counts = Counter(normalized)
    alphanumeric_count = sum(character_counts[character] for character in "abcdefghijklmnopqrstuvwxyz0123456789")
    digit_count = sum(character_counts[digit] for digit in "0123456789")

    features: dict[str, float | int | str] = {
        "query": domain,
        "total_length": len(normalized),
        "entropy": round(shannon_entropy(normalized), 8),
        "digit_ratio": round(digit_count / len(normalized), 8) if normalized else 0.0,
        "label_count": len(labels),
        "max_label_length": max((len(label) for label in labels), default=0),
        "alphanumeric_ratio": round(alphanumeric_count / len(normalized), 8) if normalized else 0.0,
    }

    for character in CHARACTERS:
        features[f"char_freq_{character}"] = round(character_counts[character] / len(normalized), 8) if normalized else 0.0

    return features


def process(log_path: Path, labels_paths: list[Path], output_path: Path) -> int:
    queries = read_queries(log_path)
    labels_by_query = read_labels(labels_paths)
    rows = []
    ignored_queries = []

    for query in queries:
        candidates = labels_by_query.get(query["query"], deque())
        if not candidates:
            ignored_queries.append(query["query"])
            continue

        label = candidates.popleft()
        row = extract_features(query["query"])
        row.update(
            {
                "family": label["family"],
                "label": label["label"],
                "seed": label["seed"],
            }
        )
        rows.append(row)

    if not rows:
        raise ValueError("Nenhuma consulta foi encontrada no log DNS")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Consultas processadas: {len(rows)}")
    if ignored_queries:
        print(f"Consultas sem rótulo ignoradas: {len(ignored_queries)}")
    print(f"Dataset salvo em: {output_path}")
    return len(rows)


def main() -> None:
    args = parse_args()
    process(args.log, args.labels, args.output)


if __name__ == "__main__":
    main()
