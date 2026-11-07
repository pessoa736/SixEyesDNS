# SixEyesDNS

[**Abrir Roadmap do projeto**](roadmap.md)

Projeto educacional e defensivo para detectar consultas DNS anômalas com
autoencoders. O laboratório gera consultas sintéticas localmente, registra os
eventos com `dnsmasq` e transforma os logs em atributos numéricos.

## Arquitetura atual

- Docker e `dnsmasq`: captura local e isolada;
- gerador Python: cria domínios normais e famílias sintéticas base32, hex e
	base64;
- gerador Python: alterna consultas DNS dos tipos `A`, `AAAA` e `CNAME`;
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

O número padrão da coleta é definido no `docker-compose.yml`. A coleta agora
usa 50.000 consultas sintéticas, cinco vezes a quantidade anterior. Isso
precisa ser acompanhado de maior variedade de domínios normais; repetir as
mesmas strings não aumenta a diversidade do treinamento.

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
dígitos, quantidade de rótulos, maior rótulo e frequências de caracteres.
`query_type` é convertido nos indicadores `is_A`, `is_AAAA`, `is_CNAME`,
`is_TXT`, `is_NS`, `is_MX` e `is_PTR`. `family` também é expandida em
`is_family_normal`, `is_family_base32`, `is_family_hex` e `is_family_base64`
para análise do dataset. Os indicadores de `family` não entram no modelo, pois
essa coluna descreve a forma sintética da anomalia e causaria vazamento do
rótulo; os indicadores de tipo DNS são usados como entrada. A coluna `label` é
usada apenas para avaliação; o autoencoder deve ser treinado somente com
exemplos `normal`.

Treinar o autoencoder híbrido principal:

```bash
python source/train.py \
	--splits-dir data/processed/splits \
	--output-dir results/autoencoder
```

Ou, usando o script reprodutível:

```bash
./scripts/train-model.sh --epochs 200
```

Se `results/autoencoder/model.pt` já existir, o script o carrega
automaticamente e continua o treinamento. O valor de `--epochs` representa
épocas adicionais:

```bash
./scripts/train-model.sh --epochs 50
```

Para ignorar o modelo existente e começar do zero:

```bash
./scripts/train-model.sh --fresh --epochs 200
```

O treino combina a reconstrução textual e numérica, ajusta a padronização
somente nos normais de treino e salva o modelo, o histórico e as métricas em
`results/autoencoder/`.

Depois do treinamento, gerar os gráficos:

```bash
./scripts/plot-training.sh
```

Durante o treino, cada época mostra no terminal as perdas, accuracy e limiar
P99. O treinamento executa exatamente a quantidade definida em `--epochs`.
O arquivo `losses.png` contém dois subplots:
perdas e accuracy. São salvos `losses.png`, `metrics.png`,
`confusion-matrices.png`, `score-distributions.png` e `thresholds.png` no diretório
de resultados. Para abrir as janelas interativas, use
`./scripts/plot-training.sh --show`.

O plot também gera `test-samples.png`, com o domínio de entrada, a string
reconstruída, a classificação e o erro por atributo numérico. A quantidade de
amostras pode ser alterada com `--test-samples 10`.

O `score-distributions.png` mostra a visão completa em escala logarítmica e
um zoom linear dos scores baixos, com o limiar P99 marcado.

Os scripts oficiais são `process-data.sh`, `train-model.sh` e
`plot-training.sh`. O treinamento e a plotagem usam exclusivamente o modelo
autoencoder.

## Arquitetura principal

A arquitetura principal combina tokens de caracteres com as 49 features numéricas.
O ramo textual preserva as posições após as convoluções, e o decoder produz
logits diretamente para as 64 posições do domínio, sem `mean pooling` nem
interpolação. O modelo reconstrói o domínio e as features; o score é
a soma dos erros textual e numérico normalizados pelos normais de validação.
Dropout e `weight_decay` reduzem a memorização dos poucos domínios normais
disponíveis. O valor padrão de `weight_decay` é `1e-4` e pode ser alterado com
`--weight-decay`.

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

O dataset atual contém muitos exemplos repetidos e apenas 88 domínios normais
únicos no treino. Esse número deve ser aumentado antes de interpretar os
resultados como generalização para domínios reais.

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
