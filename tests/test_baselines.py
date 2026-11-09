"""Testes dos baselines de entropia e Isolation Forest."""

import numpy as np
from sklearn.metrics import roc_auc_score

from source.baselines import IsolationForestBaseline, entropy_scores
from source.features import normalize_domain, shannon_entropy
from source.scoring import anomaly_labels, normal_rows, read_rows


def test_entropy_scores_use_the_shared_feature_function() -> None:
    rows = [{"query": "web.atlas.test"}, {"query": "ABCDEFGH1234.tunnel.test"}]
    scores = entropy_scores(rows)
    assert scores[0] == shannon_entropy(normalize_domain("web.atlas.test"))
    assert scores[1] > scores[0]


def test_isolation_forest_is_deterministic_and_separates_encoded_domains(
    minimal_splits,
) -> None:
    train = normal_rows(read_rows(minimal_splits / "train.csv"))
    test = read_rows(minimal_splits / "test.csv")
    first = IsolationForestBaseline(seed=42).fit(train).score(test)
    second = IsolationForestBaseline(seed=42).fit(train).score(test)
    np.testing.assert_array_equal(first, second)
    assert roc_auc_score(anomaly_labels(test), first) > 0.8
