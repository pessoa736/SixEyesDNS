# SixEyesDNS

## Criar o ambiente Python

Execute:

```bash
./create-envs.sh
```

O script detecta automaticamente uma GPU NVIDIA, uma GPU AMD com ROCm ou a
ausência de GPU e cria somente o ambiente correspondente (`.venv-nvidia`,
`.venv-amd` ou `.venv-cpu`). É possível escolher explicitamente o interpretador
com `PYTHON=/caminho/para/python ./create-envs.sh`; ele deve ser Python 3.12 ou
superior.

O ambiente também instala PyTorch (`torch`), NumPy e pandas.

Em Debian/Ubuntu, o script instala automaticamente o pacote `python3.12-venv`
quando o suporte a ambientes virtuais não está disponível. Isso pode solicitar
a senha do `sudo`.
