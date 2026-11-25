"""Testes da camada Gradio para classificação e adaptação do modelo."""

from pathlib import Path

import matplotlib.pyplot as plt

from source.demo import query_from_domain
from source.gradio_demo import (
    adapt_model,
    analyze_domain,
    attribute_rows,
    build_interface,
    character_plot,
    classify_domain,
)


def test_manual_query_uses_the_same_normalization_as_logs() -> None:
    query = query_from_domain(" Staging.Api.Orbita.test. ", "a")
    assert query.entry.source == "manual"
    assert query.entry.query == "staging.api.orbita.test"
    assert query.entry.query_type == "A"
    assert query.features["query"] == "staging.api.orbita"
    assert "label" not in query.features and "client" not in query.features


def test_domain_analysis_and_explanations_match_the_checkpoint(
    trained_models: dict[str, Path]
) -> None:
    report = analyze_domain("Staging.Api.Orbita.test.", trained_models["hybrid"])
    result = report["results"][0]
    assert report["query_count"] == 1
    assert result["query"] == "staging.api.orbita.test"
    assert result["analyzed_query"] == "staging.api.orbita"
    assert result["suspicious"] == (result["score"] > report["threshold"])
    assert len(result["character_errors"]) == len(result["analyzed_query"])
    assert len(attribute_rows(result)) == 3
    figure = character_plot(result)
    try:
        assert len(figure.axes) >= 2
    finally:
        plt.close(figure)


def test_semantic_mode_explains_the_absence_of_character_map(
    trained_models: dict[str, Path]
) -> None:
    report = analyze_domain("staging.api.orbita.test", trained_models["semantic"])
    result = report["results"][0]
    assert result["character_errors"] == []
    assert len(attribute_rows(result)) == 3
    figure = character_plot(result)
    try:
        assert "não reconstrói caracteres" in figure.axes[0].texts[0].get_text()
    finally:
        plt.close(figure)


def test_domain_event_returns_a_visible_error_for_invalid_input(
    trained_models: dict[str, Path]
) -> None:
    verdict, figure, attributes, report = classify_domain("", trained_models["hybrid"])
    assert "Não foi possível analisar" in verdict
    assert figure is None and attributes == [] and report == {}


def write_normal_log(path: Path, count: int = 60) -> Path:
    path.write_text(
        "".join(
            f"Nov 20 10:00:{index:02d} dnsmasq[41]: query[A] "
            f"node-{index:03d}.atlas.test from 172.30.0.6\n"
            for index in range(count)
        ),
        encoding="utf-8",
    )
    return path


def test_adaptation_requires_confirmation_and_returns_a_download(
    trained_models: dict[str, Path], tmp_path: Path
) -> None:
    log = write_normal_log(tmp_path / "normal.txt")
    error, no_plot, no_file, no_report = adapt_model(
        log,
        False,
        1,
        100,
        0.0001,
        trained_models["hybrid"],
        output_root=tmp_path,
    )
    assert "somente consultas normais" in error
    assert no_plot is None and no_file is None and no_report == {}

    summary, figure, checkpoint, report = adapt_model(
        log,
        True,
        1,
        100,
        0.0001,
        trained_models["hybrid"],
        output_root=tmp_path,
    )
    try:
        assert "Checkpoint adaptado gerado" in summary
        assert report["train_domains"] == 48
        assert report["validation_domains"] == 12
        assert "Atenção" in summary
        assert report["test_metrics"] is None
        assert checkpoint is not None and Path(checkpoint).is_file()
        assert figure is not None and len(figure.axes) == 1
    finally:
        if figure is not None:
            plt.close(figure)


def test_interface_and_app_entrypoint_are_constructed_without_loading_models(
    trained_models: dict[str, Path]
) -> None:
    demo = build_interface(trained_models)
    labels = [getattr(block, "label", None) for block in demo.blocks.values()]
    assert "Detector base" in labels
    assert "Baixar model.pt adaptado" in labels
    assert "Log normal de exemplo (600 domínios únicos)" in labels
    import app

    assert app.demo is not None
