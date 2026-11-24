"""Verifica a geração reproduzível dos diagramas Matplotlib."""

from pathlib import Path

from PIL import Image, ImageStat

from source.doc_figures import FIGURES, generate_all


def test_doc_figures_generate_five_nonempty_pngs(tmp_path: Path) -> None:
    paths = generate_all(tmp_path)
    assert {path.name for path in paths} == set(FIGURES) == {
        "pipeline.png",
        "architectures.png",
        "training.png",
        "roadmap.png",
        "demo.png",
    }
    for path in paths:
        assert path.stat().st_size > 10_000
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            assert image.width >= 1000 and image.height >= 600
            gray = image.convert("L")
            assert ImageStat.Stat(gray).var[0] > 100
