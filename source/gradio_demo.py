"""Interface Gradio para testar e adaptar os modelos do SixEyesDNS."""

from __future__ import annotations

import html
import tempfile
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import gradio as gr
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

from .demo import build_report, query_from_domain
from .finetune import fine_tune_from_log
from .scoring import LoadedModel, load_checkpoint


MODEL_DIRS = {
    "hybrid": Path("results/autoencoder-hybrid"),
    "lexical": Path("results/autoencoder-lexical"),
    "semantic": Path("results/autoencoder-semantic"),
}
MODEL_CHOICES = [
    ("HybridAE — caracteres + 42 atributos", "hybrid"),
    ("CharAE — sequência de caracteres", "lexical"),
    ("DenseAE — somente os 42 atributos", "semantic"),
]
ATTRIBUTE_HEADERS = ["Atributo", "Erro quadrático"]
NORMAL_EXAMPLE_LOG = Path("scripts/demo/normal-example.txt")


@lru_cache(maxsize=6)
def cached_model(model_dir: str) -> LoadedModel:
    """Mantém um checkpoint por diretório na memória entre as classificações."""
    return load_checkpoint(Path(model_dir))


def analyze_domain(domain: str, model_dir: Path) -> dict[str, Any]:
    """Classifica um domínio; tipo DNS não é feature e não altera o score."""
    query = query_from_domain(domain)
    loaded = cached_model(str(model_dir))
    return build_report(loaded, [query], model_dir, "consulta manual")


def verdict_html(report: Mapping[str, Any]) -> str:
    result = report["results"][0]
    suspicious = result["suspicious"]
    color = "#b91c1c" if suspicious else "#15803d"
    background = "#fef2f2" if suspicious else "#f0fdf4"
    comparison = "&gt;" if suspicious else "&lt;="
    return (
        f'<div style="border:2px solid {color};background:{background};'
        'border-radius:12px;padding:18px">'
        f'<h2 style="color:{color};margin:0">{result["classification"].upper()}</h2>'
        f'<p><code>{html.escape(result["analyzed_query"])}</code></p>'
        f'<p><strong>Score:</strong> {result["score"]:.6f} {comparison} '
        f'<strong>limiar P99:</strong> {report["threshold"]:.6f}</p>'
        f'<p>Erro lexical: {result["text_error"]:.6f} · '
        f'Erro numérico: {result["numeric_error"]:.6f}</p>'
        '</div>'
    )


def error_html(error: Exception) -> str:
    return (
        '<div style="border:2px solid #b91c1c;background:#fef2f2;'
        'border-radius:12px;padding:16px;color:#991b1b">'
        f'<strong>Não foi possível analisar:</strong> {html.escape(str(error))}</div>'
    )


def character_plot(result: Mapping[str, Any]) -> Figure:
    """Desenha a entropia cruzada de cada posição real do domínio."""
    errors = result["character_errors"]
    if not errors:
        figure, axis = plt.subplots(figsize=(9, 2))
        axis.axis("off")
        axis.text(
            0.5,
            0.5,
            "O DenseAE não reconstrói caracteres.\n"
            "Consulte os erros dos atributos numéricos.",
            ha="center",
            va="center",
        )
        figure.tight_layout()
        return figure

    values = np.asarray([item["error"] for item in errors], dtype=np.float32)
    characters = [item["character"] for item in errors]
    width = max(8.0, min(16.0, len(characters) * 0.32))
    figure, axis = plt.subplots(figsize=(width, 2.6))
    image = axis.imshow(values[np.newaxis, :], cmap="magma", aspect="auto", vmin=0)
    axis.set_yticks([])
    axis.set_xticks(range(len(characters)))
    axis.set_xticklabels(characters, family="monospace", fontsize=9)
    axis.set_xlabel("Posição e caractere do domínio normalizado")
    axis.set_title("Erro de reconstrução por caractere")
    figure.colorbar(image, ax=axis, fraction=0.025, pad=0.03, label="CE (nats)")
    figure.tight_layout()
    return figure


def attribute_rows(result: Mapping[str, Any]) -> list[list[Any]]:
    return [
        [item["attribute"], round(item["error"], 6)]
        for item in result["top_attributes"]
    ]


def classify_domain(
    domain: str, model_dir: Path
) -> tuple[str, Figure | None, list[list[Any]], dict[str, Any]]:
    try:
        report = analyze_domain(domain, model_dir)
    except (ValueError, OSError) as error:
        return error_html(error), None, [], {}
    result = report["results"][0]
    return verdict_html(report), character_plot(result), attribute_rows(result), report


def loss_plot(report: Mapping[str, Any]) -> Figure:
    """Plota perda de treino e validação sem apresentá-las como métricas de teste."""
    history = report["history"]
    epochs = [row["epoch"] for row in history]
    figure, axis = plt.subplots(figsize=(8, 3.5))
    axis.plot(epochs, [row["train_loss"] for row in history], marker="o", label="Treino")
    axis.plot(
        epochs,
        [row["validation_loss"] for row in history],
        marker="o",
        label="Validação normal",
    )
    axis.set_xlabel("Época")
    axis.set_ylabel("Perda de reconstrução")
    axis.set_title("Fine-tuning — seleção do melhor checkpoint")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    return figure


def warnings_html(report: Mapping[str, Any]) -> str:
    return "".join(
        '<p style="color:#b45309"><strong>Atenção:</strong> '
        f"{html.escape(warning)}</p>"
        for warning in report.get("warnings", [])
    )


def adaptation_summary_html(report: Mapping[str, Any]) -> str:
    return (
        '<div style="border:1px solid #64748b;border-radius:12px;padding:16px">'
        '<strong>Checkpoint adaptado gerado</strong><br>'
        f'{report["train_domains"]} domínios no treino · '
        f'{report["validation_domains"]} na validação<br>'
        f'Limiar P99: {report["base_threshold"]:.6f} → {report["threshold"]:.6f}<br>'
        f'Melhor perda de validação: {report["best_validation_loss"]:.6f}'
        f"{warnings_html(report)}"
        '<p><strong>Não é uma avaliação de desempenho.</strong> '
        'Antes de usar o novo limiar, avalie o checkpoint em um teste rotulado '
        'independente que não tenha participado da adaptação.</p></div>'
    )


def adapt_model(
    replay_path: str | Path | None,
    confirmed_normal: bool,
    epochs: int,
    limit: int,
    learning_rate: float,
    model_dir: Path,
    output_root: Path | None = None,
) -> tuple[str, Figure | None, str | None, dict[str, Any]]:
    """Roda a adaptação em diretório temporário e oferece o novo checkpoint."""
    if replay_path is None or not str(replay_path).strip():
        return error_html(ValueError("Envie um arquivo de log primeiro.")), None, None, {}
    try:
        output_dir = Path(
            tempfile.mkdtemp(
                prefix="sixeyesdns-finetune-",
                dir=str(output_root) if output_root is not None else None,
            )
        )
        report = fine_tune_from_log(
            model_dir,
            Path(replay_path),
            output_dir,
            confirmed_normal=confirmed_normal,
            limit=int(limit),
            epochs=int(epochs),
            learning_rate=float(learning_rate),
        )
    except (ValueError, OSError, RuntimeError) as error:
        return error_html(error), None, None, {}
    return (
        adaptation_summary_html(report),
        loss_plot(report),
        str(report["checkpoint"]),
        report,
    )


def build_interface(model_dirs: Mapping[str, Path] | None = None) -> gr.Blocks:
    """Constrói o app sem carregar checkpoints nem iniciar treinamentos."""
    directories = dict(model_dirs or MODEL_DIRS)

    def on_domain(domain: str, mode: str):
        return classify_domain(domain, directories[mode])

    def on_finetune(
        replay_path: str | None,
        confirmed_normal: bool,
        epochs: int,
        limit: int,
        learning_rate: float,
        mode: str,
    ):
        return adapt_model(
            replay_path,
            confirmed_normal,
            epochs,
            limit,
            learning_rate,
            directories[mode],
        )

    with gr.Blocks(title="SixEyesDNS", analytics_enabled=False) as demo:
        gr.Markdown(
            "# SixEyesDNS\n"
            "Detecção educacional de túneis DNS com autoencoders treinados "
            "somente em consultas normais. O modelo analisa o domínio — não usa "
            "IP, cliente, rótulo ou **tipo DNS** como feature. O resultado é "
            "uma suspeita estatística, não um veredito de segurança."
        )
        model = gr.Dropdown(
            choices=MODEL_CHOICES,
            value="hybrid",
            label="Detector base",
            info="O limiar P99 foi calibrado na validação durante o treino.",
        )

        with gr.Tabs():
            with gr.Tab("Testar modelo"):
                domain = gr.Textbox(
                    value="staging.api.orbita.test",
                    label="Domínio",
                    placeholder="ex.: aaj4pccnvdeac.tunnel.test",
                    max_lines=1,
                )
                gr.Markdown(
                    "O tipo DNS não entra no cálculo: mudar A para TXT não altera "
                    "o score quando o domínio é o mesmo."
                )
                analyze = gr.Button("Classificar consulta", variant="primary")
                gr.Examples(
                    examples=[
                        ["staging.api.orbita.test"],
                        ["aaj4pccnvdeac.tunnel.test"],
                        ["7c2a488f471558ea9c7d162f.tunnel.test"],
                        ["f4bfff32c5.cdn.brisa.test"],
                    ],
                    inputs=[domain],
                    label="Exemplos do split de teste",
                )
                verdict = gr.HTML()
                with gr.Row():
                    heatmap = gr.Plot(label="Mapa de erro por caractere")
                    attributes = gr.Dataframe(
                        headers=ATTRIBUTE_HEADERS,
                        type="array",
                        label="Maiores erros por atributo",
                        interactive=False,
                    )
                with gr.Accordion("Relatório completo", open=False):
                    domain_json = gr.JSON()
                analyze.click(
                    fn=on_domain,
                    inputs=[domain, model],
                    outputs=[verdict, heatmap, attributes, domain_json],
                )

            with gr.Tab("Fine-tuning com log normal"):
                gr.Markdown(
                    "**Use somente um log com tráfego normal confirmado.** "
                    "Se houver túnel no arquivo, o autoencoder aprenderá a "
                    "reconstruí-lo como legítimo. A adaptação separa domínios "
                    "entre treino e validação e nunca sobrescreve o modelo base."
                )
                with gr.Row():
                    replay = gr.File(
                        label="Log normal (.log ou .txt)",
                        file_types=[".log", ".txt"],
                        type="filepath",
                    )
                    confirmed = gr.Checkbox(
                        value=False,
                        label="Confirmo que todas as consultas são normais",
                    )
                if NORMAL_EXAMPLE_LOG.is_file():
                    gr.Examples(
                        examples=[[str(NORMAL_EXAMPLE_LOG)]],
                        inputs=[replay],
                        label="Log normal de exemplo (600 domínios únicos)",
                    )
                with gr.Row():
                    epochs = gr.Slider(
                        minimum=1, maximum=5, value=2, step=1, label="Épocas"
                    )
                    limit = gr.Slider(
                        minimum=50,
                        maximum=2000,
                        value=500,
                        step=50,
                        label="Máximo de consultas lidas",
                    )
                    learning_rate = gr.Number(
                        value=0.0001, label="Taxa de aprendizado"
                    )
                adapt = gr.Button("Adaptar modelo", variant="primary")
                adaptation_summary = gr.HTML()
                with gr.Row():
                    adaptation_loss = gr.Plot(label="Perda por época")
                    checkpoint = gr.File(
                        label="Baixar model.pt adaptado", interactive=False
                    )
                with gr.Accordion("Relatório da adaptação", open=False):
                    adaptation_json = gr.JSON()
                adapt.click(
                    fn=on_finetune,
                    inputs=[replay, confirmed, epochs, limit, learning_rate, model],
                    outputs=[
                        adaptation_summary,
                        adaptation_loss,
                        checkpoint,
                        adaptation_json,
                    ],
                )

        gr.Markdown(
            "**Antes de aplicar em produção:** revalide o checkpoint em dados "
            "independentes do ambiente, meça falsos positivos na prevalência "
            "real e trate o score como priorização para análise, não como bloqueio automático."
        )
    return demo
