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
2. **Dados:** logs alinhados aos rótulos, 9.911 registros e 6.924 domínios
   únicos. O treino usa só os 3.482 registros normais do split de treino; a
   validação e o teste têm normais e suspeitas.
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
para reconstruir deveria ajudar a achar suspeitas. Os dados atuais não mostram
isso. Os 42 atributos são calculados do próprio domínio, então o ramo numérico
recebe a mesma informação, reorganizada, e o CharAE já separa tudo. Para
testar de verdade seria preciso um dataset mais difícil e informação que não
derive do nome. Isso está no [roadmap](../roadmap.md), na Fase 6.

## 4. Resultados e análise crítica (3 min)

Mostrar a tabela do README (teste por registro, limiar P99):

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Entropia | 0.9838 | 0.1873 | 0.3147 | 0.0107 | 0.6712 |
| Isolation Forest | 0.9840 | 0.4513 | 0.6188 | 0.0254 | 0.9396 |
| DenseAE | 0.9986 | 0.5592 | 0.7169 | 0.0027 | 0.9901 |
| CharAE | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 |
| HybridAE | 0.9973 | 1.0000 | 0.9987 | 0.0093 | 1.0000 |

Pontos a falar:

- Os autoencoders de caracteres superam os baselines por uma margem grande.
- O CharAE não erra no teste. O HybridAE acha as mesmas 2.595 suspeitas, mas
  sinaliza **7 domínios normais** (`normal_hard`, parecidos com hashes de CDN).
  Portanto o híbrido **não** é "o melhor modelo".
- **Prevalência** (`results/evaluation/prevalence.png`): o teste tem 77,6% de
  suspeitas. Com recall 1 e FPR 0,0093, a precisão esperada do híbrido cai para
  **0,5194 com 1%** de suspeitas e **0,0967 com 0,1%**. F1 alto não basta.

Análise crítica, sem esconder:

- ROC-AUC 1 num dataset sintético **não** prova eficácia em tráfego real. Os
  splits não repetem domínios, mas os normais compartilham moldes com o treino
  (mediana de similaridade 0,64 contra 0,06 das suspeitas).
- Uma seed e um split, sem intervalo de confiança.
- **Atalho no gerador:** 100% das suspeitas terminam em `.tunnel` e nenhum
  normal contém `tunnel`. O controle (`results/evaluation/suffix_control.csv`)
  mostra que o sufixo não é necessário (recall do CharAE e do híbrido segue em
  1,0000 com sufixo normal), mas é suficiente: acrescentá-lo a normais do teste
  leva o FPR do CharAE a 0,8341 e o do híbrido a 0,4773. O detector reage a
  qualquer trecho nunca visto no treino.
- A família `low_entropy` do gerador produz só **8 domínios únicos** em 989
  linhas; o recall dela não tem poder estatístico.
- O modelo não vê a resposta DNS nem prova exfiltração.

Fechamento: a aplicação responsável hoje é **priorização para análise
humana**. O próximo passo é regenerar um dataset mais variado e realista e
comparar CharAE e híbrido com várias seeds.

## 5. Demonstração no Space (1,5 min)

Valores medidos em CPU em 24/11/2026 com o checkpoint híbrido (limiar P99 de
4,4130). No Space podem variar nas últimas casas.

**Aba "Testar modelo" (cerca de 1 min):**

| Domínio | Esperado | Score |
|---|---|---:|
| `staging.api.orbita.test` | normal | −1,359 |
| `aaj4pccnvdeac.tunnel.test` | suspeita | 7,553 |
| `7c2a488f471558ea9c7d162f.tunnel.test` | suspeita | 16,336 |
| `f4bfff32c5.cdn.brisa.test` | **suspeita (falso positivo conhecido)** | 6,821 |

- Mostrar o mapa de erro por caractere. No túnel o erro cobre o payload **e** o
  sufixo `tunnel` (que nunca aparece em normais); no falso positivo da CDN só
  o hash acende e o resto fica em zero.
- Parar no último exemplo: é um hash de CDN legítimo e ilustra a análise
  crítica.
- Opcional, digitando na caixa: `aaj4pccnvdeac.api.orbita.test`, o mesmo
  payload com sufixo de serviço normal. Em 24/11/2026 o híbrido deu suspeita
  (score 8,7 contra limiar 4,41): o detector não depende do sufixo `.tunnel`.
- Trocar para **DenseAE** e mostrar que não há mapa por caractere (ele só
  reconstrói atributos).

**Aba "Fine-tuning com log normal" (cerca de 0,5 min):** clicar no exemplo
`normal-example.txt` (600 domínios normais únicos), marcar a confirmação e
adaptar. A interface mostra 400 domínios no treino e 100 na validação, e o
limiar P99 muda. Dizer em voz alta: a validação do fine-tuning **não é teste**;
um log com túnel ensinaria o modelo a reconstruir o túnel.

Se o Space estiver lento, não esperar: pular o fine-tuning e mostrar a captura.

## Perguntas prováveis

- **"ROC-AUC 1 não é suspeito?"** É, e o README diz isso: dataset sintético,
  moldes compartilhados, uma seed. Por isso a análise de prevalência.
- **"Por que defender o híbrido se o CharAE é melhor?"** A hipótese era mais
  informação, mas os atributos derivam do domínio. Está testada só em um
  dataset de teto; o roadmap prevê um dataset mais difícil e várias seeds.
- **"Funciona em tráfego real?"** Não foi testado. Só há laboratório sintético.
- **"O modelo não está só aprendendo o sufixo `.tunnel`?"** O gerador marca
  todas as suspeitas com ele, então a dúvida é justa. Trocando o sufixo por um
  de aparência normal o recall não cai (CharAE e híbrido, 1,0000). Mas o
  inverso também vale: pôr `.tunnel` em um normal já o torna suspeito. O
  detector é, em parte, um detector de novidade.
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
