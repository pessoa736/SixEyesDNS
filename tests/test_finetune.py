"""Testes do fine-tuning normal-only e da invariância ao tipo DNS."""

import json
from pathlib import Path

import pytest
import torch

from source.demo import query_from_domain
from source.finetune import fine_tune, split_normal_queries
from source.scoring import load_checkpoint


def normal_queries(count: int = 12):
    return [query_from_domain(f"node-{index:03d}.atlas.test") for index in range(count)]


def test_query_type_does_not_change_the_score(trained_models: dict[str, Path]) -> None:
    loaded = load_checkpoint(trained_models["hybrid"])
    rows = [
        query_from_domain("staging.api.orbita.test", query_type).features
        for query_type in ("A", "TXT", "AAAA")
    ]
    scores = loaded.score(rows)
    assert scores[0] == pytest.approx(scores[1])
    assert scores[0] == pytest.approx(scores[2])


def test_split_deduplicates_domains_and_keeps_validation_disjoint() -> None:
    queries = normal_queries() + normal_queries(2)
    train, validation = split_normal_queries(queries, validation_fraction=0.2, seed=42)
    assert len(train) == 10 and len(validation) == 2
    assert {query.features["query"] for query in train}.isdisjoint(
        query.features["query"] for query in validation
    )
    with pytest.raises(ValueError, match="ao menos 10"):
        split_normal_queries(normal_queries(9))


def test_fine_tune_writes_a_loadable_checkpoint_without_mutating_the_base(
    trained_models: dict[str, Path], tmp_path: Path
) -> None:
    base = load_checkpoint(trained_models["hybrid"])
    base_state = {
        key: value.detach().clone() for key, value in base.model.state_dict().items()
    }
    output = tmp_path / "adapted"
    report = fine_tune(
        base,
        normal_queries(),
        output,
        confirmed_normal=True,
        epochs=1,
        batch_size=4,
        seed=42,
    )

    assert report["train_domains"] == 10
    assert report["validation_domains"] == 2
    assert report["test_metrics"] is None
    assert len(report["history"]) == 1
    assert report["threshold"] != 0
    assert (output / "model.pt").is_file()
    assert json.loads((output / "finetune.json").read_text()) == report
    adapted = load_checkpoint(output)
    assert adapted.mode == "hybrid"
    assert adapted.checkpoint["finetune"]["confirmed_normal_only"] is True
    for key, value in base.model.state_dict().items():
        assert torch.equal(value, base_state[key])


def test_fine_tune_refuses_unconfirmed_logs(
    trained_models: dict[str, Path], tmp_path: Path
) -> None:
    base = load_checkpoint(trained_models["hybrid"])
    with pytest.raises(ValueError, match="somente consultas normais"):
        fine_tune(
            base,
            normal_queries(),
            tmp_path / "refused",
            confirmed_normal=False,
            epochs=1,
        )
    assert not (tmp_path / "refused" / "model.pt").exists()
