# SixEyesDNS

Projeto educacional e defensivo da Unidade III de **Aprendizado Profundo
2026.2**, categoria 7 — *Autoencoders para Anomalias e Ruído*. O objetivo é
detectar consultas DNS suspeitas, representando somente o domínio e usando o
erro de reconstrução de um autoencoder treinado com consultas normais.

Os requisitos da disciplina estão em
[doc/info/Descricao_do_Trabalho.md](doc/info/Descricao_do_Trabalho.md). O
trabalho escrito será consolidado neste README.

## Introdução

Tunelamento DNS pode ocultar dados em nomes de domínio e dificultar a
separação entre consultas legítimas e suspeitas. Este projeto implementa um
laboratório local e isolado para estudar esse problema sem tráfego real:
consultas normais são inspiradas em serviços, plataformas e instituições
fictícias, enquanto as anomalias são strings codificadas geradas localmente.

O sistema deve aprender a distribuição lexical das consultas normais e usar
um limiar de erro para sinalizar `normal` ou `suspeita`. IP, cliente,
perfil de risco, tipo DNS e qualquer outro metadado de origem não fazem parte
do objetivo do modelo.

## Estado verificado do repositório

- O processamento está em `source/`, e o gerador está em
  `docker/generator/gerador_queries.py`.
- O dataset versionado possui 10.000 registros e 59 colunas.
- A parte lexical contém 42 atributos: 6 escalares e 36 frequências de
  caracteres `a-z` e `0-9`.
- O schema atual também contém indicadores de `query_type` e `family`, além
  dos metadados `query`, `query_type`, `family`, `label` e `seed`.
- Os domínios processados não mantêm o sufixo artificial `.test`.
- A nova geração amplia combinações determinísticas de serviços, regiões,
  ambientes e plataformas, incluindo casos difíceis com subdomínios
  semelhantes a identificadores de CDN.
- Os splits atuais não compartilham domínios entre si, mas repetem registros
  dentro dos próprios conjuntos. O `summary.json` ainda precisa ser ampliado
  para detalhar domínios únicos por classe e família.
- A coleta atual possui 10.000 consultas no log e 10.000 rótulos, com
  alinhamento sequencial completo. Coletas antigas tinham execuções
  concatenadas; por isso, o alinhamento deve continuar sendo verificado antes
  de novas regenerações.

Essas observações são diagnóstico, não resultados de desempenho. Não há ainda
uma tabela final de métricas válida para o relatório.

## Desenvolvimento e técnicas

### Laboratório e dados

O laboratório usa Docker com `dnsmasq` em uma rede interna. O compose define
`QUERY_COUNT=10000`, `ANOMALY_RATE=0.5` e `SEED=42`. O tráfego deve permanecer
local, usando a zona reservada `.test`; o dnsmasq não possui servidores
upstream configurados.

As famílias anômalas atuais são:

- base32;
- hexadecimal;
- base64 URL-safe.

O gerador normal usa combinações determinísticas de serviços fictícios
(`web`, `api`, `catalog`, `auth`, `metrics`, `mail`, `cdn` e `dashboard`),
regiões, ambientes e plataformas. Também produz casos difíceis com labels
curtos, índices de nós e identificadores hash-like. Esses casos mantêm
`family=normal` e são identificados pelo metadado `profile=normal_hard`.

As anomalias sintéticas incluem base32, hexadecimal, base64 URL-safe,
payloads de baixa entropia e codificações mistas. O arquivo de rótulos registra
sequência, timestamp UTC, serviço e perfil gerador para auditoria do
laboratório; esses campos são metadados e não entram no modelo.

O laboratório também sobe um Nginx em `127.0.0.1:8080`, serviços fictícios,
aplicações backend sintéticas e um dashboard local. As aplicações
`web-frontend`, `event-worker` e `monitor-agent` fazem requisições internas
para os serviços de catálogo, autenticação, eventos, busca e métricas. O
dashboard mostra consultas DNS e requisições backend por aplicação, serviço,
rota, status e latência. Os dados ficam em
`data/raw/dashboard/traffic_summary.json` e
`data/raw/dashboard/backend_traffic.json`.
Além das tabelas, a interface possui gráficos SVG de consultas por família DNS,
requisições por aplicação e requisições por serviço, atualizados a cada dois
segundos sem dependências externas.

Para aproximar padrões orgânicos sem acessar a Internet, os clients navegam
somente por sites sintéticos `.test`, com pesos de popularidade, sessões de
2–6 páginas, pausas variáveis, user agents fictícios, períodos de leitura e
variação entre aplicações. Os sites são `portal.atlas.test`,
`docs.brisa.test`, `status.cobalto.test`, `shop.lumen.test` e
`news.nuvem.test`. A telemetria também registra a distribuição por site.

### Processamento e atributos

O fluxo atual é:

```bash
./scripts/process-data.sh
```

Ele executa `source/process_raw.py` e `source/split_dataset.py` sobre os
arquivos em `data/raw/`. A implementação futura deve transformar
`source/features.py` na única fonte da verdade para:

- normalização do domínio, removendo `.test`;
- atributos lexicais;
- tokenização de caracteres;
- normalização numérica ajustada somente nos normais de treino.

As features do modelo devem ser uma lista explícita de 42 atributos. `label`,
`family`, `query_type`, `seed`, IP e cliente devem permanecer separados como
metadados e passar por uma verificação automática contra vazamento.

### Separação dos dados

O treino deve conter somente consultas `normal`. Validação e teste podem conter
normais e anomalias, mas não podem compartilhar domínios. O split deve falhar
se houver interseção e deve registrar em `summary.json` linhas e domínios
únicos por split, classe e família.

O casamento entre log e rótulos precisa considerar execuções concatenadas e
duplicatas. O arquivo de rótulos agora tem timestamp, mas o log do dnsmasq não
preserva o mesmo formato de timestamp com precisão suficiente. Não se deve
assumir que a ordem global do log corresponda a uma única execução.

### Modelos planejados

Serão comparados:

1. **DenseAE**: autoencoder denso sobre os 42 atributos, com score MSE;
2. **CharAE**: autoencoder de caracteres, com perda de entropia cruzada por
   posição;
3. **HybridAE**: combinação dos ramos numérico e de caracteres;
4. limiar simples de entropia;
5. Isolation Forest sobre os mesmos 42 atributos.

O treinamento deve usar seed 42, CPU como caminho suportado, early stopping e
somente exemplos normais. Os limiares serão calculados na validação, incluindo
percentil 99 dos normais e melhor F1 supervisionado, sem escolher limiar no
teste. O score híbrido usado no treinamento é:

```text
score = z(entropia_cruzada_dos_caracteres)
      + lambda * z(MSE_dos_atributos)
```

`lambda` pode ser alterado pela CLI, por exemplo `--lambda 0.7`. Os termos são
padronizados usando somente os normais da validação antes da combinação.

Também é possível treinar cada fonte de informação isoladamente:

```bash
# somente a sequência de caracteres (erro lexical/CE)
python -m source.train --mode lexical --fresh

# somente os 42 atributos numéricos (erro semântico/MSE)
python -m source.train --mode semantic --fresh

# os dois ramos, padrão
python -m source.train --mode hybrid --fresh
```

O modo semântico usa os atributos agregados do domínio (entropia, proporções,
tamanhos e frequências), enquanto o modo lexical usa a sequência de caracteres.
Em todos os modos, o treino continua usando apenas exemplos normais.

O decoder de caracteres produz uma matriz fixa de 64 posições porque os
domínios são preenchidos ou cortados para `MAX_LENGTH`. Ele não está tentando
acrescentar caracteres ao domínio real: está reconstruindo uma sequência
acolchoada. Para evitar que a saída pareça preenchida, o treino aplica uma
perda reduzida (`--pad-loss-weight`, padrão `0.2`) nas posições `PAD`; assim o
modelo aprende a encerrar a sequência sem deixar o preenchimento dominar a
reconstrução. O score lexical continua considerando somente posições reais.

### Avaliação

O pipeline deve gerar em `results/` métricas, CSVs e figuras para ROC-AUC,
PR-AUC, precisão, recall, F1, FPR, matriz de confusão, recall por família e
análise de prevalência. Também deve avaliar leave-one-family-out e explicar
erros por atributo ou caractere.

## Como reproduzir

### Ambiente

```bash
conda env create -f environment.yml
conda activate sixeyesdns
```

As versões das dependências devem permanecer fixadas em
[requirements.txt](requirements.txt) e [environment.yml](environment.yml).

### Coleta local

```bash
./scripts/docker-run.sh
docker compose wait generator
```

Durante a coleta, abra <http://127.0.0.1:8080> para acompanhar o tráfego
sintético. O dashboard não envia dados para a Internet e não substitui as
métricas do modelo.

Para observar as aplicações falsas:

```bash
docker compose logs -f backend-client fake-services
```

Para recriar os containers:

```bash
./scripts/docker-recreate.sh
```

A publicação `127.0.0.1:6767:53` está configurada no compose, mas deve ser
testada no ambiente antes de ser apresentada como funcional. Se a porta do
host não funcionar, a demonstração deve gerar o tráfego dentro da rede
interna ou usar o modo offline.

Em ambientes Docker Desktop ou VS Code nos quais a porta publicada pelo
daemon não aparece no host, use o servidor local do dashboard:

```bash
./scripts/dashboard.sh
```

Esse servidor escuta somente em `127.0.0.1:8080` e lê o resumo produzido pelo
gerador em `data/raw/dashboard/`; ele não substitui a rede interna do
laboratório.

### Processamento

```bash
./scripts/process-data.sh
```

O fluxo futuro deve ser executável também como módulos:

```bash
python -m source.process_raw --help
python -m source.split_dataset --help
python -m source.train --help
python -m source.evaluate --help
```

Para uma nova coleta limpa, remova somente os artefatos gerados do laboratório
e recrie os serviços:

```bash
rm -f data/raw/query_labels.csv data/raw/dashboard/traffic_summary.json
rm -f data/raw/dnsmasq/dnsmasq.log
./scripts/docker-recreate.sh
```

Não remova dados versionados sem revisar o diff. O gerador continua limitado à
rede Docker interna e ao domínio reservado `.test`.

## Estrutura

```text
SixEyesDNS/
├── data/
│   ├── raw/
│   └── processed/
├── docker/
│   ├── dnsmasq/
│   ├── generator/
│   ├── dashboard/
│   ├── nginx/
│   └── service-api/
├── scripts/
├── source/
├── results/
├── docker-compose.yml
├── environment.yml
├── requirements.txt
└── roadmap.md
```

## Segurança e ética

- gerar tráfego somente com scripts locais e sintéticos;
- manter a rede Docker interna e sem encaminhamento para a Internet;
- não implementar exfiltração real, persistência, evasão ou automação contra
  terceiros;
- não usar IP, cliente ou perfil de risco como feature;
- não versionar credenciais, dados pessoais ou datasets externos;
- documentar fontes externas realmente utilizadas;
- registrar vazamentos entre conjuntos, falsos positivos, resultados ruins e
  limitações.

## Referência da disciplina

O trabalho deve conter introdução, técnicas utilizadas, resultados, análise
crítica e conclusões. A apresentação presencial terá 10 minutos nas datas
08, 10 ou 15/12/2026, conforme a escolha registrada na planilha da turma. O
texto deve estar disponível no repositório até 15/12/2026.
