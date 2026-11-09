"""Explicabilidade por atributo e por caractere do erro de reconstrução."""

from __future__ import annotations

import numpy as np

if __package__:
    from .features import FEATURE_COLUMNS, PAD, TOKEN_TO_INDEX, VOCABULARY, normalize_domain
    from .scoring import (
        LoadedModel,
        encode_domains,
        numeric_tensor,
        reconstruction_errors,
    )
else:
    from features import FEATURE_COLUMNS, PAD, TOKEN_TO_INDEX, VOCABULARY, normalize_domain
    from scoring import LoadedModel, encode_domains, numeric_tensor, reconstruction_errors


def error_matrices(
    loaded: LoadedModel, rows: list[dict[str, str]]
) -> tuple[np.ndarray, np.ndarray]:
    """Erro por posição (N, L) e por atributo (N, D); vazio se o ramo não existe."""
    return reconstruction_errors(
        loaded.model,
        encode_domains(rows),
        numeric_tensor(rows, loaded.scaler),
        loaded.mode,
    )


def attribute_table(
    loaded: LoadedModel, rows: list[dict[str, str]], labels: np.ndarray
) -> list[dict[str, object]]:
    """Erro quadrático médio por atributo para normais e suspeitas."""
    _, feature_errors = error_matrices(loaded, rows)
    if feature_errors.shape[1] == 0:
        raise ValueError("O modo lexical não reconstrói atributos numéricos")
    normal = feature_errors[labels == 0].mean(axis=0)
    suspicious = feature_errors[labels == 1].mean(axis=0)
    table = [
        {
            "attribute": column,
            "mean_error_normal": float(normal[index]),
            "mean_error_suspeita": float(suspicious[index]),
            "ratio": float(suspicious[index] / max(normal[index], 1e-12)),
        }
        for index, column in enumerate(FEATURE_COLUMNS)
    ]
    return sorted(table, key=lambda item: item["ratio"], reverse=True)


def character_table(
    loaded: LoadedModel, rows: list[dict[str, str]], labels: np.ndarray
) -> list[dict[str, object]]:
    """Entropia cruzada média por caractere real para normais e suspeitas."""
    character_errors, _ = error_matrices(loaded, rows)
    if loaded.mode == "semantic":
        raise ValueError("O modo semântico não reconstrói caracteres")
    tokens = encode_domains(rows).numpy()
    pad = TOKEN_TO_INDEX[PAD]
    normal_rows_mask = (labels == 0)[:, None]
    suspicious_rows_mask = (labels == 1)[:, None]
    table = []
    for index, token in enumerate(VOCABULARY):
        if index == pad or token.startswith("<"):
            continue
        selected = tokens == index
        normal_values = character_errors[selected & normal_rows_mask]
        suspicious_values = character_errors[selected & suspicious_rows_mask]
        if not len(normal_values) and not len(suspicious_values):
            continue
        table.append(
            {
                "character": token,
                "count_normal": int(len(normal_values)),
                "mean_error_normal": _mean(normal_values),
                "count_suspeita": int(len(suspicious_values)),
                "mean_error_suspeita": _mean(suspicious_values),
            }
        )
    return table


def position_curves(
    loaded: LoadedModel, rows: list[dict[str, str]], labels: np.ndarray
) -> dict[str, list[float]]:
    """Erro médio por posição do domínio (somente posições reais, sem PAD)."""
    character_errors, _ = error_matrices(loaded, rows)
    valid = encode_domains(rows).numpy() != TOKEN_TO_INDEX[PAD]
    curves: dict[str, list[float]] = {}
    for name, value in (("normal", 0), ("suspeita", 1)):
        selected = valid & (labels == value)[:, None]
        counts = selected.sum(axis=0)
        sums = np.where(selected, character_errors, 0.0).sum(axis=0)
        curves[name] = [
            float(total / count) if count else float("nan")
            for total, count in zip(sums, counts)
        ]
    return curves


def explain_row(
    loaded: LoadedModel, row: dict[str, str], top_k: int = 3
) -> dict[str, object]:
    """Explica um domínio: score e principais atributos/caracteres responsáveis."""
    character_errors, feature_errors = error_matrices(loaded, [row])
    domain = normalize_domain(row["query"])
    explanation: dict[str, object] = {
        "domain": domain,
        "score": float(loaded.score([row])[0]),
    }
    if feature_errors.shape[1]:
        order = np.argsort(feature_errors[0])[::-1][:top_k]
        explanation["top_attributes"] = [
            (FEATURE_COLUMNS[index], float(feature_errors[0, index])) for index in order
        ]
    if loaded.mode != "semantic":
        length = min(len(domain), character_errors.shape[1])
        order = np.argsort(character_errors[0, :length])[::-1][:top_k]
        explanation["top_characters"] = [
            (domain[index], int(index), float(character_errors[0, index]))
            for index in order
        ]
    return explanation


def _mean(values: np.ndarray) -> float | None:
    return float(values.mean()) if len(values) else None
