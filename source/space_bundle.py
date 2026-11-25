"""Monta a pasta enviada ao Hugging Face Space com só o que o app usa.

Um ``git push`` do repositório inteiro leva o histórico com PNG, GIF e dados
que o Space não precisa, e o Hub pode recusar binários sem Xet/LFS. A pasta
gerada aqui é pequena e se publica com ``hf upload``, que envia por API.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

MODES = ("hybrid", "lexical", "semantic")
MARKER = ".space-bundle"
# O Space roda em CPU: o índice extra troca a build CUDA do PyPI (alguns GB de
# bibliotecas NVIDIA) pela build CPU, sem mudar a versão fixada do torch.
CPU_INDEX = "--extra-index-url https://download.pytorch.org/whl/cpu"
SPACE_BODY = """
# SixEyesDNS

Detecção educacional de túneis DNS com autoencoders treinados somente em
consultas normais. O resultado é uma suspeita estatística para priorizar a
análise humana, não prova de ataque.

Código, dados, avaliação e documentação:
<https://github.com/pessoa736/SixEyesDNS>
"""


def read_front_matter(readme: Path) -> str:
    """Devolve o bloco YAML (com os ``---``) que abre o README do projeto."""
    lines = readme.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"{readme} não começa com o front matter do Space")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise ValueError(f"{readme} não fecha o front matter do Space") from None
    return "\n".join(lines[: end + 1]) + "\n"


def space_requirements(requirements: Path) -> str:
    """Reaproveita o requirements.txt do projeto, trocando o torch pelo de CPU."""
    pins = [
        line.strip()
        for line in requirements.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return "\n".join([CPU_INDEX, *pins]) + "\n"


def prepare_output(output: Path) -> None:
    """Limpa só uma pasta vazia ou criada antes por este módulo."""
    if output.exists():
        if any(output.iterdir()) and not (output / MARKER).is_file():
            raise ValueError(
                f"{output} existe e não foi criada por este comando; "
                "escolha outra pasta ou apague-a manualmente"
            )
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / MARKER).write_text("pasta gerada por source.space_bundle\n")


def build_bundle(root: Path, output: Path) -> list[Path]:
    """Copia app, código, checkpoints e exemplos; devolve os arquivos criados."""
    required = [
        root / "app.py",
        root / "README.md",
        root / "requirements.txt",
        root / "scripts/demo/normal-example.txt",
        root / "scripts/demo/replay-example.txt",
        *(root / f"results/autoencoder-{mode}/model.pt" for mode in MODES),
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Arquivos ausentes para o Space: {missing}")

    prepare_output(output)
    shutil.copy2(root / "app.py", output / "app.py")
    shutil.copytree(
        root / "source", output / "source", ignore=shutil.ignore_patterns("__pycache__")
    )
    for relative in required[3:]:
        destination = output / relative.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(relative, destination)
    (output / "README.md").write_text(
        read_front_matter(root / "README.md") + SPACE_BODY, encoding="utf-8"
    )
    (output / "requirements.txt").write_text(
        space_requirements(root / "requirements.txt"), encoding="utf-8"
    )
    return sorted(
        path for path in output.rglob("*") if path.is_file() and path.name != MARKER
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/space"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    files = build_bundle(root, args.output)
    size = sum(path.stat().st_size for path in files)
    print(f"{len(files)} arquivos, {size / 1024:.0f} KiB em {args.output}")
    print(
        "Publicar: hf auth login && "
        f"hf upload <usuario>/<space> {args.output} . --repo-type=space "
        f"--exclude {MARKER}"
    )


if __name__ == "__main__":
    main()
