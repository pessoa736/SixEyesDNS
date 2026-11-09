"""Scores, calibração de limiares e métricas usados por treino, avaliação e demo.

Todos os limiares são calibrados somente com a validação; o teste nunca escolhe
limiar. Os atributos vêm de ``source/features.py``.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve
from sklearn.preprocessing import StandardScaler
from torch import nn

if __package__:
    from .features import (
        FEATURE_COLUMNS,
        MAX_LENGTH,
        PAD,
        TOKEN_TO_INDEX,
        VOCABULARY,
        encode_domain,
        transform_features,
    )
    from .models import ARCHITECTURES, build_model
else:
    from features import (
        FEATURE_COLUMNS,
        MAX_LENGTH,
        PAD,
        TOKEN_TO_INDEX,
        VOCABULARY,
        encode_domain,
        transform_features,
    )
    from models import ARCHITECTURES, build_model


DEFAULT_PERCENTILE = 99.0
DEFAULT_MAX_FPR = 0.01
CHUNK_SIZE = 4096


def read_rows(path: Path) -> list[dict[str, str]]:
    """Lê um split CSV e falha se ele estiver vazio."""
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError(f"Split vazio: {path}")
    return rows


def normal_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected = [row for row in rows if row.get("label") == "normal"]
    if not selected:
        raise ValueError("O split precisa conter exemplos normais")
    return selected


def anomaly_labels(rows: list[dict[str, str]]) -> np.ndarray:
    """Rótulo binário: 1 para suspeita e 0 para normal."""
    return np.asarray([row["label"] != "normal" for row in rows], dtype=int)


def encode_domains(rows: list[dict[str, str]]) -> torch.Tensor:
    encoded = np.stack([encode_domain(row["query"]) for row in rows])
    return torch.from_numpy(encoded)


def numeric_tensor(rows: list[dict[str, str]], scaler: StandardScaler) -> torch.Tensor:
    return torch.from_numpy(scaler.transform(transform_features(rows)).astype(np.float32))


def text_error_matrix(logits: torch.Tensor, characters: torch.Tensor) -> torch.Tensor:
    """Entropia cruzada por posição de caractere; posições PAD valem zero."""
    pad = TOKEN_TO_INDEX[PAD]
    if logits.numel() == 0:
        return torch.zeros(characters.shape, device=characters.device)
    token_loss = nn.functional.cross_entropy(
        logits, characters, ignore_index=pad, reduction="none"
    )
    return token_loss.masked_fill(characters == pad, 0.0)


def reconstruction_errors(
    model: nn.Module,
    characters: torch.Tensor,
    numeric: torch.Tensor,
    mode: str,
    chunk_size: int = CHUNK_SIZE,
) -> tuple[np.ndarray, np.ndarray]:
    """Erros por posição (N, L) e por atributo (N, D) de reconstrução."""
    device = next(model.parameters()).device
    character_parts: list[np.ndarray] = []
    feature_parts: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, characters.shape[0], chunk_size):
            chunk_characters = characters[start : start + chunk_size].to(device)
            chunk_numeric = numeric[start : start + chunk_size].to(device)
            logits, reconstructed = model(chunk_characters, chunk_numeric, mode=mode)
            character_parts.append(
                text_error_matrix(logits, chunk_characters).cpu().numpy()
            )
            if reconstructed.shape[1] == 0:
                feature_parts.append(
                    np.zeros((chunk_characters.shape[0], 0), dtype=np.float32)
                )
            else:
                feature_parts.append(
                    ((reconstructed - chunk_numeric) ** 2).cpu().numpy()
                )
    return np.concatenate(character_parts), np.concatenate(feature_parts)


def score_batch(
    model: nn.Module,
    characters: torch.Tensor,
    numeric: torch.Tensor,
    mode: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Erro textual (CE médio por token real) e numérico (MSE) por exemplo."""
    character_errors, feature_errors = reconstruction_errors(
        model, characters, numeric, mode
    )
    valid_tokens = np.maximum(
        (characters != TOKEN_TO_INDEX[PAD]).sum(dim=1).cpu().numpy(), 1
    )
    text_error = character_errors.sum(axis=1) / valid_tokens
    if feature_errors.shape[1] == 0:
        numeric_error = np.zeros(characters.shape[0], dtype=np.float32)
    else:
        numeric_error = feature_errors.mean(axis=1)
    return text_error, numeric_error


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


@dataclass
class LoadedModel:
    """Autoencoder treinado, scaler do treino e metadados do checkpoint."""

    mode: str
    model: nn.Module
    scaler: StandardScaler
    checkpoint: dict

    def components(self, rows: list[dict[str, str]]) -> tuple[np.ndarray, np.ndarray]:
        """Erros textual e numérico brutos das linhas."""
        return score_batch(
            self.model,
            encode_domains(rows),
            numeric_tensor(rows, self.scaler),
            self.mode,
        )

    def combine(
        self,
        text_error: np.ndarray,
        numeric_error: np.ndarray,
        numeric_weight: float | None = None,
        mode: str | None = None,
    ) -> np.ndarray:
        """Score padronizado com as estatísticas dos normais da validação.

        ``mode`` permite avaliar o score de um único ramo do modelo híbrido.
        """
        checkpoint = self.checkpoint
        weight = checkpoint["numeric_weight"] if numeric_weight is None else numeric_weight
        return mode_scores(
            text_error,
            numeric_error,
            mode or self.mode,
            checkpoint["text_mean"],
            checkpoint["text_std"],
            checkpoint["numeric_mean"],
            checkpoint["numeric_std"],
            weight,
        )

    def score(self, rows: list[dict[str, str]]) -> np.ndarray:
        return self.combine(*self.components(rows))


def load_checkpoint(model_dir: Path) -> LoadedModel:
    """Carrega ``model.pt`` validando arquitetura, atributos e vocabulário."""
    path = model_dir / "model.pt"
    if not path.is_file():
        raise FileNotFoundError(f"Checkpoint não encontrado: {path}")
    checkpoint = torch.load(path, map_location="cpu")
    mode = checkpoint.get("mode", "hybrid")
    if mode not in ARCHITECTURES:
        raise ValueError(f"Modo desconhecido no checkpoint {path}: {mode}")
    if checkpoint.get("architecture") != ARCHITECTURES[mode]:
        raise ValueError(
            f"{path} usa a arquitetura {checkpoint.get('architecture')!r}; "
            f"esperado {ARCHITECTURES[mode]!r}. Retreine com --fresh."
        )
    if list(checkpoint["feature_columns"]) != list(FEATURE_COLUMNS):
        raise ValueError(f"{path} foi treinado com outra lista de atributos")
    if list(checkpoint["vocabulary"]) != list(VOCABULARY):
        raise ValueError(f"{path} foi treinado com outro vocabulário")
    if int(checkpoint["max_length"]) != MAX_LENGTH:
        raise ValueError(f"{path} foi treinado com outro comprimento máximo")
    model = build_model(
        mode,
        len(FEATURE_COLUMNS),
        len(VOCABULARY),
        MAX_LENGTH,
        int(checkpoint["latent_dim"]),
    )
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    scaler = StandardScaler()
    scaler.mean_ = np.asarray(checkpoint["scaler_mean"], dtype=np.float64)
    scaler.scale_ = np.asarray(checkpoint["scaler_scale"], dtype=np.float64)
    scaler.var_ = scaler.scale_**2
    scaler.n_features_in_ = len(scaler.mean_)
    return LoadedModel(mode, model, scaler, checkpoint)


def confusion_matrix(labels: np.ndarray, predictions: np.ndarray) -> list[list[int]]:
    """Monta [[VN, FP], [FN, VP]] para a classe positiva 'suspeita'."""
    true_negative = int(np.sum((labels == 0) & (predictions == 0)))
    false_positive = int(np.sum((labels == 0) & (predictions == 1)))
    false_negative = int(np.sum((labels == 1) & (predictions == 0)))
    true_positive = int(np.sum((labels == 1) & (predictions == 1)))
    return [[true_negative, false_positive], [false_negative, true_positive]]


def percentile_threshold(
    normal_scores: np.ndarray, percentile: float = DEFAULT_PERCENTILE
) -> float:
    """Limiar P99 dos scores normais; calibrar só com a validação."""
    if len(normal_scores) == 0:
        raise ValueError("São necessários scores normais para calibrar o limiar")
    return float(np.percentile(normal_scores, percentile))


def best_f1_threshold(scores: np.ndarray, labels: np.ndarray) -> float:
    """Limiar de maior F1 (``score > limiar``); empates ficam com o maior limiar.

    Inclui o ponto que marca tudo como suspeito, que vence em detectores sem
    poder discriminativo quando as suspeitas são maioria.
    """
    if len(set(labels.tolist())) < 2:
        raise ValueError("O melhor F1 exige exemplos normais e suspeitos")
    scores = np.asarray(scores, dtype=np.float64)
    order = np.argsort(scores, kind="stable")
    sorted_scores = scores[order]
    sorted_labels = labels[order]
    unique_scores, first_index = np.unique(sorted_scores, return_index=True)
    positives_total = int(sorted_labels.sum())
    negatives_total = len(sorted_scores) - positives_total
    positives_before = np.concatenate(([0], np.cumsum(sorted_labels)))
    negatives_before = np.concatenate(([0], np.cumsum(1 - sorted_labels)))
    # Cada corte deixa à direita tudo o que é maior que o limiar candidato.
    cut_positions = np.concatenate((first_index[1:], [len(sorted_scores)]))
    true_positive = positives_total - positives_before[cut_positions]
    false_positive = negatives_total - negatives_before[cut_positions]
    false_negative = positives_total - true_positive
    denominator = 2 * true_positive + false_positive + false_negative
    f1 = np.divide(
        2 * true_positive,
        denominator,
        out=np.zeros(len(unique_scores), dtype=float),
        where=denominator > 0,
    )
    # O primeiro candidato marca tudo como suspeito (limiar abaixo do menor score).
    f1 = np.concatenate(([2 * positives_total / (2 * positives_total + negatives_total)], f1))
    candidates = np.concatenate(
        (
            [np.nextafter(unique_scores[0], -np.inf)],
            (unique_scores[:-1] + unique_scores[1:]) / 2,
            [unique_scores[-1]],
        )
    )
    best = len(f1) - 1 - int(np.argmax(f1[::-1]))
    return float(candidates[best])


def classification_metrics(
    labels: np.ndarray, scores: np.ndarray, threshold: float
) -> dict[str, object]:
    """Precisão, recall, F1, FPR, matriz de confusão e AUCs para um limiar fixo."""
    predictions = (scores > threshold).astype(int)
    matrix = confusion_matrix(labels, predictions)
    (true_negative, false_positive), (false_negative, true_positive) = matrix
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    f1 = _ratio(2 * precision * recall, precision + recall)
    return {
        "threshold": float(threshold),
        "rows": int(len(labels)),
        "accuracy": _ratio(true_negative + true_positive, len(labels)),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": _ratio(false_positive, false_positive + true_negative),
        "confusion_matrix": matrix,
        **ranking_metrics(labels, scores),
    }


def ranking_metrics(
    labels: np.ndarray, scores: np.ndarray, max_fpr: float = DEFAULT_MAX_FPR
) -> dict[str, float | None]:
    """Métricas independentes de limiar: ROC-AUC, PR-AUC e recall a FPR fixa."""
    if len(set(labels.tolist())) < 2:
        return {"roc_auc": None, "pr_auc": None, "recall_at_fpr": None}
    return {
        "roc_auc": float(roc_auc_score(labels, scores)),
        "pr_auc": float(average_precision_score(labels, scores)),
        "recall_at_fpr": recall_at_fpr(labels, scores, max_fpr),
    }


def recall_at_fpr(
    labels: np.ndarray, scores: np.ndarray, max_fpr: float = DEFAULT_MAX_FPR
) -> float:
    """Maior recall da curva ROC com FPR menor ou igual a ``max_fpr``."""
    fpr, tpr, _ = roc_curve(labels, scores)
    return float(tpr[fpr <= max_fpr].max())


def expected_precision(recall: float, fpr: float, prevalence: float) -> float:
    """Precisão esperada quando a prevalência de suspeitas é ``prevalence``."""
    true_positive = recall * prevalence
    false_positive = fpr * (1.0 - prevalence)
    return _ratio(true_positive, true_positive + false_positive)


def collapse_by_domain(
    domains: list[str], scores: np.ndarray, labels: np.ndarray
) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Uma linha por domínio único (score médio); falha com rótulos conflitantes."""
    order: dict[str, list[int]] = {}
    for index, domain in enumerate(domains):
        order.setdefault(domain, []).append(index)
    unique = list(order)
    collapsed_scores = np.asarray([scores[order[domain]].mean() for domain in unique])
    collapsed_labels = []
    for domain in unique:
        domain_labels = set(labels[order[domain]].tolist())
        if len(domain_labels) != 1:
            raise ValueError(f"O domínio {domain} possui mais de um rótulo")
        collapsed_labels.append(domain_labels.pop())
    return unique, collapsed_scores, np.asarray(collapsed_labels, dtype=int)


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0
