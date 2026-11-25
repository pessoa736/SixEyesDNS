"""Gera os diagramas da documentação somente com Matplotlib."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


COLORS = {
    "blue": "#dbeafe",
    "green": "#dcfce7",
    "yellow": "#fef3c7",
    "gray": "#e5e7eb",
    "purple": "#ede9fe",
    "red": "#fee2e2",
    "edge": "#334155",
    "text": "#0f172a",
}


def canvas(title: str, subtitle: str, figsize: tuple[float, float]) -> tuple[Figure, Axes]:
    figure, axis = plt.subplots(figsize=figsize)
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")
    axis.text(
        0.5, 0.965, title, ha="center", va="top",
        fontsize=18, fontweight="bold", color=COLORS["text"],
    )
    axis.text(
        0.5, 0.91, subtitle, ha="center", va="top",
        fontsize=10.5, color="#475569",
    )
    figure.subplots_adjust(left=0.025, right=0.975, top=0.98, bottom=0.03)
    return figure, axis


def box(
    axis: Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    color: str = "blue",
    fontsize: float = 10,
) -> None:
    patch = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        linewidth=1.4, edgecolor=COLORS["edge"], facecolor=COLORS[color],
    )
    axis.add_patch(patch)
    axis.text(
        x + width / 2, y + height / 2, text,
        ha="center", va="center", fontsize=fontsize,
        color=COLORS["text"], linespacing=1.35,
    )


def arrow(axis: Axes, start: tuple[float, float], end: tuple[float, float], rad: float = 0) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=15,
            linewidth=1.5, color=COLORS["edge"],
            connectionstyle=f"arc3,rad={rad}", shrinkA=3, shrinkB=3,
        )
    )


def flow_row(
    axis: Axes,
    labels: list[str],
    y: float,
    height: float,
    colors: list[str] | None = None,
    fontsize: float = 10,
) -> list[tuple[float, float, float, float]]:
    left, right, gap = 0.035, 0.965, 0.025
    width = (right - left - gap * (len(labels) - 1)) / len(labels)
    bounds = []
    for index, label in enumerate(labels):
        x = left + index * (width + gap)
        color = colors[index] if colors else "blue"
        box(axis, x, y, width, height, label, color, fontsize)
        bounds.append((x, y, width, height))
        if index:
            px, py, pw, ph = bounds[index - 1]
            arrow(axis, (px + pw, py + ph / 2), (x, y + height / 2))
    return bounds


def pipeline_figure() -> tuple[Figure, Axes]:
    figure, axis = canvas(
        "SixEyesDNS — pipeline",
        "Do laboratório sintético à avaliação e à demonstração",
        (15, 7.5),
    )
    first = flow_row(
        axis,
        [
            "Laboratório\nDocker · zona .test",
            "Logs e rótulos\ndnsmasq · BIND9 · Unbound",
            "process_raw\nalinhamento temporal",
            "dataset.csv\n20.000 registros",
        ],
        0.61,
        0.19,
        ["green", "blue", "blue", "yellow"],
    )
    second = flow_row(
        axis,
        [
            "Splits\nsem interseção",
            "Treino normal-only\nDense · Char · Hybrid",
            "model.pt\nscaler + vocabulário + P99",
            "Avaliação e demo\nmétricas · Gradio · CLI",
        ],
        0.25,
        0.19,
        ["yellow", "purple", "purple", "green"],
    )
    arrow(axis, (first[-1][0] + first[-1][2] / 2, 0.61), (second[-1][0] + second[-1][2] / 2, 0.44))
    axis.text(
        0.5, 0.09,
        "Treino usa somente normais · P99 e melhor F1 são escolhidos na validação, nunca no teste",
        ha="center", fontsize=10.5, color="#475569",
    )
    return figure, axis


def architectures_figure() -> tuple[Figure, Axes]:
    figure, axis = canvas(
        "Arquiteturas comparadas",
        "Todos os scores são padronizados pelos normais da validação",
        (15, 8),
    )
    columns = [
        (
            0.035,
            "DenseAE · semântico",
            [
                "42 atributos",
                "Encoder denso\n42→32→16→16",
                "Decoder denso\n16→16→32→42",
                "score = z(MSE)",
            ],
            "blue",
        ),
        (
            0.355,
            "CharAE · lexical",
            [
                "64 posições\nvocabulário 41",
                "Embedding + Conv1d\nlatente 16",
                "Decoder Conv1d\n41 logits",
                "score = z(CE)",
            ],
            "purple",
        ),
        (
            0.675,
            "HybridAE · híbrido",
            [
                "64 posições + 42 atributos",
                "Dois encoders\nconcatenação",
                "Dois decoders\ncaracteres + atributos",
                "score = z(CE) + λ·z(MSE)",
            ],
            "green",
        ),
    ]
    for x, title, steps, color in columns:
        axis.text(x + 0.14, 0.82, title, ha="center", fontsize=13, fontweight="bold")
        previous = None
        for index, step in enumerate(steps):
            y = 0.64 - index * 0.17
            box(axis, x, y, 0.28, 0.12, step, color, 10.5)
            if previous is not None:
                arrow(axis, (x + 0.14, previous), (x + 0.14, y + 0.12))
            previous = y
    axis.text(
        0.5, 0.045,
        "CE: entropia cruzada por posição real · MSE: erro quadrático dos 42 atributos",
        ha="center", fontsize=10.5, color="#475569",
    )
    return figure, axis


def training_figure() -> tuple[Figure, Axes]:
    figure, axis = canvas(
        "Treino e calibração",
        "O teste nunca escolhe pesos, scaler ou limiar",
        (16, 7),
    )
    flow_row(
        axis,
        [
            "Normais do treino",
            "Features + scaler\nsomente treino",
            "Épocas\nAdam + ruído",
            "Melhor checkpoint\nmenor perda de validação",
            "Limiar P99\nsomente validação",
            "Avaliação e demo\nsem recalibrar",
        ],
        0.51,
        0.22,
        ["green", "yellow", "purple", "purple", "yellow", "blue"],
        9.5,
    )
    flow_row(
        axis,
        [
            "GPU auto\nCPU como fallback",
            "Early stopping\npela validação",
            "Checkpoint + histórico\nfiguras + métricas",
        ],
        0.18,
        0.15,
        ["gray", "gray", "blue"],
        10,
    )
    return figure, axis


def roadmap_figure() -> tuple[Figure, Axes]:
    figure, axis = canvas(
        "Roadmap do projeto",
        "Verde: concluído · azul: consolidação · amarelo: parcial · cinza: pendente",
        (14, 7.5),
    )
    positions = [0.055, 0.365, 0.675]
    top = [
        "Fase 1\nEstrutura e schema\nCONCLUÍDA",
        "Fase 2\nDados e laboratório\nIMPLEMENTADOS",
        "Fase 3\nModelos e avaliação\nCONCLUÍDA",
    ]
    bottom = [
        "Fase 4\nDemonstração\nEM CONSOLIDAÇÃO",
        "Fase 5\nTexto e roteiro\nPRONTOS",
        "Fase 6\nRobustez\nPLANEJADA",
    ]
    for index, label in enumerate(top):
        box(axis, positions[index], 0.58, 0.27, 0.18, label, "green", 10.5)
        if index:
            arrow(axis, (positions[index - 1] + 0.27, 0.67), (positions[index], 0.67))
    colors = ["blue", "green", "gray"]
    for index, label in enumerate(bottom):
        box(axis, positions[index], 0.22, 0.27, 0.18, label, colors[index], 10.5)
    arrow(axis, (positions[2] + 0.135, 0.58), (positions[0] + 0.135, 0.40), rad=0.12)
    arrow(axis, (positions[2] + 0.135, 0.58), (positions[1] + 0.135, 0.40), rad=0.08)
    arrow(axis, (positions[0] + 0.27, 0.31), (positions[2], 0.31), rad=-0.12)
    arrow(axis, (positions[1] + 0.27, 0.27), (positions[2], 0.27))
    return figure, axis


def demo_figure() -> tuple[Figure, Axes]:
    figure, axis = canvas(
        "Demonstração e adaptação",
        "Duas operações separadas: testar o detector e adaptar uma cópia",
        (15, 8),
    )
    left = 0.05
    middle = 0.385
    right = 0.72
    width = 0.24
    box(axis, left, 0.61, width, 0.15, "Consulta manual\no tipo DNS não é feature", "blue", 10.5)
    box(axis, middle, 0.61, width, 0.15, "Classificação\ncheckpoint + P99", "purple", 10.5)
    box(axis, right, 0.61, width, 0.15, "Score + heatmap\nerros por atributo", "green", 10.5)
    arrow(axis, (left + width, 0.685), (middle, 0.685))
    arrow(axis, (middle + width, 0.685), (right, 0.685))

    box(axis, left, 0.31, width, 0.15, "Log normal\nconfirmado", "yellow", 10.5)
    box(axis, middle, 0.31, width, 0.15, "Fine-tuning\nsplit por domínio", "purple", 10.5)
    box(axis, right, 0.31, width, 0.15, "Novo model.pt\nbase preservado", "green", 10.5)
    arrow(axis, (left + width, 0.385), (middle, 0.385))
    arrow(axis, (middle + width, 0.385), (right, 0.385))

    box(
        axis, 0.13, 0.075, 0.74, 0.105,
        "Validação da adaptação não é teste independente · anomalias no log contaminam o modelo",
        "red", 10.5,
    )
    return figure, axis


FIGURES = {
    "pipeline.png": pipeline_figure,
    "architectures.png": architectures_figure,
    "training.png": training_figure,
    "roadmap.png": roadmap_figure,
    "demo.png": demo_figure,
}


def generate_all(output_dir: Path = Path("doc/figures")) -> list[Path]:
    """Regenera todos os PNGs e devolve os caminhos gravados."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, factory in FIGURES.items():
        figure, _ = factory()
        path = output_dir / name
        figure.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
        plt.close(figure)
        paths.append(path)
    return paths


def main() -> None:
    for path in generate_all():
        print(f"Figura salva em: {path}")


if __name__ == "__main__":
    main()
