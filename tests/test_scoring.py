"""Testes de limiares, métricas e scores compartilhados."""

import numpy as np
import pytest
import torch
from sklearn.metrics import roc_auc_score

from source.features import FEATURE_COLUMNS, MAX_LENGTH, PAD, TOKEN_TO_INDEX, VOCABULARY
from source.models import CharAutoencoder, DenseAE, HybridAutoencoder
from source.scoring import (
    best_f1_threshold,
    classification_metrics,
    collapse_by_domain,
    expected_precision,
    percentile_threshold,
    ranking_metrics,
    recall_at_fpr,
    reconstruction_errors,
    score_batch,
)


def f1_at(scores: np.ndarray, labels: np.ndarray, threshold: float) -> float:
    predicted = scores > threshold
    true_positive = int((predicted & (labels == 1)).sum())
    denominator = 2 * true_positive + int((predicted & (labels == 0)).sum()) + int(
        (~predicted & (labels == 1)).sum()
    )
    return 2 * true_positive / denominator if denominator else 0.0


def test_percentile_threshold_matches_numpy_and_requires_scores() -> None:
    scores = np.arange(1, 101, dtype=float)
    assert percentile_threshold(scores) == pytest.approx(np.percentile(scores, 99))
    with pytest.raises(ValueError):
        percentile_threshold(np.array([]))


def test_best_f1_separates_perfectly_separable_scores() -> None:
    scores = np.array([0.1, 0.2, 0.3, 0.8, 0.9])
    labels = np.array([0, 0, 0, 1, 1])
    threshold = best_f1_threshold(scores, labels)
    assert 0.3 < threshold < 0.8
    assert f1_at(scores, labels, threshold) == 1.0


def test_best_f1_matches_brute_force_on_random_data() -> None:
    rng = np.random.default_rng(42)
    for _ in range(20):
        labels = rng.integers(0, 2, 60)
        if len(set(labels.tolist())) < 2:
            continue
        scores = rng.normal(labels * 0.8, 1.0)
        unique = np.unique(scores)
        candidates = np.concatenate(
            ([unique[0] - 1], (unique[:-1] + unique[1:]) / 2, [unique[-1]])
        )
        best = max(f1_at(scores, labels, candidate) for candidate in candidates)
        assert f1_at(scores, labels, best_f1_threshold(scores, labels)) == pytest.approx(best)


def test_best_f1_can_flag_everything_when_scores_are_uninformative() -> None:
    scores = np.array([0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.4, 0.5])
    labels = np.array([1, 1, 1, 1, 1, 1, 1, 0])
    threshold = best_f1_threshold(scores, labels)
    assert threshold < scores.min()
    assert (scores > threshold).all()


def test_best_f1_ties_use_the_highest_threshold() -> None:
    scores = np.array([0.1, 0.2, 0.9, 0.95])
    labels = np.array([0, 0, 1, 1])
    assert best_f1_threshold(scores, labels) == pytest.approx((0.2 + 0.9) / 2)


def test_best_f1_requires_both_classes() -> None:
    with pytest.raises(ValueError):
        best_f1_threshold(np.array([0.1, 0.2]), np.array([0, 0]))


def test_classification_metrics_known_values() -> None:
    labels = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    scores = np.array([0.1, 0.2, 0.6, 0.3, 0.9, 0.8, 0.4, 0.7])
    metrics = classification_metrics(labels, scores, threshold=0.5)
    assert metrics["confusion_matrix"] == [[3, 1], [1, 3]]
    assert metrics["precision"] == pytest.approx(0.75)
    assert metrics["recall"] == pytest.approx(0.75)
    assert metrics["f1"] == pytest.approx(0.75)
    assert metrics["fpr"] == pytest.approx(0.25)
    assert metrics["accuracy"] == pytest.approx(0.75)
    assert metrics["roc_auc"] == pytest.approx(roc_auc_score(labels, scores))
    assert metrics["threshold"] == 0.5


def test_ranking_metrics_need_both_classes() -> None:
    metrics = ranking_metrics(np.array([1, 1, 1]), np.array([0.1, 0.2, 0.3]))
    assert metrics == {"roc_auc": None, "pr_auc": None, "recall_at_fpr": None}


def test_recall_at_fpr_uses_the_roc_curve() -> None:
    labels = np.array([0] * 100 + [1] * 10)
    scores = np.concatenate((np.linspace(0, 1, 100), np.linspace(0.5, 1.5, 10)))
    recall = recall_at_fpr(labels, scores, max_fpr=0.01)
    assert recall == pytest.approx(
        (scores[labels == 1] > np.sort(scores[labels == 0])[-2]).mean()
    )


def test_expected_precision_depends_on_prevalence() -> None:
    assert expected_precision(1.0, 0.01, 0.5) == pytest.approx(1 / 1.01)
    assert expected_precision(1.0, 0.01, 0.001) == pytest.approx(0.001 / (0.001 + 0.00999))
    assert expected_precision(0.0, 0.0, 0.5) == 0.0


def test_collapse_by_domain_averages_scores_and_rejects_conflicts() -> None:
    domains, scores, labels = collapse_by_domain(
        ["a", "b", "a"], np.array([1.0, 5.0, 3.0]), np.array([0, 1, 0])
    )
    assert domains == ["a", "b"]
    assert scores.tolist() == [2.0, 5.0]
    assert labels.tolist() == [0, 1]
    with pytest.raises(ValueError, match="mais de um rótulo"):
        collapse_by_domain(["a", "a"], np.array([1.0, 2.0]), np.array([0, 1]))


def make_batch(size: int = 6) -> tuple[torch.Tensor, torch.Tensor]:
    generator = torch.Generator().manual_seed(1)
    characters = torch.full((size, MAX_LENGTH), TOKEN_TO_INDEX[PAD])
    for row in range(size):
        length = 8 + row
        characters[row, :length] = torch.randint(2, len(VOCABULARY), (length,), generator=generator)
    numeric = torch.randn(size, len(FEATURE_COLUMNS), generator=generator)
    return characters, numeric


def test_score_batch_branches_follow_the_model_mode() -> None:
    characters, numeric = make_batch()
    lexical = CharAutoencoder(len(VOCABULARY), MAX_LENGTH, 16).eval()
    text, numeric_error = score_batch(lexical, characters, numeric, "lexical")
    assert (text > 0).all() and (numeric_error == 0).all()

    dense = DenseAE(len(FEATURE_COLUMNS), 16, len(VOCABULARY)).eval()
    text, numeric_error = score_batch(dense, characters, numeric, "semantic")
    assert (text == 0).all() and (numeric_error > 0).all()

    hybrid = HybridAutoencoder(len(FEATURE_COLUMNS), len(VOCABULARY), MAX_LENGTH, 16).eval()
    text, numeric_error = score_batch(hybrid, characters, numeric, "hybrid")
    assert (text > 0).all() and (numeric_error > 0).all()


def test_score_batch_is_consistent_with_error_matrices() -> None:
    characters, numeric = make_batch()
    hybrid = HybridAutoencoder(len(FEATURE_COLUMNS), len(VOCABULARY), MAX_LENGTH, 16).eval()
    character_errors, feature_errors = reconstruction_errors(hybrid, characters, numeric, "hybrid")
    text, numeric_error = score_batch(hybrid, characters, numeric, "hybrid")
    valid = (characters != TOKEN_TO_INDEX[PAD]).sum(dim=1).numpy()
    assert character_errors.shape == tuple(characters.shape)
    assert feature_errors.shape == tuple(numeric.shape)
    assert (character_errors[characters.numpy() == TOKEN_TO_INDEX[PAD]] == 0).all()
    np.testing.assert_allclose(text, character_errors.sum(axis=1) / valid, rtol=1e-5)
    np.testing.assert_allclose(numeric_error, feature_errors.mean(axis=1), rtol=1e-5)


def test_score_batch_chunking_does_not_change_scores() -> None:
    characters, numeric = make_batch(10)
    hybrid = HybridAutoencoder(len(FEATURE_COLUMNS), len(VOCABULARY), MAX_LENGTH, 16).eval()
    whole = reconstruction_errors(hybrid, characters, numeric, "hybrid")
    chunked = reconstruction_errors(hybrid, characters, numeric, "hybrid", chunk_size=3)
    for first, second in zip(whole, chunked):
        np.testing.assert_allclose(first, second, rtol=1e-5, atol=1e-6)
