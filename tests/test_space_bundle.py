"""Testes do pacote enviado ao Hugging Face Space."""

import ast
import re
import sys
from pathlib import Path

import pytest

from source.space_bundle import (
    CPU_INDEX,
    MARKER,
    build_bundle,
    read_front_matter,
    space_requirements,
)

ROOT = Path(__file__).resolve().parent.parent
# O import usa o nome do módulo; o pacote do pip às vezes tem outro nome.
PIP_NAMES = {"sklearn": "scikit-learn"}
# O numpy chega como dependência do torch e do gradio.
TRANSITIVE = {"numpy"}


def third_party_imports(paths: list[Path]) -> set[str]:
    local = {path.stem for path in (ROOT / "source").glob("*.py")} | {"source"}
    found: set[str] = set()
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found - set(sys.stdlib_module_names) - local


def pinned_names(requirements: str) -> set[str]:
    return {
        re.split(r"[=<>~!\[ ]", line.strip())[0].lower()
        for line in requirements.splitlines()
        if line.strip() and not line.startswith(("-", "#"))
    }


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[Path]]:
    output = tmp_path_factory.mktemp("space") / "bundle"
    return output, build_bundle(ROOT, output)


def test_bundle_has_the_app_the_checkpoints_and_the_examples(
    bundle: tuple[Path, list[Path]]
) -> None:
    output, files = bundle
    relative = {path.relative_to(output).as_posix() for path in files}
    assert {
        "app.py",
        "README.md",
        "requirements.txt",
        "source/gradio_demo.py",
        "source/finetune.py",
        "scripts/demo/normal-example.txt",
        "results/autoencoder-hybrid/model.pt",
        "results/autoencoder-lexical/model.pt",
        "results/autoencoder-semantic/model.pt",
    } <= relative


def test_bundle_leaves_out_data_figures_and_caches(
    bundle: tuple[Path, list[Path]]
) -> None:
    output, files = bundle
    relative = [path.relative_to(output).as_posix() for path in files]
    assert not [name for name in relative if name.startswith(("data/", "doc/", "docker/"))]
    assert not [name for name in relative if name.endswith((".png", ".gif", ".csv"))]
    assert not [name for name in relative if "__pycache__" in name]


def test_every_third_party_import_is_in_the_space_requirements(
    bundle: tuple[Path, list[Path]]
) -> None:
    output, _ = bundle
    sources = [output / "app.py", *(output / "source").glob("*.py")]
    needed = {PIP_NAMES.get(name, name) for name in third_party_imports(sources)}
    declared = pinned_names((output / "requirements.txt").read_text(encoding="utf-8"))
    assert needed - TRANSITIVE <= declared, (
        f"Importado mas ausente do requirements: {sorted(needed - TRANSITIVE - declared)}"
    )


def test_space_requirements_use_the_cpu_torch_and_keep_the_project_pins() -> None:
    text = space_requirements(ROOT / "requirements.txt")
    assert text.splitlines()[0] == CPU_INDEX
    project = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for line in project.splitlines():
        if line.strip() and not line.startswith("#"):
            assert line.strip() in text.splitlines()
    assert "pytest" not in text


def test_space_card_sdk_version_matches_the_gradio_pin(
    bundle: tuple[Path, list[Path]]
) -> None:
    output, _ = bundle
    card = (output / "README.md").read_text(encoding="utf-8")
    assert card.startswith("---\n")
    assert "app_file: app.py" in card and "sdk: gradio" in card
    pin = re.search(r"^gradio==(\S+)$", (ROOT / "requirements.txt").read_text(), re.M)
    assert pin is not None
    assert f"sdk_version: {pin.group(1)}" in card


def test_front_matter_must_open_and_close(tmp_path: Path) -> None:
    broken = tmp_path / "README.md"
    broken.write_text("# sem front matter\n", encoding="utf-8")
    with pytest.raises(ValueError, match="não começa"):
        read_front_matter(broken)
    broken.write_text("---\ntitle: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="não fecha"):
        read_front_matter(broken)


def test_bundle_refuses_to_wipe_a_foreign_directory(tmp_path: Path) -> None:
    foreign = tmp_path / "meus-arquivos"
    foreign.mkdir()
    (foreign / "importante.txt").write_text("não apague", encoding="utf-8")
    with pytest.raises(ValueError, match="não foi criada por este comando"):
        build_bundle(ROOT, foreign)
    assert (foreign / "importante.txt").is_file()
    assert not (foreign / MARKER).exists()
