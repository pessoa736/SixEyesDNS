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

O laboratório usa Docker em uma rede interna (`172.30.0.0/24`) com quatro
serviços de infraestrutura de rede:

- `resolver` (Unbound, 172.30.0.4): resolvedor recursivo, porta de entrada
  dos clientes; encaminha a zona `test.` para os autoritativos e a reversa
  `30.172.in-addr.arpa` para o BIND9;
- `dnsmasq` (172.30.0.2): autoritativo curinga, responde `#` → 172.30.0.11;
- `bind9` (172.30.0.3): autoritativo BIND9 para a zona `test.` (curinga →
  172.30.0.11) e para a zona reversa, com PTRs dos serviços do laboratório;
- `dhcp` (ISC Kea, 172.30.0.5): DHCPv4 de cenário para a sub-rede, com pool
  172.30.0.100–199 e DNS 172.30.0.4; em rede Docker interna não há clientes
  de broadcast reais, mas o serviço sobe e registra leases.

O compose define `QUERY_COUNT=10000`, `ANOMALY_RATE=0.5` e `SEED=42`. O
tráfego deve permanecer local, usando a zona reservada `.test`; nenhum
servidor possui upstream externo. O gerador distribui as consultas pelos
servidores segundo `DNS_TARGETS` (padrão `resolver:70,dnsmasq:20,bind9:10`),
com tipos ponderados por classe: normais dominam em `A`/`AAAA` e incluem
consultas reversas `PTR`, enquanto anomalias concentram-se em `TXT`/`CNAME`,
como em túneis DNS. O intervalo entre consultas tem jitter determinístico
(0,5–1,5× `QUERY_INTERVAL`).

As famílias anômalas atuais são:

- base32;
- hexadecimal;
- base64 URL-safe;
- baixa entropia;
- codificações mistas.

O gerador normal usa combinações determinísticas de serviços fictícios
(`web`, `api`, `catalog`, `auth`, `metrics`, `mail`, `cdn` e `dashboard`),
regiões, ambientes e plataformas. Também produz casos difíceis com labels
curtos, índices de nós, identificadores hash-like e prefixos hexadecimais
curtos estilo CDN (`profile=normal_hard`), consultas reversas PTR
(`profile=normal_reverse`) e tráfego temático de entretenimento: memes
clássicos (`doge`, `nyancat`, `rickroll`, `thisisfine`...) em
`profile=normal_meme` e referências a Jujutsu Kaisen (`gojo`, `sukuna`,
`domain-expansion`, `hollow-purple`...) em `profile=normal_jjk`, sempre na
zona `.test`. Esses casos mantêm `family=normal` e servem para medir falsos
positivos em domínios fora do padrão corporativo.

O arquivo de rótulos registra sequência, timestamp UTC, serviço, perfil
gerador e servidor DNS de destino para auditoria do laboratório; esses campos
são metadados e não entram no modelo. Consultas respondidas pelo cache do
resolvedor não chegam aos autoritativos e, portanto, não aparecem nos logs —
comportamento realista de DNS.

O laboratório também sobe um Nginx em `127.0.0.1:8080`, serviços fictícios,
aplicações backend sintéticas e um dashboard local. As aplicações
`web-frontend`, `event-worker` e `monitor-agent` fazem requisições internas
para os serviços de catálogo, autenticação, eventos, busca e métricas. O
dashboard mostra consultas DNS e requisições backend por aplicação, serviço,
rota, status e latência. Os dados ficam em
`data/raw/dashboard/traffic_summary.json` e
`data/raw/dashboard/backend_traffic.json`.
Além das tabelas, a interface possui gráficos SVG de consultas por família
DNS, por tipo de consulta e por minuto (normais e suspeitas empilhadas),
requisições por aplicação e requisições por serviço, atualizados a cada dois
segundos sem dependências externas. Uma tabela de infraestrutura lista os
serviços do laboratório com endereços e papéis, e outra mostra consultas,
pesos e falhas por servidor DNS.

Para aproximar padrões orgânicos sem acessar a Internet, os clients navegam
somente por sites sintéticos `.test`, com pesos de popularidade, sessões de
2–6 páginas, pausas variáveis, user agents fictícios, períodos de leitura e
variação entre aplicações. Os sites são `portal.atlas.test`,
`docs.brisa.test`, `status.cobalto.test`, `shop.lumen.test` e
`news.nuvem.test`. A telemetria também registra a distribuição por site.

### Processamento e atributos

O fluxo atual é:

```bash
./scripts/data/process-data.sh
```

Ele executa `source/process_raw.py` e `source/split_dataset.py` sobre os
arquivos em `data/raw/`. O `process_raw.py` aceita múltiplos logs e entende
os formatos do dnsmasq (`query[TIPO] nome from IP`) e do BIND9
(`query: nome IN TIPO`); por padrão, o script usa
`data/raw/dnsmasq/dnsmasq.log` e `data/raw/bind9/queries.log` quando
presentes. `source/features.py` é a única fonte da verdade para:

- normalização do domínio, removendo `.test`;
- atributos lexicais;
- vocabulário e tokenização de caracteres;
- normalização numérica ajustada somente nos normais de treino.

As features do modelo são uma lista explícita de 42 atributos lexicais (6
escalares e 36 frequências de caracteres). `label`, `family`, `query_type`,
`seed`, IP e cliente permanecem separados como metadados: `features.py`
falha na importação se algum metadado entrar na lista e
`transform_features` rejeita linhas incompletas em vez de derivar valores de
metadados.

### Separação dos dados

O treino contém somente consultas `normal`. Validação e teste podem conter
normais e anomalias, mas não compartilham domínios. O split falha se houver
interseção e registra em `summary.json` linhas e domínios únicos por split,
classe e família. Com `--holdout-family <família>`, uma família de anomalia
inteira vai somente para o teste, medindo generalização para um tipo nunca
visto na validação.

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

O treinamento deve usar seed 42, CPU como caminho suportado, early stopping
com paciência fixa de 200 épocas e somente exemplos normais. Os limiares serão calculados na validação, incluindo
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

O modo `lexical` cria um submodelo textual independente
(`char-autoencoder-v1`). Esse checkpoint pode ser usado para inicializar o
embedding e o encoder de caracteres do modelo híbrido:

```bash
python -m source.train \
  --mode lexical \
  --fresh \
  --output-dir results/autoencoder-lexical

python -m source.train \
  --mode hybrid \
  --fresh \
  --lexical-checkpoint results/autoencoder-lexical/model.pt \
  --output-dir results/autoencoder-hybrid
```

Assim, o submodelo lexical aprende primeiro a reconstruir o texto e depois
seu encoder é reutilizado junto ao encoder numérico. O decoder lexical e o
latente híbrido continuam sendo ajustados no segundo treinamento.

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

Na visualização de teste, `--samples` deve ser par: metade das amostras é
selecionada da classe `normal` e metade da classe `suspeita`, permitindo uma
comparação equilibrada no Matplotlib.

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

As versões das dependências permanecem fixadas em
[requirements.txt](requirements.txt) e [environment.yml](environment.yml).
Para conferir o ambiente ativo, execute `python scripts/check_env.py`.

### Coleta local

```bash
./scripts/lab/docker-run.sh
docker compose wait generator
```

Durante a coleta, abra <http://127.0.0.1:8080> para acompanhar o tráfego
sintético. O dashboard não envia dados para a Internet e não substitui as
métricas do modelo.

Para observar as aplicações falsas:

```bash
docker compose logs -f backend-client fake-services
```

### Construção dos modelos

Os wrappers em [`scripts/model/`](scripts/model/) organizam os três casos de
uso:

```bash
./scripts/model/train-lexical.sh
./scripts/model/train-semantic.sh
./scripts/model/train-hybrid.sh
```

O treino híbrido usa automaticamente
`results/autoencoder-lexical/model.pt` quando esse arquivo existir.

Os wrappers retomam um checkpoint existente por padrão. Para iniciar do zero,
adicione `--fresh` ao comando desejado:

```bash
./scripts/model/train-lexical.sh --fresh
```

Ao terminar, os wrappers geram automaticamente os gráficos no diretório do
modelo. Para desativar essa etapa:

```bash
PLOT_AFTER_TRAINING=0 ./scripts/model/train-lexical.sh
```

Para executar os três treinamentos em sequência:

```bash
./scripts/model/train-all.sh
```

Os gráficos do treinamento ficam em [`scripts/evaluate/`](scripts/evaluate/):

```bash
RESULTS_DIR=results/autoencoder-lexical \
  ./scripts/evaluate/generate-plots.sh --test-samples 12
```

Cada treino grava em `results/autoencoder-<modo>/`: `losses.png`,
`metrics.png`, `confusion-matrices.png`, `score-distributions.png`,
`test-samples.png`, `latent-space.png` (projeção do teste nas duas primeiras
dimensões do espaço latente, colorida por classe e família) e
`training.gif` (animação das curvas de perda e accuracy; desative com
`--no-gif`).

### Testes

```bash
./scripts/test/run-tests.sh
RESULTS_DIR=results/autoencoder-lexical ./scripts/test/test-model.sh
RESULTS_DIR=results/autoencoder-lexical ./scripts/test/plot-model.sh
```

`run-tests.sh` executa o pytest sobre [`tests/`](tests/), que cobre o
determinismo das features e do split, a ausência de metadados na matriz de
entrada, a ausência de interseção de domínios entre os splits e o holdout de
família.

O teste visual seleciona igualmente exemplos normais e suspeitos; use um valor
par em `SAMPLES` ou `TEST_SAMPLES`.

Para recriar os containers:

```bash
./scripts/lab/docker-recreate.sh
```

A publicação `127.0.0.1:6767:53` foi confirmada neste ambiente com consultas
UDP e TCP respondendo `172.30.0.11` para `web.atlas.test`. No Docker
Desktop, containers presos somente a uma rede `internal: true` têm as portas
publicadas descartadas silenciosamente; por isso o dnsmasq também é ligado à
rede de borda `lab-edge`, que existe apenas para expor essa porta ao host.
Todo o tráfego do laboratório continua na rede interna.

Em ambientes Docker Desktop ou VS Code nos quais a porta publicada pelo
daemon não aparece no host, use o servidor local do dashboard:

```bash
./scripts/lab/dashboard.sh
```

Esse servidor escuta somente em `127.0.0.1:8080` e lê o resumo produzido pelo
gerador em `data/raw/dashboard/`; ele não substitui a rede interna do
laboratório.

### Processamento

```bash
./scripts/data/process-data.sh
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
rm -f data/raw/dnsmasq/dnsmasq.log data/raw/bind9/queries.log
rm -f data/raw/resolver/unbound.log data/raw/dhcp/kea-dhcp4.log
rm -f data/raw/dhcp/kea-leases4.csv
./scripts/lab/docker-recreate.sh
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
│   ├── bind9/
│   ├── resolver/
│   ├── dhcp/
│   ├── generator/
│   ├── dashboard/
│   ├── nginx/
│   └── service-api/
├── scripts/
│   ├── data/
│   ├── model/
│   ├── evaluate/
│   ├── demo/
│   ├── lab/
│   └── env/
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
