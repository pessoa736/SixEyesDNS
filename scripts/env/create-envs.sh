#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${PYTHON:-}"

if [[ -z "$PYTHON" ]]; then
    for candidate in python3.12 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON="$candidate"
            break
        fi
    done
fi

if [[ -z "$PYTHON" ]]; then
    echo "Erro: Python 3.12 ou superior não foi encontrado." >&2
    exit 1
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
    echo "Erro: o Python encontrado precisa ser a versão 3.12 ou superior." >&2
    exit 1
fi

if ! "$PYTHON" -m ensurepip --version >/dev/null 2>&1; then
    PYTHON_VERSION="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    VENV_PACKAGE="python${PYTHON_VERSION}-venv"

    if command -v apt-get >/dev/null 2>&1; then
        if [[ "$EUID" -eq 0 ]]; then
            APT=(apt-get)
        elif command -v sudo >/dev/null 2>&1; then
            APT=(sudo apt-get)
        else
            APT=()
        fi

        if [[ "${#APT[@]}" -gt 0 ]]; then
            echo "Suporte a venv ausente. Instalando $VENV_PACKAGE..."
            "${APT[@]}" update
            "${APT[@]}" install -y "$VENV_PACKAGE"
        fi
    fi

    if ! "$PYTHON" -m ensurepip --version >/dev/null 2>&1; then
        echo "Erro: não foi possível habilitar o módulo ensurepip para $PYTHON." >&2
        if command -v apt-get >/dev/null 2>&1; then
            echo "Execute: sudo apt-get install $VENV_PACKAGE" >&2
        else
            echo "Instale o pacote de venv correspondente à versão do Python." >&2
        fi
        exit 1
    fi
fi

detect_gpu() {
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
        printf 'nvidia\n'
        return
    fi

    if command -v rocminfo >/dev/null 2>&1 && rocminfo 2>/dev/null | grep -q 'Agent'; then
        printf 'amd\n'
        return
    fi

    if [[ -d /sys/class/drm ]]; then
        for vendor_file in /sys/class/drm/card*/device/vendor; do
            [[ -f "$vendor_file" ]] || continue
            case "$(cat "$vendor_file")" in
                0x10de) printf 'nvidia\n'; return ;;
                0x1002) printf 'amd\n'; return ;;
            esac
        done
    fi

    printf 'cpu\n'
}

GPU="$(detect_gpu)"
PYTHON_VERSION="$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$GPU" in
    nvidia)
        ENV_DIR="$ROOT_DIR/.venv-nvidia"
        TENSORFLOW_PACKAGE="tensorflow"
        echo "GPU NVIDIA detectada. Criando $ENV_DIR..."
        ;;
    amd)
        if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
            echo "Erro: o ambiente AMD exige Linux x86_64 para instalar o TensorFlow ROCm." >&2
            exit 1
        fi
        if [[ "$PYTHON_VERSION" != "3.12" ]]; then
            echo "Erro: o ambiente AMD exige Python 3.12 (o wheel ROCm usado é cp312)." >&2
            exit 1
        fi
        ENV_DIR="$ROOT_DIR/.venv-amd"
        echo "GPU AMD detectada. Criando $ENV_DIR..."
        ;;
    cpu)
        ENV_DIR="$ROOT_DIR/.venv-cpu"
        TENSORFLOW_PACKAGE="tensorflow"
        echo "Nenhuma GPU compatível detectada. Criando $ENV_DIR para CPU..."
        ;;
esac

"$PYTHON" -m venv "$ENV_DIR"
VENV_PYTHON="$ENV_DIR/bin/python"

"$VENV_PYTHON" -m pip install --upgrade pip

install_torch() {
    case "$GPU" in
        amd)
            local rocm_version="${ROCM_VERSION:-}"
            if [[ -z "$rocm_version" && -r /opt/rocm/.info/version ]]; then
                rocm_version="$(cut -d. -f1,2 /opt/rocm/.info/version)"
            fi
            rocm_version="${rocm_version:-7.2}"
            echo "Instalando PyTorch ROCm $rocm_version (o torch do PyPI é CUDA e não usa GPU AMD)..."
            "$VENV_PYTHON" -m pip install torch \
                --index-url "https://download.pytorch.org/whl/rocm${rocm_version}"
            ;;
        nvidia)
            "$VENV_PYTHON" -m pip install torch
            ;;
        *)
            "$VENV_PYTHON" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
            ;;
    esac
}

if [[ "$GPU" == "amd" ]]; then
    "$VENV_PYTHON" -m pip install tf-keras --no-deps
    "$VENV_PYTHON" -m pip install \
        "https://repo.radeon.com/rocm/manylinux/rocm-rel-7.2.1/tensorflow_rocm-2.20.0.dev0%2Bselfbuilt-cp312-cp312-manylinux_2_28_x86_64.whl"
else
    "$VENV_PYTHON" -m pip install "$TENSORFLOW_PACKAGE"
fi

install_torch
"$VENV_PYTHON" -m pip install numpy pandas matplotlib jupyter notebook scikit-learn opencv-python

echo "Ambiente $ENV_DIR criado com sucesso."
echo "Ative-o com: source $ENV_DIR/bin/activate"
