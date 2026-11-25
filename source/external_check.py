"""Teste de estresse com nomes reais: o detector aceita domínios populares como normais?

Os normais do laboratório usam um vocabulário fechado e zonas fictícias
(``atlas``, ``brisa``...). Para medir o que isso custa fora do laboratório, este
módulo trata os domínios de um ranking externo (Tranco, em
``data/external/tranco_top.csv``) como consultas normais e mede a fração que o
checkpoint sinaliza com o limiar P99 gravado nele, em três conjuntos:

* ``ranking``: os nomes do ranking, como o gerador os emitiria (``<domínio>.test``,
  que o processamento reduz a ``<domínio>``);
* ``ranking_lab_zone``: os mesmos nomes com o TLD real trocado por uma zona do
  laboratório, para separar o efeito do TLD do efeito do vocabulário;
* ``test_normals``: domínios normais únicos do split de teste, pelo mesmo caminho
  de código. É o controle: deve reproduzir o FPR por domínio de ``metrics.csv``.

Não há treino nem recalibração: é só inferência. A saída é agregada (contagens e
taxas); os nomes do ranking, que têm licença própria, não são gravados.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path
from statistics import median
from typing import TypedDict

from .features import extract_features
from .scoring import LoadedModel, load_checkpoint, read_rows

MODES = ("lexical", "semantic", "hybrid")
# Mesma regra do gerador (docker/generator/external_domains.py): com ".test" o nome
# precisa caber na janela de 64 caracteres do modelo. O teste do módulo compara as
# duas leituras para que elas não divirjam.
MAX_DOMAIN_LENGTH = 48
HOSTNAME = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*")
ZONE_COUNT = 7
FIELDS: tuple[str, ...] = (
    "system", "set", "rows", "flagged", "rate", "median_score", "threshold"
)


class CheckRow(TypedDict):
    """Uma linha de ``external_check.csv``."""

    system: str
    set: str
    rows: int
    flagged: int
    rate: float
    median_score: float
    threshold: float


def read_ranking(path: Path, limit: int, skip: int = 0) -> list[str]:
    """Lê até ``limit`` domínios válidos e únicos de um ranking ``rank,domain``.

    ``skip`` descarta os primeiros domínios válidos (em ordem de rank) antes de
    contar o ``limit``; ``skip`` igual ao ``TRANCO_LIMIT`` do gerador seleciona
    nomes que ele nunca usou.
    """
    if limit <= 0:
        raise ValueError("--limit precisa ser um inteiro positivo")
    if skip < 0:
        raise ValueError("--skip não pode ser negativo")

    entries: list[tuple[int, str]] = []
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as ranking:
        for row in csv.reader(ranking):
            if len(row) < 2:
                continue
            try:
                rank = int(row[0])
            except ValueError:
                continue
            domain = row[1].strip().rstrip(".").lower()
            valid = domain and len(domain) <= MAX_DOMAIN_LENGTH and HOSTNAME.fullmatch(domain)
            if rank >= 1 and valid:
                entries.append((rank, domain))

    entries.sort(key=lambda entry: entry[0])
    domains: list[str] = []
    seen: set[str] = set()
    for _, domain in entries:
        if domain in seen:
            continue
        seen.add(domain)
        domains.append(domain)
        if len(domains) == skip + limit:
            break
    domains = domains[skip:]
    if not domains:
        raise ValueError(f"Nenhum domínio válido em {path} (depois de pular {skip})")
    return domains


def lab_zones(train_rows: list[dict[str, str]], count: int = ZONE_COUNT) -> list[str]:
    """Última etiqueta mais comum entre os normais do treino, sem as reversas."""
    counts = Counter(
        row["query"].rsplit(".", 1)[-1]
        for row in train_rows
        if row["label"] == "normal" and "." in row["query"] and not row["query"].endswith("arpa")
    )
    if not counts:
        raise ValueError("O treino não tem domínios normais para extrair zonas")
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [zone for zone, _ in ordered[:count]]


def swap_tld(domains: list[str], zones: list[str]) -> list[str]:
    """Troca só a última etiqueta (o TLD) por uma zona do laboratório, em rodízio."""
    return [
        f"{domain.rsplit('.', 1)[0]}.{zones[index % len(zones)]}"
        for index, domain in enumerate(domains)
    ]


def check_set(loaded: LoadedModel, system: str, name: str, domains: list[str]) -> CheckRow:
    """Fração de ``domains`` acima do limiar P99 do checkpoint."""
    rows = [{key: str(value) for key, value in extract_features(d).items()} for d in domains]
    scores = [float(score) for score in loaded.score(rows)]
    threshold = float(loaded.checkpoint["threshold"])
    flagged = sum(score > threshold for score in scores)
    return {
        "system": system,
        "set": name,
        "rows": len(scores),
        "flagged": flagged,
        "rate": flagged / len(scores),
        "median_score": median(scores),
        "threshold": threshold,
    }


def run_check(
    model_dir: Path, system: str, ranking: list[str], splits_dir: Path
) -> list[CheckRow]:
    """Aplica um checkpoint aos três conjuntos."""
    loaded = load_checkpoint(model_dir)
    zones = lab_zones(read_rows(splits_dir / "train.csv"))
    test = read_rows(splits_dir / "test.csv")
    normals = sorted({row["query"] for row in test if row["label"] == "normal"})
    if not normals:
        raise ValueError("O teste não tem domínios normais para o controle")
    return [
        check_set(loaded, system, "ranking", ranking),
        check_set(loaded, system, "ranking_lab_zone", swap_tld(ranking, zones)),
        check_set(loaded, system, "test_normals", normals),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ranking", type=Path, default=Path("data/external/tranco_top.csv"))
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="pula os N primeiros domínios válidos (ex.: 2000 = fora do que o gerador usa)",
    )
    parser.add_argument("--splits-dir", type=Path, default=Path("data/processed/splits"))
    parser.add_argument("--models-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--output", type=Path, default=Path("results/evaluation/external_check.csv")
    )
    args = parser.parse_args()

    if not args.ranking.is_file():
        raise SystemExit(
            f"Ranking não encontrado em {args.ranking}. Baixe a lista conforme "
            "data/external/README.md; o arquivo não é versionado."
        )
    ranking = read_ranking(args.ranking, args.limit, args.skip)

    table: list[CheckRow] = []
    for mode in MODES:
        table += run_check(args.models_dir / f"autoencoder-{mode}", mode, ranking, args.splits_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(table)

    print(f"Ranking: {args.ranking} ({len(ranking)} domínios, pulando {args.skip}, "
          f"limite {args.limit})")
    print(f"{'sistema':9s} {'limiar':>7s} {'ranking':>9s} {'ranking, zona lab':>18s} "
          f"{'normais do teste':>17s}")
    for mode in MODES:
        rate = {row["set"]: row for row in table if row["system"] == mode}
        print(f"{mode:9s} {rate['ranking']['threshold']:7.3f} "
              f"{rate['ranking']['rate']:9.1%} {rate['ranking_lab_zone']['rate']:18.1%} "
              f"{rate['test_normals']['rate']:17.1%}")
    print(f"Salvo em {args.output} (só contagens; os nomes do ranking não são gravados)")


if __name__ == "__main__":
    main()
