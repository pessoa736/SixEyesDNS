# Laboratório e reprodução dos dados

## Coleta local

O laboratório Docker gera somente tráfego sintético na zona reservada `.test`,
com dnsmasq, BIND9, Unbound, Kea DHCP, gerador, aplicações fictícias e dashboard.
Não há upstream externo.

```bash
./scripts/lab/docker-run.sh
docker compose wait generator
```

Variáveis principais: `QUERY_COUNT=20000`, `ANOMALY_RATE=0.15`, `SEED=42`,
`QUERY_INTERVAL=0.01` e `DNS_TARGETS=resolver:70,dnsmasq:20,bind9:10` (padrões
do `docker-compose.yml` desde o dataset-v2, 24/11/2026). O dashboard fica em
`http://127.0.0.1:8080`; a consulta DNS publicada no host usa a porta
`127.0.0.1:6767`.

## Perfis do gerador

`docker/generator/traffic_profiles.py` define o vocabulário e os perfis.

- **Anomalias**, em 7 famílias (`base32`, `hex`, `base64`, `mixed`,
  `low_entropy`, `dictionary` e `short`): o payload vai numa etiqueta ou dividido
  em duas, sob uma zona que ora imita a infraestrutura normal (`api.orbita`), ora
  é uma zona própria (`syncfeed`). Não há sufixo fixo. A `low_entropy` repete um
  padrão sorteado e a `dictionary` monta o payload com palavras do vocabulário
  normal.
- **Normais difíceis:** ids de CDN em base32, identificadores hexadecimais,
  ferramentas de infraestrutura pouco frequentes, hashes de CDN e os perfis
  temáticos.
- **Prevalência:** é parâmetro de execução (`ANOMALY_RATE`); o padrão do compose
  passou de 0,5 para 0,15 no dataset-v2.

O dataset versionado em `data/processed/` (dataset-v2, 24/11/2026) já usa esse
gerador: nenhuma suspeita contém `tunnel` e a `low_entropy` tem 699 domínios
únicos em 700 linhas. O dataset-v1 (sufixo fixo, `low_entropy` com 8 domínios)
fica no histórico do git; o controle de atalho medido nele está em
`results/archive/dataset-v1/suffix_control.csv` e não se aplica ao dataset
atual.

## Processamento

`source/process_raw.py` casa cada rótulo com evidência no servidor-alvo por
cliente, domínio, tipo e janela de tempo, tolerando múltiplas execuções e logs
concatenados. Ele não alinha arquivos apenas pela posição das linhas.

```bash
./scripts/data/process-data.sh
```

Os logs locais ficam em `data/raw/`, ignorados pelo Git (exceto `data/raw/archive/`,
que guarda os logs do dataset-v1). O dataset versionado (dataset-v2) tem 20.000
registros e 42 atributos lexicais; os splits atuais têm 11.901 registros de
treino, 4.026 de validação e 4.073 de teste, sem interseção de domínios entre os
splits. O relatório do alinhamento fica em `data/processed/alignment.json`
(20.000 rótulos, 20.000 linhas escritas, sem lacunas).

## Treino e avaliação

```bash
./scripts/model/train-lexical.sh
./scripts/model/train-semantic.sh
./scripts/model/train-hybrid.sh
./scripts/evaluate/evaluate.sh
```

`--device auto` é o padrão: GPU NVIDIA/AMD quando disponível e CPU como fallback.
Use `DEVICE=cpu` para execução determinística. Para reiniciar um modelo em vez de
retomá-lo, passe `--fresh` ao wrapper. Os checkpoints ficam em
`results/autoencoder-<modo>/model.pt` e os artefatos de avaliação em
`results/evaluation/`.

## Testes e figuras

```bash
python -m pytest -q
python -m source.doc_figures
```

As figuras da documentação são geradas com Matplotlib em `doc/figures/`, sem
Mermaid nem serviço de renderização externo.
