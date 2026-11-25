# Roteiro da apresentação (10 minutos)

Apresentação presencial da Unidade III de Aprendizado Profundo 2026.2
(08, 10 ou 15/12/2026). O requisito está em
[doc/info/Descricao_do_Trabalho.md](info/Descricao_do_Trabalho.md): introdução
ao problema, tecnologias e abordagens, resultados e demonstração prática.

A fala é sobre o projeto, a arquitetura e o desenvolvimento. A demonstração
roda pelo Space no navegador; Docker, geração do dataset e treino **não** fazem
parte da apresentação.

| Bloco | Tempo | Figura principal |
|---|---:|---|
| 1. Introdução ao problema | 1,5 min | — |
| 2. Pipeline e desenvolvimento | 2,0 min | `doc/figures/pipeline.png` |
| 3. Modelos | 2,0 min | `doc/figures/architectures.png` |
| 4. Resultados e análise crítica | 3,0 min | tabela do README, `roc-pr.png`, `prevalence.png` |
| 5. Demonstração no Space | 1,5 min | o próprio Space |

## Antes de começar

- Abrir o Space 5 minutos antes: Spaces gratuitos podem estar dormindo e a
  primeira abertura demora.
- Testar a rede da sala e deixar as abas **Testar modelo** e **Fine-tuning com
  log normal** já carregadas.
- Deixar as figuras da tabela abaixo abertas em outra aba ou nos slides.
- Plano B: capturas de tela do Space (itens do bloco 5) e, se levar notebook, o
  app local com `./scripts/demo/gradio.sh`. Sem rede, não improvisar: mostrar as
  capturas e seguir.

## 1. Introdução ao problema (1,5 min)

- Tunelamento DNS esconde dados em nomes de domínio: subdomínios longos em
  base32, hex ou base64. O DNS quase sempre passa pelo firewall.
- Não há muitos ataques rotulados para treinar um classificador. A saída é
  aprender como é o **normal** e sinalizar o que foge: autoencoder treinado só
  em consultas normais, com o erro de reconstrução como score.
- Categoria da disciplina: autoencoders para anomalias e ruído.
- Escopo: o modelo vê **somente o domínio**; o tráfego é sintético, local e
  `.test`. É um sinal para priorizar análise humana, não um bloqueador.

## 2. Pipeline e desenvolvimento (2 min)

Mostrar `doc/figures/pipeline.png` e percorrer da esquerda para a direita:

1. **Laboratório:** gerador de consultas, dnsmasq, BIND9, Unbound e Kea em
   Docker, sem sair para a Internet.
2. **Dados:** logs alinhados aos rótulos, 20.000 registros e 10.971 domínios
   únicos (dataset-v2, 24/11/2026; `ANOMALY_RATE=0,15`). O treino usa só os
   11.901 registros normais do split de treino; a validação e o teste têm
   normais e suspeitas.
3. **Splits sem interseção de domínios**, verificada em tempo de execução.
4. **Modelos, avaliação e demonstração.**

Decisões e correções do desenvolvimento, para contar como história:

- O log tinha execuções concatenadas (60.000 consultas para 50.000 rótulos) e o
  casamento antigo ignorava o tempo. O alinhamento foi refeito.
- O tipo DNS (`TXT`, `A`…) saiu das features: era um atalho derivado de
  metadado. Os modelos foram retreinados.
- O limiar P99 é calibrado **só na validação**; o teste nunca escolhe limiar.

## 3. Modelos (2 min)

Mostrar `doc/figures/architectures.png`.

- Entrada: 64 posições de caracteres e 42 atributos lexicais (6 escalares e 36
  frequências de `a-z`/`0-9`). Espaço latente de 16 dimensões.
- **DenseAE:** reconstrói os 42 atributos; score é o MSE.
- **CharAE:** reconstrói a sequência de caracteres; score é a entropia cruzada
  por posição real.
- **HybridAE:** os dois ramos, com score `z(CE) + λ·z(MSE)`.
- Baselines: limiar de entropia e Isolation Forest.
- Treino: Adam, seed 42, máscara e ruído na entrada, early stopping pela
  validação.

**Hipótese que motivou o híbrido, dita com honestidade:** dar mais informação
para reconstruir deveria ajudar a achar suspeitas. Os dados não confirmam essa
forma da hipótese — o HybridAE tem recall *menor* que o CharAE, não maior —,
mas mostram outra coisa: o HybridAE erra metade dos falsos positivos (14
contra 28, mesmos hashes de CDN) e generaliza melhor do treino para o teste.
Detalhes no [roadmap](../roadmap.md#hipótese-do-híbrido).

## 4. Resultados e análise crítica (3 min)

Mostrar a tabela do README (teste por registro, limiar P99):

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Entropia | 0.9174 | 0.3384 | 0.4944 | 0.0179 | 0.7613 |
| Isolation Forest | 0.8936 | 0.3225 | 0.4740 | 0.0226 | 0.8116 |
| DenseAE | 0.9811 | 0.4477 | 0.6148 | 0.0051 | 0.9492 |
| CharAE | 0.9817 | 0.9921 | 0.9868 | 0.0109 | 0.9997 |
| HybridAE | 0.9906 | 0.9808 | 0.9857 | 0.0055 | 0.9993 |

Pontos a falar:

- Os autoencoders de caracteres superam os baselines por uma margem grande.
- Com este dataset mais difícil, o teto de ROC-AUC 1 sai do teste e os dois
  autoencoders de caracteres se separam: **CharAE tem recall maior** (0,9921
  contra 0,9808), **HybridAE tem metade do FPR** (0,0055 contra 0,0109 — 14
  domínios `normal_hard` sinalizados por engano, contra 28). Nenhum dos dois
  é estritamente melhor.
- **Prevalência** (`results/evaluation/prevalence.png`): o teste tem 37,1% de
  suspeitas. Com recall 0,9808 e FPR 0,0055, a precisão esperada do HybridAE
  cai para **0,6446 com 1%** de suspeitas e **0,1524 com 0,1%**. F1 alto não
  basta.

Análise crítica, sem esconder:

- **Nomes reais (medido, `python -m source.external_check`):** tratando os 2.000
  nomes mais populares do ranking Tranco como tráfego normal, o CharAE sinaliza
  1.999, o HybridAE 1.998 e o DenseAE 1.218, contra 1% a 2% dos normais do
  laboratório. O detector aprendeu o vocabulário do laboratório; num ambiente
  real ele precisa ser adaptado a normais daquele ambiente, e isso ainda não foi
  medido em nomes reais.
- ROC-AUC alto num dataset sintético **não** prova eficácia em tráfego real,
  mesmo sem o teto de 1,0 do dataset anterior. Os splits não repetem
  domínios, mas os normais compartilham moldes com o gerador.
- Uma seed e um split, sem intervalo de confiança: o roadmap lista isso como
  próximo passo.
- **Correção no gerador:** o dataset-v1 tinha um atalho (100% das suspeitas em
  `.tunnel`); o gerador atual não usa sufixo fixo — a zona imita a
  infraestrutura normal (70%) ou é uma zona própria (30%).
- Todos os falsos positivos, nos dois modelos, são do perfil `normal_hard`
  (hashes de CDN): o detector reage a trechos de alta entropia nunca vistos
  no treino, legítimos ou não.
- O modelo não vê a resposta DNS nem prova exfiltração.

Fechamento: a aplicação responsável hoje é **priorização para análise
humana**. Os próximos passos são misturar o Tranco ao dataset (com anomalias
também em TLDs reais) e comparar CharAE e híbrido com várias seeds e splits,
para saber se a diferença de recall e FPR é estável.

## 5. Demonstração no Space (1,5 min)

Valores medidos em CPU em 24/11/2026 com o checkpoint híbrido retreinado no
dataset-v2 (limiar P99 de 5,7159; via `--replay scripts/demo/replay-example.txt`).
No Space podem variar nas últimas casas.

**Aba "Testar modelo" (cerca de 1 min):**

| Domínio | Esperado | Score |
|---|---|---:|
| `canary.mail.cobalto.test` | normal | −0,847 |
| `aen6dyl46u.eu-west.cdn.cobalto.test` | suspeita (`short`, sem `.tunnel`) | 9,410 |
| `ddddddddddddddddddddddd.metricsink.test` | suspeita (`low_entropy`) | 43,088 |
| `6222f8b896.cdn.nuvem.test` | **suspeita (falso positivo conhecido)** | 7,406 |

- Mostrar o mapa de erro por caractere. No segundo exemplo o erro se concentra
  no prefixo aleatório `aen6dyl46u`, não na zona `cdn.cobalto` — que imita
  infraestrutura real e nunca tem sufixo fixo; no falso positivo da CDN só o
  hash `6222f8b896` acende e o resto fica em zero.
- Destacar o terceiro exemplo: nenhuma suspeita no dataset-v2 termina em
  `.tunnel` ou em qualquer sufixo fixo; o gerador varia a zona (70% imita
  infraestrutura normal, 30% usa zona própria do atacante).
- Parar no último exemplo: é um hash de CDN legítimo e ilustra a análise
  crítica — o detector reage a alta entropia nunca vista no treino, legítima
  ou não.
- Trocar para **DenseAE** e mostrar que não há mapa por caractere (ele só
  reconstrói atributos).

**Aba "Fine-tuning com log normal" (cerca de 0,5 min):** clicar no exemplo
`normal-example.txt` (600 domínios normais únicos), marcar a confirmação e
adaptar. A interface mostra 400 domínios no treino e 100 na validação, e o
limiar P99 muda. Dizer em voz alta: a validação do fine-tuning **não é teste**;
um log com túnel ensinaria o modelo a reconstruir o túnel.

Se o Space estiver lento, não esperar: pular o fine-tuning e mostrar a captura.

## Perguntas prováveis

- **"ROC-AUC alto não é suspeito?"** Ainda é um dataset sintético com moldes
  compartilhados e uma seed, mesmo sem o teto de 1,0 que o dataset anterior
  tinha. Por isso a análise de prevalência.
- **"CharAE ou HybridAE: qual é melhor?"** Nenhum dos dois estritamente: o
  CharAE tem recall maior (0,9921 contra 0,9808), o HybridAE tem metade do FPR
  (0,0055 contra 0,0109) e generaliza melhor do treino para o teste. A escolha
  depende de priorizar recall ou FPR. Uma seed e um split; o roadmap prevê
  múltiplas seeds para fechar essa comparação.
- **"Funciona em tráfego real?"** Não, e eu medi isso: aplicado aos 2.000 nomes
  mais populares do Tranco, o CharAE sinaliza 1.999 e o HybridAE 1.998 como
  suspeitos. Em um ambiente real o modelo precisa ser adaptado a normais dele
  (a aba de fine-tuning), e a eficácia disso em nomes reais ainda não foi medida.
- **"Por que o dataset não tem nomes reais?"** O gerador aceita o ranking Tranco
  (perfil `normal_tranco`), mas o dataset-v2 foi gerado sem ele; misturá-lo é o
  próximo passo, com anomalias também em TLDs reais para o TLD não virar atalho.
- **"O modelo não está aprendendo algum atalho do gerador?"** Era o caso do
  dataset anterior: 100% das suspeitas terminavam em `.tunnel`, e um controle
  (`results/archive/dataset-v1/suffix_control.csv`) mostrou que acrescentar o
  sufixo a normais levava o FPR a 0,83 (CharAE). O gerador atual não usa
  sufixo fixo — por isso essa auditoria foi feita e por isso o dataset foi
  regenerado.
- **"Por que o tipo DNS não é feature?"** Seria um atalho ("TXT é suspeito") e
  não generaliza. Mudar `A` para `TXT` não altera o score.
- **"O fine-tuning melhora o detector?"** Não sabemos: a validação só escolhe o
  checkpoint e o limiar. Medir exige um teste rotulado independente.
- **"Por que autoencoder e não um classificador?"** Em produção quase não há
  ataques rotulados; aqui os rótulos servem só para avaliar.

## Figuras da apresentação

Não revisei as imagens visualmente: confira a legibilidade no projetor.

| Bloco | Arquivo | Uso |
|---|---|---|
| 2 | `doc/figures/pipeline.png` | fluxo do laboratório à demonstração |
| 3 | `doc/figures/architectures.png` | DenseAE, CharAE e HybridAE |
| 3 | `doc/figures/training.png` | fluxo de treino (opcional) |
| 4 | `results/evaluation/roc-pr.png` | curvas ROC e precisão-recall |
| 4 | `results/evaluation/prevalence.png` | precisão esperada por prevalência |
| 4 | `results/evaluation/fpr-by-profile.png` | FPR por perfil normal (CDN) |
| 4 | `results/evaluation/recall-by-family.png` | recall por família de túnel |
| 4 | `results/autoencoder-hybrid/score-distributions.png` | normais × suspeitas e limiar |
| 5 | `doc/figures/demo.png` | fluxo da demo e do fine-tuning (se não houver rede) |
