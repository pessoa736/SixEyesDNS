

import argparse
import csv
import re
from collections import defaultdict, deque
from pathlib import Path

if __package__:
    from .features import extract_features
else:
    from features import extract_features


DNSMASQ_PATTERN = re.compile(r"query\[([^]]+)\]\s+(\S+)\s+from\s+(\S+)")
BIND9_PATTERN = re.compile(r"query:\s+(\S+)\s+IN\s+([A-Z0-9]+)\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, nargs="+", required=True)
    parser.add_argument("--labels", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def read_queries(log_paths: list[Path]) -> list[dict[str, str]]:
    """Lê consultas de logs dnsmasq e BIND9, normalizando o nome sem ponto final."""
    queries = []
    for log_path in log_paths:
        with log_path.open(encoding="utf-8") as log_file:
            for line in log_file:
                match = DNSMASQ_PATTERN.search(line)
                if match:
                    queries.append(
                        {"query_type": match.group(1), "query": match.group(2)}
                    )
                    continue
                match = BIND9_PATTERN.search(line)
                if match:
                    queries.append(
                        {
                            "query_type": match.group(2),
                            "query": match.group(1).rstrip("."),
                        }
                    )
    return queries


def read_labels(labels_paths: list[Path]) -> dict[tuple[str, str], deque[dict[str, str]]]:
    labels_by_query: dict[tuple[str, str], deque[dict[str, str]]] = defaultdict(deque)
    for labels_path in labels_paths:
        with labels_path.open(newline="", encoding="utf-8") as labels_file:
            for row in csv.DictReader(labels_file):
                labels_by_query[(row["query"], row.get("query_type", "A"))].append(row)
    return labels_by_query


def process(log_paths: list[Path], labels_paths: list[Path], output_path: Path) -> int:
    queries = read_queries(log_paths)
    labels_by_query = read_labels(labels_paths)
    rows = []
    ignored_queries = []

    for query in queries:
        candidates = labels_by_query.get(
            (query["query"], query["query_type"]), deque()
        )
        if not candidates:
            candidates = labels_by_query.get((query["query"], "A"), deque())
        if not candidates:
            ignored_queries.append(query["query"])
            continue

        label = candidates.popleft()
        row = extract_features(
            query["query"],
            query_type=query["query_type"],
            family=label["family"],
        )
        row.update(
            {
                "query_type": query["query_type"],
                "family": label["family"],
                "profile": label.get("profile", label["family"]),
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
