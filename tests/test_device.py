"""Testes da escolha de dispositivo: GPU NVIDIA, GPU AMD ou CPU."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from source import device as device_module
from source.device import (
    HSA_OVERRIDE,
    amd_gfx_targets,
    configure_amd_environment,
    describe_device,
    resolve_device,
)


def write_kfd(root: Path, *gpu_targets: int) -> Path:
    nodes = root / "nodes"
    for index, target in enumerate((0, *gpu_targets)):
        node = nodes / str(index)
        node.mkdir(parents=True)
        (node / "properties").write_text(
            f"cpu_cores_count 12\ngfx_target_version {target}\n", encoding="utf-8"
        )
    return nodes


@pytest.fixture
def no_amd_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device_module, "configure_amd_environment", lambda: None)


def test_amd_gfx_targets_ignores_cpu_nodes(tmp_path: Path) -> None:
    assert amd_gfx_targets(write_kfd(tmp_path, 100302)) == [100302]
    assert amd_gfx_targets(tmp_path / "ausente") == []


def test_rdna2_gets_override_on_rocm_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(torch.version, "hip", "7.2")
    environ: dict[str, str] = {}
    assert configure_amd_environment(environ, write_kfd(tmp_path, 100302)) == "10.3.0"
    assert environ[HSA_OVERRIDE] == "10.3.0"


def test_override_not_applied_on_cuda_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(torch.version, "hip", None)
    environ: dict[str, str] = {}
    assert configure_amd_environment(environ, write_kfd(tmp_path, 100302)) is None
    assert environ == {}


def test_override_respects_user_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(torch.version, "hip", "7.2")
    environ = {HSA_OVERRIDE: "11.0.0"}
    assert configure_amd_environment(environ, write_kfd(tmp_path, 100302)) is None
    assert environ[HSA_OVERRIDE] == "11.0.0"


@pytest.mark.parametrize("targets", [(100300,), (110000,), (100302, 110000), ()])
def test_override_skipped_for_native_or_other_architectures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, targets: tuple[int, ...]
) -> None:
    monkeypatch.setattr(torch.version, "hip", "7.2")
    environ: dict[str, str] = {}
    assert configure_amd_environment(environ, write_kfd(tmp_path, *targets)) is None
    assert environ == {}


def test_auto_falls_back_to_cpu_without_gpu(
    monkeypatch: pytest.MonkeyPatch, no_amd_setup: None
) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert resolve_device("auto") == torch.device("cpu")
    with pytest.raises(ValueError, match="nenhuma GPU"):
        resolve_device("cuda")
    with pytest.raises(ValueError, match="nenhuma GPU"):
        resolve_device("cuda:0")


def test_auto_picks_gpu_with_most_free_memory(
    monkeypatch: pytest.MonkeyPatch, no_amd_setup: None
) -> None:
    free_gb = (10, 20, 5)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "device_count", lambda: len(free_gb))
    monkeypatch.setattr(
        torch.cuda, "mem_get_info", lambda index: (free_gb[index] * 2**30, 24 * 2**30)
    )
    assert resolve_device("auto") == torch.device("cuda", 1)
    assert resolve_device("cuda") == torch.device("cuda", 1)
    assert resolve_device("cuda:2") == torch.device("cuda", 2)


def test_explicit_gpu_index_must_exist(
    monkeypatch: pytest.MonkeyPatch, no_amd_setup: None
) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 1)
    with pytest.raises(ValueError, match="1 GPU"):
        resolve_device("cuda:2")


def test_cpu_description_explains_why(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device_module, "gpu_diagnosis", lambda: None)
    assert describe_device(torch.device("cpu")) == "CPU (nenhuma GPU detectada)"
    monkeypatch.setattr(device_module, "gpu_diagnosis", lambda: "sem ROCm")
    assert describe_device(torch.device("cpu")) == "CPU (sem ROCm)"
    assert "--device cpu" in describe_device(torch.device("cpu"), requested="cpu")


@pytest.mark.parametrize(
    ("hip", "cuda", "expected"),
    [("7.2", None, "GPU AMD (ROCm/HIP 7.2)"), (None, "13.2", "GPU NVIDIA (CUDA 13.2)")],
)
def test_gpu_description_names_vendor_and_backend(
    monkeypatch: pytest.MonkeyPatch, hip: str | None, cuda: str | None, expected: str
) -> None:
    monkeypatch.setattr(torch.version, "hip", hip)
    monkeypatch.setattr(torch.version, "cuda", cuda)
    monkeypatch.setattr(
        torch.cuda,
        "get_device_properties",
        lambda device: SimpleNamespace(name="Placa X", total_memory=8 * 2**30),
    )
    description = describe_device(torch.device("cuda", 0))
    assert description.startswith(expected)
    assert "Placa X" in description
