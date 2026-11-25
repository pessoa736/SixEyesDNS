"""Controle do atalho do sufixo ``.tunnel`` nas anomalias do gerador.

No dataset versionado todas as suspeitas terminam em ``.tunnel`` e nenhum normal
contém ``tunnel``. Dois testes separam o que o detector aprendeu:

* **necessário?** troca ``.tunnel`` por um sufixo de aparência normal nas
  suspeitas do teste e mede o recall; se cair, o sufixo era a pista;
* **suficiente?** acrescenta ``.tunnel`` aos domínios normais do teste e mede o
  FPR; se subir, o detector reage a qualquer trecho nunca visto no treino.

O limiar é o P99 gravado no checkpoint, o mesmo da tabela principal. Não há
treino nem recalibração aqui: é só inferência.

O controle vale para o dataset anterior (dataset-v1, até o commit 279358c do
gerador). O gerador atual não usa sufixo fixo, então o dataset regenerado não
tem ``.tunnel`` e o controle recusa rodar nele. O resultado medido fica em
``results/archive/dataset-v1/suffix_control.csv``.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from typing import TypedDict

from .features import extract_features
from .scoring import LoadedModel, load_checkpoint, read_rows

MODES = ("lexical", "semantic", "hybrid")
TUNNEL = "tunnel"
SUFFIX_COUNT = 12
FIELDS: tuple[str, ...] = (
    "system", "experiment", "unit", "group", "rows", "flagged", "rate"
)


class ControlRow(TypedDict):
    """Uma linha de ``suffix_control.csv``."""

    system: str
    experiment: str
    unit: str
    group: str
    rows: int
    flagged: int
    rate: float


def swap_suffix(query: str, replacement: str) -> str:
    """Troca o sufixo ``.tunnel`` pelo ``replacement`` e mantém só o payload."""
    marker = f".{TUNNEL}"
    if not query.endswith(marker):
        raise ValueError(f"A suspeita {query!r} não termina em {marker}")
    return f"{query[: -len(marker)].split('.')[0]}.{replacement}"


def normal_suffixes(
    train_rows: list[dict[str, str]], count: int = SUFFIX_COUNT
) -> list[str]:
    """Sufixos de duas etiquetas mais comuns entre os normais do treino."""
    names = [
        row["query"]
        for row in train_rows
        if row["label"] == "normal" and not row["query"].endswith("arpa")
    ]
    for minimum_labels in (3, 2):
        counts = Counter(
            ".".join(name.split(".")[-2:])
            for name in names
            if name.count(".") + 1 >= minimum_labels
        )
        if counts:
            ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
            return [suffix for suffix, _ in ordered[:count]]
    raise ValueError("O treino não tem domínios normais para extrair sufixos")


def features_of(domains: list[str]) -> list[dict[str, str]]:
    return [{key: str(value) for key, value in extract_features(d).items()} for d in domains]


def flagged(loaded: LoadedModel, rows: list[dict[str, str]]) -> list[bool]:
    threshold = float(loaded.checkpoint["threshold"])
    return [bool(score > threshold) for score in loaded.score(rows)]


def summarize(
    system: str, experiment: str, unit: str, groups: dict[str, list[bool]]
) -> list[ControlRow]:
    everything = [value for values in groups.values() for value in values]
    table = []
    for group, values in [("all", everything), *sorted(groups.items())]:
        table.append(
            {
                "system": system,
                "experiment": experiment,
                "unit": unit,
                "group": group,
                "rows": len(values),
                "flagged": sum(values),
                "rate": sum(values) / len(values),
            }
        )
    return table


def run_control(model_dir: Path, system: str, splits_dir: Path) -> list[ControlRow]:
    """Roda os quatro experimentos de um checkpoint; suspeitas por registro."""
    loaded = load_checkpoint(model_dir)
    train = read_rows(splits_dir / "train.csv")
    test = read_rows(splits_dir / "test.csv")
    suffixes = normal_suffixes(train)
    suspects = [row for row in test if row["label"] != "normal"]
    if not suspects:
        raise ValueError("O teste não tem suspeitas para o controle")
    if not all(row["query"].endswith(f".{TUNNEL}") for row in suspects):
        raise ValueError(
            f"Nem todas as suspeitas terminam em .{TUNNEL}: o controle só se aplica "
            "ao dataset-v1; o resultado está em results/archive/dataset-v1/"
        )
    normals = list({row["query"]: row for row in test if row["label"] == "normal"}.values())

    swapped = features_of(
        [swap_suffix(row["query"], suffixes[i % len(suffixes)]) for i, row in enumerate(suspects)]
    )
    tunneled = features_of([f"{row['query']}.{TUNNEL}" for row in normals])
    families = sorted({row["family"] for row in suspects})

    def by_family(flags: list[bool]) -> dict[str, list[bool]]:
        return {
            family: [flag for flag, row in zip(flags, suspects) if row["family"] == family]
            for family in families
        }

    return [
        *summarize(system, "suspects_original", "record", by_family(flagged(loaded, suspects))),
        *summarize(system, "suspects_normal_suffix", "record", by_family(flagged(loaded, swapped))),
        *summarize(system, "normals_original", "domain", {"normal": flagged(loaded, normals)}),
        *summarize(system, "normals_plus_tunnel", "domain", {"normal": flagged(loaded, tunneled)}),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", type=Path, default=Path("data/processed/splits"))
    parser.add_argument("--models-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/archive/dataset-v1/suffix_control.csv"),
    )
    args = parser.parse_args()

    table: list[ControlRow] = []
    for mode in MODES:
        table += run_control(args.models_dir / f"autoencoder-{mode}", mode, args.splits_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(table)

    print(f"{'sistema':9s} {'recall orig.':>13s} {'recall sufixo normal':>21s} "
          f"{'FPR orig.':>10s} {'FPR +.tunnel':>13s}")
    for mode in MODES:
        rate = {
            row["experiment"]: row["rate"]
            for row in table
            if row["system"] == mode and row["group"] == "all"
        }
        print(f"{mode:9s} {rate['suspects_original']:13.4f} "
              f"{rate['suspects_normal_suffix']:21.4f} "
              f"{rate['normals_original']:10.4f} {rate['normals_plus_tunnel']:13.4f}")
    print(f"Salvo em {args.output}")


if __name__ == "__main__":
    main()
