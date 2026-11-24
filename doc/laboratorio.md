# Laboratório e reprodução dos dados

## Coleta local

O laboratório Docker gera somente tráfego sintético na zona reservada `.test`,
com dnsmasq, BIND9, Unbound, Kea DHCP, gerador, aplicações fictícias e dashboard.
Não há upstream externo.

```bash
./scripts/lab/docker-run.sh
docker compose wait generator
```

Variáveis principais: `QUERY_COUNT=10000`, `ANOMALY_RATE=0.5`, `SEED=42`,
`QUERY_INTERVAL=0.01` e `DNS_TARGETS=resolver:70,dnsmasq:20,bind9:10`. O dashboard
fica em `http://127.0.0.1:8080`; a consulta DNS publicada no host usa a porta
`127.0.0.1:6767`.

## Processamento

`source/process_raw.py` casa cada rótulo com evidência no servidor-alvo por
cliente, domínio, tipo e janela de tempo, tolerando múltiplas execuções e logs
concatenados. Ele não alinha arquivos apenas pela posição das linhas.

```bash
./scripts/data/process-data.sh
```

Os logs locais ficam em `data/raw/`, ignorados pelo Git. O dataset versionado tem
9.911 registros e 42 atributos lexicais; os splits atuais têm 3.482 registros de
treino, 3.085 de validação e 3.344 de teste, sem interseção de domínios entre os
splits. O alinhamento corrigido gera 10.000 linhas, mas regenerar mudaria os
splits e invalidaria os checkpoints atuais; a regeneração foi decidida em
24/11/2026 e está nas
[pendências do roadmap](../roadmap.md#pendências-em-ordem-de-execução).

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
