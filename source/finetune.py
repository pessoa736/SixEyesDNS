"""Fine-tuning não supervisionado de autoencoders com normais confirmados.

A adaptação separa domínios entre treino e validação, ajusta o scaler somente
no treino e recalibra o P99 somente na validação. Não produz métricas de teste:
isso exigiria um conjunto rotulado independente do arquivo de adaptação.
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from .demo import ReplayQuery, read_replay
from .features import TOKEN_TO_INDEX, PAD, transform_features
from .scoring import (
    LoadedModel,
    encode_domains,
    load_checkpoint,
    mode_scores,
    numeric_tensor,
    percentile_threshold,
    score_batch,
)
from .train import character_loss, set_seed


def split_normal_queries(
    queries: list[ReplayQuery], validation_fraction: float = 0.2, seed: int = 42
) -> tuple[list[ReplayQuery], list[ReplayQuery]]:
    """Deduplica por domínio e separa validação sem vazamento de moldes iguais."""
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction precisa estar entre 0 e 1")
    unique = list({query.features["query"]: query for query in queries}.values())
    if len(unique) < 10:
        raise ValueError(
            "O fine-tuning precisa de ao menos 10 domínios normais únicos; "
            f"o arquivo contém {len(unique)}"
        )
    random.Random(seed).shuffle(unique)
    validation_count = min(
        len(unique) - 1, max(1, round(len(unique) * validation_fraction))
    )
    return unique[validation_count:], unique[:validation_count]


def reconstruction_objective(
    model: nn.Module,
    characters: torch.Tensor,
    numeric: torch.Tensor,
    mode: str,
    numeric_weight: float,
    pad_loss_weight: float,
) -> torch.Tensor:
    """Mesma combinação CE/MSE usada no treinamento original."""
    logits, reconstructed = model(characters, numeric, mode=mode)
    lexical_loss = (
        character_loss(logits, characters, pad_loss_weight)
        if mode != "semantic"
        else torch.zeros((), device=characters.device)
    )
    semantic_loss = (
        nn.functional.mse_loss(reconstructed, numeric)
        if mode != "lexical"
        else torch.zeros((), device=characters.device)
    )
    if mode == "lexical":
        return lexical_loss
    if mode == "semantic":
        return semantic_loss
    return lexical_loss + numeric_weight * semantic_loss


def fine_tune(
    loaded: LoadedModel,
    queries: list[ReplayQuery],
    output_dir: Path,
    *,
    confirmed_normal: bool,
    epochs: int = 3,
    learning_rate: float = 1e-4,
    batch_size: int = 32,
    validation_fraction: float = 0.2,
    seed: int = 42,
) -> dict[str, Any]:
    """Adapta uma cópia do checkpoint e salva um novo modelo, nunca o original."""
    if not confirmed_normal:
        raise ValueError(
            "Confirme que o log contém somente consultas normais; anomalias no "
            "fine-tuning ensinam o autoencoder a reconstruir o túnel"
        )
    if epochs <= 0 or batch_size <= 0 or learning_rate <= 0:
        raise ValueError("epochs, batch_size e learning_rate precisam ser positivos")

    train_queries, validation_queries = split_normal_queries(
        queries, validation_fraction, seed
    )
    train_rows = [query.features for query in train_queries]
    validation_rows = [query.features for query in validation_queries]
    scaler = StandardScaler().fit(transform_features(train_rows))
    train_characters = encode_domains(train_rows)
    train_numeric = numeric_tensor(train_rows, scaler)
    validation_characters = encode_domains(validation_rows)
    validation_numeric = numeric_tensor(validation_rows, scaler)

    set_seed(seed)
    model = copy.deepcopy(loaded.model).cpu()
    checkpoint = copy.deepcopy(loaded.checkpoint)
    mode = loaded.mode
    numeric_weight = float(checkpoint["numeric_weight"])
    pad_loss_weight = float(checkpoint.get("pad_loss_weight", 0.2))
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=learning_rate,
        weight_decay=float(checkpoint.get("weight_decay", 1e-4)),
    )
    loader = DataLoader(
        TensorDataset(train_characters, train_numeric),
        batch_size=batch_size,
        shuffle=True,
        generator=torch.Generator().manual_seed(seed),
    )

    best_loss = float("inf")
    best_model_state = copy.deepcopy(model.state_dict())
    best_optimizer_state = copy.deepcopy(optimizer.state_dict())
    history: list[dict[str, float | int]] = []
    for epoch in range(1, epochs + 1):
        model.train()
        train_losses = []
        for characters, numeric in loader:
            corrupted_characters = characters.clone()
            mask = torch.rand_like(characters, dtype=torch.float32) < 0.05
            mask &= characters != TOKEN_TO_INDEX[PAD]
            corrupted_characters[mask] = TOKEN_TO_INDEX["<UNK>"]
            corrupted_numeric = numeric + torch.randn_like(numeric) * 0.01
            loss = reconstruction_objective(
                model,
                corrupted_characters,
                corrupted_numeric,
                mode,
                numeric_weight,
                pad_loss_weight,
            )
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_losses.append(float(loss.item()))

        model.eval()
        with torch.no_grad():
            validation_loss = float(
                reconstruction_objective(
                    model,
                    validation_characters,
                    validation_numeric,
                    mode,
                    numeric_weight,
                    pad_loss_weight,
                ).item()
            )
        history.append(
            {
                "epoch": epoch,
                "train_loss": float(np.mean(train_losses)),
                "validation_loss": validation_loss,
            }
        )
        if validation_loss < best_loss:
            best_loss = validation_loss
            best_model_state = copy.deepcopy(model.state_dict())
            best_optimizer_state = copy.deepcopy(optimizer.state_dict())

    model.load_state_dict(best_model_state)
    optimizer.load_state_dict(best_optimizer_state)
    model.eval()
    validation_text, validation_numeric_error = score_batch(
        model, validation_characters, validation_numeric, mode
    )
    text_mean = float(validation_text.mean())
    text_std = float(validation_text.std() + 1e-8)
    numeric_mean = float(validation_numeric_error.mean())
    numeric_std = float(validation_numeric_error.std() + 1e-8)
    threshold = percentile_threshold(
        mode_scores(
            validation_text,
            validation_numeric_error,
            mode,
            text_mean,
            text_std,
            numeric_mean,
            numeric_std,
            numeric_weight,
        )
    )

    checkpoint.update(
        {
            "model_state": {
                key: value.detach().cpu() for key, value in model.state_dict().items()
            },
            "optimizer_state": best_optimizer_state,
            "best_validation_loss": best_loss,
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist(),
            "threshold": threshold,
            "text_mean": text_mean,
            "text_std": text_std,
            "numeric_mean": numeric_mean,
            "numeric_std": numeric_std,
        }
    )
    adaptation = {
        "confirmed_normal_only": True,
        "train_domains": len(train_queries),
        "validation_domains": len(validation_queries),
        "validation_fraction": validation_fraction,
        "epochs": epochs,
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "seed": seed,
    }
    checkpoint["finetune"] = adaptation
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "model.pt"
    torch.save(checkpoint, checkpoint_path)

    report: dict[str, Any] = {
        **adaptation,
        "mode": mode,
        "base_threshold": float(loaded.checkpoint["threshold"]),
        "threshold": threshold,
        "best_validation_loss": best_loss,
        "history": history,
        "checkpoint": str(checkpoint_path),
        "test_metrics": None,
        "warning": (
            "A validação de fine-tuning só escolhe o checkpoint e o limiar; "
            "não mede desempenho em dados novos. Avalie com um teste independente."
        ),
    }
    (output_dir / "finetune.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def fine_tune_from_log(
    model_dir: Path,
    replay_path: Path,
    output_dir: Path,
    *,
    confirmed_normal: bool,
    limit: int | None = None,
    epochs: int = 3,
    learning_rate: float = 1e-4,
    batch_size: int = 32,
    validation_fraction: float = 0.2,
    seed: int = 42,
) -> dict[str, Any]:
    """Lê normais de um log e produz um checkpoint em diretório separado."""
    if output_dir.resolve() == model_dir.resolve():
        raise ValueError("output_dir precisa ser diferente do checkpoint base")
    queries = read_replay(replay_path, limit=limit)
    loaded = load_checkpoint(model_dir)
    return fine_tune(
        loaded,
        queries,
        output_dir,
        confirmed_normal=confirmed_normal,
        epochs=epochs,
        learning_rate=learning_rate,
        batch_size=batch_size,
        validation_fraction=validation_fraction,
        seed=seed,
    )
