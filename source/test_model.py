"""Visualiza a reconstrução textual e numérica do autoencoder."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.preprocessing import StandardScaler

if __package__:
    from .features import FEATURE_COLUMNS, normalize_domain, transform_features
    from .models import CharAutoencoder, HybridAutoencoder
    from .train import MAX_LENGTH, TOKEN_TO_INDEX, VOCABULARY, encode_domains
else:
    from features import FEATURE_COLUMNS, normalize_domain, transform_features
    from models import CharAutoencoder, HybridAutoencoder
    from train import MAX_LENGTH, TOKEN_TO_INDEX, VOCABULARY, encode_domains


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", type=Path, default=Path("data/processed/splits"))
    parser.add_argument("--results-dir", type=Path, default=Path("results/autoencoder"))
    parser.add_argument("--samples", type=int, default=6)
    parser.add_argument("--show", action="store_true")
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError(f"Split vazio: {path}")
    return rows


def balanced_rows(rows: list[dict[str, str]], samples: int) -> list[dict[str, str]]:
    """Seleciona igualmente exemplos normais e suspeitos para a visualização."""
    if samples <= 0 or samples % 2:
        raise ValueError("--samples precisa ser um número positivo e par")
    normal = [row for row in rows if row.get("label") == "normal"]
    suspicious = [row for row in rows if row.get("label") != "normal"]
    per_class = samples // 2
    if len(normal) < per_class or len(suspicious) < per_class:
        raise ValueError(
            f"O teste precisa de pelo menos {per_class} exemplos de cada classe"
        )
    return normal[:per_class] + suspicious[:per_class]


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


def generate_test_plot(
    splits_dir: Path, results_dir: Path, samples: int = 6, show: bool = False
) -> Path:
    """Avalia amostras do teste e salva entrada, saída e erros."""
    if samples <= 0:
        raise ValueError("--samples precisa ser positivo")
    checkpoint = torch.load(results_dir / "model.pt", map_location="cpu")
    rows = balanced_rows(read_rows(splits_dir / "test.csv"), samples)
    scaler = StandardScaler()
    scaler.mean_ = np.asarray(checkpoint["scaler_mean"], dtype=np.float64)
    scaler.scale_ = np.asarray(checkpoint["scaler_scale"], dtype=np.float64)
    scaler.var_ = scaler.scale_ ** 2
    scaler.n_features_in_ = len(FEATURE_COLUMNS)
    numeric = scaler.transform(transform_features(rows)).astype(np.float32)
    characters = encode_domains(rows)
    model_class = (
        CharAutoencoder
        if checkpoint.get("architecture") == "char-autoencoder-v1"
        else HybridAutoencoder
    )
    model = (
        model_class(len(VOCABULARY), int(checkpoint["max_length"]), int(checkpoint["latent_dim"]))
        if model_class is CharAutoencoder
        else model_class(
            len(FEATURE_COLUMNS),
            len(VOCABULARY),
            int(checkpoint["max_length"]),
            int(checkpoint["latent_dim"]),
        )
    )
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    mode = checkpoint.get("mode", "hybrid")
    with torch.no_grad():
        logits, reconstructed_numeric = model(
            characters, torch.from_numpy(numeric), mode=mode
        )
    reconstructed_tokens = decode_tokens(logits)
    token_error = torch.nn.functional.cross_entropy(
        logits,
        characters,
        ignore_index=TOKEN_TO_INDEX["<PAD>"],
        reduction="none",
    )
    valid_tokens = (characters != TOKEN_TO_INDEX["<PAD>"]).sum(dim=1).clamp_min(1)
    text_error = (
        token_error.masked_fill(characters == TOKEN_TO_INDEX["<PAD>"], 0.0).sum(dim=1)
        / valid_tokens
    ).numpy()
    if reconstructed_numeric.shape[1] == 0:
        numeric_error = np.zeros(len(rows), dtype=np.float32)
    else:
        numeric_error = ((reconstructed_numeric.numpy() - numeric) ** 2).mean(axis=1)
    metrics_path = results_dir / "metrics.json"
    metrics = {}
    if metrics_path.is_file():
        import json

        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    numeric_weight = float(metrics.get("numeric_weight", 1.0))
    text_normalized = (text_error - float(checkpoint["text_mean"])) / float(
        checkpoint["text_std"]
    )
    numeric_normalized = numeric_weight * (
        numeric_error - float(checkpoint["numeric_mean"])
    ) / float(checkpoint["numeric_std"])
    if mode == "lexical":
        scores = text_normalized
    elif mode == "semantic":
        scores = (numeric_error - float(checkpoint["numeric_mean"])) / float(
            checkpoint["numeric_std"]
        )
    else:
        scores = text_normalized + numeric_normalized
    threshold = float(checkpoint["threshold"])
    predictions = scores > threshold

    for row, reconstructed, score, prediction in zip(
        rows, reconstructed_tokens, scores, predictions
    ):
        print(
            f"{normalize_domain(row['query'])} -> {reconstructed} | "
            f"real={row['label']} | predito={'suspeita' if prediction else 'normal'} | "
            f"score={score:.4f}"
        )

    figure, axes = plt.subplots(
        len(rows), 2, figsize=(15, max(4, len(rows) * 2.4)), squeeze=False
    )
    for index, (row, reconstructed, score, prediction) in enumerate(
        zip(rows, reconstructed_tokens, scores, predictions)
    ):
        color = "tab:red" if prediction else "tab:green"
        axes[index, 0].axis("off")
        axes[index, 0].text(
            0.02,
            0.75,
            f"Entrada:\n{normalize_domain(row['query'])}\n\n"
            f"Saída:\n{reconstructed}",
            fontsize=11,
            family="monospace",
            va="center",
        )
        axes[index, 0].text(
            0.02,
            0.08,
            f"Real: {row['label']} | Predito: "
            f"{'suspeita' if prediction else 'normal'} | Score: {score:.4f}",
            color=color,
            fontsize=10,
            weight="bold",
        )
        if mode == "lexical":
            error = token_error[index].numpy()
            error_title = "Erro lexical por posição"
            error_labels = np.arange(len(error))
        else:
            error = np.abs(reconstructed_numeric[index].numpy() - numeric[index])
            error_title = "Erro por atributo numérico"
            error_labels = np.arange(len(FEATURE_COLUMNS))
        image = axes[index, 1].imshow(error[np.newaxis, :], aspect="auto", cmap="Reds")
        axes[index, 1].set_title(error_title, fontsize=10)
        axes[index, 1].set_yticks([])
        axes[index, 1].set_xticks(error_labels)
        axes[index, 1].set_xticklabels(
            FEATURE_COLUMNS if mode != "lexical" else error_labels,
            rotation=90,
            fontsize=6,
        )
        figure.colorbar(image, ax=axes[index, 1], fraction=0.02, pad=0.02)
    figure.suptitle("Teste: entrada, reconstrução textual e erro numérico")
    figure.tight_layout()
    output_path = results_dir / "test-samples.png"
    figure.savefig(output_path, dpi=150, bbox_inches="tight")
    if not show:
        plt.close(figure)
    return output_path


def main() -> None:
    args = parse_args()
    output_path = generate_test_plot(
        args.splits_dir, args.results_dir, args.samples, args.show
    )
    print(f"Gráfico de teste salvo em: {output_path}")
    if args.show:
        image = plt.imread(output_path)
        plt.figure(figsize=(15, 8))
        plt.imshow(image)
        plt.axis("off")
        plt.show()


if __name__ == "__main__":
    main()
