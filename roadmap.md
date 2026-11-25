# Roadmap do SixEyesDNS

## Objetivo e prazo

Concluir o projeto individual da Unidade III de **Aprendizado Profundo
2026.2**, categoria **Autoencoders para Anomalias e Ruído**.

- apresentação presencial: 08, 10 ou 15/12/2026;
- texto no repositório, lido na `master`: 15/12/2026;
- demonstração prática como parte central da apresentação, pelo Space no
  navegador; capturas de tela e o app local ficam como plano B.

O requisito acadêmico está em
[doc/info/Descricao_do_Trabalho.md](doc/info/Descricao_do_Trabalho.md).

## Estado atual

A consolidação do laboratório, dos modelos, da avaliação e da documentação foi
mergeada na branch `master` pela PR #1 (08/11/2026). O texto da disciplina está
consolidado no [README](README.md), com introdução, técnicas, resultados, análise
crítica e conclusões — as cinco partes do escopo escrito. Esse texto ainda está
na branch `docs/atualizar-readme-roadmap`, não mergeada, e a entrega é lida na
`master`.

![Fases do projeto](doc/figures/roadmap.png)

| Fase | Estado | O que falta |
|---|---|---|
| 1 — Estrutura e schema | concluída | — |
| 2 — Dados | concluída (dataset-v2 regenerado, 24/11/2026) | separar metadados (baixa prioridade) |
| 3 — Modelos, treino e avaliação | concluída (retreinados e reavaliados no dataset-v2) | — |
| 4 — Demonstração | Gradio, replay e fine-tuning prontos; pacote do Space verificado localmente | blocos 1, 4 e 6 |
| 5 — Relatório e apresentação | texto e roteiro prontos | blocos 2 e 5 |
| 6 — Robustez | regeneração e retreino feitos; falta variância (seeds/splits) e CI | bloco 4 |

## Decisões do autor (24/11/2026)

- **Entrega:** o professor lê o repositório na `master`; o texto consolidado e a
  demonstração precisam estar nela antes de 15/12.
- **Apresentação:** presencial, no laboratório da sala (máquinas Ryzen 7 5700G
  com 16 GB de RAM). O foco é falar do projeto, mostrar a arquitetura e contar
  o desenvolvimento; a demonstração roda pelo Space no navegador. Docker,
  geração do dataset e treino não fazem parte da apresentação.
- **Space no Hugging Face:** é um extra do projeto, mas é o meio de
  demonstração na sala.
- **Dataset:** regenerado em 24/11/2026 (dataset-v2: 20.000 registros, 10.971
  domínios únicos, `ANOMALY_RATE=0,15`, anomalias sem sufixo fixo). Os três
  modelos foram retreinados e reavaliados nele.
- **Modelo híbrido:** o autor quer defender o híbrido pela hipótese de que mais
  informação para reconstruir o torna mais capaz de identificar domínios
  suspeitos. A hipótese e o que os dados atuais dizem sobre ela estão em
  [Hipótese do híbrido](#hipótese-do-híbrido).

## Pendências em ordem de execução

Todos os itens em aberto estão aqui, uma vez só, na ordem em que devem ser
feitos. Ao concluir um item, mova-o para a fase de origem em
[Histórico por fase](#histórico-por-fase).

### 1. Publicar e verificar o Space

- [ ] Publicar o Space no Hugging Face (extra, mas é o meio de demonstração na
      sala): criar o Space e rodar `hf auth login` e `hf upload <usuario>/<space>
      build/space . --repo-type=space --exclude .space-bundle`. Depende da conta
      do autor; o `git push` do repositório inteiro leva PNG, GIF e dados no
      histórico, e o Hub pode recusá-los sem Xet/LFS (não testado).
- [ ] Verificar o Space publicado. **Já verificado (24/11/2026)** a partir do
      pacote, num venv novo só com o `requirements.txt` do Space (torch
      2.15.0+cpu): `/on_domain` nos quatro exemplos, `/on_finetune` com o log
      de exemplo (1,5 s em CPU), reabertura do checkpoint adaptado e as duas
      recusas. Falta repetir no Space publicado.
      O venv dessa verificação usou Python 3.14.10, e não o 3.12 do projeto:
      fixar `python_version` no front matter do README ou repetir com 3.12.

### 2. Fechar a apresentação

O roteiro e a lista de figuras já existem em
[doc/roteiro-apresentacao.md](doc/roteiro-apresentacao.md).

- [ ] Plano B para a apresentação: tirar capturas de tela (ou um vídeo curto)
      do Space para o caso de a rede da sala falhar, ensaiar a fala com
      cronômetro e abrir o Space antes de começar (Spaces gratuitos podem
      estar dormindo).
- [ ] Aba **"Analisar log"** no Gradio (ideia de 24/11/2026). Hoje o replay só
      existe na CLI (`source/demo.py --replay`); a aba de log do Gradio só
      adapta o modelo. A lógica já é compartilhada (`build_report` é
      documentado como "comum ao CLI e à interface web"), então falta só a
      interface. Desenho proposto:
      - upload de `.log`/`.txt` (dnsmasq, BIND9, Unbound, formatos misturados)
        com limite de consultas, como o slider da aba de fine-tuning;
      - tabela **deduplicada por domínio** (domínio, nº de consultas, score,
        veredito), ordenada por score, com filtro "só suspeitas"; visão
        opcional na ordem do log (o "um após o outro");
      - clicar numa linha abre o mapa de erro por caractere e os atributos
        que a aba "Testar modelo" já tem (`character_plot`, `attribute_rows`);
      - exemplo clicável com `scripts/demo/replay-example.txt` (confirmar que
        o `space_bundle.py` o inclui);
      - **privacidade:** no Space público o upload vai para o servidor do
        Hugging Face e log real de DNS revela navegação; reaproveitar o padrão
        de aviso + checkbox da aba de fine-tuning e pedir logs sintéticos ou
        anonimizados;
      - **limiar:** o replay não recalibra; o P99 vem da validação sintética e
        em log real muito domínio normal desconhecido deve estourá-lo. Mostrar
        o score ordenado, não só o veredito, e apresentar o fluxo "adaptar com
        log normal, depois analisar" (hoje o fine-tuning gera um `model.pt`
        para baixar e não troca o modelo ativo; usá-lo na mesma sessão exige
        trabalho extra);
      - opcional e barato: agregar por **zona** (domínio-pai) e contar
        subdomínios únicos suspeitos por zona, já que túnel costuma gerar
        muitos subdomínios únicos sob a mesma zona (princípio de design, não
        validado aqui);
      - testes em `tests/test_gradio_demo.py` e atualização do roteiro (encurtar
        "Testar modelo" e dar a maior parte da demo à aba de log, com captura
        de tela de plano B).

### 3. Schema do dataset e fontes de domínios (baixa prioridade)

A regeneração, o retreino e a reavaliação (24/11/2026) estão concluídos; ver o
histórico das Fases 2 e 3. Resta só a limpeza de schema abaixo, que exige uma
nova regeneração (dataset-v3) e por isso não é prioridade para 15/12.

- [ ] Separar features de metadados no `dataset.csv`: ele tem 59 colunas e
      grava `is_<tipo DNS>`, `is_family_*`, `query_type`, `family`, `profile`,
      `label` e `seed` ao lado dos 42 atributos. O modelo já as ignora
      (`FEATURE_COLUMNS` e o `assert` de `source/features.py`), mas gravar só
      `query`, os 42 atributos e `label`, com os metadados de auditoria em
      arquivo separado, elimina o risco de vazamento por construção.
- [ ] Usar domínios populares reais (Tranco) como normais no próximo dataset.
      O suporte já existe no gerador (`docker/generator/external_domains.py`,
      perfil `normal_tranco`, `TRANCO_LIMIT`/`TRANCO_RATE`), mas
      `data/external/tranco_top.csv` não existe e o dataset-v2 **não tem**
      nenhuma linha `normal_tranco`. Cuidados: (1) o Tranco mede
      **popularidade, não segurança**: o ranking padrão agrega Umbrella,
      Majestic, Farsight, CrUX e Cloudflare Radar, e o site oferece filtros
      opcionais como o do Google Safe Browsing, o que indica que a lista crua
      pode conter domínios indesejados; baixar uma lista com esse filtro e
      citar o identificador dela; (2) a lista padrão traz domínios registrados
      (existe uma variante "com subdomínios"), então os nomes são curtos e
      limpos e não representam hashes de CDN nem subdomínios longos, que são
      os falsos positivos reais; (3) o Tranco não diz quais domínios são
      acessados **em conjunto**: para sessões realistas, é preciso um modelo
      próprio de co-acesso no gerador (ex.: uma página popular dispara
      consultas a seus CDNs e trackers); (4) o gerador limita o nome a 48
      caracteres e só os usa como texto `.test`.

### 4. Robustez e hipótese do híbrido

O dataset-v2 já existe e foi usado numa única seed; os quatro últimos itens
pedem múltiplas seeds ou splits sobre ele, não um dataset novo.

- [ ] Passar `weights_only=True` explícito nos `torch.load`
      (`source/scoring.py`, `source/train.py`): o padrão do torch atual já é
      `True`, mas a intenção fica registrada e não depende da versão. Aproveitar
      para padronizar os imports de `scoring.py` (aceita pacote e script) com
      `finetune.py` (só relativo).
- [ ] Configurar CI no GitHub Actions (o repositório não tem workflow hoje; a
      verificação é local, no `.venv-amd`).
- [ ] Medir se refazer o `StandardScaler` só com o log de adaptação
      (`source/finetune.py`) desloca a entrada em relação aos pesos treinados
      com o scaler original. **Hipótese, não medida:** com 2–5 épocas e taxa de
      1e-4 o modelo pode não compensar o deslocamento. Comparar scaler novo ×
      scaler original em normais independentes antes de afirmar qualquer coisa.
- [ ] Verificar a origem do falso positivo `normal_jjk`: ele aparece nos
      treinos CUDA (A100, NPAD) e não no AMD, com uma seed por backend. Não há
      evidência para atribuí-lo ao backend; pode ser não determinismo. Repetir
      com várias seeds por backend e recuperar os checkpoints do NPAD (jobs
      2247654 e 2247952, provavelmente ainda lá) para versionar a tabela
      AMD × A100. Até lá, nenhum texto deve apontar o backend como causa (README
      e `doc/` hoje não apontam).
- [ ] Repetir o treino com múltiplas seeds para estimar variância e publicar
      intervalos de confiança.
- [ ] Avaliar mais de um split para medir a sensibilidade aos cortes.
- [ ] Comparar CharAE e híbrido com várias seeds e intervalos de confiança; se
      o CharAE continuar equivalente, relatar isso no texto.
- [ ] Se couber, um ramo com informação que não deriva do nome, como o
      comportamento por cliente e domínio-pai numa janela (taxa de consultas,
      subdomínios únicos, rcode), sem reintroduzir atalhos como o tipo DNS
      isolado.

### 5. Entrega na `master`

- [ ] Reautenticar o `gh` (`gh auth login` e depois `gh auth setup-git`): em
      24/11/2026 ele devolveu HTTP 401, o que impede consultar a PR #2 e
      bloqueia o push e o merge na `master`.
- [x] Atualizar `.github/copilot-instructions.md`, que descrevia um estado de
      08/11/2026 (50.000 linhas, 60.000 consultas no log, 126 domínios
      normais, branch `ajustes-u3`). Passou a descrever o dataset-v2 (20.000
      linhas, 59 colunas, gerador sem sufixo fixo).
- [ ] Mergear a PR #2 (`docs/atualizar-readme-roadmap`) na `master` antes de
      15/12 e fazer a revisão final do README e do roteiro.
- [ ] Sugerir, sem executar, os comandos `gh repo edit` e criação da tag
      `entrega-u3` no dia da entrega.

### 6. Despriorizado

Mantidos para registro; não bloqueiam a entrega.

- [ ] Implementar modo ao vivo para log do dnsmasq quando a conectividade for
      confirmada. **Despriorizado (24/11/2026):** a apresentação usa o Space;
      Docker, geração do dataset e treino ficam fora dela.
- [ ] Documentar a alternativa dentro da rede Docker se a porta do host não
      funcionar.

## Hipótese do híbrido

Hipótese do autor: dar mais informação ao autoencoder para reconstruir aumenta
a capacidade de separar domínios suspeitos. **Resultado no dataset-v2**
(20.000 registros, retreino completo até o early stopping, 24/11/2026; uma
seed, um split — ver bloco 4 para variância):

- O teto de ROC-AUC 1 saiu do teste: CharAE 0,9997, HybridAE 0,9993 (teste por
  registro, limiar P99). Os dois se separam de verdade, e **nenhum dos dois é
  estritamente melhor**:
  - **CharAE tem recall maior:** 0,9921 contra 0,9808 do HybridAE (28 falsos
    negativos a menos).
  - **HybridAE tem metade do FPR:** 0,0055 contra 0,0109 — 14 domínios
    `normal_hard` sinalizados por engano, contra 28 do CharAE; os dois erram
    exclusivamente em hashes de CDN (`results/evaluation/false_positives.csv`).
  - **HybridAE generaliza melhor:** a razão entre o FPR do teste e o do treino
    é 0,76× (sem sinal de sobreajuste) contra 3,02× do CharAE
    (`results/evaluation/overfitting.csv`).
- A ablação de λ (`results/evaluation/ablation.md`) mostra a troca: λ=0,25 dá
  o maior recall (0,9953) com FPR 0,0105; λ=1 (o padrão) reduz o FPR para
  0,0054 ao custo de recall 0,9807; λ=4 leva o FPR a 0,0031 mas o recall cai
  para 0,8715. Mesmo λ=0 (só o erro lexical do encoder híbrido, sem usar o
  ramo numérico no score) já tem menos FPR que o CharAE treinado separado
  (0,0070 contra 0,0109): o ganho de generalização parece vir do treino
  conjunto do encoder, não da soma do erro numérico ao score.
- Isso não confirma a hipótese original (mais informação → mais recall): os
  42 atributos continuam derivados do domínio, e o HybridAE tem recall menor,
  não maior. O que o treino conjunto parece trazer é regularização: o híbrido
  erra metade dos falsos positivos do CharAE nos mesmos hashes de CDN difíceis,
  e generaliza melhor do treino para o teste. A escolha entre os dois depende
  de priorizar recall (CharAE) ou FPR/estabilidade (HybridAE).
- **Limites desta leitura:** uma seed, um split, um checkpoint por modo. O
  bloco 4 lista o que falta para uma conclusão robusta (múltiplas seeds e
  splits, intervalo de confiança).

Histórico desta hipótese: o dataset-v1 (9.911 registros, 100% das suspeitas em
`.tunnel`) tinha ROC-AUC 1 nos dois modelos e não permitia comparação; uma
prévia sem Docker, não versionada, já indicava que o teto sumia com o gerador
novo, mas não tinha convergido (early stopping não disparado em 800 épocas).

## Utilidade e limites de uso

Avaliação de 24/11/2026 (números do HybridAE no teste do dataset-v2, P99; o
resto é inferência, marcada como tal).

- **Medido:** FPR 0,55% por registro e 1,17% por domínio único (14 de 1.194
  normais); precisão esperada 0,64 a 1% de suspeitas e 0,15 a 0,1%. O modelo
  vê só o nome da consulta, sem volume, frequência por zona, tamanho de
  resposta nem timing. Tudo sobre tráfego sintético.
- **Faz sentido:** caça retroativa em logs de resolvedor (revisão humana
  sobre os N domínios únicos de maior score); um sinal dentro de um pipeline
  maior (SIEM, Zeek, Suricata), combinado com contagem de subdomínios por
  zona; baseline por rede via fine-tuning com log normal, mais plausível em
  redes pequenas e homogêneas (laboratório, filial, IoT, honeypot; inferência);
  ensino e pesquisa, pelo mapa de erro por caractere; e, como extensão não
  testada, detecção de DGA.
- **Não usar:** bloqueio automático sem revisão, única camada de defesa, ou
  rede grande e heterogênea sem recalibração.
- **Ressalva:** em rede real, hashes de CDN, trackers e DKIM são mais variados
  que os do gerador; espera-se FPR pior (inferência; não testado em log real).

## Critérios de aceitação

- [x] `./scripts/data/process-data.sh` roda do zero e falha em caso de
      interseção (verificado com os logs reais, saída fora de `data/processed/`;
      `split_dataset` verifica a interseção em tempo de execução).
- [x] `python -m source.train --mode lexical|semantic|hybrid` roda em CPU em
      poucos minutos com o dataset versionado (100 épocas do híbrido: 121 s).
- [x] `python -m source.evaluate` roda em CPU no dataset mínimo e no dataset
      versionado.
- [x] `pytest` passa (271 testes em 24/11/2026).
- [x] Nenhuma feature usa `label`, `family`, `query_type`, `seed`, IP ou
      cliente.
- [x] O README não contém métricas inventadas (as tabelas de resultados foram
      conferidas célula a célula contra `results/evaluation/metrics.csv`).
- [x] O texto cobre introdução, técnicas, resultados, análise crítica e
      conclusões.
- [x] A demo funciona ao vivo ou em replay offline (replay verificado).
- [ ] A `master` contém o README com as cinco partes e o Space publicado
      responde na demonstração.

## Histórico por fase

Itens concluídos, na ordem das fases. O que está em aberto fica em
[Pendências](#pendências-em-ordem-de-execução).

### Diagnóstico concluído

- [x] Confirmar que o repositório usa `source/`, não `src/`.
- [x] Localizar o gerador em `docker/generator/gerador_queries.py`.
- [x] Confirmar que o dataset versionado possui 50.000 registros.
- [x] Regenerar o dataset limpo com 10.000 consultas do laboratório ampliado.
- [x] Confirmar 42 atributos lexicais e 58 colunas no schema da época (hoje o
      `dataset.csv` tem 59, com `profile`).
- [x] Confirmar que `.test` é removido da coluna de domínio processada.
- [x] Confirmar ausência de interseção de domínios entre os splits atuais.
- [x] Identificar somente 126 domínios normais únicos no gerador atual.
- [x] Identificar log concatenado: 60.000 consultas para 50.000 rótulos.
- [x] Identificar que o casamento atual usa domínio e tipo, sem timestamp.
- [x] Planejar e implementar serviços fictícios, Nginx e dashboard local.
- [x] Ampliar famílias sintéticas e perfis normais difíceis sem tráfego externo.
- [x] Confirmar funcionamento da porta `127.0.0.1:6767` com uma ferramenta DNS
      disponível (consulta crua UDP/TCP; no Docker Desktop foi preciso ligar o
      dnsmasq à rede de borda `lab-edge`, pois portas de containers presos só
      à rede interna não chegam ao host).

### Fase 1 — Estrutura e schema

Status: **concluída**; modelos retreinados sem os indicadores de tipo DNS.

- [x] Trabalhar na branch `ajustes-u3`.
- [x] Manter os módulos executáveis com `python -m source.<modulo>` nos
      scripts de treino e plotagem.
- [x] Manter `source/features.py` como origem dos atributos usados no treino.
- [x] Adicionar `source/__init__.py`.
- [x] Consolidar completamente em `source/features.py` a normalização,
      tokenização, vocabulário e os 42 atributos numéricos.
- [x] Separar explicitamente features e metadados.
- [x] Rejeitar automaticamente `label`, `family`, `query_type`, `seed`, IP e
      cliente na matriz de entrada.
- [x] Remover os indicadores de tipo DNS (`is_A`, `is_TXT` etc.) das features,
      pois derivam de `query_type`, que é metadado; retreinar os modelos após
      a correção.
- [x] Fazer `process_raw.py` e `split_dataset.py` funcionarem com
      `python -m source.<modulo>`.
- [x] Adicionar `--holdout-family`.
- [x] Expandir `summary.json` com linhas e domínios únicos por split, classe e
      família.
- [x] Adicionar testes de determinismo, ausência de metadados e ausência de
      interseção.
- [x] Mover `VL.py` para `scripts/check_env.py`.
- [x] Fixar dependências e incluir pytest, scikit-learn e matplotlib quando
      realmente usados.

### Fase 2 — Dados

Status: **concluída**; laboratório, gerador, alinhamento, regeneração e
retreino (Fase 3) feitos em 24/11/2026. Resta só separar features de metadados
do schema (bloco 3, baixa prioridade, exige dataset-v3).

- [x] Corrigir o alinhamento entre logs e rótulos e documentar o tratamento de
      execuções concatenadas e duplicadas (`source/process_raw.py`: casa por
      servidor-alvo, IP do gerador, janela de tempo e `(query, tipo)`; falha em
      rótulos concatenados ou conflitantes; relatório em `alignment.json`).
- [x] Alinhar README, compose e scripts quanto a `QUERY_COUNT`,
      `ANOMALY_RATE` e `SEED`.
- [x] Decidir se o dataset versionado será regenerado. **Decisão do autor
      (24/11/2026): regenerar**, com um laboratório mais completo e variado
      (bloco 3 das pendências), em commit separado. O alinhamento novo gera 10.000
      linhas em vez de 9.911 (as 89 que faltam são normais), mas os splits com
      seed 42 mudam, o que invalida os checkpoints atuais e a release
      `hybrid-v1`; regenerar exige retreinar os três modelos (viável com a
      GPU) e reavaliar.
- [x] Controlar o atalho do sufixo `.tunnel` (`python -m source.suffix_control`;
      resultado em `results/evaluation/suffix_control.csv`). No dataset, 100%
      das 4.977 linhas suspeitas terminam em `.tunnel` e nenhuma das 4.934
      linhas normais contém `tunnel` (`docker/generator/gerador_queries.py:300-303`).
      Medido no teste, com o P99 de cada checkpoint: o sufixo **não é
      necessário** (trocar `.tunnel` por sufixos de aparência normal mantém o
      recall do CharAE e do híbrido em 1,0000 nas cinco famílias; o do DenseAE
      cai de 0,5592 para 0,4644), mas é **suficiente** (acrescentar `.tunnel`
      aos 440 domínios normais do teste leva o FPR do CharAE de 0,0000 para
      0,8341 e o do híbrido de 0,0159 para 0,4773). O detector reage ao
      payload, mas também a qualquer trecho nunca visto no treino, o que
      combina com os falsos positivos de hash de CDN.
- [x] Adicionar fonte opcional local `data/external/tranco_top.csv`, ignorada
      pelo Git, com fallback interno (`docker/generator/external_domains.py`;
      sem o arquivo a saída do gerador é idêntica à anterior; o download é
      manual e a fonte deve ser citada).
- [x] Adicionar normais difíceis com subdomínios semelhantes a hashes de CDN.
- [x] Adicionar anomalias de baixa entropia, labels curtos e codificações mistas.
- [x] Registrar sequência, timestamp UTC, serviço e perfil no arquivo de
      rótulos para auditoria sem usá-los como features.
- [x] Adicionar Nginx, API fictícia e dashboard local de coleta.
- [x] Adicionar aplicações backend sintéticas e telemetria de requisições.
- [x] Manter o tráfego sintético, local e em `.test`.
- [x] Adicionar BIND9 autoritativo (zona `test.` e reversa), resolvedor
      Unbound e DHCP Kea ao laboratório.
- [x] Distribuir as consultas do gerador por múltiplos servidores DNS com
      pesos (`DNS_TARGETS`), tipos ponderados por classe, reversas PTR e
      jitter determinístico.
- [x] Ler logs do dnsmasq, do BIND9 e do Unbound no `process_raw.py`
      (múltiplos `--log`).
- [x] Ampliar o dashboard com consultas por servidor, por tipo, por minuto,
      falhas DNS e tabela de infraestrutura.
- [x] Gerar as anomalias sob zonas e sufixos de aparência normal, em vez de
      sempre `.tunnel` (`docker/generator/traffic_profiles.py`): 70% imitam a
      infraestrutura normal (`api.orbita`) e 30% usam uma zona própria
      (`syncfeed`).
- [x] Corrigir a família `low_entropy` do gerador: o padrão repetido agora é
      sorteado e a família passou de 8 domínios únicos em 989 linhas para 699
      em 700 (`tests/test_traffic_profiles.py`). Foram criadas as famílias
      `dictionary` (palavras do vocabulário normal) e `short` (payload curto), e
      payloads longos podem ir em duas etiquetas.
- [x] Regenerar e versionar `data/processed/` com o gerador novo e o
      alinhamento corrigido (24/11/2026): `QUERY_COUNT=20000`,
      `ANOMALY_RATE=0,15` (também os novos padrões do `docker-compose.yml`),
      `SEED=42`. Dataset-v2: 20.000 registros, 10.971 domínios únicos, nenhum
      contém `tunnel`; alinhamento 20.000/20.000, sem lacunas. Os logs do
      dataset-v1 ficam em `data/raw/archive/dataset-v1-2026-11-13/` (fora do
      Git). O `docker-compose.yml` precisou de dois ajustes para subir no
      Linux: `dockerfile:` em minúscula em cada `build:` (o compose procurava
      `Dockerfile`) e os serviços dnsmasq/BIND9/Unbound passaram a criar o
      próprio log no bind mount antes de trocar de usuário (senão o daemon não
      conseguia escrever nele); o BIND9 também precisou de `named -u named`.
- [x] Versionar `data/processed/alignment.json` junto com o dataset
      regenerado (sem lacunas: `labels_without_log: 0`, `sequence_gaps: 0`).

### Fase 3 — Modelos, treino e avaliação

Status: **concluída**; treino lexical, semântico (DenseAE) e híbrido,
baselines, avaliação completa e retreino no dataset-v2 implementados.

- [x] Implementar `DenseAE` para 42 atributos e score MSE (modo `semantic`).
- [x] Implementar submodelo lexical independente com tokens, convoluções e
      reconstrução de caracteres.
- [x] Implementar `HybridAutoencoder` com score combinado CE/MSE.
- [x] Implementar `source/train.py` com seed 42, Adam e treino somente com
      exemplos normais; GPU como caminho padrão e CPU como fallback automático
      (`--device auto`: NVIDIA/CUDA ou AMD/ROCm, caindo para CPU quando não há
      GPU disponível, sem erro e sem configuração).
- [x] Permitir os modos `lexical`, `semantic` e `hybrid` por CLI.
- [x] Permitir inicializar o encoder híbrido com o checkpoint lexical
      pré-treinado.
- [x] Combinar no treinamento o erro lexical CE e o MSE numérico por
      `z(CE) + lambda*z(MSE)`, com `lambda` configurável.
- [x] Salvar checkpoint, histórico, métricas, scaler, vocabulário e limiar.
- [x] Gerar automaticamente gráficos ao terminar os wrappers de treinamento.
- [x] Corrigir o plot lexical para mostrar erro por posição de caractere e o
      plot híbrido/semântico para mostrar erro numérico.
- [x] Organizar os scripts em `data/`, `model/`, `evaluate/`, `test/`, `lab/`
      e `env/`.
- [x] Implementar `source/scoring.py` com limiar P99 e melhor F1 calibrados
      somente na validação.
- [x] Implementar baselines de entropia e Isolation Forest
      (`source/baselines.py`).
- [x] Implementar `source/evaluate.py` com métricas, figuras, prevalência,
      recall a FPR de 1% e recall por família.
- [x] Reportar precisão, recall, F1, FPR e ROC-AUC além da acurácia, com
      curvas ROC e precisão-recall (`results/evaluation/`).
- [x] Reportar métricas por registro e por domínio único; investigar os
      falsos positivos por domínio (no dataset-v2, limiar P99: HybridAE erra
      14 domínios `normal_hard`, CharAE erra 28, ambos só hashes de CDN).
- [x] Avaliar leave-one-family-out sem escolher limiar no teste.
- [x] Adicionar explicabilidade por atributo e por caractere
      (`source/explain.py`).
- [x] Testar shapes, parâmetros, treino de uma época e avaliação em dataset
      mínimo.
- [x] Gerar tabela de ablação em `results/` (`results/evaluation/ablation.md`).
- [x] Corrigir os rótulos das perdas nos gráficos: CE no lexical, MSE no
      semântico e perda combinada no híbrido.
- [x] Exibir matrizes de confusão com contagens e percentuais por classe,
      com texto legível sobre células escuras.
- [x] Adicionar zoom próximo ao limiar nas distribuições de score, com eixo
      comum entre validação e teste e contagem dos pontos fora do recorte.
- [x] Verificar a correspondência entre scores salvos e rótulos do split
      (ordem e quantidade) antes de plotar as distribuições.
- [x] Marcar a melhor época (checkpoint) nos gráficos de perda e adicionar
      zoom do trecho final do treinamento.
- [x] Reorganizar `test-samples.png`: menos exemplos por figura, escala de
      cores comum, erro por caractere e numérico no híbrido e sem
      reconstrução textual no modo semântico.
- [x] Versionar a avaliação completa em `results/evaluation/` (22 artefatos),
      para que os números do README sejam verificáveis.
- [x] Retreinar os três modelos sobre o dataset-v2 e reavaliar (24/11/2026):
      `--fresh`, até 3.000 épocas; early stopping disparou no CharAE (2.955,
      melhor 2.755) e no HybridAE (2.770, melhor 2.570); o DenseAE rodou as
      3.000 sem parar. Reconferidas célula a célula as tabelas do README contra
      `results/evaluation/metrics.csv`. Os checkpoints do dataset-v1 ficam no
      histórico do git; backups locais em `*.pt.bak` (fora do Git).

### Fase 4 — Demonstração

Status: dashboard, replay offline, interface Gradio e fine-tuning normal-only
implementados; o pacote do Space foi verificado localmente e falta publicá-lo
(bloco 1). O app foi verificado por HTTP e pelos eventos de classificação e
adaptação da API. O fine-tuning separa domínios, preserva o modelo base e não
declara métricas sem teste independente.

- [x] Criar `source/demo.py` usando a mesma normalização e features do treino.
- [x] Criar `scripts/demo/demo.sh`.
- [x] Criar `app.py` e `source/gradio_demo.py` com consulta manual, seleção dos
      três modelos, heatmap e relatório JSON para o Space.
- [x] Implementar `source/finetune.py` com confirmação normal-only, split por
      domínio, scaler de treino, melhor checkpoint e P99 de validação; oferecer
      download sem alterar o checkpoint base.
- [x] Documentar aplicações reais e os limites de produção em
      `doc/aplicacoes.md` e o protocolo em `doc/fine-tuning.md`.
- [x] Implementar `--replay <log>` para apresentação sem Docker, incluindo um
      exemplo versionado em `scripts/demo/replay-example.txt` e saída JSON.
      Atualizado em 24/11/2026 com domínios do dataset-v2 (os antigos, em
      `.tunnel`, não existem mais no split de teste); `source/gradio_demo.py`
      e `scripts/demo/normal-example.txt` também trocaram de exemplos.
- [x] Exibir score, classificação e mapa de erro por caractere.
- [x] Disponibilizar dashboard local em `http://127.0.0.1:8080`.
- [x] Monitorar aplicações, serviços, rotas, erros e latência no dashboard.
- [x] Adicionar gráficos visuais de famílias DNS, aplicações e serviços.
- [x] Simular navegação orgânica somente em sites sintéticos `.test`, com
      sessões, pesos, pausas e telemetria por site.
- [x] Adicionar scripts de teste para pytest, checkpoint e geração de plots.
- [x] Corrigir o `requirements.txt` e montar o pacote do Space. Faltavam
      `scikit-learn` (`source/scoring.py`) e `matplotlib`
      (`source/gradio_demo.py`); o `pytest` foi para `requirements-dev.txt`.
      `./scripts/demo/space-bundle.sh` gera `build/space` (26 arquivos, 3,9 MiB:
      `app.py`, `source/`, os três `model.pt`, os logs de exemplo e o
      `requirements.txt` com o torch de CPU). `tests/test_space_bundle.py`
      falha se algum import de terceiros ficar fora do requirements.
- [x] Definir o mínimo de domínios do fine-tuning. Com 10 domínios únicos a
      validação ficava com 2 e o P99 virava praticamente o máximo. Agora a
      adaptação é recusada abaixo de 50 domínios únicos e avisa (relatório,
      checkpoint e interface) abaixo de 500. A aba traz um log normal de
      exemplo, `scripts/demo/normal-example.txt` (600 domínios únicos).
      Os limites 50 e 500 são heurísticos, não calibrados.

#### Plano da demonstração

![Fluxo da demonstração e do fine-tuning](doc/figures/demo.png)

Prioridade: o `--replay` vem antes do modo ao vivo. A apresentação não pode
depender de daemon Docker funcionando na sala; o replay com um log gravado é
determinístico e reproduzível.

### Fase 5 — Relatório e apresentação

Status: **texto concluído** no README (introdução, técnicas, resultados,
análise crítica e conclusões) e roteiro cronometrado com lista de figuras em
[doc/roteiro-apresentacao.md](doc/roteiro-apresentacao.md); faltam o plano B e
a entrega na `master` (blocos 2 e 5).

- [x] Organizar o README com Introdução, Desenvolvimento/Técnicas, Resultados,
      Reprodução, Segurança/Ética e Referências.
- [x] Incluir somente números gerados e verificáveis (as tabelas do README e
      do `summary.md` foram conferidas célula a célula contra
      `results/evaluation/metrics.csv`).
- [x] Substituir os diagramas Mermaid por PNGs Matplotlib reproduzíveis:
      pipeline, arquiteturas, treino, roadmap e demonstração/adaptação.
- [x] Manter `source/doc_figures.py` para regenerar as figuras em
      `doc/figures/` sem serviço externo de renderização.
- [x] Criar `doc/roteiro-apresentacao.md` para 10 minutos:
      introdução 1,5; pipeline 2; modelos 2; resultados 3; demo 1,5 (pelo
      Space).
- [x] Listar as figuras necessárias para a apresentação (tabela no roteiro; as
      imagens não foram revisadas visualmente).
- [x] Atualizar referências apenas para fontes realmente utilizadas.
- [x] Versionar os resultados gráficos dos treinamentos lexical, semântico e
      híbrido produzidos localmente.
- [x] Atualizar `.github/copilot-instructions.md`, que descrevia um estado de
      08/11/2026 (50.000 linhas, 60.000 consultas no log, 126 domínios
      normais, branch `ajustes-u3`). Passou a descrever o dataset-v2.

### Fase 6 — Robustez (nova)

Status: a regeneração e o retreino (itens abaixo) estão feitos; falta
variância (múltiplas seeds/splits) e CI, que seguem no bloco 4 das pendências.

- [x] Regenerar `data/processed/` com o alinhamento corrigido e retreinar os
      três modelos (24/11/2026) — ver o histórico das Fases 2 e 3 para os
      números. Isso também fecha o teto de ROC-AUC 1 que impedia comparar
      CharAE e híbrido (ver [Hipótese do híbrido](#hipótese-do-híbrido)).
