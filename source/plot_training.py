"""Gera gráficos do treinamento e da avaliação do autoencoder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from matplotlib.axes import Axes
from matplotlib.image import AxesImage
from matplotlib.ticker import NullLocator, PercentFormatter

if __package__:
    from .models import LOSS_DESCRIPTIONS
    from .scoring import (
        CHUNK_SIZE,
        DEFAULT_PERCENTILE,
        LoadedModel,
        anomaly_labels,
        encode_domains,
        load_checkpoint,
        numeric_tensor,
        percentile_threshold,
        read_rows,
    )
    from .test_model import MODE_NAMES, generate_test_plots
else:
    from models import LOSS_DESCRIPTIONS
    from scoring import (
        CHUNK_SIZE,
        DEFAULT_PERCENTILE,
        LoadedModel,
        anomaly_labels,
        encode_domains,
        load_checkpoint,
        numeric_tensor,
        percentile_threshold,
        read_rows,
    )
    from test_model import MODE_NAMES, generate_test_plots


CLASS_NAMES = ("normal", "suspeita")
SCORE_LABELS = {
    "lexical": "z(CE dos caracteres)",
    "semantic": "z(MSE dos atributos)",
    "hybrid": "z(CE) + λ·z(MSE)",
}
NORMAL_COLOR = "tab:blue"
ANOMALY_COLOR = "tab:orange"
BEST_EPOCH_COLOR = "tab:red"
ZOOM_FRACTION = 0.20
MIN_ZOOM_EPOCHS = 50
FULL_BINS = 60
ZOOM_BINS = 40
ZOOM_HEADROOM = 8
SCORE_TICKS = (-100, -50, -20, -10, -5, -2, 0, 2, 5, 10, 20, 50, 100, 200, 500, 1000)
SCORE_TOLERANCE = 1e-3


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
        help=(
            "Total de exemplos do teste (par, metade por classe); "
            "cada figura test-samples*.png mostra até 6"
        ),
    )
    return parser.parse_args()


def read_json(path: Path) -> object:
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo de resultado não encontrado: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def loss_label(history: list[dict[str, float]]) -> str:
    """Nome da perda conforme o modo do histórico; o híbrido inclui o λ."""
    first = history[0]
    mode = first.get("mode")
    description = LOSS_DESCRIPTIONS.get(mode, "perda de reconstrução")
    if mode == "hybrid" and "lambda" in first:
        return f"{description} (λ = {first['lambda']:g})"
    return description


def best_epoch_position(history: list[dict[str, float]]) -> int:
    """Posição da menor perda de validação, que é a época do checkpoint salvo."""
    return int(np.argmin([item["validation_loss"] for item in history]))


def zoom_start(total_epochs: int) -> int:
    """Posição inicial do zoom: últimos 20% das épocas, no mínimo 50."""
    length = max(MIN_ZOOM_EPOCHS, int(np.ceil(ZOOM_FRACTION * total_epochs)))
    return max(0, total_epochs - length)


def mark_best_epoch(axis: Axes, epoch: int, value: float, label: str) -> None:
    """Linha vertical e estrela sobre a época do checkpoint."""
    axis.axvline(
        epoch, color=BEST_EPOCH_COLOR, linestyle="--", linewidth=1.0, label=label
    )
    axis.plot(
        epoch,
        value,
        marker="*",
        markersize=12,
        color=BEST_EPOCH_COLOR,
        linestyle="none",
        zorder=5,
    )


def plot_history(history: list[dict[str, float]], output_dir: Path) -> Path:
    """Perda completa e em zoom no trecho final, com a melhor época, e accuracy."""
    if not history:
        raise ValueError("O histórico de treinamento está vazio")
    epochs = np.asarray([item["epoch"] for item in history])
    train_loss = np.asarray([item["train_loss"] for item in history])
    validation_loss = np.asarray([item["validation_loss"] for item in history])
    best = best_epoch_position(history)
    best_epoch = int(epochs[best])
    best_loss = float(validation_loss[best])
    start = zoom_start(len(history))
    loss_name = loss_label(history)
    mode = history[0].get("mode")

    figure = plt.figure(figsize=(13, 8.5), layout="constrained")
    grid = figure.add_gridspec(2, 2, height_ratios=(1.1, 0.9))
    loss_axis = figure.add_subplot(grid[0, 0])
    zoom_axis = figure.add_subplot(grid[0, 1])
    accuracy_axis = figure.add_subplot(grid[1, :])
    if mode in MODE_NAMES:
        figure.suptitle(f"Treinamento do autoencoder {MODE_NAMES[mode]}")

    for axis, begin in ((loss_axis, 0), (zoom_axis, start)):
        axis.plot(epochs[begin:], train_loss[begin:], label="Treino", linewidth=1.1)
        axis.plot(
            epochs[begin:],
            validation_loss[begin:],
            label="Validação normal",
            linewidth=1.1,
        )
        axis.set_xlabel("Época")
        axis.set_ylabel(loss_name)
        axis.grid(alpha=0.25)
    loss_axis.set_title("Perda de reconstrução")
    mark_best_epoch(
        loss_axis,
        best_epoch,
        best_loss,
        f"Melhor época (checkpoint): {best_epoch}",
    )
    zoom_axis.set_title(
        f"Zoom no trecho final: épocas {int(epochs[start])} a {int(epochs[-1])}"
    )
    if best >= start:
        mark_best_epoch(
            zoom_axis,
            best_epoch,
            best_loss,
            f"Melhor época: {best_epoch} (validação = {best_loss:.4f})",
        )
    else:
        zoom_axis.plot(
            (epochs[start], epochs[-1]),
            (best_loss, best_loss),
            color=BEST_EPOCH_COLOR,
            linestyle=":",
            label=(
                f"Melhor validação = {best_loss:.4f} "
                f"(época {best_epoch}, fora do recorte)"
            ),
        )
    loss_axis.legend()
    zoom_axis.legend()

    if "validation_accuracy" in history[0]:
        accuracy = np.asarray([item["validation_accuracy"] for item in history])
        accuracy_axis.plot(
            epochs, accuracy, label="Validação - P99", color="tab:green", linewidth=1.0
        )
        mark_best_epoch(
            accuracy_axis,
            best_epoch,
            float(accuracy[best]),
            f"Melhor época (checkpoint): {best_epoch}",
        )
        accuracy_axis.annotate(
            f"accuracy = {accuracy[best]:.4f}",
            (best_epoch, accuracy[best]),
            textcoords="offset points",
            xytext=(12, -26),
            color=BEST_EPOCH_COLOR,
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.9},
        )
        accuracy_axis.set_title("Accuracy de classificação na validação")
        accuracy_axis.set_ylabel("Accuracy")
        accuracy_axis.set_ylim(0, 1.05)
        accuracy_axis.grid(alpha=0.25)
        accuracy_axis.legend(loc="lower right")
    else:
        accuracy_axis.text(
            0.5, 0.5, "Accuracy não disponível neste histórico", ha="center"
        )
        accuracy_axis.set_axis_off()
    accuracy_axis.set_xlabel("Época")
    output = output_dir / "losses.png"
    figure.savefig(output, dpi=150)
    return output


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


def readable_text_color(background: tuple[float, ...]) -> str:
    """Branco sobre fundo escuro e preto sobre fundo claro (contraste WCAG máximo)."""
    red, green, blue = (
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in background[:3]
    )
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return "white" if luminance < 0.179 else "black"


def draw_confusion_matrix(
    axis: Axes,
    matrix: object,
    title: str,
    class_names: tuple[str, ...] = CLASS_NAMES,
) -> AxesImage:
    """Desenha contagens e % por classe real (linha normalizada) em um eixo.

    A cor codifica o percentual da linha, então classes raras ficam comparáveis.
    Devolve a imagem para o chamador criar a barra de cores.
    """
    counts = np.asarray(matrix, dtype=float)
    size = len(class_names)
    if counts.shape != (size, size):
        raise ValueError(
            f"A matriz de confusão precisa ser {size}x{size}, recebida {counts.shape}"
        )
    totals = counts.sum(axis=1, keepdims=True)
    rates = np.divide(counts, totals, out=np.zeros_like(counts), where=totals > 0)
    image = axis.imshow(rates, cmap="Blues", vmin=0.0, vmax=1.0)
    for row, column in np.ndindex(counts.shape):
        percent = f"{rates[row, column]:.1%}" if totals[row, 0] else "–"
        axis.text(
            column,
            row,
            f"{int(counts[row, column])}\n{percent}",
            ha="center",
            va="center",
            color=readable_text_color(image.cmap(image.norm(rates[row, column]))),
            fontsize=13,
            fontweight="bold",
        )
    axis.set_title(title)
    axis.set_xlabel("Predito")
    axis.set_ylabel("Real")
    axis.set_xticks(range(size), class_names)
    axis.set_yticks(
        range(size),
        [f"{name}\n(n={int(total)})" for name, total in zip(class_names, totals[:, 0])],
    )
    return image


def validation_threshold(metrics: dict[str, object]) -> float:
    """Limiar P99 dos scores normais da validação salvo nas métricas."""
    if "threshold" in metrics:
        return float(metrics["threshold"])
    return float(metrics["validation_percentile_99"]["threshold"])


def plot_confusion_matrices(metrics: dict[str, object], output_dir: Path) -> Path | None:
    """Matrizes de confusão com contagens e percentuais por classe real."""
    if "validation_percentile_99" in metrics:
        matrices = [
            ("Teste - percentil 99", metrics["test_percentile_99"]["confusion_matrix"]),
            ("Teste - melhor F1", metrics["test_best_f1"]["confusion_matrix"]),
        ]
    elif "test_confusion_matrix" in metrics:
        threshold = validation_threshold(metrics)
        matrices = [
            (
                f"Validação - limiar P{DEFAULT_PERCENTILE:g} = {threshold:.3f}",
                metrics["validation_confusion_matrix"],
            ),
            (
                f"Teste - limiar P{DEFAULT_PERCENTILE:g} da validação = {threshold:.3f}",
                metrics["test_confusion_matrix"],
            ),
        ]
    else:
        return None
    figure, axes = plt.subplots(
        1, len(matrices), figsize=(5.4 * len(matrices) + 1.2, 5), layout="constrained"
    )
    for axis, (title, values) in zip(np.atleast_1d(axes), matrices):
        image = draw_confusion_matrix(axis, values, title)
    colorbar = figure.colorbar(
        image, ax=axes, fraction=0.04, pad=0.03, format=PercentFormatter(1.0)
    )
    colorbar.set_label("Percentual da classe real")
    output = output_dir / "confusion-matrices.png"
    figure.savefig(output, dpi=150)
    return output


def verify_saved_scores(
    saved: object,
    rows: list[dict[str, str]],
    split: str,
    loaded: LoadedModel | None = None,
) -> np.ndarray:
    """Confere quantidade e ordem dos scores salvos contra as linhas do split.

    A ordem só é confirmada quando ``loaded`` é informado: as linhas são
    reavaliadas com o checkpoint e comparadas com os scores salvos.
    """
    scores = np.asarray(saved, dtype=float)
    if scores.ndim != 1 or len(scores) != len(rows):
        raise ValueError(
            f"Quantidade divergente em {split}: {scores.size} scores salvos para "
            f"{len(rows)} linhas no split. Regenere o split ou retreine o modelo "
            "(--fresh) antes de plotar."
        )
    if loaded is not None:
        fresh = loaded.score(rows)
        if not np.allclose(scores, fresh, rtol=SCORE_TOLERANCE, atol=SCORE_TOLERANCE):
            worst = int(np.argmax(np.abs(scores - fresh)))
            raise ValueError(
                f"Os scores salvos de {split} não coincidem com a reavaliação do "
                "checkpoint (ordem das linhas ou modelo diferentes): "
                f"linha {worst}, salvo={scores[worst]:.4f}, "
                f"reavaliado={fresh[worst]:.4f}."
            )
    return scores


def load_split_scores(
    metrics: dict[str, object],
    split: str,
    splits_dir: Path,
    loaded: LoadedModel | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Scores salvos e rótulos binários (1 = suspeita) do split, já verificados."""
    key = f"{split}_scores"
    if key not in metrics:
        raise ValueError(f"metrics.json não contém {key}; retreine o modelo")
    rows = read_rows(splits_dir / f"{split}.csv")
    return verify_saved_scores(metrics[key], rows, split, loaded), anomaly_labels(rows)


def verify_validation_threshold(
    threshold: float, validation_scores: np.ndarray, validation_labels: np.ndarray
) -> None:
    """Confere que o limiar desenhado é o P99 dos scores normais da validação."""
    expected = percentile_threshold(validation_scores[validation_labels == 0])
    if not np.isclose(threshold, expected, rtol=SCORE_TOLERANCE, atol=SCORE_TOLERANCE):
        raise ValueError(
            f"O limiar salvo ({threshold:.4f}) não é o P{DEFAULT_PERCENTILE:g} dos "
            f"scores normais da validação ({expected:.4f})."
        )


def zoom_window(normal_scores: np.ndarray, threshold: float) -> tuple[float, float]:
    """Recorte simétrico ao redor do limiar que cobre o corpo dos scores normais."""
    low, high = np.percentile(normal_scores, (0.5, 99.5))
    half_width = 1.05 * max(threshold - low, high - threshold, 1e-3)
    return float(threshold - half_width), float(threshold + half_width)


def asinh_edges(low: float, high: float, linear_width: float, bins: int) -> np.ndarray:
    """Limites de classes uniformes na escala arcsinh (centro linear, caudas log)."""
    ends = np.arcsinh(np.asarray((low, high)) / linear_width)
    edges = linear_width * np.sinh(np.linspace(ends[0], ends[1], bins + 1))
    edges[0], edges[-1] = low, high
    return edges


def asinh_limits(
    low: float, high: float, linear_width: float, margin: float = 0.02
) -> tuple[float, float]:
    """Amplia [low, high] em ``margin`` da largura visual da escala arcsinh."""
    ends = np.arcsinh(np.asarray((low, high)) / linear_width)
    pad = margin * (ends[1] - ends[0]) or 1e-3
    return tuple(float(value) for value in linear_width * np.sinh(ends + (-pad, pad)))


def asinh_ticks(
    low: float, high: float, linear_width: float, min_gap: float = 0.05
) -> list[float]:
    """Marcas legíveis para a escala arcsinh, sem rótulos sobrepostos."""

    def position(value: float) -> float:
        return float(np.arcsinh(value / linear_width))

    span = position(high) - position(low)
    ticks: list[float] = []
    for value in SCORE_TICKS:
        if low <= value <= high and (
            not ticks or position(value) - position(ticks[-1]) >= min_gap * span
        ):
            ticks.append(float(value))
    return ticks


def outside_counts(
    scores: np.ndarray, labels: np.ndarray, low: float, high: float
) -> dict[str, tuple[int, int, int]]:
    """Por classe: pontos abaixo do recorte, acima do recorte e total."""
    counts = {}
    for value, name in enumerate(CLASS_NAMES):
        selected = scores[labels == value]
        counts[name] = (
            int((selected < low).sum()),
            int((selected > high).sum()),
            len(selected),
        )
    return counts


def draw_score_histogram(
    axis: Axes,
    scores: np.ndarray,
    labels: np.ndarray,
    edges: np.ndarray,
    threshold: float,
    outside: dict[str, tuple[int, int, int]] | None = None,
) -> None:
    """Histogramas sobrepostos por classe e a linha do limiar da validação.

    Com ``outside``, a legenda informa quantos pontos de cada classe ficaram fora
    do recorte do eixo x.
    """
    for value, name, color in (
        (0, CLASS_NAMES[0], NORMAL_COLOR),
        (1, CLASS_NAMES[1], ANOMALY_COLOR),
    ):
        selected = scores[labels == value]
        label = f"{name} (n={len(selected)})"
        if outside is not None:
            below, above, _ = outside[name]
            label += f"; fora do recorte: {below + above}"
        axis.hist(selected, bins=edges, color=color, alpha=0.6, label=label)
    axis.axvline(
        threshold,
        color="black",
        linestyle="--",
        linewidth=1.4,
        label=f"Limiar = P{DEFAULT_PERCENTILE:g} da validação ({threshold:.3f})",
    )
    axis.grid(alpha=0.2)


def plot_score_distributions(
    metrics: dict[str, object], output_dir: Path, splits_dir: Path
) -> Path:
    """Distribuição dos scores por classe: visão completa e zoom perto do limiar.

    Falha se os scores salvos não corresponderem às linhas e à ordem dos splits.
    Validação e teste compartilham o eixo x de cada coluna; o limiar é sempre o
    P99 dos normais da validação.
    """
    threshold = validation_threshold(metrics)
    loaded = load_checkpoint(output_dir)
    splits = [
        (title, *load_split_scores(metrics, split, splits_dir, loaded))
        for split, title in (("validation", "Validação"), ("test", "Teste"))
    ]
    verify_validation_threshold(threshold, splits[0][1], splits[0][2])
    all_scores = np.concatenate([scores for _, scores, _ in splits])
    normal_scores = np.concatenate(
        [scores[labels == 0] for _, scores, labels in splits]
    )
    zoom_low, zoom_high = zoom_window(normal_scores, threshold)
    linear_width = (zoom_high - zoom_low) / 2
    full_low, full_high = asinh_limits(
        float(all_scores.min()), float(all_scores.max()), linear_width
    )
    full_edges = asinh_edges(full_low, full_high, linear_width, FULL_BINS)
    zoom_edges = np.linspace(zoom_low, zoom_high, ZOOM_BINS + 1)
    score_label = f"Score: {SCORE_LABELS.get(loaded.mode, 'combinado')}"

    figure, axes = plt.subplots(
        2, 2, figsize=(14, 9), sharex="col", sharey="col", layout="constrained"
    )
    for row, (title, scores, labels) in enumerate(splits):
        full_axis, zoom_axis = axes[row]
        draw_score_histogram(full_axis, scores, labels, full_edges, threshold)
        full_axis.axvspan(
            zoom_low, zoom_high, color="0.5", alpha=0.12, zorder=0, label="Recorte do zoom"
        )
        full_axis.set_xscale("asinh", linear_width=linear_width)
        full_axis.set_xlim(full_low, full_high)
        ticks = asinh_ticks(full_low, full_high, linear_width)
        if len(ticks) >= 2:
            full_axis.set_xticks(ticks, [f"{tick:g}" for tick in ticks])
        full_axis.xaxis.set_minor_locator(NullLocator())
        full_axis.set_title(f"{title} - visão completa (escala arcsinh)")
        full_axis.set_ylabel("Quantidade")
        full_axis.legend(fontsize=8, loc="upper right")

        outside = outside_counts(scores, labels, zoom_low, zoom_high)
        draw_score_histogram(zoom_axis, scores, labels, zoom_edges, threshold, outside)
        zoom_axis.set_yscale("log")
        zoom_axis.set_xlim(zoom_low, zoom_high)
        zoom_axis.set_title(f"{title} - zoom perto do limiar")
        zoom_axis.set_ylabel("Quantidade (escala log)")
    top = axes[0, 1].get_ylim()[1]
    axes[0, 1].set_ylim(0.8, top * ZOOM_HEADROOM)
    for row in range(2):
        axes[row, 1].legend(fontsize=8, loc="upper center")
    for column in range(2):
        axes[1, column].set_xlabel(score_label)
    output = output_dir / "score-distributions.png"
    figure.savefig(output, dpi=150)
    return output


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


def latent_codes(loaded: LoadedModel, rows: list[dict[str, str]]) -> np.ndarray:
    """Códigos latentes das linhas (lexical, semântico ou híbrido), em blocos."""
    characters = encode_domains(rows)
    numeric = numeric_tensor(rows, loaded.scaler)
    parts = []
    with torch.no_grad():
        for start in range(0, len(rows), CHUNK_SIZE):
            chunk = slice(start, start + CHUNK_SIZE)
            if loaded.mode == "lexical":
                latent = loaded.model.encode(characters[chunk])
            else:
                latent = loaded.model.encode(
                    characters[chunk], numeric[chunk], mode=loaded.mode
                )
            parts.append(latent.numpy())
    return np.concatenate(parts)


def plot_latent_space(
    splits_dir: Path, results_dir: Path, max_points: int = 4000
) -> Path | None:
    """Projeta o teste no espaço latente e desenha pontos por classe/família."""
    test_path = splits_dir / "test.csv"
    if not (results_dir / "model.pt").is_file() or not test_path.is_file():
        return None
    loaded = load_checkpoint(results_dir)
    latent_dim = int(loaded.checkpoint["latent_dim"])
    if latent_dim < 2:
        return None
    rows = read_rows(test_path)
    points = latent_codes(loaded, rows)
    mode = loaded.mode

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
        "#38bdf8", "#a78bfa", "#34d399", "#fbbf24", "#f87171",
        "#f472b6", "#a3e635", "#fb923c", "#22d3ee", "#e879f9",
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
        loc="best",
        fontsize=9,
        markerscale=3,
        facecolor="#111827",
        labelcolor="#e5e7eb",
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
    test_plots = generate_test_plots(
        args.splits_dir,
        args.results_dir,
        samples=args.test_samples,
        show=args.show,
    )
    print(f"Graficos salvos em: {args.results_dir}")
    if latent_plot is not None:
        print(f"Grafico do espaco latente salvo em: {latent_plot}")
    for test_plot in test_plots:
        print(f"Grafico de teste salvo em: {test_plot}")
    if args.show:
        plt.show()
    else:
        plt.close("all")


if __name__ == "__main__":
    main()
