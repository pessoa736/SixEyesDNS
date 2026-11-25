"""Escolha do dispositivo de treino: GPU NVIDIA (CUDA), GPU AMD (ROCm) ou CPU."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

import torch


KFD_NODES = Path("/sys/class/kfd/kfd/topology/nodes")
RDNA2_TARGETS = range(100300, 100400)
RDNA2_OVERRIDE = "10.3.0"
HSA_OVERRIDE = "HSA_OVERRIDE_GFX_VERSION"


def amd_gfx_targets(nodes: Path = KFD_NODES) -> list[int]:
    """Versões gfx das GPUs AMD vistas pelo driver KFD (ex.: 100302 para gfx1032)."""
    targets = []
    for properties in sorted(nodes.glob("*/properties")):
        try:
            lines = properties.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            key, _, value = line.partition(" ")
            if key == "gfx_target_version" and value.strip().isdigit() and int(value) > 0:
                targets.append(int(value))
    return targets


def configure_amd_environment(
    environ: MutableMapping[str, str] = os.environ, nodes: Path = KFD_NODES
) -> str | None:
    """Define ``HSA_OVERRIDE_GFX_VERSION`` para GPUs RDNA2 sem build oficial.

    A RX 6600 XT (gfx1032) trava o PyTorch ROCm sem o override para gfx1030.
    Precisa rodar antes da primeira chamada de GPU; respeita valor já definido.
    """
    if HSA_OVERRIDE in environ or getattr(torch.version, "hip", None) is None:
        return None
    targets = amd_gfx_targets(nodes)
    if targets and all(target in RDNA2_TARGETS for target in targets) and any(
        target != 100300 for target in targets
    ):
        environ[HSA_OVERRIDE] = RDNA2_OVERRIDE
        return RDNA2_OVERRIDE
    return None


def freest_gpu() -> int:
    """Índice da GPU visível com mais memória livre; empates ficam com a menor."""
    best_index, best_free = 0, -1
    for index in range(torch.cuda.device_count()):
        try:
            free, _ = torch.cuda.mem_get_info(index)
        except RuntimeError:
            continue
        if free > best_free:
            best_index, best_free = index, free
    return best_index


def resolve_device(name: str = "auto") -> torch.device:
    """Resolve 'auto', 'cpu', 'cuda' ou 'cuda:N'.

    ``auto`` usa a GPU (NVIDIA ou AMD) com mais memória livre e cai para a CPU
    se nenhuma estiver disponível; ``cuda`` exige GPU.
    """
    configure_amd_environment()
    if name in {"auto", "cuda"}:
        if torch.cuda.is_available():
            return torch.device("cuda", freest_gpu())
        if name == "auto":
            return torch.device("cpu")
        raise ValueError("Dispositivo 'cuda' indisponível: nenhuma GPU detectada")
    device = torch.device(name)
    if device.type == "cuda":
        if not torch.cuda.is_available():
            raise ValueError(f"Dispositivo '{name}' indisponível: nenhuma GPU detectada")
        if device.index is not None and device.index >= torch.cuda.device_count():
            raise ValueError(
                f"Dispositivo '{name}' indisponível: "
                f"{torch.cuda.device_count()} GPU(s) visível(eis)"
            )
    return device


def gpu_diagnosis() -> str | None:
    """Explica por que a GPU existente no sistema não está sendo usada."""
    if torch.cuda.is_available():
        return None
    if getattr(torch.version, "hip", None):
        return (
            "build ROCm sem GPU visível; confira /dev/kfd, os grupos render e video "
            f"e {HSA_OVERRIDE}"
        )
    if amd_gfx_targets():
        return (
            "GPU AMD detectada, mas este PyTorch não tem suporte a ROCm; instale a "
            "build ROCm (README, seção Treino em GPU)"
        )
    if Path("/dev/nvidiactl").exists():
        return "GPU NVIDIA detectada, mas este PyTorch não enxerga CUDA; confira driver e build"
    return None


def describe_device(device: torch.device, requested: str = "auto") -> str:
    """Texto curto com vendor, backend e nome do dispositivo escolhido."""
    if device.type != "cuda":
        if requested == "cpu":
            return "CPU (solicitada com --device cpu)"
        return f"CPU ({gpu_diagnosis() or 'nenhuma GPU detectada'})"
    properties = torch.cuda.get_device_properties(device)
    hip = getattr(torch.version, "hip", None)
    vendor, backend = ("AMD", f"ROCm/HIP {hip}") if hip else ("NVIDIA", f"CUDA {torch.version.cuda}")
    return (
        f"GPU {vendor} ({backend}) {device} - {properties.name}, "
        f"{properties.total_memory / 2**30:.0f} GB"
    )
