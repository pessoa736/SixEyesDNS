"""Gera gráficos do treinamento e da avaliação do autoencoder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

if __package__:
    from .test_model import generate_test_plot
else:
    from test_model import generate_test_plot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir", type=Path, default=Path("results/autoencoder")
    )
    parser.add_argument(
        "--splits-dir", type=Path, default=Path("data/processed/splits")
    )
    parser.add_argument("--show", action="store_true", help="Abre os gráficos ao final")
    parser.add_argument("--test-samples", type=int, default=6)
    return parser.parse_args()


def read_json(path: Path) -> object:
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo de resultado não encontrado: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def plot_history(history: list[dict[str, float]], output_dir: Path) -> None:
    epochs = [item["epoch"] for item in history]
    train_loss = [item["train_loss"] for item in history]
    validation_loss = [item["validation_loss"] for item in history]

    figure, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(epochs, train_loss, label="Treino")
    axes[0].plot(epochs, validation_loss, label="Validação normal")
    axes[0].set_title("Perda de reconstrução")
    axes[0].set_ylabel("MSE")
    axes[0].grid(alpha=0.25)
    axes[0].legend()

    if "validation_accuracy" in history[0]:
        accuracy = [item["validation_accuracy"] for item in history]
        axes[1].plot(epochs, accuracy, label="Validação - P99", color="tab:green")
        axes[1].set_title("Accuracy de classificação")
        axes[1].set_ylabel("Accuracy")
        axes[1].set_ylim(0, 1.05)
        axes[1].grid(alpha=0.25)
        axes[1].legend()
    else:
        axes[1].text(0.5, 0.5, "Accuracy não disponível neste histórico", ha="center")
        axes[1].set_axis_off()
    axes[1].set_xlabel("Época")
    figure.tight_layout()
    figure.savefig(output_dir / "losses.png", dpi=150)


def plot_metrics(metrics: dict[str, object], output_dir: Path) -> None:
    if "validation_percentile_99" not in metrics:
        labels = ("Validação", "Teste")
        values = (float(metrics["validation_accuracy"]), float(metrics["test_accuracy"]))
        figure, axis = plt.subplots(figsize=(7, 5))
        bars = axis.bar(labels, values, color=("tab:blue", "tab:orange"))
        axis.set_title("Accuracy do modelo")
        axis.set_ylabel("Accuracy")
        axis.set_ylim(0, 1.05)
        axis.grid(axis="y", alpha=0.25)
        axis.bar_label(bars, fmt="%.4f", padding=3)
        figure.tight_layout()
        figure.savefig(output_dir / "metrics.png", dpi=150)
        return
    names = (
        "validation_percentile_99",
        "validation_best_f1",
        "test_percentile_99",
        "test_best_f1",
    )
    labels = ("Val P99", "Val melhor F1", "Teste P99", "Teste melhor F1")
    metric_names = ("accuracy", "precision", "recall", "f1", "roc_auc")
    x = np.arange(len(labels))
    width = 0.16

    figure, axis = plt.subplots(figsize=(10, 5))
    for index, metric_name in enumerate(metric_names):
        values = [
            float(metrics[name][metric_name]) if metrics[name][metric_name] is not None else 0.0
            for name in names
        ]
        axis.bar(x + (index - 2) * width, values, width, label=metric_name.upper())
    axis.set_title("Métricas por conjunto e limiar")
    axis.set_ylabel("Valor")
    axis.set_ylim(0, 1.05)
    axis.set_xticks(x, labels)
    axis.grid(axis="y", alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_dir / "metrics.png", dpi=150)


def plot_confusion_matrices(metrics: dict[str, object], output_dir: Path) -> None:
    if "validation_percentile_99" not in metrics:
        return
    names = ("test_percentile_99", "test_best_f1")
    titles = ("Teste - percentil 99", "Teste - melhor F1")
    figure, axes = plt.subplots(1, 2, figsize=(9, 4))
    for axis, name, title in zip(axes, names, titles):
        matrix = np.asarray(metrics[name]["confusion_matrix"])
        image = axis.imshow(matrix, cmap="Blues")
        for row in range(matrix.shape[0]):
            for column in range(matrix.shape[1]):
                axis.text(column, row, int(matrix[row, column]), ha="center", va="center")
        axis.set_title(title)
        axis.set_xlabel("Predito")
        axis.set_ylabel("Real")
        axis.set_xticks((0, 1), ("normal", "suspeita"))
        axis.set_yticks((0, 1), ("normal", "suspeita"))
        figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
    figure.tight_layout()
    figure.savefig(output_dir / "confusion-matrices.png", dpi=150)


def plot_score_distributions(metrics: dict[str, object], output_dir: Path) -> None:
    if "score_distributions" not in metrics:
        figure, axis = plt.subplots(figsize=(9, 5))
        validation = np.asarray(metrics["validation_scores"])
        test = np.asarray(metrics["test_scores"])
        threshold = float(metrics["threshold"])
        axis.hist(validation, bins=35, alpha=0.6, label="validação")
        axis.hist(test, bins=35, alpha=0.6, label="teste")
        axis.axvline(threshold, color="black", linestyle="--", label=f"P99={threshold:.3f}")
        axis.set_title("Scores combinados do modelo")
        axis.set_xlabel("Score normalizado (texto + numérico)")
        axis.set_ylabel("Quantidade")
        axis.grid(alpha=0.2)
        axis.legend()
        figure.tight_layout()
        figure.savefig(output_dir / "score-distributions.png", dpi=150)
        return
    distributions = metrics["score_distributions"]
    figure, axes = plt.subplots(2, 2, figsize=(13, 8))
    for row, (prefix, title) in enumerate(
        (
            ("validation", "Validação"),
            ("test", "Teste"),
        )
    ):
        normal = np.asarray(distributions[f"{prefix}_normal"])
        anomaly = np.asarray(distributions[f"{prefix}_anomaly"])
        threshold = float(metrics[f"{prefix}_percentile_99"]["threshold"])
        combined = np.concatenate((normal, anomaly))
        positive_scores = combined[combined > 0]
        full_bins = np.geomspace(
            max(float(positive_scores.min()), 1e-8),
            float(positive_scores.max()),
            36,
        )
        zoom_limit = max(float(np.percentile(normal, 99.5)), threshold) * 1.15
        zoom_bins = np.linspace(0, zoom_limit, 36)
        for axis, bins, subtitle, values_limit in (
            (axes[row, 0], full_bins, "visão completa", None),
            (axes[row, 1], zoom_bins, "zoom nos scores baixos", zoom_limit),
        ):
            axis.hist(normal, bins=bins, alpha=0.65, label="normal")
            axis.hist(anomaly, bins=bins, alpha=0.65, label="suspeita")
            axis.axvline(threshold, color="black", linestyle="--", label=f"P99={threshold:.3f}")
            axis.set_title(f"{title} - {subtitle}")
            axis.set_xlabel("MSE de reconstrução")
            axis.set_ylabel("Quantidade")
            if values_limit is None:
                axis.set_xscale("log")
            if values_limit is not None:
                axis.set_xlim(0, values_limit)
            axis.grid(alpha=0.2)
            axis.legend(fontsize=8)
        print(
            f"{title}: normal mediana={np.median(normal):.4f}, "
            f"p99={np.percentile(normal, 99):.4f}; "
            f"suspeita mediana={np.median(anomaly):.4f}"
        )
    figure.tight_layout()
    figure.savefig(output_dir / "score-distributions.png", dpi=150)


def plot_thresholds(metrics: dict[str, object], output_dir: Path) -> None:
    if "validation_percentile_99" not in metrics:
        threshold = float(metrics["threshold"])
        figure, axis = plt.subplots(figsize=(7, 4))
        bar = axis.bar(["Híbrido - P99"], [threshold], color="tab:purple")
        axis.set_title("Limiar do modelo")
        axis.set_ylabel("Score combinado")
        axis.bar_label(bar, fmt="%.4f", padding=3)
        figure.tight_layout()
        figure.savefig(output_dir / "thresholds.png", dpi=150)
        return
    names = ("validation_percentile_99", "validation_best_f1", "test_percentile_99", "test_best_f1")
    labels = ("Val P99", "Val F1", "Teste P99", "Teste F1")
    thresholds = [float(metrics[name]["threshold"]) for name in names]
    figure, axis = plt.subplots(figsize=(9, 4))
    bars = axis.bar(labels, thresholds, color=("tab:blue", "tab:orange", "tab:green", "tab:red"))
    axis.set_title("Limiares de classificação")
    axis.set_ylabel("MSE de reconstrução")
    axis.grid(axis="y", alpha=0.2)
    axis.bar_label(bars, fmt="%.4f", padding=3)
    figure.tight_layout()
    figure.savefig(output_dir / "thresholds.png", dpi=150)


def main() -> None:
    args = parse_args()
    args.results_dir.mkdir(parents=True, exist_ok=True)
    history = read_json(args.results_dir / "history.json")
    metrics = read_json(args.results_dir / "metrics.json")
    if not isinstance(history, list) or not isinstance(metrics, dict):
        raise ValueError("Formato inválido em history.json ou metrics.json")

    plot_history(history, args.results_dir)
    plot_metrics(metrics, args.results_dir)
    plot_confusion_matrices(metrics, args.results_dir)
    plot_score_distributions(metrics, args.results_dir)
    plot_thresholds(metrics, args.results_dir)
    test_plot = generate_test_plot(
        args.splits_dir,
        args.results_dir,
        samples=args.test_samples,
        show=args.show,
    )
    print(f"Graficos salvos em: {args.results_dir}")
    print(f"Grafico de teste salvo em: {test_plot}")
    if args.show:
        plt.show()
    else:
        plt.close("all")


if __name__ == "__main__":
    main()
