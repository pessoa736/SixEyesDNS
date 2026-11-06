import sys

import numpy as np
import pandas as pd
import torch

print(f"Python: {sys.version.split()[0]}")
print(f"NumPy: {np.__version__}")
print(f"pandas: {pd.__version__}")
print(f"PyTorch: {torch.__version__}")
print(f"CUDA disponível: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"Dispositivo: {torch.cuda.get_device_name(0)}")
else:
    print("Dispositivo: CPU")