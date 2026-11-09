"""Fixtures com um dataset mínimo e sintético para testes rápidos em CPU."""

import base64
import csv
import random
import sys
from pathlib import Path

import pytest

from source.features import extract_features


SERVICES = ("web", "api", "auth", "cdn", "mail", "search", "billing", "metrics")
PLATFORMS = ("atlas", "brisa", "cobalto", "lumen", "nuvem", "orbita")
ANOMALY_FAMILIES = ("base32", "hex", "base64")
MODES = ("semantic", "lexical", "hybrid")


def normal_domain(index: int) -> str:
    return f"{SERVICES[index % 8]}-{index:03d}.{PLATFORMS[index % 6]}.test"


def anomalous_domain(rng: random.Random, family: str) -> str:
    payload = bytes(rng.randrange(256) for _ in range(12))
    if family == "base32":
        text = base64.b32encode(payload).decode("ascii").rstrip("=").lower()
    elif family == "hex":
        text = payload.hex()
    else:
        text = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{text}.tunnel.test"


def make_row(domain: str, label: str, family: str, profile: str) -> dict[str, object]:
    row = extract_features(domain, query_type="A", family=family)
    row.update(
        {
            "query_type": "A",
            "family": family,
            "profile": profile,
            "label": label,
            "seed": 42,
        }
    )
    return row


def write_split(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_splits(directory: Path, seed: int = 42) -> Path:
    """Cria train/validation/test sem domínios repetidos entre os splits."""
    rng = random.Random(seed)
    normal_counts = {"train": 60, "validation": 24, "test": 24}
    anomaly_counts = {"train": 0, "validation": 12, "test": 12}
    directory.mkdir(parents=True, exist_ok=True)
    next_normal = 0
    for split, normals in normal_counts.items():
        rows = []
        for _ in range(normals):
            domain = normal_domain(next_normal)
            profile = "normal_hard" if next_normal % 5 == 0 else "normal"
            rows.append(make_row(domain, "normal", "normal", profile))
            if next_normal % 3 == 0:
                rows.append(make_row(domain, "normal", "normal", profile))
            next_normal += 1
        for family in ANOMALY_FAMILIES:
            for _ in range(anomaly_counts[split]):
                domain = anomalous_domain(rng, family)
                rows.append(make_row(domain, "suspeita", family, family))
        rng.shuffle(rows)
        write_split(directory / f"{split}.csv", rows)
    return directory


@pytest.fixture(scope="session")
def minimal_splits(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_splits(tmp_path_factory.mktemp("splits"))


def run_training(
    splits_dir: Path, output_dir: Path, mode: str, epochs: int = 2, device: str = "cpu"
) -> None:
    from source import train

    argv = [
        "train",
        "--mode",
        mode,
        "--splits-dir",
        str(splits_dir),
        "--output-dir",
        str(output_dir),
        "--epochs",
        str(epochs),
        "--batch-size",
        "32",
        "--device",
        device,
        "--fresh",
        "--no-live-plot",
        "--no-gif",
    ]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "argv", argv)
        train.main()


@pytest.fixture(scope="session")
def trained_models(
    minimal_splits: Path, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("models")
    directories = {}
    for mode in MODES:
        directories[mode] = root / f"autoencoder-{mode}"
        run_training(minimal_splits, directories[mode], mode)
    return directories
