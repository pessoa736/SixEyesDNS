# SixEyesDNS

Projeto educacional e defensivo para detectar consultas DNS anômalas com
autoencoders. O laboratório gera consultas sintéticas localmente, registra os
eventos com `dnsmasq` e transforma os logs em atributos numéricos.

## Arquitetura atual

- Docker e `dnsmasq`: captura local e isolada;
- gerador Python: cria domínios normais e famílias sintéticas base32, hex e
	base64;
- `source/process_raw.py`: extrai atributos e remove a zona artificial `.test`;
- `source/split_dataset.py`: cria treino, validação e teste sem sobreposição de
	domínios;
- Conda: ambiente principal para execução no NPAD;
- scripts shell: execução e atualização reproduzíveis.

O IP presente no log do `dnsmasq` é somente informação operacional. Ele não é
incluído no dataset processado, pois o objetivo é analisar o domínio.

## Ambiente Conda

Criar e ativar o ambiente:

```bash
conda env create -f environment.yml
conda activate sixeyesdns
```

O `environment.yml` instala as dependências gerais e chama o
`requirements.txt` para os pacotes instalados via pip. A instalação do PyTorch
pode precisar ser ajustada conforme CUDA/ROCm e os módulos disponíveis no NPAD.

## Coleta local

O laboratório usa somente zonas sintéticas terminadas em `.test`, por exemplo:

```text
www.google.com.test
sigaa.ufrn.edu.br.test
abc123.tunnel.test
```

O sufixo `.test` evita consultas acidentais a domínios reais. Iniciar a coleta:

```bash
./scripts/docker-run.sh
docker compose wait generator
```

Para destruir e recriar os containers e a rede do projeto:

```bash
./scripts/docker-recreate.sh
```

O número padrão da coleta é definido no `docker-compose.yml`. A coleta atual
usa 300 consultas sintéticas.

## Processamento

Depois que o gerador terminar, atualizar o dataset e os splits:

```bash
./scripts/process-data.sh
```

O script executa:

```bash
python source/process_raw.py \
	--log data/raw/dnsmasq/dnsmasq.log \
	--labels data/raw/query_labels.csv \
	--output data/processed/dataset.csv

python source/split_dataset.py \
	--input data/processed/dataset.csv \
	--output-dir data/processed/splits \
	--seed 42
```

O dataset processado contém atributos como tamanho, entropia, proporção de
dígitos, quantidade de rótulos, maior rótulo e frequências de caracteres. A
coluna `label` é usada apenas para avaliação; o autoencoder deve ser treinado
somente com exemplos `normal`.

Arquivos principais:

```text
data/processed/dataset.csv
data/processed/splits/train.csv
data/processed/splits/validation.csv
data/processed/splits/test.csv
data/processed/splits/summary.json
```

O dataset processado sintético é versionado. Logs, rótulos brutos e arquivos
gerados em `data/raw/` permanecem ignorados pelo Git.

## Estrutura

```text
SixEyesDNS/
├── docker/
│   ├── dnsmasq/
│   └── generator/
├── data/
│   └── processed/
├── scripts/
├── source/
│   ├── process_raw.py
│   └── split_dataset.py
├── docker-compose.yml
├── environment.yml
├── requirements.txt
└── roadmap.md
```

Notebooks não fazem parte do fluxo principal. Jupyter pode ser usado
opcionalmente no NPAD apenas para inspeção de resultados.

## Segurança

- gerar tráfego somente no ambiente local;
- não encaminhar consultas para a Internet;
- não capturar clientes de terceiros;
- não usar IP, perfil de cliente ou metadados equivalentes como entrada do
	modelo;
- manter o tráfego anômalo sintético e documentado.
