"""Visualiza a reconstrução textual e numérica do autoencoder em amostras do teste."""

from __future__ import annotations

import argparse
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from matplotlib.axes import Axes
from matplotlib.cm import ScalarMappable
from matplotlib.colors import PowerNorm
from matplotlib.figure import Figure

if __package__:
    from .features import FEATURE_COLUMNS, MAX_LENGTH, VOCABULARY, normalize_domain
    from .scoring import (
        DEFAULT_PERCENTILE,
        LoadedModel,
        encode_domains,
        load_checkpoint,
        numeric_tensor,
        read_rows,
        reconstruction_errors,
    )
else:
    from features import FEATURE_COLUMNS, MAX_LENGTH, VOCABULARY, normalize_domain
    from scoring import (
        DEFAULT_PERCENTILE,
        LoadedModel,
        encode_domains,
        load_checkpoint,
        numeric_tensor,
        read_rows,
        reconstruction_errors,
    )


MAX_SAMPLES_PER_FIGURE = 6
MODE_NAMES = {"lexical": "lexical", "semantic": "semântico", "hybrid": "híbrido"}
CHARACTER_MODES = ("lexical", "hybrid")
FEATURE_MODES = ("semantic", "hybrid")
COLOR_MAP = "Reds"
COLOR_GAMMA = 0.5
PAGE_PATTERN = re.compile(r"test-samples-(\d+)\.png")


@dataclass(frozen=True)
class Sample:
    """Uma consulta do teste com score, previsão e erros de reconstrução."""

    domain: str
    label: str
    score: float
    predicted: bool
    reconstruction: str
    character_error: np.ndarray
    feature_error: np.ndarray

    @property
    def outcome(self) -> str:
        """Acerto, falso positivo ou falso negativo da previsão."""
        if (self.label != "normal") == self.predicted:
            return "acerto"
        return "falso positivo" if self.predicted else "falso negativo"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", type=Path, default=Path("data/processed/splits"))
    parser.add_argument("--results-dir", type=Path, default=Path("results/autoencoder"))
    parser.add_argument(
        "--samples",
        type=int,
        default=6,
        help=(
            "Total de exemplos (par: metade normais, metade suspeitas); "
            f"cada figura mostra até {MAX_SAMPLES_PER_FIGURE}"
        ),
    )
    parser.add_argument("--show", action="store_true")
    return parser.parse_args()


def diversified_rows(
    rows: list[dict[str, str]], count: int, key: str
) -> list[dict[str, str]]:
    """Até ``count`` domínios distintos, alternando entre os valores de ``key``."""
    groups: dict[str, list[dict[str, str]]] = {}
    seen: set[str] = set()
    for row in rows:
        domain = normalize_domain(row["query"])
        if domain not in seen:
            seen.add(domain)
            groups.setdefault(row.get(key) or "", []).append(row)
    selected: list[dict[str, str]] = []
    queues = [list(reversed(group)) for group in groups.values()]
    while len(selected) < count and any(queues):
        for queue in queues:
            if queue and len(selected) < count:
                selected.append(queue.pop())
    return selected


def balanced_rows(rows: list[dict[str, str]], samples: int) -> list[dict[str, str]]:
    """Metade normais e metade suspeitas, sem domínios repetidos.

    Os normais alternam entre perfis e as suspeitas entre famílias, na ordem do
    arquivo, para a figura ser determinística e variada.
    """
    if samples <= 0 or samples % 2:
        raise ValueError("--samples precisa ser um número positivo e par")
    per_class = samples // 2
    normal = diversified_rows(
        [row for row in rows if row.get("label") == "normal"], per_class, "profile"
    )
    suspicious = diversified_rows(
        [row for row in rows if row.get("label") != "normal"], per_class, "family"
    )
    if len(normal) < per_class or len(suspicious) < per_class:
        raise ValueError(
            f"O teste precisa de pelo menos {per_class} domínios distintos "
            "de cada classe"
        )
    return normal + suspicious


def paginate(selected: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    """Divide em figuras de até 6 exemplos, mantendo as classes equilibradas."""
    half = len(selected) // 2
    normal, suspicious = selected[:half], selected[half:]
    step = max(1, MAX_SAMPLES_PER_FIGURE // 2)
    return [
        normal[start : start + step] + suspicious[start : start + step]
        for start in range(0, half, step)
    ]


def decode_tokens(logits: torch.Tensor) -> list[str]:
    indices = logits.argmax(dim=1).cpu().numpy()
    decoded = []
    for row in indices:
        characters = []
        for index in row:
            token = VOCABULARY[int(index)]
            if token == "<PAD>":
                break
            if token != "<UNK>":
                characters.append(token)
        decoded.append("".join(characters))
    return decoded


def evaluate_samples(loaded: LoadedModel, rows: list[dict[str, str]]) -> list[Sample]:
    """Score, previsão, reconstrução textual e erros por caractere e atributo."""
    characters = encode_domains(rows)
    numeric = numeric_tensor(rows, loaded.scaler)
    scores = loaded.combine(*loaded.components(rows))
    character_errors, feature_errors = reconstruction_errors(
        loaded.model, characters, numeric, loaded.mode
    )
    reconstructions = [""] * len(rows)
    if loaded.mode in CHARACTER_MODES:
        with torch.no_grad():
            logits, _ = loaded.model(characters, numeric, mode=loaded.mode)
        reconstructions = decode_tokens(logits)
    threshold = float(loaded.checkpoint["threshold"])
    samples = []
    for index, row in enumerate(rows):
        domain = normalize_domain(row["query"])[:MAX_LENGTH]
        character_error = (
            character_errors[index, : len(domain)]
            if loaded.mode in CHARACTER_MODES
            else np.zeros(0)
        )
        samples.append(
            Sample(
                domain=domain,
                label=row["label"],
                score=float(scores[index]),
                predicted=bool(scores[index] > threshold),
                reconstruction=reconstructions[index],
                character_error=character_error,
                feature_error=feature_errors[index],
            )
        )
    return samples


def shared_norm(arrays: list[np.ndarray]) -> PowerNorm:
    """Escala única de 0 ao maior erro, em raiz quadrada para realçar erros pequenos.

    Compartilhada por todas as linhas (e figuras) para que as cores sejam comparáveis.
    """
    values = np.concatenate([array for array in arrays if array.size] or [np.zeros(1)])
    top = float(values.max())
    return PowerNorm(gamma=COLOR_GAMMA, vmin=0.0, vmax=top if top > 0 else 1.0)


def wrap_field(prefix: str, value: str, width: int = 56) -> str:
    """Quebra um campo longo mantendo o recuo do rótulo."""
    return textwrap.fill(
        value or "(vazia)",
        width=width,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_on_hyphens=False,
    )


def draw_info(axis: Axes, sample: Sample, mode: str) -> None:
    """Entrada, saída reconstruída (quando existe) e resultado da classificação."""
    axis.axis("off")
    header = wrap_field("Entrada: ", sample.domain)
    if mode in CHARACTER_MODES:
        header += "\n" + wrap_field("Saída:   ", sample.reconstruction)
    axis.text(
        0.0,
        0.97,
        header,
        transform=axis.transAxes,
        va="top",
        family="monospace",
        fontsize=8.5,
    )
    axis.text(
        0.0,
        0.03,
        f"Real: {sample.label} | Predito: "
        f"{'suspeita' if sample.predicted else 'normal'}\n"
        f"Score: {sample.score:.3f} ({sample.outcome})",
        transform=axis.transAxes,
        va="bottom",
        color="tab:green" if sample.outcome == "acerto" else "tab:red",
        fontsize=8.5,
        fontweight="bold",
    )


def draw_strip(axis: Axes, errors: np.ndarray, norm: PowerNorm, width: int) -> None:
    """Faixa de uma linha com o erro de cada posição, alinhada à esquerda."""
    axis.imshow(
        errors[np.newaxis, :],
        cmap=COLOR_MAP,
        norm=norm,
        aspect="auto",
        extent=(-0.5, len(errors) - 0.5, 0, 1),
    )
    axis.set_xlim(-0.5, width - 0.5)
    axis.set_facecolor("0.93")
    axis.set_xticks([])
    axis.set_yticks([])
    axis.set_xticks(np.arange(-0.5, len(errors)), minor=True)
    axis.grid(which="minor", axis="x", color="white", linewidth=0.6)
    axis.tick_params(which="both", length=0)


def add_colorbar(figure: Figure, axis: Axes, norm: PowerNorm, label: str) -> None:
    """Barra de cores horizontal única, com rótulo e marcas no topo."""
    colorbar = figure.colorbar(
        ScalarMappable(norm=norm, cmap=COLOR_MAP), cax=axis, orientation="horizontal"
    )
    colorbar.set_label(label, fontsize=9)
    axis.xaxis.set_ticks_position("top")
    axis.xaxis.set_label_position("top")
    axis.tick_params(labelsize=8)


def draw_sample_page(
    samples: list[Sample],
    mode: str,
    threshold: float,
    norms: tuple[PowerNorm, PowerNorm],
    page: int,
    pages: int,
) -> Figure:
    """Uma figura: texto, erro por caractere e erro por atributo de cada exemplo."""
    show_characters = mode in CHARACTER_MODES
    show_features = mode in FEATURE_MODES
    widths = [4.4] + [6.6] * show_characters + [5.8] * show_features
    figure = plt.figure(
        figsize=(sum(widths) + 1.0, 1.05 * len(samples) + 3.0), layout="constrained"
    )
    grid = figure.add_gridspec(
        len(samples) + 1,
        len(widths),
        width_ratios=widths,
        height_ratios=[0.2] + [1.0] * len(samples),
    )
    character_column = 1 if show_characters else None
    feature_column = 1 + show_characters if show_features else None
    max_length = max(len(sample.domain) for sample in samples)

    if character_column is not None:
        add_colorbar(
            figure,
            figure.add_subplot(grid[0, character_column]),
            norms[0],
            "Erro por caractere: entropia cruzada (nats), escala de raiz quadrada",
        )
    if feature_column is not None:
        add_colorbar(
            figure,
            figure.add_subplot(grid[0, feature_column]),
            norms[1],
            "Erro quadrático por atributo (padronizado), escala de raiz quadrada",
        )
    for row, sample in enumerate(samples, start=1):
        draw_info(figure.add_subplot(grid[row, 0]), sample, mode)
        if character_column is not None:
            axis = figure.add_subplot(grid[row, character_column])
            draw_strip(axis, sample.character_error, norms[0], max_length)
            axis.set_xticks(range(len(sample.domain)))
            axis.set_xticklabels(list(sample.domain), fontsize=8, family="monospace")
        if feature_column is not None:
            axis = figure.add_subplot(grid[row, feature_column])
            draw_strip(axis, sample.feature_error, norms[1], len(FEATURE_COLUMNS))
            if row == len(samples):
                axis.set_xticks(range(len(FEATURE_COLUMNS)))
                axis.set_xticklabels(FEATURE_COLUMNS, rotation=90, fontsize=6.5)
    note = (
        "sem reconstrução textual: o modelo usa só os atributos numéricos"
        if mode == "semantic"
        else "texto verde: acerto; vermelho: erro de classificação"
    )
    figure.suptitle(
        f"Amostras do teste - autoencoder {MODE_NAMES[mode]} "
        f"(figura {page} de {pages})\n"
        f"Limiar = P{DEFAULT_PERCENTILE:g} dos normais da validação = "
        f"{threshold:.3f}; {note}",
        fontsize=12,
    )
    return figure


def describe_sample(sample: Sample, mode: str) -> str:
    """Linha de texto para o console com entrada, saída, rótulo e score."""
    reconstruction = f" -> {sample.reconstruction}" if mode in CHARACTER_MODES else ""
    return (
        f"{sample.domain}{reconstruction} | real={sample.label} | "
        f"predito={'suspeita' if sample.predicted else 'normal'} | "
        f"score={sample.score:.4f}"
    )


def remove_stale_pages(results_dir: Path, pages: int) -> None:
    """Apaga test-samples-N.png de execuções anteriores com mais figuras."""
    for path in results_dir.glob("test-samples-*.png"):
        match = PAGE_PATTERN.fullmatch(path.name)
        if match and int(match.group(1)) > pages:
            path.unlink()


def generate_test_plots(
    splits_dir: Path, results_dir: Path, samples: int = 6, show: bool = False
) -> list[Path]:
    """Salva test-samples.png e, com mais de 6 exemplos, test-samples-2.png etc."""
    selected = balanced_rows(read_rows(splits_dir / "test.csv"), samples)
    loaded = load_checkpoint(results_dir)
    threshold = float(loaded.checkpoint["threshold"])
    pages = [evaluate_samples(loaded, rows) for rows in paginate(selected)]
    every_sample = [sample for page in pages for sample in page]
    for sample in every_sample:
        print(describe_sample(sample, loaded.mode))
    norms = (
        shared_norm([sample.character_error for sample in every_sample]),
        shared_norm([sample.feature_error for sample in every_sample]),
    )
    paths = []
    for number, page_samples in enumerate(pages, start=1):
        figure = draw_sample_page(
            page_samples, loaded.mode, threshold, norms, number, len(pages)
        )
        name = "test-samples.png" if number == 1 else f"test-samples-{number}.png"
        figure.savefig(results_dir / name, dpi=150)
        if not show:
            plt.close(figure)
        paths.append(results_dir / name)
    remove_stale_pages(results_dir, len(pages))
    return paths


def generate_test_plot(
    splits_dir: Path, results_dir: Path, samples: int = 6, show: bool = False
) -> Path:
    """Gera as figuras de amostras do teste e devolve a primeira (test-samples.png)."""
    return generate_test_plots(splits_dir, results_dir, samples, show)[0]


def main() -> None:
    args = parse_args()
    for path in generate_test_plots(
        args.splits_dir, args.results_dir, args.samples, args.show
    ):
        print(f"Gráfico de teste salvo em: {path}")
    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
