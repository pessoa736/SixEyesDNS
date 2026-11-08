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
- O dataset versionado (`data/processed/dataset.csv`) possui 9.911 registros
  (e não 10.000), 59 colunas e 6.924 domínios únicos. Ele foi gerado pelo
  método antigo de alinhamento entre logs e rótulos (veja "Alinhamento entre
  logs e rótulos") e ainda não foi regenerado.
- A parte lexical contém 42 atributos: 6 escalares e 36 frequências de
  caracteres `a-z` e `0-9`.
- O schema atual também contém indicadores de `query_type` e `family` (que
  não entram no modelo), além dos metadados `query_type`, `family`,
  `profile`, `label` e `seed`.
- Os domínios processados não mantêm o sufixo artificial `.test`.
- A nova geração amplia combinações determinísticas de serviços, regiões,
  ambientes e plataformas, incluindo casos difíceis com subdomínios
  semelhantes a identificadores de CDN.
- Os splits atuais não compartilham domínios entre si, mas repetem registros
  dentro dos próprios conjuntos: treino com 3.482 linhas e 2.049 domínios,
  validação com 3.085 e 2.437, teste com 3.344 e 2.438 (valores de
  `data/processed/splits/summary.json`, que também detalha domínios únicos por
  classe e família). `source/split_dataset.py` falha em tempo de execução se
  algum domínio aparecer em mais de um split.
- Os logs do laboratório acumulam várias execuções (o `dnsmasq.log` local tem
  25.253 linhas de consulta) e incluem consultas encaminhadas pelo resolvedor
  e de outros clientes, enquanto o arquivo de rótulos (10.000 linhas, uma única
  execução) é sobrescrito a cada coleta. Por isso o alinhamento não pode ser
  sequencial: o método atual casa cada rótulo com uma linha do log do
  servidor-alvo por cliente, consulta, tipo e janela de tempo. Verificação
  local em 08/11/2026 (`data/raw/` não é versionado): 10.000 rótulos casaram
  com 10.000 linhas de log (dnsmasq 2.047, bind9 1.007, resolver 6.946), sem
  rótulos sem log e sem linhas extras; o comando e os detalhes estão em
  "Alinhamento entre logs e rótulos".
- Reprocessar essa coleta com o método atual não reproduz o dataset
  versionado. Os 6.924 domínios únicos são os mesmos, mas o método antigo
  perdeu 89 consultas normais e 817 das suas 9.911 linhas têm um par
  (domínio, tipo) que não consta nos rótulos atuais. Como a ordem das linhas
  muda, o split com a mesma seed também muda (320 dos domínios do novo teste
  estavam no treino do split versionado). **Decisão pendente:** regenerar
  `data/processed/` invalida os checkpoints e a release `hybrid-v1` atuais.

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

O gerador lê três variáveis de ambiente, que o `docker-compose.yml` expõe com
estes padrões e que podem ser sobrescritas ao subir o laboratório (veja
"Coleta local"):

| Variável | Padrão | Função |
| --- | --- | --- |
| `QUERY_COUNT` | `10000` | consultas enviadas por execução |
| `ANOMALY_RATE` | `0.5` | fração de consultas suspeitas |
| `SEED` | `42` | semente do gerador e do tráfego dos backends (`TRAFFIC_SEED`) |

O `./scripts/data/process-data.sh` lê a mesma variável `SEED` (padrão `42`)
como semente do split por domínio.

O tráfego deve permanecer local, usando a zona reservada `.test`; nenhum
servidor possui upstream externo. O gerador distribui as consultas pelos
servidores segundo `DNS_TARGETS` (padrão `resolver:70,dnsmasq:20,bind9:10`),
com tipos ponderados por classe: normais dominam em `A`/`AAAA` e incluem
consultas reversas `PTR`, enquanto anomalias concentram-se em `TXT`/`CNAME`,
como em túneis DNS. O intervalo entre consultas (`QUERY_INTERVAL`, padrão
`0.01` s) tem jitter determinístico (0,5–1,5× o valor configurado).

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

Opcionalmente, um ranking local de domínios populares (Tranco) alimenta o
perfil `normal_tranco`: o arquivo `rank,domain` fica em
`data/external/tranco_top.csv`, é ignorado pelo Git e nunca é baixado nem
versionado pelo projeto (veja
[data/external/README.md](data/external/README.md)). O gerador usa até
`TRANCO_LIMIT` domínios (padrão `2000`) em uma fração `TRANCO_RATE` (padrão
`0.15`) das consultas normais que não são `PTR`, sempre como `<domínio>.test`:
o nome real é só texto dentro do laboratório e nenhuma consulta sai para a
Internet. A escolha é determinística por hash de `(SEED, índice)` e não
consome o gerador pseudoaleatório principal; sem o arquivo, o perfil fica
desligado e o tráfego gerado não muda. Se o arquivo for usado, a fonte e a
versão da lista devem ser citadas.

O arquivo de rótulos registra sequência, timestamp UTC, serviço, perfil
gerador e servidor DNS de destino para auditoria do laboratório; esses campos
são metadados e não entram no modelo. Consultas respondidas pelo cache do
resolvedor não chegam aos autoritativos, mas o Unbound registra todas as
consultas dos clientes (`log-queries`); por isso cada rótulo é confirmado no
log do seu servidor-alvo (coluna `server`). O arquivo de rótulos é
sobrescrito a cada execução, enquanto os logs DNS acumulam execuções.

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

#### Alinhamento entre logs e rótulos

O arquivo de rótulos (`data/raw/query_labels.csv`) é sobrescrito a cada
execução do gerador, mas os logs do dnsmasq, do BIND9 e do Unbound acumulam
execuções. Os autoritativos também registram as consultas que o resolvedor
encaminha (cliente `172.30.0.4`) e as de outros clientes, como o DHCP Kea
(`172.30.0.5`). Casar logs e rótulos por posição, ou só por `(consulta, tipo)`,
mistura execuções e clientes: o `dnsmasq.log` local, por exemplo, guarda 10.000
consultas de outro cliente (`172.30.0.3`) feitas entre 00:49 e 00:51 de
08/11, anteriores à execução atual. Por isso `source/process_raw.py` trata os
logs somente como **evidência** e grava **uma linha por rótulo confirmado**,
em ordem de `sequence`:

1. cada rótulo é procurado no log do seu servidor-alvo (coluna `server`:
   `dnsmasq` → `dnsmasq.log`, `bind9` → `queries.log`, `resolver` →
   `unbound.log`). O formato de cada linha é detectado por expressão regular;
   no Unbound valem só as linhas de consulta, não as de resposta;
2. a linha precisa vir do cliente `--client-ip` (padrão `172.30.0.6`, o
   gerador), ter a mesma consulta normalizada (minúsculas, sem ponto final) e o
   mesmo tipo, e ter timestamp em `[rótulo − --tolerance-seconds, rótulo + 1 s]`
   (padrão de 5 s): o rótulo é gravado depois da resposta, e o dnsmasq e o
   Unbound truncam o log ao segundo;
3. o casamento é guloso em ordem temporal por chave (servidor, consulta, tipo)
   e cada linha de log confirma no máximo um rótulo;
4. o dnsmasq não registra o ano: usa-se o ano dos rótulos, inclusive na virada
   de ano;
5. linhas de outros clientes (inclusive o resolvedor nos autoritativos),
   linhas do gerador fora da janela da execução (outras execuções acumuladas no
   log) e linhas extras dentro da janela (retransmissões ou consultas sem
   rótulo) são ignoradas e apenas contadas. Como só rótulos geram linhas no
   dataset, duplicatas no log nunca criam registros.

O processamento falha com mensagem em português e código de saída diferente de
zero, sem gravar o dataset, quando:

- o arquivo de rótulos parece concatenado: `sequence` repetida ou timestamps
  decrescentes na ordem de `sequence`. Lacunas em `sequence` não indicam
  concatenação e são toleradas (veja abaixo);
- a mesma `(consulta, tipo)` tem rótulos conflitantes (`label`, `family` ou
  `profile` diferentes), o que tornaria o casamento ambíguo;
- há rótulos sem linha de log acima de `--max-missing-ratio` (padrão `0`:
  qualquer rótulo sem evidência falha). Com um valor maior, esses rótulos são
  descartados do dataset e contados no relatório. Se o BIND9 rotacionar o log
  durante a coleta, inclua também os arquivos rotacionados em `--log`;
- faltam colunas obrigatórias nos rótulos (`sequence`, `timestamp`, `query`,
  `query_type`, `family`, `profile`, `label`, `seed` e `server`), o servidor é
  desconhecido ou duas execuções se sobrepõem no tempo.

O gerador não grava rótulo para uma consulta que falhou (por exemplo, por
timeout), mas o número de `sequence` dela é consumido. Portanto, lacunas em
`sequence` são consultas que falharam no gerador, e uma única falha não derruba
a coleta: as lacunas são toleradas e reportadas. `sequence_gaps` conta os
números ausentes entre 0 e o último `sequence` e aparece, junto de
`first_sequence` e `last_sequence`, por execução no `alignment.json` e no
resumo impresso. A linha de log de uma consulta que falhou, se o servidor a
registrou, entra como extra na janela e não gera registro. A opção
`--strict-sequence` (desligada por padrão) restaura a exigência de `sequence`
contígua em `0..N-1`: com ela, qualquer lacuna falha.

Cada arquivo de `--labels` é tratado como **uma** execução e validado
individualmente; vários arquivos (e vários `--log`) são aceitos, cada
execução com a sua janela de tempo. O schema de saída não muda: `server`,
`sequence` e `timestamp` servem só ao alinhamento e não entram no dataset.

O relatório `alignment.json` fica por padrão ao lado do `--output`
(`--report` altera o caminho) e o `process-data.sh` o grava em
`data/processed/alignment.json`. Ele registra os totais de rótulos, linhas
escritas, rótulos sem log e lacunas de `sequence`, os casados por servidor, as
opções usadas (`client_ip`, `tolerance_seconds`, `max_missing_ratio` e
`strict_sequence`) e, por execução, a janela (início e fim) e `first_sequence`,
`last_sequence` e `sequence_gaps`. Registra também as contagens de linhas de
log: lidas por fonte, de outros clientes (também por IP), fora da janela e
extras dentro da janela.

Verificação local em 08/11/2026 sobre os dados de `data/raw/` (não
versionados), com a saída fora de `data/processed/` para não sobrescrever o
dataset versionado:

```bash
python -m source.process_raw \
  --log data/raw/dnsmasq/dnsmasq.log data/raw/bind9/queries.log \
        data/raw/resolver/unbound.log \
  --labels data/raw/query_labels.csv \
  --output <diretório temporário>/dataset.csv
```

Resultado: 10.000 rótulos e 10.000 linhas escritas (dnsmasq 2.047, bind9
1.007, resolver 6.946), com 0 rótulos sem log, 0 linhas extras na janela e
`sequence` de 0 a 9999 sem lacunas (`sequence_gaps` = 0). Foram ignoradas
33.248 linhas de outros clientes e 9.186 linhas do gerador fora da janela
(execuções anteriores acumuladas nos logs). O `dnsmasq.log` tem 25.253 linhas
de consulta, das quais só 2.047 pertencem a esta execução.
`TODO(resultados)`: regenerar e versionar `data/processed/alignment.json` junto
com o dataset, se a regeneração for aprovada.

### Processamento e atributos

O fluxo atual é:

```bash
./scripts/data/process-data.sh
```

Ele executa `python -m source.process_raw` e `python -m source.split_dataset`
sobre os arquivos em `data/raw/`. O `process_raw` aceita múltiplos logs e
detecta por linha os formatos do dnsmasq (`query[TIPO] nome from IP`), do BIND9
(`query: nome IN TIPO`) e do Unbound (linha de consulta `IP nome. TIPO IN`, sem
as linhas de resposta); por padrão, o script usa `data/raw/dnsmasq/dnsmasq.log`,
`data/raw/bind9/queries.log` e `data/raw/resolver/unbound.log` quando presentes.
O resultado é uma linha por rótulo confirmado no log do servidor-alvo (veja
"Alinhamento entre logs e rótulos"), gravada em `data/processed/dataset.csv`
junto do relatório `data/processed/alignment.json`. O processamento falha com
mensagem explícita se os rótulos estiverem concatenados, se o casamento for
ambíguo ou se faltar log para algum rótulo, e o `split_dataset` falha se algum
domínio aparecer em mais de um conjunto. As opções do alinhamento (`--client-ip`,
`--tolerance-seconds`, `--max-missing-ratio`, `--strict-sequence` e `--report`)
têm padrões que o `process-data.sh` não altera; para mudá-las, chame o módulo
diretamente (`python -m source.process_raw --help`). A sequência equivalente,
a partir da raiz do repositório, é:

```bash
python -m source.process_raw \
  --log data/raw/dnsmasq/dnsmasq.log data/raw/bind9/queries.log \
        data/raw/resolver/unbound.log \
  --labels data/raw/query_labels.csv \
  --output data/processed/dataset.csv \
  --report data/processed/alignment.json
python -m source.split_dataset \
  --input data/processed/dataset.csv \
  --output-dir data/processed/splits \
  --seed 42
```

Esses comandos, como o próprio script, sobrescrevem `data/processed/`;
regenerar o dataset versionado é uma decisão pendente (veja "Estado verificado
do repositório"). `source/features.py` é a única fonte da verdade para:

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

O casamento entre log e rótulos considera execuções concatenadas e duplicatas:
o `process_raw` confirma cada rótulo no log do servidor-alvo pelo IP do
gerador, pela consulta, pelo tipo e pelo timestamp, sem assumir que a ordem
global do log corresponda a uma única execução (veja "Alinhamento entre logs e
rótulos"). Do lado do split, `python -m source.split_dataset` verifica
explicitamente, em tempo de execução, que nenhum domínio aparece em mais de um
conjunto: se aparecer, falha com um `ValueError` que lista até cinco exemplos e
não grava os splits. A mesma `--seed` sobre o mesmo `dataset.csv` produz sempre
os mesmos splits.

### Modelos

São comparados cinco detectores, todos treinados ou ajustados somente com
exemplos normais do treino:

1. **DenseAE** (`--mode semantic`, `dense-autoencoder-v1`): autoencoder denso
   sobre os 42 atributos, com score MSE;
2. **CharAE** (`--mode lexical`, `char-autoencoder-v1`): autoencoder de
   caracteres, com perda de entropia cruzada por posição;
3. **HybridAE** (`--mode hybrid`, `positional-conv-v2`): combinação dos ramos
   numérico e de caracteres; é o modelo principal;
4. limiar simples de entropia de Shannon do domínio normalizado;
5. Isolation Forest sobre os mesmos 42 atributos padronizados (200 árvores,
   seed 42).

O treinamento usa seed 42, early stopping com paciência fixa de 200 épocas e
somente exemplos normais. A CPU é o caminho de referência para
reprodutibilidade; a GPU é opcional (veja *Treino em GPU*). Os limiares são
calculados na validação, incluindo percentil 99 dos normais e melhor F1
supervisionado, sem escolher limiar no teste. O score híbrido usado no
treinamento é:

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

```bash
./scripts/evaluate/evaluate.sh        # equivale a: python -m source.evaluate
```

[`source/evaluate.py`](source/evaluate.py) compara o DenseAE, o CharAE e o
HybridAE com o limiar de entropia e o Isolation Forest e grava tudo em
[`results/evaluation/`](results/evaluation/). Protocolo:

- **Limiares só na validação:** P99 dos scores normais da validação ou melhor
  F1 da validação (o candidato "tudo suspeito" entra na busca). O teste nunca
  escolhe limiar; ROC-AUC, PR-AUC e recall a FPR ≤ 1% não dependem de limiar.
- **Por registro e por domínio único:** os splits repetem o mesmo domínio com
  tipos DNS diferentes; por isso toda métrica sai também com um ponto por
  domínio (score médio do domínio).
- **Proteções antes de avaliar:** o script falha se o treino tiver suspeitas,
  se um domínio aparecer em mais de um split ou se o limiar P99 e os scores
  recalculados divergirem dos salvos no checkpoint (sinal de que os splits
  mudaram depois do treino).
- **Recall por família, FPR por perfil normal e falsos positivos por
  domínio** (`recall_by_family.csv`, `fpr_by_profile.csv`,
  `false_positives.csv`).
- **Prevalência:** a precisão esperada é recalculada a partir de recall e FPR
  do teste para prevalências menores (`prevalence.csv`), pois o teste tem
  prevalência de suspeitas muito acima da de tráfego real.
- **Leave-one-family-out (`lofo.csv`):** os modelos nunca veem suspeitas no
  treino, então só a calibração pode depender de uma família. Para cada
  família, o limiar de melhor F1 é recalibrado na validação sem ela e a
  família é avaliada no teste.
- **Ablação (`ablation.md`):** sistemas, valores de λ do score híbrido
  (somente no score, sem retreinar) e o score só com o MSE dos atributos.
- **Explicabilidade:** erro por atributo e por caractere/posição
  (`explain_*.csv`, `explain-*.png`) e exemplos concretos em
  `explain_examples.md`.
- **Indicador de vazamento por molde:** maior similaridade de trigramas de
  cada domínio com os normais do treino (`leakage.csv`).
- **Figuras:** `roc-pr.png`, `confusion-matrices.png`, `prevalence.png`,
  `recall-by-family.png`, `fpr-by-profile.png`, `lofo.png`,
  `explain-attributes.png` e `explain-characters.png`.

Resultados no teste, por registro, gerados em
[`results/evaluation/summary.md`](results/evaluation/summary.md) (3.344
registros e 2.438 domínios únicos; 77,6% de suspeitas). As tabelas por domínio
único ficam no mesmo arquivo.

Limiar P99 dos normais da validação:

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC | PR-AUC | Recall a FPR ≤ 1% |
|---|---|---|---|---|---|---|---|
| Limiar de entropia | 0.9838 | 0.1873 | 0.3147 | 0.0107 | 0.6712 | 0.8977 | 0.1464 |
| Isolation Forest | 0.9840 | 0.4513 | 0.6188 | 0.0254 | 0.9396 | 0.9784 | 0.3730 |
| DenseAE (atributos) | 0.9986 | 0.5592 | 0.7169 | 0.0027 | 0.9901 | 0.9966 | 0.7368 |
| CharAE (caracteres) | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 |
| HybridAE | 0.9973 | 1.0000 | 0.9987 | 0.0093 | 1.0000 | 1.0000 | 1.0000 |

Limiar de melhor F1 da validação:

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC | PR-AUC | Recall a FPR ≤ 1% |
|---|---|---|---|---|---|---|---|
| Limiar de entropia | 0.7600 | 0.8605 | 0.8072 | 0.9413 | 0.6712 | 0.8977 | 0.1464 |
| Isolation Forest | 0.9357 | 0.9869 | 0.9606 | 0.2350 | 0.9396 | 0.9784 | 0.3730 |
| DenseAE (atributos) | 0.9774 | 0.9842 | 0.9808 | 0.0788 | 0.9901 | 0.9966 | 0.7368 |
| CharAE (caracteres) | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 |
| HybridAE | 0.9996 | 1.0000 | 0.9998 | 0.0013 | 1.0000 | 1.0000 | 1.0000 |

Como 77,6% do teste é suspeito, marcar tudo como suspeito já rende F1 de
0,8739; compare também FPR, ROC-AUC e PR-AUC. O DenseAE tem ROC-AUC alto, mas
só 0,5592 de recall no limiar P99: com apenas os 42 atributos, parte das
anomalias fica dentro da cauda dos normais.

#### Limitações e riscos

- **Conjunto sintético fácil.** CharAE e HybridAE separam o teste quase por
  completo (ROC-AUC 1,0000). Isso mostra que as anomalias geradas (base32,
  hex, base64, baixa entropia e mista) são muito diferentes dos moldes normais
  do gerador, não que o detector funcionaria em tráfego real.
- **Vazamento por molde.** Os splits não repetem domínios, mas domínios
  diferentes saem dos mesmos moldes. A mediana da maior similaridade de
  trigramas de um normal do teste com algum normal do treino é 0,6364 (3,64%
  chegam a 0,8 ou mais); para as suspeitas é 0,0556 (`leakage.csv`).
- **Poucos domínios em `low_entropy`.** A família tem 5 domínios únicos no teste
  e 602 dos 2.595 registros suspeitos; por isso as métricas por domínio único
  importam.
- **Falsos positivos.** No limiar P99 o HybridAE sinaliza 7 domínios normais,
  todos do perfil `normal_hard` e parecidos com hashes hexadecimais de CDN
  (por exemplo `f4bfff32c5.cdn.brisa`): 7 de 230 registros (3,0%) desse
  perfil. Com o limiar de melhor F1 sobra 1 domínio.
- **Prevalência.** Com recall 1,0000 e FPR 0,0093 (P99), a precisão esperada do
  HybridAE cai para 0,5194 com 1% de suspeitas e para 0,0967 com 0,1%
  (`prevalence.csv`): em tráfego real, com suspeitas raras, a maior parte dos
  alertas seria falsa.
- **Leave-one-family-out.** CharAE e HybridAE mantêm recall mínimo de 1,0000 e
  0,9920 nas famílias omitidas da calibração. Já o limiar de entropia perde
  `low_entropy` por completo (recall 0,0000 contra 0,4000 com todas as
  famílias) e o Isolation Forest cai de 1,0000 para 0,8020.
- **Sem intervalos de confiança, uma única seed e um único split.** Os
  treinos em GPU não são idênticos bit a bit aos da CPU.
- **Dataset versionado.** Foi gerado com o casamento antigo entre logs e
  rótulos (9.911 linhas); o alinhamento corrigido produz 10.000 linhas, mas
  mudaria os splits e invalidaria os checkpoints atuais. A regeneração depende
  de decisão do autor (veja o `roadmap.md`).

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

O gerador lê `QUERY_COUNT` (padrão `10000`), `ANOMALY_RATE` (padrão `0.5`) e
`SEED` (padrão `42`) do ambiente; o `SEED` também alimenta o tráfego dos
backends (`TRAFFIC_SEED`). O `docker-run.sh` imprime os valores efetivos antes
de subir o laboratório:

```bash
QUERY_COUNT=2000 ANOMALY_RATE=0.4 SEED=7 ./scripts/lab/docker-run.sh
docker compose wait generator
```

O `./scripts/data/process-data.sh` lê a mesma variável `SEED` (padrão `42`)
para o split por domínio; defina-a também nele
(`SEED=7 ./scripts/data/process-data.sh`) para manter a mesma semente da
coleta à separação dos dados. `QUERY_INTERVAL` (padrão `0.01` s) e
`TRANCO_PATH`, `TRANCO_LIMIT` e `TRANCO_RATE` (veja
[data/external/README.md](data/external/README.md)) seguem o mesmo mecanismo.

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

### Treino em GPU (local e NPAD)

O treino usa `--device auto` por padrão e informa a escolha na primeira linha:

```text
Dispositivo selecionado: GPU AMD (ROCm/HIP 7.2.53211) cuda:0 - AMD Radeon RX 6600, 8 GB
Dispositivo selecionado: GPU NVIDIA (CUDA 13.2) cuda:1 - NVIDIA A100-SXM4-40GB, 40 GB
Dispositivo selecionado: CPU (nenhuma GPU detectada)
```

- **GPU NVIDIA (CUDA)**, como no NPAD, ou **GPU AMD (ROCm)**, como no PC local:
  o modelo treina na GPU. Havendo mais de uma GPU visível, `auto` escolhe a que
  tem mais memória livre no momento.
- **Sem GPU no ambiente Linux:** cai para a CPU, que continua sendo o caminho
  de referência para reprodutibilidade (seed 42; treinos em GPU podem diferir
  numericamente da CPU).
- Se existir uma GPU no sistema que o PyTorch instalado não consegue usar, a
  linha da CPU explica o motivo (por exemplo, build CUDA em máquina AMD).

A escolha pode ser forçada pela CLI (`--device cpu`, `--device cuda`,
`--device cuda:1`) ou pela variável `DEVICE` dos wrappers:

```bash
DEVICE=cpu ./scripts/model/train-hybrid.sh
DEVICE=cuda:1 ./scripts/model/train-hybrid.sh
```

`python scripts/check_env.py` mostra a build do PyTorch, as GPUs visíveis e o
dispositivo que `auto` escolheria.

**PC local com GPU AMD (RX 6600 XT, gfx1032).** O pacote `torch` do PyPI é a
build CUDA e não enxerga placas AMD; o ambiente precisa da build ROCm do
PyTorch, de acordo com o ROCm instalado (aqui, 7.2). Como a gfx1032 não tem
build oficial no ROCm, o código define sozinho
`HSA_OVERRIDE_GFX_VERSION=10.3.0` (sem isso o PyTorch ROCm trava); um valor
já exportado é respeitado. Para trocar o `torch` do ambiente:

```bash
.venv-amd/bin/python -m pip uninstall -y torch triton \
  $(.venv-amd/bin/python -m pip list --format=freeze | grep -E '^(nvidia|cuda)-' | cut -d= -f1)
.venv-amd/bin/python -m pip install torch --index-url https://download.pytorch.org/whl/rocm7.2
python scripts/check_env.py
```

O `scripts/env/create-envs.sh` já instala a build ROCm ao criar um ambiente em
máquinas AMD (versão do ROCm detectada em `/opt/rocm`, ou `ROCM_VERSION=7.2`).

**NPAD (NVIDIA).** Crie o ambiente no nó com `scripts/env/create-envs.sh`, que
detecta a GPU NVIDIA e instala o PyTorch com CUDA (se o NPAD recomendar outra
variante, veja o comentário em [requirements.txt](requirements.txt)). Em jobs
Slurm, solicite a GPU com `--gres=gpu:1`: o Slurm define
`CUDA_VISIBLE_DEVICES` e `auto` usa a GPU alocada. Sem Slurm, `auto` escolhe a
GPU visível com mais memória livre; para restringir o conjunto, exporte
`CUDA_VISIBLE_DEVICES` antes de treinar:

```bash
export CUDA_VISIBLE_DEVICES=0,1   # GPUs candidatas
./scripts/model/train-hybrid.sh
```

Os gráficos do treinamento ficam em [`scripts/evaluate/`](scripts/evaluate/):

```bash
RESULTS_DIR=results/autoencoder-lexical \
  ./scripts/evaluate/generate-plots.sh --test-samples 12
```

Cada treino grava em `results/autoencoder-<modo>/`: `losses.png` (perda com o
rótulo do modo — CE, MSE ou CE + λ·MSE —, melhor época marcada, zoom no trecho
final e accuracy), `metrics.png`, `confusion-matrices.png` (contagens e
percentual por classe real), `score-distributions.png` (visão completa e zoom
perto do limiar, com eixo comum entre validação e teste e a contagem de pontos
fora do recorte; antes de plotar, confere que os scores salvos batem com os
rótulos do split e com o checkpoint), `test-samples.png` (até 6 amostras por
figura, com páginas `test-samples-2.png` etc.; erro por caractere e por
atributo na mesma escala de cores), `latent-space.png` (projeção do teste nas
duas primeiras dimensões do espaço latente, colorida por classe e família) e
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
família, o alinhamento entre logs e rótulos, o gerador (incluindo a fonte
Tranco opcional), os shapes e a contagem de parâmetros dos três autoencoders,
limiares e métricas (P99, melhor F1, ROC-AUC, recall a FPR fixa, prevalência),
os baselines, a escolha de dispositivo GPU/CPU, o treino de poucas épocas, a
geração dos gráficos e a avaliação completa em um dataset mínimo sintético
([`tests/conftest.py`](tests/conftest.py)). Os testes que treinam modelos usam
`--device cpu` para serem determinísticos em qualquer máquina.

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

Todos os passos são executáveis também como módulos:

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
│   ├── raw/             # logs e rótulos do laboratório (ignorado pelo Git)
│   ├── external/        # fonte opcional Tranco (ignorada pelo Git)
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
│   ├── test/
│   ├── demo/
│   ├── lab/
│   └── env/
├── source/
│   ├── features.py      # normalização, vocabulário e os 42 atributos
│   ├── process_raw.py   # alinhamento logs-rótulos e dataset
│   ├── split_dataset.py
│   ├── models.py        # DenseAE, CharAutoencoder e HybridAutoencoder
│   ├── scoring.py       # scores, limiares (P99, melhor F1) e métricas
│   ├── device.py        # GPU NVIDIA/AMD ou CPU
│   ├── train.py
│   ├── baselines.py     # entropia e Isolation Forest
│   ├── evaluate.py
│   ├── explain.py
│   ├── plot_training.py
│   └── test_model.py
├── tests/
├── results/
│   ├── autoencoder-<modo>/
│   └── evaluation/
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
