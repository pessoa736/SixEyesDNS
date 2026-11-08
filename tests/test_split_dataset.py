"""Testes de interseção, determinismo e holdout do split por domínio."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from source.features import extract_features

FAMILIES = ("base32", "hex", "base64")


def build_dataset(path: Path, domains_per_family: int = 6) -> None:
    fieldnames = list(
        extract_features("web.atlas.test", query_type="A", family="normal")
    ) + ["query_type", "family", "label", "seed"]
    with path.open("w", newline="", encoding="utf-8") as dataset_file:
        writer = csv.DictWriter(dataset_file, fieldnames=fieldnames)
        writer.writeheader()
        for index in range(domains_per_family):
            normal = f"node-{index:03d}.web.atlas.test"
            row = extract_features(normal, query_type="A", family="normal")
            row.update(
                {"query_type": "A", "family": "normal", "label": "normal", "seed": "42"}
            )
            writer.writerow(row)
            for family in FAMILIES:
                domain = f"ab{family}{index}.tunnel.test"
                row = extract_features(domain, query_type="TXT", family=family)
                row.update(
                    {
                        "query_type": "TXT",
                        "family": family,
                        "label": "suspeita",
                        "seed": "42",
                    }
                )
                writer.writerow(row)


def run_split(dataset: Path, output_dir: Path, *extra: str) -> dict:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "source.split_dataset",
            "--input",
            str(dataset),
            "--output-dir",
            str(output_dir),
            "--seed",
            "42",
            *extra,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))


def read_domains(output_dir: Path, split: str) -> set[str]:
    with (output_dir / f"{split}.csv").open(newline="", encoding="utf-8") as file:
        return {row["query"] for row in csv.DictReader(file)}


def test_splits_have_no_domain_intersection(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    build_dataset(dataset)
    output_dir = tmp_path / "splits"
    run_split(dataset, output_dir)
    train = read_domains(output_dir, "train")
    validation = read_domains(output_dir, "validation")
    test = read_domains(output_dir, "test")
    assert not train & validation
    assert not train & test
    assert not validation & test
    assert train | validation | test == train | validation | test != set()


def test_train_contains_only_normals(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    build_dataset(dataset)
    output_dir = tmp_path / "splits"
    run_split(dataset, output_dir)
    with (output_dir / "train.csv").open(newline="", encoding="utf-8") as file:
        labels = {row["label"] for row in csv.DictReader(file)}
    assert labels == {"normal"}


def test_split_is_deterministic(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    build_dataset(dataset)
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_split(dataset, first)
    run_split(dataset, second)
    for split in ("train", "validation", "test"):
        assert (first / f"{split}.csv").read_text() == (second / f"{split}.csv").read_text()


def test_holdout_family_goes_entirely_to_test(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    build_dataset(dataset)
    output_dir = tmp_path / "splits"
    summary = run_split(dataset, output_dir, "--holdout-family", "base64")
    assert summary["holdout_family"] == "base64"
    for split in ("train", "validation"):
        with (output_dir / f"{split}.csv").open(newline="", encoding="utf-8") as file:
            families = {row["family"] for row in csv.DictReader(file)}
        assert "base64" not in families
    with (output_dir / "test.csv").open(newline="", encoding="utf-8") as file:
        test_families = {row["family"] for row in csv.DictReader(file)}
    assert "base64" in test_families
    by_family = summary["splits"]["test"]["by_family"]
    assert by_family["base64"]["rows"] == 6
    assert by_family["base64"]["domains"] == 6


def test_holdout_family_must_exist(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    build_dataset(dataset)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "source.split_dataset",
            "--input",
            str(dataset),
            "--output-dir",
            str(tmp_path / "splits"),
            "--holdout-family",
            "inexistente",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "ausente no dataset" in result.stderr


def test_summary_reports_domains_by_label_and_family(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    build_dataset(dataset)
    summary = run_split(dataset, tmp_path / "splits")
    for split in ("train", "validation", "test"):
        info = summary["splits"][split]
        assert info["rows"] == sum(v["rows"] for v in info["by_label"].values())
        assert info["rows"] == sum(v["rows"] for v in info["by_family"].values())
        for counts in info["by_family"].values():
            assert counts["domains"] <= counts["rows"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
