"""Testes de treino de poucas épocas, checkpoints e escolha de dispositivo."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

from source.features import FEATURE_COLUMNS, MAX_LENGTH, VOCABULARY, transform_features
from source.models import ARCHITECTURES
from source.scoring import load_checkpoint, normal_rows, read_rows

from conftest import MODES, run_training


@pytest.mark.parametrize("mode", MODES)
def test_checkpoint_has_expected_contents(
    trained_models: dict[str, Path], minimal_splits: Path, mode: str
) -> None:
    directory = trained_models[mode]
    checkpoint = torch.load(directory / "model.pt", map_location="cpu")
    assert checkpoint["mode"] == mode
    assert checkpoint["architecture"] == ARCHITECTURES[mode]
    assert checkpoint["feature_columns"] == list(FEATURE_COLUMNS)
    assert checkpoint["numeric_dim"] == len(FEATURE_COLUMNS) == 42
    assert list(checkpoint["vocabulary"]) == list(VOCABULARY)
    assert checkpoint["max_length"] == MAX_LENGTH
    assert all(value.device.type == "cpu" for value in checkpoint["model_state"].values())
    train_normals = normal_rows(read_rows(minimal_splits / "train.csv"))
    np.testing.assert_allclose(
        checkpoint["scaler_mean"], transform_features(train_normals).mean(axis=0), rtol=1e-4, atol=1e-6
    )
    history = json.loads((directory / "history.json").read_text(encoding="utf-8"))
    assert len(history) == 2 and history[0]["mode"] == mode
    assert (directory / "metrics.json").is_file()


@pytest.mark.parametrize("mode", MODES)
def test_loaded_model_reproduces_the_scores_saved_by_training(
    trained_models: dict[str, Path], minimal_splits: Path, mode: str
) -> None:
    loaded = load_checkpoint(trained_models[mode])
    saved = json.loads((trained_models[mode] / "metrics.json").read_text(encoding="utf-8"))
    scores = loaded.score(read_rows(minimal_splits / "test.csv"))
    np.testing.assert_allclose(scores, saved["test_scores"], rtol=1e-4, atol=1e-4)


def test_training_is_deterministic_on_cpu(minimal_splits: Path, tmp_path: Path) -> None:
    for name in ("first", "second"):
        run_training(minimal_splits, tmp_path / name, "hybrid", epochs=1)
    histories = [
        json.loads((tmp_path / name / "history.json").read_text(encoding="utf-8"))
        for name in ("first", "second")
    ]
    assert histories[0][0]["train_loss"] == histories[1][0]["train_loss"]
    assert histories[0][0]["validation_loss"] == histories[1][0]["validation_loss"]


def test_training_requires_normal_examples(minimal_splits: Path, tmp_path: Path) -> None:
    broken = tmp_path / "splits"
    broken.mkdir()
    for split in ("validation", "test"):
        (broken / f"{split}.csv").write_text(
            (minimal_splits / f"{split}.csv").read_text(encoding="utf-8"), encoding="utf-8"
        )
    lines = (minimal_splits / "train.csv").read_text(encoding="utf-8").splitlines()
    (broken / "train.csv").write_text("\n".join(lines[:1]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Split vazio"):
        run_training(broken, tmp_path / "out", "lexical", epochs=1)


def test_cuda_flag_fails_clearly_without_gpu(
    minimal_splits: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(ValueError, match="nenhuma GPU"):
        run_training(minimal_splits, tmp_path / "out", "lexical", epochs=1, device="cuda")


def test_auto_device_falls_back_to_cpu_and_reports_it(
    minimal_splits: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    run_training(minimal_splits, tmp_path / "out", "semantic", epochs=1, device="auto")
    assert "Dispositivo selecionado: CPU" in capsys.readouterr().out


def test_early_stop_patience_is_configurable(
    minimal_splits: Path, tmp_path: Path
) -> None:
    """A paciencia do early stopping pode ser ajustada pela CLI."""
    from source import train

    argv = [
        "train",
        "--mode", "semantic",
        "--splits-dir", str(minimal_splits),
        "--output-dir", str(tmp_path / "out"),
        "--epochs", "2",
        "--batch-size", "32",
        "--device", "cpu",
        "--fresh",
        "--no-live-plot",
        "--no-gif",
        "--early-stop-patience", "7",
    ]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", argv)
        train.main()

    checkpoint = torch.load(tmp_path / "out" / "model.pt", map_location="cpu")
    assert checkpoint["early_stop_patience"] == 7

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", [*argv[:-1], "-1"])
        with pytest.raises(ValueError, match="inválidos"):
            train.main()


def test_default_early_stop_patience_is_200() -> None:
    from source.train import EARLY_STOP_PATIENCE, parse_args

    assert EARLY_STOP_PATIENCE == 200
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", ["train"])
        assert parse_args().early_stop_patience == 200
