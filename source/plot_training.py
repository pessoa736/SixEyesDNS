"""Gera gráficos do treinamento e da avaliação do autoencoder."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.preprocessing import StandardScaler

if __package__:
    from .features import FEATURE_COLUMNS, transform_features
    from .models import CharAutoencoder, HybridAutoencoder
    from .test_model import generate_test_plot
    from .train import encode_domains
else:
    from features import FEATURE_COLUMNS, transform_features
    from models import CharAutoencoder, HybridAutoencoder
    from test_model import generate_test_plot
    from train import encode_domains


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir", type=Path, default=Path("results/autoencoder")
    )
    parser.add_argument(
        "--splits-dir", type=Path, default=Path("data/processed/splits")
    )
    parser.add_argument("--show", action="store_true", help="Abre os gráficos ao final")
    parser.add_argument(
        "--test-samples",
        type=int,
        default=6,
        help="Total de exemplos no gráfico, igualmente dividido entre as classes",
    )
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
    if "validation_percentile_99" in metrics:
        matrices = [
            ("Teste - percentil 99", metrics["test_percentile_99"]["confusion_matrix"]),
            ("Teste - melhor F1", metrics["test_best_f1"]["confusion_matrix"]),
        ]
    elif "test_confusion_matrix" in metrics:
        matrices = [
            ("Validação - P99", metrics["validation_confusion_matrix"]),
            ("Teste - P99", metrics["test_confusion_matrix"]),
        ]
    else:
        return
    figure, axes = plt.subplots(1, 2, figsize=(9, 4))
    for axis, (title, values) in zip(axes, matrices):
        matrix = np.asarray(values)
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


def read_split_labels(splits_dir: Path, split: str, expected: int) -> np.ndarray | None:
    """Lê os rótulos de um split na mesma ordem dos scores salvos."""
    path = splits_dir / f"{split}.csv"
    if not path.is_file():
        return None
    with path.open(newline="", encoding="utf-8") as file:
        labels = np.asarray(
            [row.get("label") != "normal" for row in csv.DictReader(file)],
            dtype=bool,
        )
    return labels if len(labels) == expected else None


def plot_score_distributions(
    metrics: dict[str, object], output_dir: Path, splits_dir: Path
) -> None:
    if "score_distributions" not in metrics:
        threshold = float(metrics["threshold"])
        figure, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
        for axis, split, title in (
            (axes[0], "validation", "Validação"),
            (axes[1], "test", "Teste"),
        ):
            scores = np.asarray(metrics[f"{split}_scores"], dtype=float)
            labels = read_split_labels(splits_dir, split, len(scores))
            low = float(np.percentile(scores, 0.5))
            high = max(
                float(np.percentile(scores, 99.5)),
                threshold * 1.05,
            )
            if high <= low:
                high = low + 1e-8
            bins = np.linspace(low, high, 41)
            if labels is None:
                axis.hist(scores, bins=bins, alpha=0.65, label="scores")
            else:
                axis.hist(scores[~labels], bins=bins, alpha=0.65, label="normal")
                axis.hist(scores[labels], bins=bins, alpha=0.65, label="suspeita")
            axis.axvline(
                threshold, color="black", linestyle="--", label=f"P99={threshold:.3f}"
            )
            axis.set_title(f"{title} - distribuição dos scores")
            axis.set_xlabel("Score combinado")
            axis.set_ylabel("Quantidade")
            axis.set_xlim(low, high)
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
        # O limiar já aparece como linha no gráfico de distribuição dos scores.
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


def plot_latent_space(
    splits_dir: Path, results_dir: Path, max_points: int = 4000
) -> Path | None:
    """Projeta o teste no espaço latente e desenha pontos por classe/família."""
    checkpoint_path = results_dir / "model.pt"
    test_path = splits_dir / "test.csv"
    if not checkpoint_path.is_file() or not test_path.is_file():
        return None
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    mode = checkpoint.get("mode", "hybrid")
    latent_dim = int(checkpoint["latent_dim"])
    if latent_dim < 2:
        return None
    if mode == "lexical":
        model: torch.nn.Module = CharAutoencoder(
            len(checkpoint["vocabulary"]),
            int(checkpoint["max_length"]),
            latent_dim,
        )
    else:
        model = HybridAutoencoder(
            len(checkpoint["feature_columns"]),
            len(checkpoint["vocabulary"]),
            int(checkpoint["max_length"]),
            latent_dim,
        )
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    with test_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        return None
    characters = encode_domains(rows)
    scaler = StandardScaler()
    scaler.mean_ = np.asarray(checkpoint["scaler_mean"], dtype=np.float64)
    scaler.scale_ = np.asarray(checkpoint["scaler_scale"], dtype=np.float64)
    numeric = torch.from_numpy(
        scaler.transform(transform_features(rows)).astype(np.float32)
    )
    with torch.no_grad():
        if mode == "lexical":
            latent = model.encode(characters)
        else:
            latent = model.encode(characters, numeric, mode=mode)
    points = latent.numpy()

    labels = np.asarray([row["label"] for row in rows])
    families = np.asarray([row.get("family", "") for row in rows])
    normal_profiles = np.asarray(
        [
            row.get("profile", "normal") if label == "normal" else ""
            for row, label in zip(rows, labels)
        ]
    )
    groups: list[tuple[str, np.ndarray]] = [("normal", labels == "normal")]
    hard = (labels == "normal") & (normal_profiles != "normal")
    if hard.any():
        groups = [("normal", (labels == "normal") & ~hard), ("normal difícil", hard)]
    for family in sorted({family for family in families if family != "normal"}):
        groups.append((family, families == family))

    palette = (
        "#7dd3fc", "#c4b5fd", "#4ade80", "#fbbf24", "#fb7185",
        "#f472b6", "#38bdf8", "#a3e635", "#f97316", "#e879f9",
    )
    background = "#0b0f19"
    rng = np.random.default_rng(42)
    figure, axis = plt.subplots(figsize=(9, 7), facecolor=background)
    axis.set_facecolor(background)
    for color, (name, mask) in zip(palette, groups):
        if not mask.any():
            continue
        indices = np.flatnonzero(mask)
        if len(indices) > max_points:
            indices = rng.choice(indices, size=max_points, replace=False)
        axis.scatter(
            points[indices, 0],
            points[indices, 1],
            s=4,
            alpha=0.75,
            linewidths=0,
            color=color,
            label=name,
        )
    axis.set_xlabel("primeira dimensão do código latente", color="#d1d5db")
    axis.set_ylabel("segunda dimensão do código latente", color="#d1d5db")
    axis.set_title(
        f"Teste no espaço latente ({mode}, {latent_dim}D)", color="#e5e7eb"
    )
    axis.grid(alpha=0.15, color="#4b5563")
    axis.tick_params(colors="#9ca3af")
    for spine in axis.spines.values():
        spine.set_color("#374151")
    legend = axis.legend(
        loc="best", fontsize=9, facecolor="#111827", labelcolor="#e5e7eb"
    )
    legend.get_frame().set_edgecolor("#374151")
    figure.tight_layout()
    output = results_dir / "latent-space.png"
    figure.savefig(output, dpi=150, facecolor=background)
    plt.close(figure)
    return output


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
    plot_score_distributions(metrics, args.results_dir, args.splits_dir)
    plot_thresholds(metrics, args.results_dir)
    latent_plot = plot_latent_space(args.splits_dir, args.results_dir)
    test_plot = generate_test_plot(
        args.splits_dir,
        args.results_dir,
        samples=args.test_samples,
        show=args.show,
    )
    print(f"Graficos salvos em: {args.results_dir}")
    if latent_plot is not None:
        print(f"Grafico do espaco latente salvo em: {latent_plot}")
    print(f"Grafico de teste salvo em: {test_plot}")
    if args.show:
        plt.show()
    else:
        plt.close("all")


if __name__ == "__main__":
    main()
