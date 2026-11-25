"""Testes dos gráficos: perdas, matrizes de confusão, scores e amostras do teste."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.image import AxesImage
from matplotlib.text import Text

from source import plot_training
from source.features import FEATURE_COLUMNS, normalize_domain
from source.plot_training import (
    asinh_edges,
    best_epoch_position,
    draw_confusion_matrix,
    draw_score_histogram,
    loss_label,
    outside_counts,
    plot_history,
    plot_latent_space,
    plot_score_distributions,
    readable_text_color,
    verify_saved_scores,
    verify_validation_threshold,
    zoom_start,
    zoom_window,
)
from source.scoring import load_checkpoint, percentile_threshold, read_rows
from source.test_model import (
    balanced_rows,
    generate_test_plot,
    generate_test_plots,
    paginate,
)

from conftest import MODES

plt.switch_backend("Agg")


@pytest.fixture(autouse=True)
def close_figures():
    yield
    plt.close("all")


@pytest.fixture(params=MODES)
def mode(request: pytest.FixtureRequest) -> str:
    return request.param


def _copy_results(trained_models: dict[str, Path], mode: str, tmp_path: Path) -> Path:
    directory = tmp_path / f"autoencoder-{mode}"
    shutil.copytree(trained_models[mode], directory)
    return directory


@pytest.fixture
def results_dir(mode: str, trained_models: dict[str, Path], tmp_path: Path) -> Path:
    return _copy_results(trained_models, mode, tmp_path)


@pytest.fixture
def hybrid_results(trained_models: dict[str, Path], tmp_path: Path) -> Path:
    return _copy_results(trained_models, "hybrid", tmp_path)


def _history(mode: str, epochs: int, best_epoch: int) -> list[dict[str, float | str]]:
    return [
        {
            "epoch": epoch,
            "train_loss": 1.0 + abs(epoch - best_epoch) / epochs,
            "validation_loss": 1.0 + abs(epoch - best_epoch) / epochs,
            "validation_accuracy": 0.9,
            "mode": mode,
            "lambda": 1.0,
        }
        for epoch in range(1, epochs + 1)
    ]


def _metrics(results_dir: Path) -> dict[str, object]:
    return json.loads((results_dir / "metrics.json").read_text(encoding="utf-8"))


def _texts(figure: plt.Figure) -> list[str]:
    return [text.get_text() for text in figure.findobj(Text)]


def test_draw_confusion_matrix_shows_counts_and_percentages_per_real_class() -> None:
    _, axis = plt.subplots()
    draw_confusion_matrix(axis, [[90, 10], [5, 195]], "Teste")
    assert [text.get_text() for text in axis.texts] == [
        "90\n90.0%",
        "10\n10.0%",
        "5\n2.5%",
        "195\n97.5%",
    ]
    assert axis.get_title() == "Teste"
    assert [label.get_text() for label in axis.get_yticklabels()] == [
        "normal\n(n=100)",
        "suspeita\n(n=200)",
    ]


def test_draw_confusion_matrix_uses_white_text_on_dark_and_black_on_light() -> None:
    _, axis = plt.subplots()
    draw_confusion_matrix(axis, [[95, 5], [10, 90]], "Teste")
    assert [text.get_color() for text in axis.texts] == ["white", "black", "black", "white"]


def test_draw_confusion_matrix_accepts_class_without_samples() -> None:
    _, axis = plt.subplots()
    draw_confusion_matrix(axis, [[10, 0], [0, 0]], "Sem suspeitas")
    assert [text.get_text() for text in axis.texts][2:] == ["0\n–", "0\n–"]


def test_draw_confusion_matrix_rejects_wrong_shape() -> None:
    _, axis = plt.subplots()
    with pytest.raises(ValueError, match="2x2"):
        draw_confusion_matrix(axis, [[1, 2, 3]], "Inválida")


def test_readable_text_color() -> None:
    assert readable_text_color((0.03, 0.19, 0.42, 1.0)) == "white"
    assert readable_text_color((0.97, 0.98, 1.0, 1.0)) == "black"


@pytest.mark.parametrize(
    ("loss_mode", "expected"),
    [
        ("lexical", "CE dos caracteres"),
        ("semantic", "MSE dos atributos"),
        ("hybrid", "CE + λ·MSE (λ = 0.5)"),
    ],
)
def test_loss_label_follows_training_mode(loss_mode: str, expected: str) -> None:
    assert loss_label([{"epoch": 1, "mode": loss_mode, "lambda": 0.5}]) == expected


def test_loss_label_without_mode_is_generic() -> None:
    assert loss_label([{"epoch": 1}]) == "perda de reconstrução"


def test_best_epoch_is_first_minimum_of_validation_loss() -> None:
    history = [{"validation_loss": value} for value in (3.0, 1.0, 2.0, 1.0)]
    assert best_epoch_position(history) == 1


@pytest.mark.parametrize(
    ("total", "expected"),
    [(10, 0), (50, 0), (200, 150), (300, 240), (684, 547), (2191, 1752)],
)
def test_zoom_start_uses_last_fifth_with_minimum_of_50_epochs(
    total: int, expected: int
) -> None:
    assert zoom_start(total) == expected


@pytest.mark.parametrize("history_mode", MODES)
@pytest.mark.parametrize(("best_epoch", "inside"), [(115, True), (5, False)])
def test_plot_history_labels_best_epoch_and_zoom(
    history_mode: str, best_epoch: int, inside: bool, tmp_path: Path
) -> None:
    history = _history(history_mode, epochs=120, best_epoch=best_epoch)
    output = plot_history(history, tmp_path)
    assert output == tmp_path / "losses.png" and output.stat().st_size > 0

    loss_axis, zoom_axis, accuracy_axis = plt.gcf().axes
    expected_label = loss_label(history)
    assert loss_axis.get_ylabel() == zoom_axis.get_ylabel() == expected_label
    best_label = f"Melhor época (checkpoint): {best_epoch}"
    for axis in (loss_axis, accuracy_axis):
        assert best_label in [text.get_text() for text in axis.get_legend().get_texts()]
    zoom_legend = [text.get_text() for text in zoom_axis.get_legend().get_texts()]
    if inside:
        assert any(text.startswith(f"Melhor época: {best_epoch}") for text in zoom_legend)
    else:
        assert any("fora do recorte" in text for text in zoom_legend)
    first_zoom_epoch = zoom_start(120) + 1
    assert zoom_axis.get_xlim()[0] >= first_zoom_epoch - 5
    assert loss_axis.get_xlim()[0] < first_zoom_epoch


def test_plot_history_accepts_single_epoch(tmp_path: Path) -> None:
    assert plot_history(_history("hybrid", epochs=1, best_epoch=1), tmp_path).is_file()


def test_plot_history_rejects_empty_history(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="vazio"):
        plot_history([], tmp_path)


def test_zoom_window_is_symmetric_around_threshold_and_covers_normals() -> None:
    normal = np.linspace(-1.0, 3.0, 101)
    low, high = zoom_window(normal, threshold=3.0)
    assert (low + high) / 2 == pytest.approx(3.0)
    assert low < normal.min()
    assert high > 3.0


def test_outside_counts_by_class() -> None:
    scores = np.array([-5.0, 0.0, 1.0, 9.0, 2.0, 12.0, 3.0])
    labels = np.array([0, 0, 0, 0, 1, 1, 1])
    assert outside_counts(scores, labels, low=-1.0, high=10.0) == {
        "normal": (1, 0, 4),
        "suspeita": (0, 1, 3),
    }


def test_draw_score_histogram_reports_points_outside_the_zoom_in_the_legend() -> None:
    scores = np.array([-5.0, 0.0, 1.0, 9.0, 2.0, 12.0, 3.0])
    labels = np.array([0, 0, 0, 0, 1, 1, 1])
    outside = outside_counts(scores, labels, low=-1.0, high=10.0)
    _, axis = plt.subplots()
    draw_score_histogram(axis, scores, labels, np.linspace(-1.0, 10.0, 12), 3.0, outside)
    axis.legend()
    assert [text.get_text() for text in axis.get_legend().get_texts()] == [
        "normal (n=4); fora do recorte: 1",
        "suspeita (n=3); fora do recorte: 1",
        "Limiar = P99 da validação (3.000)",
    ]


def test_asinh_edges_are_monotonic_and_cover_the_range() -> None:
    edges = asinh_edges(-2.0, 350.0, 6.0, 30)
    assert len(edges) == 31
    assert edges[0] == -2.0 and edges[-1] == 350.0
    assert np.all(np.diff(edges) > 0)


def test_verify_validation_threshold_requires_p99_of_validation_normals() -> None:
    scores = np.concatenate((np.linspace(0.0, 1.0, 101), np.full(20, 50.0)))
    labels = np.concatenate((np.zeros(101, dtype=int), np.ones(20, dtype=int)))
    verify_validation_threshold(0.99, scores, labels)
    with pytest.raises(ValueError, match="P99"):
        verify_validation_threshold(50.0, scores, labels)


def test_verify_saved_scores_rejects_count_mismatch() -> None:
    rows = [{"label": "normal"}] * 5
    with pytest.raises(ValueError, match="Quantidade divergente em test"):
        verify_saved_scores([0.1, 0.2], rows, "test")
    assert len(verify_saved_scores([0.1] * 5, rows, "test")) == 5


def test_verify_saved_scores_confirms_order_with_checkpoint(
    results_dir: Path, minimal_splits: Path
) -> None:
    loaded = load_checkpoint(results_dir)
    rows = read_rows(minimal_splits / "validation.csv")
    scores = verify_saved_scores(
        _metrics(results_dir)["validation_scores"], rows, "validation", loaded
    )
    assert len(scores) == len(rows)
    with pytest.raises(ValueError, match="não coincidem"):
        verify_saved_scores(scores[::-1], rows, "validation", loaded)


def test_verify_saved_scores_tolerates_gpu_rounding(
    results_dir: Path, minimal_splits: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reavaliacao em GPU CUDA nao e bit a bit igual ao treino.

    A verificacao aceita a diferenca de ponto flutuante, mas continua
    rejeitando uma ordem de linhas realmente diferente.
    """
    loaded = load_checkpoint(results_dir)
    rows = read_rows(minimal_splits / "validation.csv")
    saved = np.asarray(_metrics(results_dir)["validation_scores"], dtype=float)

    original = loaded.score

    def perturbed(items: list[dict[str, str]]) -> np.ndarray:
        fresh = original(items)
        # ruido pequeno, do tamanho do que a GPU CUDA produz
        return fresh + fresh.std() * 1e-3

    monkeypatch.setattr(loaded, "score", perturbed)
    accepted = verify_saved_scores(saved, rows, "validation", loaded)
    assert len(accepted) == len(rows)

    def shuffled(items: list[dict[str, str]]) -> np.ndarray:
        fresh = original(items)
        return fresh[::-1]

    monkeypatch.setattr(loaded, "score", shuffled)
    with pytest.raises(ValueError, match="não coincidem"):
        verify_saved_scores(saved, rows, "validation", loaded)


def test_verify_validation_threshold_tolerates_gpu_rounding() -> None:
    """O P99 recalculado pode diferir levemente do salvo em GPU."""
    scores = np.concatenate((np.linspace(0.0, 1.0, 101), np.full(20, 50.0)))
    labels = np.concatenate((np.zeros(101, dtype=int), np.ones(20, dtype=int)))
    expected = percentile_threshold(scores[labels == 0])
    verify_validation_threshold(expected + 0.001, scores, labels)
    with pytest.raises(ValueError, match="P99"):
        verify_validation_threshold(expected + 5.0, scores, labels)


def test_plot_score_distributions_shares_x_axis_and_reports_points_outside_zoom(
    results_dir: Path, minimal_splits: Path
) -> None:
    output = plot_score_distributions(_metrics(results_dir), results_dir, minimal_splits)
    assert output == results_dir / "score-distributions.png" and output.is_file()

    validation_full, validation_zoom, test_full, test_zoom = plt.gcf().axes
    assert validation_full.get_xlim() == test_full.get_xlim()
    assert validation_zoom.get_xlim() == test_zoom.get_xlim()
    for axis in (validation_zoom, test_zoom):
        legend = [text.get_text() for text in axis.get_legend().get_texts()]
        assert sum("fora do recorte" in text for text in legend) == 2
        assert any(text.startswith("Limiar = P99 da validação") for text in legend)


def test_plot_score_distributions_fails_when_score_count_differs(
    results_dir: Path, minimal_splits: Path
) -> None:
    metrics = _metrics(results_dir)
    metrics["test_scores"] = metrics["test_scores"][:-1]
    with pytest.raises(ValueError, match="Quantidade divergente em test"):
        plot_score_distributions(metrics, results_dir, minimal_splits)


def test_plot_score_distributions_fails_when_score_order_differs(
    results_dir: Path, minimal_splits: Path
) -> None:
    metrics = _metrics(results_dir)
    metrics["validation_scores"] = metrics["validation_scores"][::-1]
    with pytest.raises(ValueError, match="não coincidem"):
        plot_score_distributions(metrics, results_dir, minimal_splits)


def test_plot_score_distributions_fails_when_threshold_is_not_the_validation_p99(
    results_dir: Path, minimal_splits: Path
) -> None:
    metrics = _metrics(results_dir)
    metrics["threshold"] += 5.0
    with pytest.raises(ValueError, match="P99 dos scores normais da validação"):
        plot_score_distributions(metrics, results_dir, minimal_splits)


def test_balanced_rows_are_distinct_balanced_and_diversified(minimal_splits: Path) -> None:
    rows = read_rows(minimal_splits / "test.csv")
    selected = balanced_rows(rows + rows, 6)
    assert len({row["query"] for row in selected}) == 6
    assert [row["label"] for row in selected] == ["normal"] * 3 + ["suspeita"] * 3
    assert {row["profile"] for row in selected[:3]} == {"normal", "normal_hard"}
    assert {row["family"] for row in selected[3:]} == {"base32", "hex", "base64"}


def test_balanced_rows_validate_samples_and_available_domains(minimal_splits: Path) -> None:
    rows = read_rows(minimal_splits / "test.csv")
    with pytest.raises(ValueError, match="par"):
        balanced_rows(rows, 5)
    distinct_normals = {
        normalize_domain(row["query"]) for row in rows if row["label"] == "normal"
    }
    with pytest.raises(ValueError, match="domínios distintos"):
        balanced_rows(rows, 2 * (len(distinct_normals) + 1))


def test_paginate_keeps_classes_balanced_in_each_figure() -> None:
    rows = [{"label": "normal", "query": f"n{index}"} for index in range(4)]
    rows += [{"label": "suspeita", "query": f"s{index}"} for index in range(4)]
    pages = paginate(rows)
    assert [len(page) for page in pages] == [6, 2]
    assert [row["label"] for row in pages[0]] == ["normal"] * 3 + ["suspeita"] * 3
    assert [row["label"] for row in pages[1]] == ["normal", "suspeita"]


def test_generate_test_plot_returns_the_first_figure(
    hybrid_results: Path, minimal_splits: Path
) -> None:
    path = generate_test_plot(minimal_splits, hybrid_results, samples=6)
    assert path == hybrid_results / "test-samples.png" and path.stat().st_size > 0
    assert not (hybrid_results / "test-samples-2.png").exists()


def test_generate_test_plots_follow_the_model_mode(
    mode: str, results_dir: Path, minimal_splits: Path
) -> None:
    paths = generate_test_plots(minimal_splits, results_dir, samples=12, show=True)
    assert [path.name for path in paths] == ["test-samples.png", "test-samples-2.png"]
    assert all(path.is_file() for path in paths)
    assert len(plt.get_fignums()) == 2
    for number in plt.get_fignums():
        figure = plt.figure(number)
        texts = _texts(figure)
        assert any("Saída:" in text for text in texts) == (mode != "semantic")
        assert (FEATURE_COLUMNS[0] in texts) == (mode != "lexical")
        limits = {(image.norm.vmin, image.norm.vmax) for image in figure.findobj(AxesImage)}
        assert len(limits) == (2 if mode == "hybrid" else 1)


def test_generate_test_plots_removes_only_stale_pages(
    hybrid_results: Path, minimal_splits: Path
) -> None:
    stale = [hybrid_results / "test-samples-2.png", hybrid_results / "test-samples-7.png"]
    unrelated = hybrid_results / "test-samples-notas.png"
    for path in (*stale, unrelated):
        path.write_bytes(b"antigo")
    generate_test_plots(minimal_splits, hybrid_results, samples=6)
    assert not any(path.exists() for path in stale)
    assert unrelated.exists()


def test_generate_test_plot_rejects_odd_sample_count(
    hybrid_results: Path, minimal_splits: Path
) -> None:
    with pytest.raises(ValueError, match="par"):
        generate_test_plot(minimal_splits, hybrid_results, samples=5)


def test_plot_latent_space_supports_every_mode(
    results_dir: Path, minimal_splits: Path
) -> None:
    output = plot_latent_space(minimal_splits, results_dir)
    assert output == results_dir / "latent-space.png" and output.stat().st_size > 0


def test_plot_training_main_creates_every_figure(
    hybrid_results: Path, minimal_splits: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plot_training",
            "--results-dir", str(hybrid_results),
            "--splits-dir", str(minimal_splits),
            "--test-samples", "12",
        ],
    )
    plot_training.main()
    for name in (
        "losses.png",
        "metrics.png",
        "confusion-matrices.png",
        "score-distributions.png",
        "latent-space.png",
        "test-samples.png",
        "test-samples-2.png",
    ):
        assert (hybrid_results / name).stat().st_size > 0, name
