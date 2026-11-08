"""Treina os ramos lexical, semântico ou híbrido do autoencoder."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import random
from pathlib import Path

import numpy as np
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

if __package__:
    from .features import FEATURE_COLUMNS, normalize_domain, transform_features
    from .models import HybridAutoencoder
else:
    from features import FEATURE_COLUMNS, normalize_domain, transform_features
    from models import HybridAutoencoder


CHARACTERS = tuple("abcdefghijklmnopqrstuvwxyz0123456789-_.")
PAD = "<PAD>"
UNK = "<UNK>"
VOCABULARY = (PAD, UNK) + CHARACTERS
TOKEN_TO_INDEX = {token: index for index, token in enumerate(VOCABULARY)}
MAX_LENGTH = 64


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
        "--numeric-noise-std",
        type=float,
        default=0.01,
        help="Desvio do ruído gaussiano nas features durante o treino",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fresh", action="store_true")
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError(f"Split vazio: {path}")
    return rows


def encode_domains(rows: list[dict[str, str]]) -> torch.Tensor:
    encoded = np.full((len(rows), MAX_LENGTH), TOKEN_TO_INDEX[PAD], dtype=np.int64)
    for row_index, row in enumerate(rows):
        domain = normalize_domain(row["query"])[:MAX_LENGTH]
        for column, character in enumerate(domain):
            encoded[row_index, column] = TOKEN_TO_INDEX.get(character, TOKEN_TO_INDEX[UNK])
    return torch.from_numpy(encoded)


def normal_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected = [row for row in rows if row.get("label") == "normal"]
    if not selected:
        raise ValueError("O split precisa conter exemplos normais")
    return selected


def numeric_tensor(rows: list[dict[str, str]], scaler: StandardScaler) -> torch.Tensor:
    return torch.from_numpy(scaler.transform(transform_features(rows)).astype(np.float32))


def score_batch(
    model: HybridAutoencoder,
    characters: torch.Tensor,
    numeric: torch.Tensor,
    mode: str,
) -> tuple[np.ndarray, np.ndarray]:
    with torch.no_grad():
        logits, reconstructed_numeric = model(characters, numeric, mode=mode)
        token_loss = nn.functional.cross_entropy(
            logits,
            characters,
            ignore_index=TOKEN_TO_INDEX[PAD],
            reduction="none",
        )
        valid_tokens = (characters != TOKEN_TO_INDEX[PAD]).sum(dim=1).clamp_min(1)
        text_error = (
            token_loss.masked_fill(characters == TOKEN_TO_INDEX[PAD], 0.0).sum(dim=1)
            / valid_tokens
        )
        numeric_error = ((reconstructed_numeric - numeric) ** 2).mean(dim=1)
    return text_error.numpy(), numeric_error.numpy()


def combine_scores(
    text_error: np.ndarray,
    numeric_error: np.ndarray,
    text_mean: float,
    text_std: float,
    numeric_mean: float,
    numeric_std: float,
    numeric_weight: float,
) -> np.ndarray:
    """Combina CE lexical e MSE numérico em escalas comparáveis."""
    return (text_error - text_mean) / text_std + numeric_weight * (
        (numeric_error - numeric_mean) / numeric_std
    )


def mode_scores(
    text_error: np.ndarray,
    numeric_error: np.ndarray,
    mode: str,
    text_mean: float,
    text_std: float,
    numeric_mean: float,
    numeric_std: float,
    numeric_weight: float,
) -> np.ndarray:
    if mode == "lexical":
        return (text_error - text_mean) / text_std
    if mode == "semantic":
        return (numeric_error - numeric_mean) / numeric_std
    return combine_scores(
        text_error,
        numeric_error,
        text_mean,
        text_std,
        numeric_mean,
        numeric_std,
        numeric_weight,
    )


def main() -> None:
    args = parse_args()
    if (
        args.epochs <= 0
        or args.batch_size <= 0
        or args.numeric_weight < 0
        or args.weight_decay < 0
        or not 0 <= args.char_mask_prob < 1
        or args.numeric_noise_std < 0
    ):
        raise ValueError("Parâmetros de treino inválidos")
    set_seed(args.seed)
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
    model = HybridAutoencoder(
        len(FEATURE_COLUMNS), len(VOCABULARY), MAX_LENGTH, args.latent_dim
    )
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
        if checkpoint.get("architecture") != "positional-conv-v2":
            raise ValueError(
                "O checkpoint usa a arquitetura antiga; execute com --fresh "
                "para treinar a arquitetura posicional atualizada."
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

    loader = DataLoader(
        TensorDataset(train_characters, train_numeric),
        batch_size=args.batch_size,
        shuffle=True,
    )
    text_loss = nn.CrossEntropyLoss(ignore_index=TOKEN_TO_INDEX[PAD])
    numeric_loss = nn.MSELoss()
    for offset in range(args.epochs):
        model.train()
        losses = []
        for characters, numeric in loader:
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
            lexical_loss = text_loss(logits, characters)
            semantic_loss = numeric_loss(reconstructed, numeric)
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
            validation_lexical_loss = text_loss(
                validation_logits, validation_normal_characters
            )
            validation_semantic_loss = numeric_loss(
                validation_reconstructed, validation_normal_numeric
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
        validation_labels = np.asarray(
            [row["label"] != "normal" for row in validation], dtype=int
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
        print(
            f"Época {epoch:03d} | treino_loss={np.mean(losses):.6f} | "
            f"val_loss={validation_loss:.6f} | "
            f"val_accuracy={history[-1]['validation_accuracy']:.4f}"
        )

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
    metrics = {
        "threshold": threshold,
        "validation_accuracy": float(
            np.mean((validation_score > threshold) == np.asarray([row["label"] != "normal" for row in validation]))
        ),
        "test_accuracy": float(
            np.mean((test_score > threshold) == np.asarray([row["label"] != "normal" for row in test]))
        ),
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
            "model_state": model.state_dict(),
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
            "architecture": "positional-conv-v2",
            "weight_decay": args.weight_decay,
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


if __name__ == "__main__":
    main()
