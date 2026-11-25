"""Treina os ramos lexical, semântico ou híbrido do autoencoder."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import random
import time
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import animation
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

if __package__:
    from .device import describe_device, resolve_device
    from .features import (
        FEATURE_COLUMNS,
        MAX_LENGTH,
        PAD,
        TOKEN_TO_INDEX,
        VOCABULARY,
        transform_features,
    )
    from .models import ARCHITECTURES, LOSS_DESCRIPTIONS, build_model
    from .scoring import (
        anomaly_labels,
        confusion_matrix,
        encode_domains,
        mode_scores,
        normal_rows,
        numeric_tensor,
        read_rows,
        score_batch,
    )
else:
    from device import describe_device, resolve_device
    from features import (
        FEATURE_COLUMNS,
        MAX_LENGTH,
        PAD,
        TOKEN_TO_INDEX,
        VOCABULARY,
        transform_features,
    )
    from models import ARCHITECTURES, LOSS_DESCRIPTIONS, build_model
    from scoring import (
        anomaly_labels,
        confusion_matrix,
        encode_domains,
        mode_scores,
        normal_rows,
        numeric_tensor,
        read_rows,
        score_batch,
    )


EARLY_STOP_PATIENCE = 200
NON_INTERACTIVE_BACKENDS = {"agg", "cairo", "pdf", "ps", "svg", "template"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", type=Path, default=Path("data/processed/splits"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/autoencoder"))
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--latent-dim", type=int, default=16)
    parser.add_argument(
        "--mode",
        choices=("lexical", "semantic", "hybrid"),
        default="hybrid",
        help="Ramo treinado: caracteres, atributos numéricos ou ambos",
    )
    parser.add_argument(
        "--lexical-checkpoint",
        type=Path,
        help="Checkpoint lexical para inicializar embedding e encoder no híbrido",
    )
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=1e-4,
        help="Regularização L2 para reduzir memorização dos domínios",
    )
    parser.add_argument(
        "--lambda",
        dest="numeric_weight",
        type=float,
        default=1.0,
        help="Peso do erro MSE numérico no score combinado",
    )
    parser.add_argument(
        "--numeric-weight",
        dest="numeric_weight",
        type=float,
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--char-mask-prob",
        type=float,
        default=0.05,
        help="Probabilidade de mascarar caracteres durante o treino",
    )
    parser.add_argument(
        "--pad-loss-weight",
        type=float,
        default=0.2,
        help="Peso da perda nas posições PAD para o decoder aprender o fim",
    )
    parser.add_argument(
        "--numeric-noise-std",
        type=float,
        default=0.01,
        help="Desvio do ruído gaussiano nas features durante o treino",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--early-stop-patience",
        type=int,
        default=EARLY_STOP_PATIENCE,
        help="Épocas sem melhora na validação antes de parar "
        f"(padrão: {EARLY_STOP_PATIENCE}); 0 desliga o early stopping",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="Dispositivo de treino: 'auto' (padrão; GPU NVIDIA/AMD com mais "
        "memória livre ou CPU), 'cpu', 'cuda' (exige GPU) ou 'cuda:N'",
    )
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument(
        "--no-live-plot",
        action="store_true",
        help="Desativa a janela interativa de acompanhamento do treino",
    )
    parser.add_argument(
        "--no-gif",
        action="store_true",
        help="Desativa o GIF animado das curvas de treino",
    )
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class LiveTrainingPlot:
    """Janela interativa com as curvas de perda e accuracy do treino."""

    def __init__(self, enabled: bool) -> None:
        self.figure = None
        if not enabled:
            return
        if matplotlib.get_backend().lower() in NON_INTERACTIVE_BACKENDS:
            print("Backend matplotlib sem janela; plot ao vivo desativado.")
            return
        try:
            plt.ion()
            self.figure, (self.loss_axis, self.accuracy_axis) = plt.subplots(
                1, 2, figsize=(11, 4), num="Treinamento do autoencoder"
            )
            self.figure.show()
        except Exception as error:
            print(f"Plot ao vivo desativado: {error}")
            self.figure = None

    def update(self, history: list[dict[str, float]]) -> None:
        if self.figure is None:
            return
        epochs = [item["epoch"] for item in history]
        train_loss = [item["train_loss"] for item in history]
        validation_loss = [item["validation_loss"] for item in history]
        accuracy = [item["validation_accuracy"] for item in history]
        self.loss_axis.clear()
        loss_name = LOSS_DESCRIPTIONS.get(history[-1].get("mode", "hybrid"), "perda")
        self.loss_axis.plot(epochs, train_loss, label="Treino")
        self.loss_axis.plot(epochs, validation_loss, label="Validação normal")
        self.loss_axis.set_title(f"Perda de reconstrução ({loss_name})")
        self.loss_axis.set_ylabel(loss_name)
        self.loss_axis.set_xlabel("Época")
        self.loss_axis.grid(alpha=0.25)
        self.loss_axis.legend()
        self.accuracy_axis.clear()
        self.accuracy_axis.plot(
            epochs, accuracy, color="tab:green", label="Validação - P99"
        )
        self.accuracy_axis.set_title("Accuracy de classificação")
        self.accuracy_axis.set_xlabel("Época")
        self.accuracy_axis.set_ylim(0, 1.05)
        self.accuracy_axis.grid(alpha=0.25)
        self.accuracy_axis.legend()
        self.figure.tight_layout()
        try:
            self.figure.canvas.draw_idle()
            self.figure.canvas.flush_events()
            plt.pause(0.001)
        except Exception:
            pass

    def close(self) -> None:
        if self.figure is not None:
            plt.ioff()
            plt.close(self.figure)
            self.figure = None


def save_training_gif(history: list[dict[str, float]], output_dir: Path) -> Path | None:
    """Grava um GIF com a evolução das curvas de perda e accuracy."""
    if len(history) < 2:
        return None
    frame_count = min(60, len(history))
    frame_indices = np.unique(
        np.linspace(1, len(history), num=frame_count, dtype=int)
    )
    epochs = [item["epoch"] for item in history]
    train_loss = [item["train_loss"] for item in history]
    validation_loss = [item["validation_loss"] for item in history]
    accuracy = [item["validation_accuracy"] for item in history]

    figure, (loss_axis, accuracy_axis) = plt.subplots(1, 2, figsize=(11, 4))
    figure.suptitle("Evolução do treinamento")
    loss_name = LOSS_DESCRIPTIONS.get(history[-1].get("mode", "hybrid"), "perda")

    def draw(frame: int) -> None:
        end = int(frame_indices[frame])
        loss_axis.clear()
        loss_axis.plot(epochs[:end], train_loss[:end], label="Treino")
        loss_axis.plot(
            epochs[:end], validation_loss[:end], label="Validação normal"
        )
        loss_axis.set_title(f"Perda de reconstrução ({loss_name})")
        loss_axis.set_ylabel(loss_name)
        loss_axis.set_xlabel("Época")
        loss_axis.set_xlim(epochs[0], epochs[-1])
        loss_axis.set_ylim(0, max(train_loss) * 1.05)
        loss_axis.grid(alpha=0.25)
        loss_axis.legend(loc="upper right")
        accuracy_axis.clear()
        accuracy_axis.plot(
            epochs[:end],
            accuracy[:end],
            color="tab:green",
            label="Validação - P99",
        )
        accuracy_axis.set_title("Accuracy de classificação")
        accuracy_axis.set_xlabel("Época")
        accuracy_axis.set_xlim(epochs[0], epochs[-1])
        accuracy_axis.set_ylim(0, 1.05)
        accuracy_axis.grid(alpha=0.25)
        accuracy_axis.legend(loc="lower right")
        figure.tight_layout()

    try:
        gif = animation.FuncAnimation(
            figure, draw, frames=len(frame_indices), interval=100
        )
        gif_path = output_dir / "training.gif"
        gif.save(gif_path, writer=animation.PillowWriter(fps=10))
        return gif_path
    except Exception as error:
        print(f"GIF do treinamento desativado: {error}")
        return None
    finally:
        plt.close(figure)


def character_loss(
    logits: torch.Tensor, targets: torch.Tensor, pad_weight: float
) -> torch.Tensor:
    """Treina caracteres reais e ensina o decoder a encerrar em PAD."""
    losses = nn.functional.cross_entropy(logits, targets, reduction="none")
    weights = torch.where(
        targets == TOKEN_TO_INDEX[PAD],
        torch.full_like(losses, pad_weight),
        torch.ones_like(losses),
    )
    return (losses * weights).sum() / weights.sum().clamp_min(1.0)


def main() -> None:
    args = parse_args()
    if (
        args.epochs <= 0
        or args.batch_size <= 0
        or args.numeric_weight < 0
        or args.weight_decay < 0
        or not 0 <= args.char_mask_prob < 1
        or args.numeric_noise_std < 0
        or args.pad_loss_weight < 0
        or args.early_stop_patience < 0
    ):
        raise ValueError("Parâmetros de treino inválidos")
    device = resolve_device(args.device)
    set_seed(args.seed)
    print(f"Dispositivo selecionado: {describe_device(device, args.device)}")
    train = read_rows(args.splits_dir / "train.csv")
    validation = read_rows(args.splits_dir / "validation.csv")
    test = read_rows(args.splits_dir / "test.csv")
    train_normals = normal_rows(train)
    validation_normals = normal_rows(validation)
    scaler = StandardScaler().fit(transform_features(train_normals))
    train_numeric = numeric_tensor(train_normals, scaler)
    train_characters = encode_domains(train_normals)
    validation_normal_numeric = numeric_tensor(validation_normals, scaler)
    validation_normal_characters = encode_domains(validation_normals)
    validation_numeric = numeric_tensor(validation, scaler)
    validation_characters = encode_domains(validation)
    test_numeric = numeric_tensor(test, scaler)
    test_characters = encode_domains(test)
    model = build_model(
        args.mode, len(FEATURE_COLUMNS), len(VOCABULARY), MAX_LENGTH, args.latent_dim
    )
    if args.mode == "hybrid" and args.lexical_checkpoint:
        lexical_checkpoint = torch.load(args.lexical_checkpoint, map_location="cpu")
        lexical_state = {
            key: value
            for key, value in lexical_checkpoint["model_state"].items()
            if key.startswith(("embedding.", "char_encoder."))
        }
        model.load_state_dict(lexical_state, strict=False)
    model.to(device)
    validation_normal_numeric = validation_normal_numeric.to(device)
    validation_normal_characters = validation_normal_characters.to(device)
    validation_numeric = validation_numeric.to(device)
    validation_characters = validation_characters.to(device)
    test_numeric = test_numeric.to(device)
    test_characters = test_characters.to(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay
    )
    checkpoint_path = args.output_dir / "model.pt"
    history: list[dict[str, float]] = []
    start_epoch = 1
    best_validation_loss = float("inf")
    best_model_state = None
    best_optimizer_state = None
    if checkpoint_path.is_file() and not args.fresh:
        checkpoint = torch.load(checkpoint_path, map_location="cpu")
        expected_architecture = ARCHITECTURES[args.mode]
        if checkpoint.get("architecture") != expected_architecture:
            raise ValueError(
                "O checkpoint usa a arquitetura antiga; execute com --fresh "
                "para treinar a arquitetura atualizada."
            )
        if checkpoint.get("mode", "hybrid") != args.mode:
            raise ValueError("O checkpoint usa outro --mode; execute com --fresh.")
        checkpoint_numeric_dim = checkpoint.get("numeric_dim")
        if checkpoint_numeric_dim is None:
            checkpoint_numeric_dim = len(checkpoint.get("feature_columns", []))
        if checkpoint_numeric_dim == 0:
            numeric_weights = checkpoint["model_state"].get("numeric_encoder.0.weight")
            checkpoint_numeric_dim = numeric_weights.shape[1] if numeric_weights is not None else 0
        if checkpoint_numeric_dim and checkpoint_numeric_dim != len(FEATURE_COLUMNS):
            raise ValueError(
                "O checkpoint usa outra quantidade de features; execute com --fresh "
                "para treinar o modelo atualizado."
            )
        model.load_state_dict(checkpoint["model_state"])
        optimizer.load_state_dict(checkpoint["optimizer_state"])
        best_validation_loss = float(
            checkpoint.get("best_validation_loss", float("inf"))
        )
        best_model_state = {
            key: value.detach().clone() for key, value in model.state_dict().items()
        }
        best_optimizer_state = copy.deepcopy(optimizer.state_dict())
        history_path = args.output_dir / "history.json"
        if history_path.is_file():
            history = json.loads(history_path.read_text(encoding="utf-8"))
            start_epoch = int(history[-1]["epoch"]) + 1
        print(f"Modelo encontrado. Retomando na época {start_epoch}.")

    validation_labels = anomaly_labels(validation)
    test_labels = anomaly_labels(test)
    loader = DataLoader(
        TensorDataset(train_characters, train_numeric),
        batch_size=args.batch_size,
        shuffle=True,
        pin_memory=device.type == "cuda",
    )
    numeric_loss = nn.MSELoss()
    print_interval = max(1, args.epochs // 10)
    total_epochs = start_epoch + args.epochs - 1
    live_plot = LiveTrainingPlot(enabled=not args.no_live_plot)
    epochs_without_improvement = 0
    last_report_time = time.monotonic()
    for offset in range(args.epochs):
        model.train()
        losses = []
        for characters, numeric in loader:
            characters = characters.to(device, non_blocking=True)
            numeric = numeric.to(device, non_blocking=True)
            corrupted_characters = characters.clone()
            mask = (
                torch.rand_like(corrupted_characters, dtype=torch.float32)
                < args.char_mask_prob
            )
            mask &= corrupted_characters != TOKEN_TO_INDEX["<PAD>"]
            corrupted_characters[mask] = TOKEN_TO_INDEX["<UNK>"]
            corrupted_numeric = numeric + torch.randn_like(numeric) * args.numeric_noise_std
            logits, reconstructed = model(
                corrupted_characters, corrupted_numeric, mode=args.mode
            )
            lexical_loss = (
                character_loss(logits, characters, args.pad_loss_weight)
                if args.mode != "semantic"
                else torch.zeros((), device=characters.device)
            )
            semantic_loss = (
                numeric_loss(reconstructed, numeric)
                if args.mode != "lexical"
                else torch.zeros((), device=characters.device)
            )
            if args.mode == "lexical":
                loss = lexical_loss
            elif args.mode == "semantic":
                loss = semantic_loss
            else:
                loss = lexical_loss + args.numeric_weight * semantic_loss
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.item()))
        model.eval()
        with torch.no_grad():
            validation_logits, validation_reconstructed = model(
                validation_normal_characters,
                validation_normal_numeric,
                mode=args.mode,
            )
            validation_lexical_loss = (
                character_loss(
                    validation_logits,
                    validation_normal_characters,
                    args.pad_loss_weight,
                )
                if args.mode != "semantic"
                else torch.zeros((), device=validation_normal_characters.device)
            )
            validation_semantic_loss = (
                numeric_loss(validation_reconstructed, validation_normal_numeric)
                if args.mode != "lexical"
                else torch.zeros((), device=validation_normal_characters.device)
            )
            validation_loss = float(
                validation_lexical_loss
                if args.mode == "lexical"
                else validation_semantic_loss
                if args.mode == "semantic"
                else validation_lexical_loss
                + args.numeric_weight * validation_semantic_loss
            )
        normal_text, normal_numeric = score_batch(
            model,
            validation_normal_characters,
            validation_normal_numeric,
            args.mode,
        )
        all_text, all_numeric = score_batch(
            model, validation_characters, validation_numeric, args.mode
        )
        text_mean = normal_text.mean()
        text_std = normal_text.std() + 1e-8
        numeric_mean = normal_numeric.mean()
        numeric_std = normal_numeric.std() + 1e-8
        validation_threshold = np.percentile(
            mode_scores(
                normal_text,
                normal_numeric,
                args.mode,
                text_mean,
                text_std,
                numeric_mean,
                numeric_std,
                args.numeric_weight,
            ),
            99,
        )
        validation_score = mode_scores(
            all_text,
            all_numeric,
            args.mode,
            text_mean,
            text_std,
            numeric_mean,
            numeric_std,
            args.numeric_weight,
        )
        epoch = start_epoch + offset
        history.append(
            {
                "epoch": epoch,
                "train_loss": float(np.mean(losses)),
                "validation_loss": validation_loss,
                "validation_char_error": float(normal_text.mean()),
                "validation_numeric_error": float(normal_numeric.mean()),
                "lambda": args.numeric_weight,
                "mode": args.mode,
                "validation_accuracy": float(
                    np.mean((validation_score > validation_threshold) == validation_labels)
                ),
            }
        )
        if validation_loss < best_validation_loss:
            best_validation_loss = validation_loss
            best_model_state = {
                key: value.detach().clone() for key, value in model.state_dict().items()
            }
            best_optimizer_state = copy.deepcopy(optimizer.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
        now = time.monotonic()
        if (
            (offset + 1) % print_interval == 0
            or now - last_report_time >= 5.0
            or offset == args.epochs - 1
        ):
            last_report_time = now
            print(
                f"Época {epoch:03d}/{total_epochs:03d} | "
                f"treino_loss={np.mean(losses):.6f} | "
                f"val_loss={validation_loss:.6f} | "
                f"val_accuracy={history[-1]['validation_accuracy']:.4f}"
            )
            live_plot.update(history)
        if (
            args.early_stop_patience != 0
            and epochs_without_improvement >= args.early_stop_patience
        ):
            print(
                f"Early stopping na época {epoch}: "
                f"{args.early_stop_patience} épocas sem melhora na validação."
            )
            break
    live_plot.close()

    if best_model_state is None:
        raise RuntimeError("Nenhum estado válido foi produzido durante o treinamento")
    model.load_state_dict(best_model_state)
    if best_optimizer_state is None:
        best_optimizer_state = copy.deepcopy(optimizer.state_dict())
    model.eval()
    validation_text_normal, validation_numeric_normal = score_batch(
        model, validation_normal_characters, validation_normal_numeric, args.mode
    )
    validation_text, validation_numeric_scores = score_batch(
        model, validation_characters, validation_numeric, args.mode
    )
    test_text, test_numeric_scores = score_batch(
        model, test_characters, test_numeric, args.mode
    )
    text_mean, text_std = validation_text_normal.mean(), validation_text_normal.std() + 1e-8
    numeric_mean, numeric_std = validation_numeric_normal.mean(), validation_numeric_normal.std() + 1e-8
    validation_score = mode_scores(
        validation_text,
        validation_numeric_scores,
        args.mode,
        text_mean,
        text_std,
        numeric_mean,
        numeric_std,
        args.numeric_weight,
    )
    test_score = mode_scores(
        test_text,
        test_numeric_scores,
        args.mode,
        text_mean,
        text_std,
        numeric_mean,
        numeric_std,
        args.numeric_weight,
    )
    threshold = float(np.percentile(
        mode_scores(
            validation_text_normal,
            validation_numeric_normal,
            args.mode,
            text_mean,
            text_std,
            numeric_mean,
            numeric_std,
            args.numeric_weight,
        ),
        99,
    ))
    validation_predictions = (validation_score > threshold).astype(int)
    test_predictions = (test_score > threshold).astype(int)
    metrics = {
        "threshold": threshold,
        "validation_accuracy": float(np.mean(validation_predictions == validation_labels)),
        "test_accuracy": float(np.mean(test_predictions == test_labels)),
        "validation_confusion_matrix": confusion_matrix(
            validation_labels, validation_predictions
        ),
        "test_confusion_matrix": confusion_matrix(test_labels, test_predictions),
        "validation_scores": validation_score.tolist(),
        "test_scores": test_score.tolist(),
        "text_weight": 1.0,
        "numeric_weight": args.numeric_weight,
        "mode": args.mode,
        "score_formula": (
            "z(char_cross_entropy)"
            if args.mode == "lexical"
            else "z(numeric_mse)"
            if args.mode == "semantic"
            else "z(char_cross_entropy) + lambda * z(numeric_mse)"
        ),
        "validation_normal_char_mean": float(text_mean),
        "validation_normal_char_std": float(text_std),
        "validation_normal_numeric_mean": float(numeric_mean),
        "validation_normal_numeric_std": float(numeric_std),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": {
                key: value.detach().cpu() for key, value in model.state_dict().items()
            },
            "optimizer_state": optimizer.state_dict(),
            "best_validation_loss": best_validation_loss,
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist(),
            "vocabulary": VOCABULARY,
            "max_length": MAX_LENGTH,
            "latent_dim": args.latent_dim,
            "threshold": threshold,
            "text_mean": float(text_mean),
            "text_std": float(text_std),
            "numeric_mean": float(numeric_mean),
            "numeric_std": float(numeric_std),
            "feature_columns": list(FEATURE_COLUMNS),
            "numeric_dim": len(FEATURE_COLUMNS),
            "architecture": ARCHITECTURES[args.mode],
            "weight_decay": args.weight_decay,
            "pad_loss_weight": args.pad_loss_weight,
            "early_stop_patience": args.early_stop_patience,
            "numeric_weight": args.numeric_weight,
            "mode": args.mode,
            "score_formula": (
                "z(char_cross_entropy)"
                if args.mode == "lexical"
                else "z(numeric_mse)"
                if args.mode == "semantic"
                else "z(char_cross_entropy) + lambda * z(numeric_mse)"
            ),
        },
        checkpoint_path,
    )
    (args.output_dir / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    (args.output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if not args.no_gif:
        gif_path = save_training_gif(history, args.output_dir)
        if gif_path is not None:
            print(f"GIF do treinamento salvo em: {gif_path}")


if __name__ == "__main__":
    main()
