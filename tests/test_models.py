"""Testes de shapes, parâmetros e modos dos autoencoders."""

import pytest
import torch

from source.features import FEATURE_COLUMNS, MAX_LENGTH, VOCABULARY
from source.models import (
    ARCHITECTURES,
    CharAutoencoder,
    DenseAE,
    HybridAutoencoder,
    build_model,
)


BATCH = 5
LATENT = 16


def make_inputs() -> tuple[torch.Tensor, torch.Tensor]:
    generator = torch.Generator().manual_seed(0)
    characters = torch.randint(0, len(VOCABULARY), (BATCH, MAX_LENGTH), generator=generator)
    numeric = torch.randn(BATCH, len(FEATURE_COLUMNS), generator=generator)
    return characters, numeric


def count_parameters(model: torch.nn.Module) -> int:
    return sum(parameter.numel() for parameter in model.parameters())


@pytest.mark.parametrize("mode", ["lexical", "semantic", "hybrid"])
def test_build_model_returns_registered_architecture(mode: str) -> None:
    model = build_model(mode, len(FEATURE_COLUMNS), len(VOCABULARY), MAX_LENGTH, LATENT)
    expected = {"lexical": CharAutoencoder, "semantic": DenseAE, "hybrid": HybridAutoencoder}
    assert isinstance(model, expected[mode])
    assert mode in ARCHITECTURES


def test_build_model_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="inválido"):
        build_model("outro")


def test_lexical_output_shapes() -> None:
    characters, numeric = make_inputs()
    logits, reconstructed = CharAutoencoder(len(VOCABULARY), MAX_LENGTH, LATENT)(
        characters, numeric, mode="lexical"
    )
    assert logits.shape == (BATCH, len(VOCABULARY), MAX_LENGTH)
    assert reconstructed.shape == (BATCH, 0)


def test_dense_output_shapes_ignore_characters() -> None:
    characters, numeric = make_inputs()
    model = DenseAE(len(FEATURE_COLUMNS), LATENT, len(VOCABULARY)).eval()
    logits, reconstructed = model(characters, numeric)
    assert logits.numel() == 0
    assert reconstructed.shape == (BATCH, len(FEATURE_COLUMNS))
    other_logits, other_reconstructed = model(characters.flip(0), numeric)
    assert torch.equal(reconstructed, other_reconstructed)
    assert model.encode(characters, numeric).shape == (BATCH, LATENT)


def test_hybrid_output_shapes_and_modes() -> None:
    characters, numeric = make_inputs()
    model = HybridAutoencoder(
        len(FEATURE_COLUMNS), len(VOCABULARY), MAX_LENGTH, LATENT
    ).eval()
    for mode in ("lexical", "semantic", "hybrid"):
        logits, reconstructed = model(characters, numeric, mode=mode)
        assert logits.shape == (BATCH, len(VOCABULARY), MAX_LENGTH)
        assert reconstructed.shape == (BATCH, len(FEATURE_COLUMNS))
        assert model.encode(characters, numeric, mode=mode).shape == (BATCH, LATENT)
    with pytest.raises(ValueError, match="inválido"):
        model.encode(characters, numeric, mode="outro")


def test_hybrid_latent_uses_both_branches() -> None:
    characters, numeric = make_inputs()
    model = HybridAutoencoder(
        len(FEATURE_COLUMNS), len(VOCABULARY), MAX_LENGTH, LATENT
    ).eval()
    base = model.encode(characters, numeric, mode="hybrid")
    assert not torch.equal(base, model.encode(characters, numeric * 2, mode="hybrid"))
    assert not torch.equal(base, model.encode(characters.flip(0), numeric, mode="hybrid"))
    assert torch.equal(
        model.encode(characters, numeric, mode="semantic"),
        model.encode(characters.flip(0), numeric, mode="semantic"),
    )


def test_parameter_counts() -> None:
    dense = count_parameters(DenseAE(len(FEATURE_COLUMNS), LATENT, len(VOCABULARY)))
    lexical = count_parameters(CharAutoencoder(len(VOCABULARY), MAX_LENGTH, LATENT))
    hybrid = count_parameters(
        HybridAutoencoder(len(FEATURE_COLUMNS), len(VOCABULARY), MAX_LENGTH, LATENT)
    )
    assert 0 < dense < lexical < hybrid
    # Entrada de 42 atributos: Linear(42, 32) + Linear(32, 16) + gargalo + decodificador.
    assert dense == (42 * 32 + 32) + (32 * 16 + 16) + (16 * 16 + 16) + (16 * 16 + 16) + (
        16 * 32 + 32
    ) + (32 * 42 + 42)


@pytest.mark.parametrize("max_length", [16, 32, 64])
def test_char_models_follow_max_length(max_length: int) -> None:
    """O decoder e o gargalo acompanham max_length em vez de assumir 64."""
    generator = torch.Generator().manual_seed(0)
    characters = torch.randint(
        0, len(VOCABULARY), (BATCH, max_length), generator=generator
    )
    numeric = torch.randn(BATCH, len(FEATURE_COLUMNS), generator=generator)

    lexical = CharAutoencoder(len(VOCABULARY), max_length, LATENT).eval()
    logits, _ = lexical(characters)
    assert logits.shape == (BATCH, len(VOCABULARY), max_length)

    hybrid = HybridAutoencoder(
        len(FEATURE_COLUMNS), len(VOCABULARY), max_length, LATENT
    ).eval()
    for mode in ("lexical", "semantic", "hybrid"):
        logits, reconstructed = hybrid(characters, numeric, mode=mode)
        assert logits.shape == (BATCH, len(VOCABULARY), max_length)
        assert reconstructed.shape == (BATCH, len(FEATURE_COLUMNS))
