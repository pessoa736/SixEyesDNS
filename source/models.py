"""Modelo que reconstrói caracteres e atributos lexicais."""

from __future__ import annotations

import torch
from torch import nn


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
            nn.Linear(64 * (max_length // 2), latent_dim),
            nn.Tanh(),
            nn.Dropout(0.10),
        )
        self.char_decoder = nn.Sequential(
            nn.Linear(latent_dim, 64 * 32), nn.ReLU(), nn.Dropout(0.10),
            nn.Unflatten(1, (32, 64)),
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
        numeric_dim: int = 49,
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
            nn.Linear(64 * (max_length // 2) + 16, latent_dim),
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
            nn.Linear(latent_dim, 64 * 32),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Unflatten(1, (32, 64)),
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
                (characters.shape[0], 64 * (self.max_length // 2)),
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
