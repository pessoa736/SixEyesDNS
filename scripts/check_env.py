"""Verifica o ambiente Python, as dependências e o dispositivo de treino."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
import numpy as np
import sklearn
import torch

from source.device import (
    HSA_OVERRIDE,
    configure_amd_environment,
    describe_device,
    resolve_device,
)

override = configure_amd_environment()

print(f"Python: {sys.version.split()[0]}")
print(f"NumPy: {np.__version__}")
print(f"scikit-learn: {sklearn.__version__}")
print(f"matplotlib: {matplotlib.__version__}")
print(f"PyTorch: {torch.__version__}")
if torch.version.hip:
    print(f"ROCm/HIP: {torch.version.hip}")
if override:
    print(f"{HSA_OVERRIDE}={override} (aplicado automaticamente para a GPU AMD)")
print(f"GPU disponível para o PyTorch: {torch.cuda.is_available()}")

for index in range(torch.cuda.device_count()):
    print(f"  cuda:{index}: {torch.cuda.get_device_name(index)}")
print(f"Dispositivo selecionado (--device auto): {describe_device(resolve_device('auto'))}")
