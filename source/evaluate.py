"""Avalia autoencoders e baselines; todos os limiares são calibrados na validação.

Gera em ``results/evaluation/`` tabelas (CSV, Markdown e JSON) e figuras com
precisão, recall, F1, FPR, ROC-AUC, PR-AUC, matrizes de confusão, recall por
família, FPR por perfil normal, falsos positivos por domínio, prevalência,
leave-one-family-out, ablação e explicabilidade por atributo e por caractere.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import precision_recall_curve, roc_curve

if __package__:
    from .baselines import IsolationForestBaseline, entropy_scores
    from .explain import (
        attribute_table,
        character_table,
        explain_row,
        position_curves,
    )
    from .scoring import (
        LoadedModel,
        anomaly_labels,
        best_f1_threshold,
        classification_metrics,
        collapse_by_domain,
        expected_precision,
        load_checkpoint,
        normal_rows,
        percentile_threshold,
        ranking_metrics,
        read_rows,
    )
else:
    from baselines import IsolationForestBaseline, entropy_scores
    from explain import attribute_table, character_table, explain_row, position_curves
    from scoring import (
        LoadedModel,
        anomaly_labels,
        best_f1_threshold,
        classification_metrics,
        collapse_by_domain,
        expected_precision,
        load_checkpoint,
        normal_rows,
        percentile_threshold,
        ranking_metrics,
        read_rows,
    )


SEED = 42
SPLIT_NAMES = ("train", "validation", "test")
EVALUATED_SPLITS = ("validation", "test")
LEVELS = ("record", "domain")
POLICIES = ("p99", "best_f1")
POLICY_LABELS = {
    "p99": "P99 dos normais da validação",
    "best_f1": "melhor F1 da validação",
}
SYSTEM_LABELS = {
    "entropy": "Limiar de entropia",
    "isolation_forest": "Isolation Forest",
    "semantic": "AE denso (atributos)",
    "lexical": "AE lexical (caracteres)",
    "hybrid": "AE híbrido",
}
SYSTEM_COLORS = {
    "entropy": "#7f7f7f",
    "isolation_forest": "#8c564b",
    "semantic": "#2ca02c",
    "lexical": "#ff7f0e",
    "hybrid": "#1f77b4",
}
AUTOENCODER_MODES = ("semantic", "lexical", "hybrid")
DEFAULT_PREVALENCES = (0.001, 0.01, 0.05, 0.10, 0.25, 0.50)
DEFAULT_LAMBDAS = (0.0, 0.25, 0.5, 1.0, 2.0, 4.0)
CONSISTENCY_TOLERANCE = 1e-3
NEAR_DUPLICATE_THRESHOLD = 0.8


@dataclass
class Split:
    """Linhas de um split e vetores alinhados a elas."""

    rows: list[dict[str, str]]
    labels: np.ndarray
    domains: list[str]
    families: np.ndarray
    profiles: np.ndarray

    @classmethod
    def from_rows(cls, rows: list[dict[str, str]]) -> "Split":
        return cls(
            rows=rows,
            labels=anomaly_labels(rows),
            domains=[row["query"] for row in rows],
            families=np.asarray([row.get("family", "") for row in rows]),
            profiles=np.asarray(
                [row.get("profile") or row.get("family", "") for row in rows]
            ),
        )


@dataclass
class System:
    """Um detector avaliado: baseline ou autoencoder."""

    key: str
    scores: dict[str, np.ndarray]
    loaded: LoadedModel | None = None
    components: dict[str, tuple[np.ndarray, np.ndarray]] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return SYSTEM_LABELS.get(self.key, self.key)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", type=Path, default=Path("data/processed/splits"))
    parser.add_argument(
        "--model",
        action="append",
        metavar="MODO=DIR",
        help="Diretório de um autoencoder (semantic, lexical ou hybrid); repetível. "
        "Padrão: results/autoencoder-<modo> para os três modos.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("results/evaluation"))
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--prevalences",
        type=float,
        nargs="+",
        default=list(DEFAULT_PREVALENCES),
        help="Prevalências de suspeitas para a análise de precisão esperada",
    )
    parser.add_argument(
        "--lambdas",
        type=float,
        nargs="+",
        default=list(DEFAULT_LAMBDAS),
        help="Valores de lambda da ablação do score híbrido (somente no score)",
    )
    parser.add_argument("--top-false-positives", type=int, default=25)
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument(
        "--skip-consistency-check",
        action="store_true",
        help="Não compara limiar e scores recalculados com os do checkpoint",
    )
    return parser.parse_args()


def parse_model_dirs(items: list[str] | None) -> dict[str, Path]:
    if not items:
        return {mode: Path(f"results/autoencoder-{mode}") for mode in AUTOENCODER_MODES}
    directories: dict[str, Path] = {}
    for item in items:
        mode, separator, directory = item.partition("=")
        if not separator or mode not in AUTOENCODER_MODES:
            raise ValueError(
                f"--model deve ser MODO=DIR com MODO em {AUTOENCODER_MODES}: {item!r}"
            )
        directories[mode] = Path(directory)
    return directories


def load_splits(splits_dir: Path) -> dict[str, Split]:
    splits = {
        name: Split.from_rows(read_rows(splits_dir / f"{name}.csv"))
        for name in SPLIT_NAMES
    }
    check_splits(splits)
    return splits


def check_splits(splits: dict[str, Split]) -> None:
    """Falha em vazamento: treino com suspeitas ou domínios repetidos entre splits."""
    if splits["train"].labels.any():
        raise ValueError("O split de treino deve conter somente exemplos normais")
    for first, second in combinations(SPLIT_NAMES, 2):
        shared = set(splits[first].domains) & set(splits[second].domains)
        if shared:
            raise ValueError(
                f"Domínios repetidos entre {first} e {second}: {sorted(shared)[:5]}"
            )
    for name in EVALUATED_SPLITS:
        if len(set(splits[name].labels.tolist())) < 2:
            raise ValueError(f"O split {name} precisa conter normais e suspeitas")


def split_description(splits: dict[str, Split]) -> dict[str, object]:
    description: dict[str, object] = {}
    for name, split in splits.items():
        normal = split.labels == 0
        description[name] = {
            "rows": len(split.rows),
            "domains": len(set(split.domains)),
            "normal_rows": int(normal.sum()),
            "normal_domains": len({d for d, n in zip(split.domains, normal) if n}),
            "suspeita_rows": int((~normal).sum()),
            "suspeita_domains": len({d for d, n in zip(split.domains, normal) if not n}),
            "suspeita_prevalence": float(split.labels.mean()),
        }
    return description


def near_duplicate_rows(
    splits: dict[str, Split], threshold: float = NEAR_DUPLICATE_THRESHOLD
) -> list[dict[str, object]]:
    """Quase-duplicatas em relação ao treino por similaridade de trigramas.

    Os splits não repetem domínios, mas domínios diferentes podem vir do mesmo
    molde do gerador. A maior similaridade de Jaccard de trigramas de caracteres
    com um normal do treino indica o risco de vazamento por padrão.
    """
    vectorizer = CountVectorizer(
        analyzer="char", ngram_range=(3, 3), binary=True, lowercase=False
    )
    train_matrix = vectorizer.fit_transform(sorted(set(splits["train"].domains)))
    train_matrix = train_matrix.astype(np.float32)
    train_sizes = np.asarray(train_matrix.sum(axis=1)).ravel()
    rows = []
    for name in EVALUATED_SPLITS:
        split = splits[name]
        for class_name, value in (("normal", 0), ("suspeita", 1)):
            domains = sorted(
                {d for d, label in zip(split.domains, split.labels) if label == value}
            )
            matrix = vectorizer.transform(domains).astype(np.float32)
            sizes = np.asarray(matrix.sum(axis=1)).ravel()
            intersection = (matrix @ train_matrix.T).toarray()
            union = sizes[:, None] + train_sizes[None, :] - intersection
            similarity = np.divide(
                intersection, union, out=np.zeros_like(intersection), where=union > 0
            )
            best = similarity.max(axis=1)
            rows.append(
                {
                    "split": name,
                    "class": class_name,
                    "domains": len(domains),
                    "median_max_jaccard": float(np.median(best)),
                    "p90_max_jaccard": float(np.percentile(best, 90)),
                    "share_near_duplicate": float((best >= threshold).mean()),
                    "threshold": threshold,
                }
            )
    return rows


def verify_checkpoint(
    directory: Path,
    loaded: LoadedModel,
    splits: dict[str, Split],
    scores: dict[str, np.ndarray],
) -> dict[str, float]:
    """Garante que checkpoint e splits são os mesmos do treino."""
    recomputed = percentile_threshold(
        scores["validation"][splits["validation"].labels == 0]
    )
    stored = float(loaded.checkpoint["threshold"])
    tolerance = CONSISTENCY_TOLERANCE * max(1.0, abs(stored))
    if abs(recomputed - stored) > tolerance:
        raise ValueError(
            f"{directory}: o limiar P99 recalculado ({recomputed:.6f}) difere do "
            f"salvo no checkpoint ({stored:.6f}). Os splits mudaram desde o treino? "
            "Retreine o modelo ou use --skip-consistency-check."
        )
    report = {"threshold_difference": abs(recomputed - stored)}
    metrics_path = directory / "metrics.json"
    if not metrics_path.is_file():
        return report
    saved = json.loads(metrics_path.read_text(encoding="utf-8"))
    for split_name in EVALUATED_SPLITS:
        saved_scores = np.asarray(saved.get(f"{split_name}_scores", []), dtype=float)
        if not len(saved_scores):
            continue
        if len(saved_scores) != len(scores[split_name]):
            raise ValueError(
                f"{directory}: {len(saved_scores)} scores salvos de {split_name} "
                f"para {len(scores[split_name])} linhas no split atual."
            )
        difference = float(np.max(np.abs(saved_scores - scores[split_name])))
        if difference > CONSISTENCY_TOLERANCE * max(1.0, float(np.abs(saved_scores).max())):
            raise ValueError(
                f"{directory}: os scores recalculados de {split_name} divergem dos "
                f"salvos no treino (diferença máxima {difference:.6f})."
            )
        report[f"{split_name}_scores_max_difference"] = difference
    return report


def build_systems(
    model_dirs: dict[str, Path],
    splits: dict[str, Split],
    seed: int,
    check_consistency: bool,
) -> tuple[list[System], dict[str, dict[str, float]]]:
    """Cria baselines e carrega autoencoders; scores só de validação e teste."""
    systems = [
        System(
            "entropy",
            {name: entropy_scores(splits[name].rows) for name in EVALUATED_SPLITS},
        )
    ]
    forest = IsolationForestBaseline(seed).fit(normal_rows(splits["train"].rows))
    systems.append(
        System(
            "isolation_forest",
            {name: forest.score(splits[name].rows) for name in EVALUATED_SPLITS},
        )
    )
    consistency: dict[str, dict[str, float]] = {}
    for mode in AUTOENCODER_MODES:
        if mode not in model_dirs:
            continue
        loaded = load_checkpoint(model_dirs[mode])
        if loaded.mode != mode:
            raise ValueError(f"{model_dirs[mode]} contém um modelo {loaded.mode!r}, não {mode!r}")
        components = {name: loaded.components(splits[name].rows) for name in EVALUATED_SPLITS}
        scores = {name: loaded.combine(*components[name]) for name in EVALUATED_SPLITS}
        if check_consistency:
            consistency[mode] = verify_checkpoint(model_dirs[mode], loaded, splits, scores)
        systems.append(System(mode, scores, loaded, components))
    return systems, consistency


def calibrate(
    scores: dict[str, np.ndarray], validation: Split
) -> dict[str, float]:
    """Limiares escolhidos somente com a validação."""
    return {
        "p99": percentile_threshold(scores["validation"][validation.labels == 0]),
        "best_f1": best_f1_threshold(scores["validation"], validation.labels),
    }


def level_arrays(
    split: Split, scores: np.ndarray, level: str
) -> tuple[np.ndarray, np.ndarray]:
    """Rótulos e scores por registro ou por domínio único."""
    if level == "record":
        return split.labels, scores
    _, domain_scores, domain_labels = collapse_by_domain(
        split.domains, scores, split.labels
    )
    return domain_labels, domain_scores


def metric_rows(
    system: System,
    splits: dict[str, Split],
    thresholds: dict[str, float],
) -> list[dict[str, object]]:
    rows = []
    for policy in POLICIES:
        for split_name in EVALUATED_SPLITS:
            for level in LEVELS:
                labels, scores = level_arrays(
                    splits[split_name], system.scores[split_name], level
                )
                metrics = classification_metrics(labels, scores, thresholds[policy])
                (tn, fp), (fn, tp) = metrics.pop("confusion_matrix")
                rows.append(
                    {
                        "system": system.key,
                        "policy": policy,
                        "split": split_name,
                        "level": level,
                        **metrics,
                        "tn": tn,
                        "fp": fp,
                        "fn": fn,
                        "tp": tp,
                    }
                )
    return rows


def group_rows(
    system: System,
    split: Split,
    thresholds: dict[str, float],
    values: np.ndarray,
    positive: int,
) -> list[dict[str, object]]:
    """Taxa de alarme por grupo: recall por família ou FPR por perfil normal."""
    scores = system.scores["test"]
    rows = []
    for policy in POLICIES:
        flagged = scores > thresholds[policy]
        for group in sorted(set(values[split.labels == positive].tolist())):
            mask = (values == group) & (split.labels == positive)
            rows.append(
                {
                    "system": system.key,
                    "policy": policy,
                    "group": group,
                    "rows": int(mask.sum()),
                    "domains": len({d for d, m in zip(split.domains, mask) if m}),
                    "flagged": int(flagged[mask].sum()),
                    "rate": float(flagged[mask].mean()),
                }
            )
    return rows


def false_positive_rows(
    system: System,
    split: Split,
    thresholds: dict[str, float],
    top: int,
) -> list[dict[str, object]]:
    """Domínios normais sinalizados no teste, ordenados pela quantidade de registros."""
    scores = system.scores["test"]
    rows = []
    for policy in POLICIES:
        counts: dict[str, dict[str, object]] = {}
        for index in np.flatnonzero((scores > thresholds[policy]) & (split.labels == 0)):
            entry = counts.setdefault(
                split.domains[index],
                {"profile": str(split.profiles[index]), "rows": 0, "score": float(scores[index])},
            )
            entry["rows"] += 1
        ordered = sorted(
            counts.items(), key=lambda item: (-item[1]["rows"], -item[1]["score"], item[0])
        )
        for domain, entry in ordered[:top]:
            rows.append(
                {
                    "system": system.key,
                    "policy": policy,
                    "domain": domain,
                    "profile": entry["profile"],
                    "rows": entry["rows"],
                    "score": entry["score"],
                    "threshold": thresholds[policy],
                    "false_positive_domains_total": len(counts),
                    "false_positive_rows_total": sum(e["rows"] for e in counts.values()),
                }
            )
    return rows


def false_positive_summary(
    systems: list[System],
    split: Split,
    thresholds: dict[str, dict[str, float]],
) -> list[dict[str, object]]:
    """Total de falsos positivos por sistema e limiar, inclusive quando é zero."""
    rows = []
    for system in systems:
        for policy in POLICIES:
            flagged = (system.scores["test"] > thresholds[system.key][policy]) & (split.labels == 0)
            rows.append(
                {
                    "system": system.key,
                    "policy": policy,
                    "false_positive_rows": int(flagged.sum()),
                    "false_positive_domains": len(
                        {d for d, f in zip(split.domains, flagged) if f}
                    ),
                    "normal_rows": int((split.labels == 0).sum()),
                    "normal_domains": len(
                        {d for d, l in zip(split.domains, split.labels) if l == 0}
                    ),
                }
            )
    return rows


def lofo_rows(
    systems: list[System],
    validation: Split,
    test: Split,
    thresholds: dict[str, dict[str, float]],
) -> list[dict[str, object]]:
    """Leave-one-family-out: a família fica fora da calibração, nunca do teste.

    Os autoencoders e baselines não veem suspeitas no treino; o que a família
    omitida pode influenciar é o limiar de melhor F1, recalibrado sem ela na
    validação. O teste nunca escolhe limiar.
    """
    rows = []
    normals = test.labels == 0
    for family in sorted(set(test.families[test.labels == 1].tolist())):
        held_out = (test.labels == 1) & (test.families == family)
        keep = ~((validation.labels == 1) & (validation.families == family))
        if len(set(validation.labels[keep].tolist())) < 2:
            continue
        for system in systems:
            threshold = best_f1_threshold(system.scores["validation"][keep], validation.labels[keep])
            test_scores = system.scores["test"]
            rows.append(
                {
                    "system": system.key,
                    "heldout_family": family,
                    "heldout_rows": int(held_out.sum()),
                    "threshold_without_family": threshold,
                    "threshold_all_families": thresholds[system.key]["best_f1"],
                    "recall_best_f1_without_family": float((test_scores[held_out] > threshold).mean()),
                    "recall_best_f1_all_families": float(
                        (test_scores[held_out] > thresholds[system.key]["best_f1"]).mean()
                    ),
                    "recall_p99": float(
                        (test_scores[held_out] > thresholds[system.key]["p99"]).mean()
                    ),
                    "fpr_best_f1_without_family": float((test_scores[normals] > threshold).mean()),
                }
            )
    return rows


def prevalence_rows(
    test_metrics: list[dict[str, object]],
    prevalences: list[float],
    observed: float,
) -> list[dict[str, object]]:
    """Precisão e F1 esperados em outras prevalências, a partir de recall e FPR."""
    rows = []
    for metrics in test_metrics:
        recall, fpr = float(metrics["recall"]), float(metrics["fpr"])
        for prevalence in [*prevalences, observed]:
            precision = expected_precision(recall, fpr, prevalence)
            denominator = precision + recall
            rows.append(
                {
                    "system": metrics["system"],
                    "policy": metrics["policy"],
                    "prevalence": prevalence,
                    "is_observed": prevalence == observed,
                    "recall": recall,
                    "fpr": fpr,
                    "expected_precision": precision,
                    "expected_f1": 2 * precision * recall / denominator if denominator else 0.0,
                }
            )
    return rows


def ablation_rows(
    systems: list[System],
    splits: dict[str, Split],
    lambdas: list[float],
) -> list[dict[str, object]]:
    """Compara sistemas e variações do score híbrido, sempre calibrando na validação."""
    variants: list[tuple[str, dict[str, np.ndarray]]] = [
        (system.label, system.scores) for system in systems
    ]
    hybrid = next((system for system in systems if system.key == "hybrid"), None)
    if hybrid is not None and hybrid.loaded is not None:
        for weight in lambdas:
            variants.append(
                (
                    f"AE híbrido, score com λ={weight:g}",
                    {
                        name: hybrid.loaded.combine(*hybrid.components[name], numeric_weight=weight)
                        for name in EVALUATED_SPLITS
                    },
                )
            )
        variants.append(
            (
                "AE híbrido, score só MSE dos atributos",
                {
                    name: hybrid.loaded.combine(*hybrid.components[name], mode="semantic")
                    for name in EVALUATED_SPLITS
                },
            )
        )
    rows = []
    for name, scores in variants:
        thresholds = calibrate(scores, splits["validation"])
        row: dict[str, object] = {"variant": name}
        row.update(ranking_metrics(splits["test"].labels, scores["test"]))
        for policy in POLICIES:
            metrics = classification_metrics(splits["test"].labels, scores["test"], thresholds[policy])
            row[f"{policy}_threshold"] = thresholds[policy]
            for key in ("precision", "recall", "f1", "fpr"):
                row[f"{policy}_{key}"] = metrics[key]
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        if not rows:
            return
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(
    rows: list[dict[str, object]], columns: list[tuple[str, str]], digits: int = 4
) -> str:
    """Tabela Markdown com ``(coluna, cabeçalho)``; números com ``digits`` casas."""

    def cell(value: object) -> str:
        if value is None:
            return "—"
        if isinstance(value, float):
            return f"{value:.{digits}f}"
        return str(value)

    lines = [
        "| " + " | ".join(header for _, header in columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell(row.get(column)) for column, _ in columns) + " |")
    return "\n".join(lines) + "\n"


def summary_markdown(
    all_metrics: list[dict[str, object]],
    splits: dict[str, Split],
    leakage: list[dict[str, object]],
) -> str:
    """Tabela principal: teste, por registro e por domínio único."""
    label_of = {row["system"]: SYSTEM_LABELS.get(row["system"], row["system"]) for row in all_metrics}
    columns = [
        ("system", "Sistema"),
        ("precision", "Precisão"),
        ("recall", "Recall"),
        ("f1", "F1"),
        ("fpr", "FPR"),
        ("roc_auc", "ROC-AUC"),
        ("pr_auc", "PR-AUC"),
        ("recall_at_fpr", "Recall a FPR ≤ 1%"),
        ("rows", "Linhas"),
    ]
    description = split_description(splits)["test"]
    prevalence = float(description["suspeita_prevalence"])
    parts = [
        "# Resultados no teste\n",
        f"\nTeste: {description['rows']} registros, {description['domains']} domínios únicos, "
        f"prevalência de suspeitas {prevalence:.4f}. Limiares calibrados somente na validação.\n",
        f"\nCom essa prevalência, marcar tudo como suspeito já rende precisão {prevalence:.4f}, "
        f"recall 1 e F1 {2 * prevalence / (1 + prevalence):.4f}; compare também FPR, ROC-AUC e PR-AUC.\n",
    ]
    for level, level_title in (("record", "por registro"), ("domain", "por domínio único")):
        for policy in POLICIES:
            selected = [
                {**row, "system": label_of[row["system"]]}
                for row in all_metrics
                if row["split"] == "test" and row["level"] == level and row["policy"] == policy
            ]
            parts.append(f"\n## Teste {level_title} — limiar {POLICY_LABELS[policy]}\n\n")
            parts.append(markdown_table(selected, columns))
    parts.append(
        "\n## Quase-duplicatas em relação ao treino\n\n"
        "Maior similaridade de Jaccard de trigramas de caracteres com um domínio normal do "
        "treino; indica vazamento por molde do gerador, não por domínio idêntico.\n\n"
    )
    parts.append(
        markdown_table(
            leakage,
            [
                ("split", "Split"),
                ("class", "Classe"),
                ("domains", "Domínios"),
                ("median_max_jaccard", "Mediana"),
                ("p90_max_jaccard", "P90"),
                ("share_near_duplicate", "Fração ≥ limiar"),
                ("threshold", "Limiar"),
            ],
        )
    )
    return "".join(parts)


def ablation_markdown(rows: list[dict[str, object]]) -> str:
    columns = [
        ("variant", "Variante"),
        ("roc_auc", "ROC-AUC"),
        ("pr_auc", "PR-AUC"),
        ("recall_at_fpr", "Recall a FPR ≤ 1%"),
        ("p99_precision", "P99 precisão"),
        ("p99_recall", "P99 recall"),
        ("p99_f1", "P99 F1"),
        ("p99_fpr", "P99 FPR"),
        ("best_f1_precision", "F1* precisão"),
        ("best_f1_recall", "F1* recall"),
        ("best_f1_f1", "F1* F1"),
        ("best_f1_fpr", "F1* FPR"),
    ]
    return (
        "# Ablação no teste (por registro)\n\n"
        "P99 = limiar no percentil 99 dos normais da validação; F1* = limiar de "
        "melhor F1 da validação. As linhas com λ variam só a combinação do score "
        "do mesmo modelo híbrido, sem retreinar.\n\n"
        + markdown_table(rows, columns)
    )


def savefig(figure: plt.Figure, path: Path) -> None:
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def plot_curves(
    systems: list[System],
    test: Split,
    thresholds: dict[str, dict[str, float]],
    output_dir: Path,
) -> None:
    """Curvas ROC (linear e FPR em escala log) e precisão-recall no teste."""
    figure, axes = plt.subplots(1, 3, figsize=(17, 5))
    for system in systems:
        scores = system.scores["test"]
        color = SYSTEM_COLORS.get(system.key)
        fpr, tpr, _ = roc_curve(test.labels, scores)
        precision, recall, _ = precision_recall_curve(test.labels, scores)
        metrics = ranking_metrics(test.labels, scores)
        flagged = scores > thresholds[system.key]["p99"]
        op_fpr = float(flagged[test.labels == 0].mean())
        op_tpr = float(flagged[test.labels == 1].mean())
        for axis in axes[:2]:
            axis.plot(fpr, tpr, color=color, label=f"{system.label} (AUC {metrics['roc_auc']:.3f})")
            axis.scatter([op_fpr], [op_tpr], color=color, edgecolor="black", zorder=3)
        axes[2].plot(recall, precision, color=color, label=f"{system.label} (AP {metrics['pr_auc']:.3f})")
        axes[2].scatter([op_tpr], [flagged[test.labels == 1].sum() / max(flagged.sum(), 1)],
                        color=color, edgecolor="black", zorder=3)
    axes[0].set_title("ROC no teste (círculo: limiar P99)")
    axes[1].set_title("ROC no teste, FPR em escala log")
    axes[1].set_xscale("log")
    axes[1].set_xlim(1e-3, 1)
    axes[1].axvline(0.01, color="black", linestyle=":", label="FPR = 1%")
    axes[2].set_title("Precisão-recall no teste")
    for axis, xlabel, ylabel in zip(
        axes, ("FPR", "FPR (log)", "Recall"), ("TPR (recall)", "TPR (recall)", "Precisão")
    ):
        axis.set_xlabel(xlabel)
        axis.set_ylabel(ylabel)
        axis.grid(alpha=0.25)
        axis.legend(fontsize=8, loc="lower right")
    savefig(figure, output_dir / "roc-pr.png")


def plot_grouped_bars(
    path: Path,
    title: str,
    ylabel: str,
    rows: list[dict[str, object]],
    group_key: str,
    value_key: str,
    series_key: str = "system",
    systems_order: list[str] | None = None,
) -> None:
    groups = sorted({str(row[group_key]) for row in rows})
    series = systems_order or sorted({str(row[series_key]) for row in rows})
    width = 0.8 / max(len(series), 1)
    figure, axis = plt.subplots(figsize=(max(7, 1.6 * len(groups) + 3), 5))
    for index, name in enumerate(series):
        values = []
        for group in groups:
            match = [r for r in rows if r[series_key] == name and str(r[group_key]) == group]
            values.append(float(match[0][value_key]) if match else np.nan)
        positions = np.arange(len(groups)) + (index - (len(series) - 1) / 2) * width
        axis.bar(positions, values, width, label=SYSTEM_LABELS.get(name, name),
                 color=SYSTEM_COLORS.get(name))
    axis.set_xticks(np.arange(len(groups)), groups, rotation=20, ha="right")
    axis.set_ylabel(ylabel)
    axis.set_ylim(0, 1.05)
    axis.set_title(title)
    axis.grid(axis="y", alpha=0.25)
    axis.legend(fontsize=8)
    savefig(figure, path)


def plot_prevalence(rows: list[dict[str, object]], output_dir: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for axis, policy in zip(axes, POLICIES):
        for system in dict.fromkeys(str(row["system"]) for row in rows):
            selected = sorted(
                (r for r in rows if r["system"] == system and r["policy"] == policy and not r["is_observed"]),
                key=lambda r: r["prevalence"],
            )
            axis.plot(
                [r["prevalence"] for r in selected],
                [r["expected_precision"] for r in selected],
                marker="o",
                color=SYSTEM_COLORS.get(system),
                label=SYSTEM_LABELS.get(system, system),
            )
        axis.set_xscale("log")
        axis.set_xlabel("Prevalência de suspeitas no tráfego")
        axis.set_title(f"Limiar {POLICY_LABELS[policy]}")
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("Precisão esperada (recall e FPR do teste)")
    axes[0].set_ylim(0, 1.05)
    axes[0].legend(fontsize=8)
    savefig(figure, output_dir / "prevalence.png")


def plot_explain_attributes(
    tables: dict[str, list[dict[str, object]]], output_dir: Path, top: int = 10
) -> None:
    figure, axes = plt.subplots(1, len(tables), figsize=(7 * len(tables), 5), squeeze=False)
    for axis, (system, table) in zip(axes[0], tables.items()):
        ranked = sorted(
            table, key=lambda r: r["mean_error_suspeita"] - r["mean_error_normal"], reverse=True
        )[:top][::-1]
        positions = np.arange(len(ranked))
        axis.barh(positions - 0.2, [r["mean_error_normal"] for r in ranked], 0.4, label="normal")
        axis.barh(positions + 0.2, [r["mean_error_suspeita"] for r in ranked], 0.4, label="suspeita")
        axis.set_yticks(positions, [r["attribute"] for r in ranked])
        axis.set_xlabel("Erro quadrático médio (atributo padronizado)")
        axis.set_title(f"{SYSTEM_LABELS[system]}: atributos com maior aumento de erro")
        axis.grid(axis="x", alpha=0.25)
        axis.legend()
    savefig(figure, output_dir / "explain-attributes.png")


def plot_explain_characters(
    tables: dict[str, list[dict[str, object]]],
    curves: dict[str, dict[str, list[float]]],
    output_dir: Path,
) -> None:
    figure, axes = plt.subplots(2, len(tables), figsize=(8 * len(tables), 9), squeeze=False)
    for column, (system, table) in enumerate(tables.items()):
        axis = axes[0, column]
        positions = np.arange(len(table))
        normal = [np.nan if r["mean_error_normal"] is None else r["mean_error_normal"] for r in table]
        suspicious = [np.nan if r["mean_error_suspeita"] is None else r["mean_error_suspeita"] for r in table]
        axis.bar(positions - 0.2, normal, 0.4, label="normal")
        axis.bar(positions + 0.2, suspicious, 0.4, label="suspeita")
        axis.set_xticks(positions, [r["character"] for r in table], fontsize=8)
        axis.set_ylabel("Entropia cruzada média")
        axis.set_title(f"{SYSTEM_LABELS[system]}: erro por caractere real")
        axis.grid(axis="y", alpha=0.25)
        axis.legend()
        axis = axes[1, column]
        for name, values in curves[system].items():
            axis.plot(values, label=name)
        axis.set_xlabel("Posição no domínio")
        axis.set_ylabel("Entropia cruzada média")
        axis.set_title(f"{SYSTEM_LABELS[system]}: erro por posição")
        axis.grid(alpha=0.25)
        axis.legend()
    savefig(figure, output_dir / "explain-characters.png")


def explain_examples_markdown(
    system: System, test: Split, thresholds: dict[str, dict[str, float]], count: int = 5
) -> str:
    """Casos concretos do modelo principal: acertos, falsos positivos e falsos negativos."""
    assert system.loaded is not None
    scores = system.scores["test"]
    threshold = thresholds[system.key]["p99"]
    flagged = scores > threshold
    groups = {
        "Verdadeiros positivos de maior score": np.flatnonzero(flagged & (test.labels == 1))[::-1],
        "Falsos positivos (limiar P99)": np.flatnonzero(flagged & (test.labels == 0)),
        "Falsos negativos de menor score (limiar P99)": np.flatnonzero(~flagged & (test.labels == 1)),
    }
    lines = [
        f"# Exemplos explicados — {system.label}\n\n",
        f"Limiar P99 da validação: {threshold:.4f}. Domínios sintéticos sem o sufixo `.test`.\n",
    ]
    for title, indices in groups.items():
        ascending = title.startswith("Falsos negativos")
        ordered = sorted(indices, key=lambda i: scores[i], reverse=not ascending)
        seen: set[str] = set()
        lines.append(f"\n## {title}\n\n")
        picked = 0
        for index in ordered:
            domain = test.domains[index]
            if domain in seen:
                continue
            seen.add(domain)
            explanation = explain_row(system.loaded, test.rows[index])
            parts = [f"`{domain}` ({test.profiles[index]}): score {explanation['score']:.2f}"]
            if "top_attributes" in explanation:
                parts.append(
                    "atributos: "
                    + ", ".join(f"{name}={error:.2f}" for name, error in explanation["top_attributes"])
                )
            if "top_characters" in explanation:
                parts.append(
                    "caracteres: "
                    + ", ".join(
                        f"'{char}'@{position}={error:.2f}"
                        for char, position, error in explanation["top_characters"]
                    )
                )
            lines.append("- " + "; ".join(parts) + "\n")
            picked += 1
            if picked == count:
                break
        if not picked:
            lines.append("Nenhum caso no teste.\n")
    return "".join(lines)


def run(
    splits_dir: Path,
    model_dirs: dict[str, Path],
    output_dir: Path,
    seed: int = SEED,
    prevalences: list[float] | None = None,
    lambdas: list[float] | None = None,
    top_false_positives: int = 25,
    plots: bool = True,
    check_consistency: bool = True,
) -> dict[str, object]:
    """Executa a avaliação completa e grava os resultados em ``output_dir``."""
    prevalences = list(DEFAULT_PREVALENCES) if prevalences is None else prevalences
    lambdas = list(DEFAULT_LAMBDAS) if lambdas is None else lambdas
    splits = load_splits(splits_dir)
    systems, consistency = build_systems(model_dirs, splits, seed, check_consistency)
    thresholds = {
        system.key: calibrate(system.scores, splits["validation"]) for system in systems
    }
    output_dir.mkdir(parents=True, exist_ok=True)

    all_metrics: list[dict[str, object]] = []
    family_rows: list[dict[str, object]] = []
    profile_rows: list[dict[str, object]] = []
    false_positives: list[dict[str, object]] = []
    for system in systems:
        all_metrics += metric_rows(system, splits, thresholds[system.key])
        family_rows += group_rows(system, splits["test"], thresholds[system.key], splits["test"].families, 1)
        profile_rows += group_rows(system, splits["test"], thresholds[system.key], splits["test"].profiles, 0)
        false_positives += false_positive_rows(
            system, splits["test"], thresholds[system.key], top_false_positives
        )
    test_record = [
        row for row in all_metrics if row["split"] == "test" and row["level"] == "record"
    ]
    prevalence = prevalence_rows(
        test_record, prevalences, float(splits["test"].labels.mean())
    )
    lofo = lofo_rows(systems, splits["validation"], splits["test"], thresholds)
    ablation = ablation_rows(systems, splits, lambdas)
    leakage = near_duplicate_rows(splits)

    attribute_tables = {}
    character_tables = {}
    curves = {}
    for system in systems:
        if system.loaded is None:
            continue
        if system.loaded.mode != "lexical":
            attribute_tables[system.key] = attribute_table(
                system.loaded, splits["test"].rows, splits["test"].labels
            )
        if system.loaded.mode != "semantic":
            character_tables[system.key] = character_table(
                system.loaded, splits["test"].rows, splits["test"].labels
            )
            curves[system.key] = position_curves(
                system.loaded, splits["test"].rows, splits["test"].labels
            )

    write_csv(output_dir / "metrics.csv", all_metrics)
    write_csv(output_dir / "recall_by_family.csv", family_rows)
    write_csv(output_dir / "fpr_by_profile.csv", profile_rows)
    write_csv(output_dir / "false_positives.csv", false_positives)
    write_csv(output_dir / "prevalence.csv", prevalence)
    write_csv(output_dir / "lofo.csv", lofo)
    write_csv(output_dir / "ablation.csv", ablation)
    write_csv(output_dir / "leakage.csv", leakage)
    write_csv(
        output_dir / "explain_attributes.csv",
        [{"system": s, **row} for s, table in attribute_tables.items() for row in table],
    )
    write_csv(
        output_dir / "explain_characters.csv",
        [{"system": s, **row} for s, table in character_tables.items() for row in table],
    )
    (output_dir / "summary.md").write_text(
        summary_markdown(all_metrics, splits, leakage), encoding="utf-8"
    )
    (output_dir / "ablation.md").write_text(ablation_markdown(ablation), encoding="utf-8")
    principal = next((s for s in reversed(systems) if s.loaded is not None), None)
    if principal is not None:
        (output_dir / "explain_examples.md").write_text(
            explain_examples_markdown(principal, splits["test"], thresholds), encoding="utf-8"
        )

    result: dict[str, object] = {
        "seed": seed,
        "splits": split_description(splits),
        "thresholds": thresholds,
        "consistency": consistency,
        "metrics": all_metrics,
        "recall_by_family": family_rows,
        "fpr_by_profile": profile_rows,
        "false_positive_summary": false_positive_summary(
            systems, splits["test"], thresholds
        ),
        "lofo": lofo,
        "ablation": ablation,
        "leakage": leakage,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if plots:
        keys = [system.key for system in systems]
        plot_curves(systems, splits["test"], thresholds, output_dir)
        plot_prevalence(prevalence, output_dir)
        plot_grouped_bars(
            output_dir / "recall-by-family.png",
            "Recall por família de anomalia no teste (limiar P99)",
            "Recall",
            [r for r in family_rows if r["policy"] == "p99"],
            "group",
            "rate",
            systems_order=keys,
        )
        plot_grouped_bars(
            output_dir / "fpr-by-profile.png",
            "FPR por perfil normal no teste (limiar P99)",
            "FPR",
            [r for r in profile_rows if r["policy"] == "p99"],
            "group",
            "rate",
            systems_order=keys,
        )
        if lofo:
            plot_grouped_bars(
                output_dir / "lofo.png",
                "Leave-one-family-out: recall da família omitida da calibração (melhor F1)",
                "Recall",
                lofo,
                "heldout_family",
                "recall_best_f1_without_family",
                systems_order=keys,
            )
        if attribute_tables:
            plot_explain_attributes(attribute_tables, output_dir)
        if character_tables:
            plot_explain_characters(character_tables, curves, output_dir)
    return result


def print_summary(result: dict[str, object]) -> None:
    print("Teste, por registro (limiares calibrados na validação):")
    print(f"{'sistema':<26}{'limiar':<9}{'prec':>8}{'recall':>8}{'F1':>8}{'FPR':>8}{'ROC-AUC':>9}")
    for row in result["metrics"]:
        if row["split"] == "test" and row["level"] == "record":
            print(
                f"{SYSTEM_LABELS.get(row['system'], row['system']):<26}{row['policy']:<9}"
                f"{row['precision']:>8.4f}{row['recall']:>8.4f}{row['f1']:>8.4f}"
                f"{row['fpr']:>8.4f}{row['roc_auc']:>9.4f}"
            )


def main() -> None:
    args = parse_args()
    result = run(
        args.splits_dir,
        parse_model_dirs(args.model),
        args.output_dir,
        seed=args.seed,
        prevalences=args.prevalences,
        lambdas=args.lambdas,
        top_false_positives=args.top_false_positives,
        plots=not args.no_plots,
        check_consistency=not args.skip_consistency_check,
    )
    print_summary(result)
    print(f"Resultados salvos em: {args.output_dir}")


if __name__ == "__main__":
    main()
