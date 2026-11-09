"""Baselines sem rede neural: limiar de entropia e Isolation Forest."""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

if __package__:
    from .features import normalize_domain, shannon_entropy, transform_features
else:
    from features import normalize_domain, shannon_entropy, transform_features


ISOLATION_FOREST_TREES = 200


def entropy_scores(rows: list[dict[str, str]]) -> np.ndarray:
    """Entropia de Shannon do domínio normalizado; maior significa mais suspeito."""
    return np.asarray(
        [shannon_entropy(normalize_domain(row["query"])) for row in rows],
        dtype=np.float64,
    )


class IsolationForestBaseline:
    """Isolation Forest ajustado somente com os normais do treino."""

    def __init__(self, seed: int = 42, n_estimators: int = ISOLATION_FOREST_TREES) -> None:
        self.scaler = StandardScaler()
        self.forest = IsolationForest(
            n_estimators=n_estimators,
            contamination="auto",
            random_state=seed,
            n_jobs=1,
        )

    def fit(self, normal_rows: list[dict[str, str]]) -> "IsolationForestBaseline":
        features = self.scaler.fit_transform(transform_features(normal_rows))
        self.forest.fit(features)
        return self

    def score(self, rows: list[dict[str, str]]) -> np.ndarray:
        """Score de anomalia: o oposto de ``score_samples`` (maior é mais anômalo)."""
        features = self.scaler.transform(transform_features(rows))
        return -self.forest.score_samples(features)
