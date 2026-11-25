# Fine-tuning com log normal

## Finalidade

A adaptação parte de um checkpoint existente e continua o treino não
supervisionado com consultas consideradas normais. Não é fine-tuning
supervisionado e não ensina classes “normal” e “túnel”. O objetivo é aproximar a
reconstrução dos padrões lexicais de um ambiente específico.

## Regra de segurança do processo

**O arquivo precisa conter somente consultas normais confirmadas.** Se houver
anomalias no log, o autoencoder aprenderá a reconstruí-las e poderá reduzir o
score justamente do comportamento que deveria detectar. A interface exige uma
confirmação explícita antes de iniciar.

## Protocolo implementado

1. Lê dnsmasq, BIND9 ou Unbound e ignora linhas que não são consultas.
2. Normaliza os domínios e deduplica por nome; tipo DNS continua fora das features.
3. Embaralha com seed e separa domínios distintos entre treino e validação.
4. Ajusta um novo `StandardScaler` somente nos domínios de treino.
5. Continua o treino de uma cópia do checkpoint com a mesma perda CE/MSE do modo.
6. Seleciona o melhor estado pela perda de reconstrução da validação.
7. Recalcula médias, desvios e o limiar P99 somente com essa validação.
8. Salva um novo `model.pt`, sem alterar o checkpoint base.

**Tamanho mínimo.** O arquivo precisa ter ao menos 50 domínios normais únicos;
com menos, a adaptação é recusada. Entre 50 e 499 ela roda, mas o relatório e a
interface avisam: com poucos pontos na validação o P99 fica perto do maior
score e o limiar é instável. Com 10 domínios, por exemplo, a validação teria 2.

A separação por domínio impede que o mesmo nome apareça nos dois lados. Isso não
elimina vazamento por moldes semelhantes nem transforma a validação em teste.

## O relatório significa — e o que não significa

O relatório contém quantidades de domínios, histórico de perda, melhor perda de
validação e limiar anterior/novo. `test_metrics` fica nulo intencionalmente: não
existe teste rotulado independente dentro do upload.

**Um limiar menor ou uma perda menor não provam melhora.** Para comparar o modelo
base e o adaptado, use outro conjunto, de outro período quando possível, com
normais e anomalias conhecidas. Reporte FPR, recall, F1 e precisão esperada na
prevalência real antes de adotar o novo checkpoint.

## Interface

Abra `./scripts/demo/gradio.sh`, entre em **Fine-tuning com log normal**, envie o
arquivo (ou clique no exemplo `scripts/demo/normal-example.txt`), marque a
confirmação e escolha épocas, quantidade máxima de consultas e taxa de
aprendizado. O Space limita uploads e executa uma adaptação por vez.
O resultado inclui o gráfico de perda, o relatório JSON e o `model.pt` para
download. Os arquivos gerados no Space são temporários; baixe o checkpoint e o
relatório se quiser preservá-los.

O replay usado apenas para classificar continua disponível no terminal com
`./scripts/demo/demo.sh`, sem participar do treino.
