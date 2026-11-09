"""Testes da avaliação completa em dataset mínimo, só com CPU."""

import csv
import json
from pathlib import Path

import numpy as np
import pytest

from source.evaluate import (
    Split,
    build_systems,
    calibrate,
    check_splits,
    load_splits,
    overfitting_rows,
    parse_model_dirs,
    run,
)
from source.scoring import percentile_threshold

from conftest import ANOMALY_FAMILIES, build_splits, make_row


@pytest.fixture(scope="module")
def evaluation(
    minimal_splits: Path, trained_models: dict[str, Path], tmp_path_factory: pytest.TempPathFactory
) -> tuple[dict[str, object], Path]:
    output = tmp_path_factory.mktemp("evaluation")
    result = run(minimal_splits, trained_models, output, top_false_positives=3)
    return result, output


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def test_outputs_are_written(evaluation: tuple[dict[str, object], Path]) -> None:
    _, output = evaluation
    expected = {
        "metrics.json", "metrics.csv", "summary.md", "ablation.md", "ablation.csv",
        "recall_by_family.csv", "fpr_by_profile.csv", "false_positives.csv",
        "prevalence.csv", "lofo.csv", "leakage.csv", "overfitting.csv",
        "explain_attributes.csv",
        "explain_characters.csv", "explain_examples.md", "roc-pr.png", "prevalence.png",
        "recall-by-family.png", "fpr-by-profile.png", "lofo.png", "confusion-matrices.png",
        "explain-attributes.png", "explain-characters.png",
    }
    assert expected <= {path.name for path in output.iterdir()}
    assert json.loads((output / "metrics.json").read_text(encoding="utf-8"))["seed"] == 42


def test_all_systems_and_levels_are_reported(evaluation: tuple[dict[str, object], Path]) -> None:
    result, _ = evaluation
    rows = result["metrics"]
    assert {row["system"] for row in rows} == {
        "entropy", "isolation_forest", "semantic", "lexical", "hybrid",
    }
    assert {row["level"] for row in rows} == {"record", "domain"}
    for row in rows:
        assert 0.0 <= row["fpr"] <= 1.0 and 0.0 <= row["recall"] <= 1.0
        assert 0.0 <= row["roc_auc"] <= 1.0
        assert row["tn"] + row["fp"] + row["fn"] + row["tp"] == row["rows"]


def test_domain_level_counts_unique_domains(evaluation: tuple[dict[str, object], Path]) -> None:
    result, _ = evaluation
    test = result["splits"]["test"]
    by_level = {
        row["level"]: row["rows"]
        for row in result["metrics"]
        if row["system"] == "hybrid" and row["split"] == "test" and row["policy"] == "p99"
    }
    assert by_level["record"] == test["rows"]
    assert by_level["domain"] == test["domains"] < test["rows"]


def test_thresholds_come_from_the_validation_split_only(
    evaluation: tuple[dict[str, object], Path], minimal_splits: Path
) -> None:
    result, _ = evaluation
    splits = load_splits(minimal_splits)
    validation_normal = splits["validation"].labels == 0
    for system, values in result["thresholds"].items():
        validation_rows = [
            row for row in result["metrics"]
            if row["system"] == system and row["split"] == "validation"
            and row["level"] == "record" and row["policy"] == "p99"
        ]
        assert validation_rows[0]["threshold"] == values["p99"]
        assert validation_rows[0]["fpr"] <= 0.1
    assert validation_normal.sum() > 0
    assert all("test" not in key for key in result["thresholds"]["hybrid"])


def test_lofo_covers_each_family_without_using_test_to_calibrate(
    evaluation: tuple[dict[str, object], Path]
) -> None:
    result, _ = evaluation
    families = {row["heldout_family"] for row in result["lofo"]}
    assert families == set(ANOMALY_FAMILIES)
    for row in result["lofo"]:
        assert 0.0 <= row["recall_best_f1_without_family"] <= 1.0
        assert row["threshold_all_families"] == result["thresholds"][row["system"]]["best_f1"]


def test_ablation_includes_lambda_variants(evaluation: tuple[dict[str, object], Path]) -> None:
    result, _ = evaluation
    variants = [row["variant"] for row in result["ablation"]]
    assert any("λ=0" in name for name in variants)
    assert any("só MSE" in name for name in variants)
    main = next(row for row in result["ablation"] if row["variant"] == "AE híbrido")
    same = next(row for row in result["ablation"] if row["variant"] == "AE híbrido, score com λ=1")
    assert main["p99_threshold"] == pytest.approx(same["p99_threshold"])


def test_false_positive_summary_includes_zero_counts(
    evaluation: tuple[dict[str, object], Path]
) -> None:
    result, _ = evaluation
    summary = result["false_positive_summary"]
    assert len(summary) == 10
    assert all(row["false_positive_rows"] >= 0 for row in summary)


def test_prevalence_table_matches_the_formula(evaluation: tuple[dict[str, object], Path]) -> None:
    _, output = evaluation
    for row in read_csv(output / "prevalence.csv"):
        recall, fpr, prevalence = float(row["recall"]), float(row["fpr"]), float(row["prevalence"])
        denominator = recall * prevalence + fpr * (1 - prevalence)
        expected = recall * prevalence / denominator if denominator else 0.0
        assert float(row["expected_precision"]) == pytest.approx(expected)


def test_explanations_cover_attributes_and_characters(
    evaluation: tuple[dict[str, object], Path]
) -> None:
    _, output = evaluation
    attributes = read_csv(output / "explain_attributes.csv")
    characters = read_csv(output / "explain_characters.csv")
    assert {row["system"] for row in attributes} == {"semantic", "hybrid"}
    assert {row["system"] for row in characters} == {"lexical", "hybrid"}
    assert len([row for row in attributes if row["system"] == "hybrid"]) == 42


def test_splits_with_shared_domains_are_rejected(tmp_path: Path) -> None:
    directory = build_splits(tmp_path / "splits")
    train = (directory / "train.csv").read_text(encoding="utf-8").splitlines()
    test_lines = (directory / "test.csv").read_text(encoding="utf-8").splitlines()
    (directory / "test.csv").write_text("\n".join(test_lines + [train[1]]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Domínios repetidos"):
        load_splits(directory)


def test_training_split_must_not_contain_suspicious_rows() -> None:
    normal = Split.from_rows([make_row("web.atlas.test", "normal", "normal", "normal")])
    suspicious = Split.from_rows([make_row("aaaa.tunnel.test", "suspeita", "hex", "hex")])
    with pytest.raises(ValueError, match="somente exemplos normais"):
        check_splits({"train": suspicious, "validation": normal, "test": normal})


def test_stale_checkpoint_is_detected(
    minimal_splits: Path, trained_models: dict[str, Path], tmp_path: Path
) -> None:
    other_splits = build_splits(tmp_path / "other", seed=7)
    # Outros domínios de validação mudam o limiar P99 salvo no checkpoint.
    for name in ("train", "validation", "test"):
        lines = (other_splits / f"{name}.csv").read_text(encoding="utf-8")
        (other_splits / f"{name}.csv").write_text(lines, encoding="utf-8")
    with pytest.raises(ValueError, match="splits mudaram|divergem|limiar"):
        run(other_splits, trained_models, tmp_path / "out", plots=False)


def test_overfitting_rows_compare_train_and_test_fpr(
    evaluation: tuple[dict[str, object], Path], minimal_splits: Path
) -> None:
    """A FPR do treino e do teste sao medidas com o mesmo limiar calibrado."""
    result, output = evaluation
    splits = load_splits(minimal_splits)
    systems, _ = build_systems({}, splits, 42, False)
    thresholds = {
        system.key: calibrate(system.scores, splits["validation"]) for system in systems
    }
    rows: list[dict[str, object]] = overfitting_rows(systems, splits, thresholds)
    assert rows
    for row in rows:
        train_fpr = float(str(row["train_fpr"]))
        test_fpr = float(str(row["test_fpr"]))
        assert 0.0 <= train_fpr <= 1.0
        assert 0.0 <= test_fpr <= 1.0
        assert row["train_normal_rows"] == int((splits["train"].labels == 0).sum())
        assert row["test_normal_rows"] == int((splits["test"].labels == 0).sum())
        if train_fpr > 0:
            assert float(str(row["test_over_train_ratio"])) == pytest.approx(
                test_fpr / train_fpr
            )
        else:
            assert row["test_over_train_ratio"] is None

    written = read_csv(output / "overfitting.csv")
    # a fixture da avaliacao inclui os tres autoencoders; as linhas calculadas
    # aqui usam apenas os baselines (build_systems sem diretorios de modelo)
    assert {row["system"] for row in written} >= {row["system"] for row in rows}
    for row in written:
        assert row["policy"] in {"p99", "best_f1"}
        assert float(row["train_fpr"]) >= 0.0
        assert float(row["test_fpr"]) >= 0.0


def test_model_argument_parsing() -> None:
    assert parse_model_dirs(["hybrid=results/x"]) == {"hybrid": Path("results/x")}
    with pytest.raises(ValueError):
        parse_model_dirs(["quantico=results/x"])
    assert set(parse_model_dirs(None)) == {"semantic", "lexical", "hybrid"}


def test_percentile_helper_is_shared_with_training(
    evaluation: tuple[dict[str, object], Path], minimal_splits: Path
) -> None:
    result, _ = evaluation
    splits = load_splits(minimal_splits)
    assert isinstance(percentile_threshold(np.arange(10.0)), float)
    assert result["splits"]["validation"]["normal_domains"] == len(
        {d for d, l in zip(splits["validation"].domains, splits["validation"].labels) if l == 0}
    )
