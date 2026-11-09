"""Autoencoders lexical, semântico (denso) e híbrido."""

from __future__ import annotations

import torch
from torch import nn


ARCHITECTURES = {
    "lexical": "char-autoencoder-v1",
    "semantic": "dense-autoencoder-v1",
    "hybrid": "positional-conv-v2",
}
LOSS_DESCRIPTIONS = {
    "lexical": "CE dos caracteres",
    "semantic": "MSE dos atributos",
    "hybrid": "CE + λ·MSE",
}


class DenseAE(nn.Module):
    """Autoencoder denso dos atributos numéricos; o score é o MSE por exemplo."""

    def __init__(
        self,
        numeric_dim: int = 42,
        latent_dim: int = 16,
        vocabulary_size: int = 41,
    ) -> None:
        super().__init__()
        self.vocabulary_size = vocabulary_size
        self.encoder = nn.Sequential(
            nn.Linear(numeric_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(16, latent_dim),
            nn.Tanh(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 16),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(16, 32),
            nn.ReLU(),
            nn.Linear(32, numeric_dim),
        )

    def encode(
        self,
        characters: torch.Tensor,
        numeric: torch.Tensor,
        mode: str = "semantic",
    ) -> torch.Tensor:
        """Projeta os atributos no espaço latente; os caracteres são ignorados."""
        return self.encoder(numeric)

    def forward(
        self,
        characters: torch.Tensor,
        numeric: torch.Tensor,
        mode: str = "semantic",
    ) -> tuple[torch.Tensor, torch.Tensor]:
        no_logits = torch.empty(
            (characters.shape[0], self.vocabulary_size, 0), device=characters.device
        )
        return no_logits, self.decoder(self.encode(characters, numeric))


class CharAutoencoder(nn.Module):
    """Autoencoder lexical independente para pré-treinar o ramo textual."""

    def __init__(
        self,
        vocabulary_size: int = 41,
        max_length: int = 64,
        latent_dim: int = 16,
        padding_index: int = 0,
    ) -> None:
        super().__init__()
        self.embedding = nn.Embedding(vocabulary_size, 16, padding_idx=padding_index)
        self.char_encoder = nn.Sequential(
            nn.Conv1d(16, 64, 3, padding=1), nn.ReLU(), nn.Dropout(0.10),
            nn.Conv1d(64, 64, 3, stride=2, padding=1), nn.ReLU(),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.Dropout(0.10),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(),
        )
        self.latent = nn.Sequential(
            nn.Linear(64 * ((max_length + 1) // 2), latent_dim),
            nn.Tanh(),
            nn.Dropout(0.10),
        )
        self.char_decoder = nn.Sequential(
            nn.Linear(latent_dim, 32 * max_length), nn.ReLU(), nn.Dropout(0.10),
            nn.Unflatten(1, (32, max_length)),
            nn.Conv1d(32, 64, 3, padding=1), nn.ReLU(),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(), nn.Dropout(0.10),
            nn.Conv1d(64, 64, 3, padding=1), nn.ReLU(),
            nn.Conv1d(64, vocabulary_size, 3, padding=1),
        )

    def encode(self, characters: torch.Tensor) -> torch.Tensor:
        """Projeta caracteres no espaço latente."""
        encoded = self.char_encoder(
            self.embedding(characters).transpose(1, 2)
        ).flatten(start_dim=1)
        return self.latent(encoded)

    def forward(
        self,
        characters: torch.Tensor,
        numeric: torch.Tensor | None = None,
        mode: str = "lexical",
    ) -> tuple[torch.Tensor, torch.Tensor]:
        logits = self.char_decoder(self.encode(characters))
        return logits, torch.empty((characters.shape[0], 0), device=characters.device)


class HybridAutoencoder(nn.Module):
    """Combina sequência de caracteres com os atributos lexicais numéricos."""

    def __init__(
        self,
        numeric_dim: int = 42,
        vocabulary_size: int = 41,
        max_length: int = 64,
        latent_dim: int = 16,
        padding_index: int = 0,
    ) -> None:
        super().__init__()
        self.max_length = max_length
        self.padding_index = padding_index
        self.embedding = nn.Embedding(vocabulary_size, 16, padding_idx=padding_index)
        self.char_encoder = nn.Sequential(
            nn.Conv1d(16, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Conv1d(64, 64, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(),
        )
        self.numeric_encoder = nn.Sequential(
            nn.Linear(numeric_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(16, 16),
            nn.ReLU(),
        )
        self.latent = nn.Sequential(
            nn.Linear(64 * ((max_length + 1) // 2) + 16, latent_dim),
            nn.Tanh(),
            nn.Dropout(0.10),
        )
        self.numeric_decoder = nn.Sequential(
            nn.Linear(latent_dim, 16),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(16, 16),
            nn.ReLU(),
            nn.Linear(16, 32),
            nn.ReLU(),
            nn.Linear(32, numeric_dim),
        )
        self.char_decoder = nn.Sequential(
            nn.Linear(latent_dim, 32 * max_length),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Unflatten(1, (32, max_length)),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Conv1d(64, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv1d(64, vocabulary_size, kernel_size=3, padding=1),
        )

    def encode(
        self,
        characters: torch.Tensor,
        numeric: torch.Tensor,
        mode: str = "hybrid",
    ) -> torch.Tensor:
        """Projeta a entrada no espaço latente conforme o modo."""
        if mode not in {"lexical", "semantic", "hybrid"}:
            raise ValueError(f"Modo de autoencoder inválido: {mode}")
        if mode == "semantic":
            char_position_encoding = torch.zeros(
                (characters.shape[0], 64 * ((self.max_length + 1) // 2)),
                device=characters.device,
            )
        else:
            embedded = self.embedding(characters).transpose(1, 2)
            encoded_characters = self.char_encoder(embedded)
            char_position_encoding = encoded_characters.flatten(start_dim=1)
        if mode == "lexical":
            numeric_encoding = torch.zeros(
                (numeric.shape[0], 16), device=numeric.device
            )
        else:
            numeric_encoding = self.numeric_encoder(numeric)
        return self.latent(
            torch.cat((char_position_encoding, numeric_encoding), dim=1)
        )

    def forward(
        self,
        characters: torch.Tensor,
        numeric: torch.Tensor,
        mode: str = "hybrid",
    ) -> tuple[torch.Tensor, torch.Tensor]:
        latent = self.encode(characters, numeric, mode)
        numeric_output = self.numeric_decoder(latent)
        char_logits = self.char_decoder(latent)
        return char_logits, numeric_output


def build_model(
    mode: str,
    numeric_dim: int = 42,
    vocabulary_size: int = 41,
    max_length: int = 64,
    latent_dim: int = 16,
) -> nn.Module:
    """Cria o autoencoder do modo pedido com a arquitetura registrada."""
    if mode == "lexical":
        return CharAutoencoder(vocabulary_size, max_length, latent_dim)
    if mode == "semantic":
        return DenseAE(numeric_dim, latent_dim, vocabulary_size)
    if mode == "hybrid":
        return HybridAutoencoder(numeric_dim, vocabulary_size, max_length, latent_dim)
    raise ValueError(f"Modo de autoencoder inválido: {mode}")
