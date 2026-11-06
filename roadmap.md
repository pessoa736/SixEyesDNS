# Roadmap do SixEyesDNS

## Estado atual

O projeto está na fase de fundação. O script `create-envs.sh` já cria o ambiente Python com PyTorch, NumPy, pandas, scikit-learn e ferramentas auxiliares. O arquivo `VL.py` verifica as versões instaladas e a disponibilidade de CPU/GPU.

Ainda precisam ser implementados os módulos de geração de dados, extração de atributos, treinamento, avaliação e demonstração com Docker.

## Objetivo

Construir um sistema defensivo e educacional para detectar consultas DNS suspeitas usando um autoencoder treinado somente com consultas normais. A classificação será baseada no erro de reconstrução, com comparação contra métodos baseline.

## Fase 1 — Estrutura e configuração

Criar a estrutura inicial:

```text
data/raw/
data/processed/
results/
src/
scripts/
configs/
requirements.txt
environment.yml
```

Implementar:

- configuração por argumentos de linha de comando;
- sementes fixas para `random`, NumPy e PyTorch;
- registro das configurações e dos resultados dos experimentos;
- ambiente Conda reproduzível para execução no supercomputador;
- instruções completas de instalação e execução no `README.md`.

**Validação:** executar um diagnóstico básico e registrar versões, dispositivo disponível e semente utilizada.

## Fase 2 — Geração e organização dos dados

Criar `src/generate_data.py` para gerar dados sintéticos exclusivamente no ambiente local:

- domínios normais;
- subdomínios com codificação base32;
- codificação hexadecimal;
- codificação base64;
- variações de tamanho, entropia e ruído.

Separar os dados em:

- treino: somente domínios normais;
- validação: domínios normais e anômalos;
- teste: famílias e domínios não vistos durante o treinamento.

**Regra crítica:** o mesmo domínio, payload ou família de exemplos não pode aparecer em mais de uma divisão.

**Validação:** gerar um relatório com a quantidade de exemplos, famílias presentes e interseções entre treino, validação e teste.

## Fase 3 — Engenharia de atributos

Criar `src/features.py` com uma função única e reutilizável para extrair:

- tamanho total do domínio;
- entropia de Shannon dos caracteres;
- proporção de dígitos;
- número de rótulos;
- tamanho do maior rótulo;
- frequências de caracteres;
- atributos derivados, se forem necessários.

A normalização deve ser ajustada somente usando o conjunto de treino.

Adicionar testes para:

- domínios curtos;
- domínios longos;
- domínios com dígitos;
- caracteres repetidos;
- entradas inválidas ou vazias.

**Validação:** confirmar que treino, avaliação e demonstração usam exatamente a mesma função de extração.

## Fase 4 — Modelo principal

Criar `src/models.py` com um autoencoder denso pequeno em PyTorch:

- camada de entrada compatível com os atributos;
- espaço latente reduzido;
- reconstrução da entrada;
- cálculo do erro MSE;
- salvamento do modelo e dos parâmetros de normalização.

Criar `src/train.py` para:

- treinar somente com dados normais;
- registrar a perda de treino e validação;
- definir o limiar usando o conjunto de validação;
- salvar o modelo, o limiar e a configuração do experimento.

**Validação:** verificar se o erro médio de reconstrução dos exemplos normais é menor que o erro dos exemplos anômalos.

## Fase 5 — Baselines

Criar `src/baselines.py` e comparar o autoencoder com:

1. limiar simples baseado em entropia;
2. Isolation Forest;
3. autoencoder principal.

Todos os métodos devem usar as mesmas divisões de dados e, quando aplicável, os mesmos atributos.

**Validação:** gerar uma tabela comparativa com precisão, recall, F1, ROC-AUC e taxa de falsos positivos.

## Fase 6 — Avaliação e generalização

Criar `src/evaluate.py` para produzir:

- matriz de confusão;
- precisão;
- recall;
- F1;
- ROC-AUC;
- taxa de falsos positivos;
- limiar utilizado;
- distribuição dos erros de reconstrução.

Executar o experimento de generalização:

- treinar com uma codificação, por exemplo base32;
- testar com outra, por exemplo hexadecimal;
- comparar com o cenário em que todas as famílias aparecem no treinamento.

**Validação:** registrar explicitamente falhas, falsos positivos e tipos de domínio que não foram detectados.

## Fase 7 — Execução no supercomputador

Adaptar o projeto para execução não interativa no NPAD:

- criar `environment.yml` com as dependências gerais do projeto;
- manter a instalação do PyTorch compatível com o hardware e os módulos
  disponibilizados pelo supercomputador;
- criar scripts em `scripts/` para preparar dados, treinar, avaliar e executar
  experimentos;
- aceitar caminhos, sementes, épocas, batch size e parâmetros por argumentos de
  linha de comando ou arquivos em `configs/`;
- salvar modelos, métricas, logs e configurações em `results/`;
- criar um script de submissão `.sh` compatível com o agendador disponível no
  NPAD;
- registrar o commit, a configuração e a semente de cada execução.

O fluxo principal deve usar arquivos Python:

```bash
conda env create -f environment.yml
conda activate sixeyesdns
python -m src.generate_data --config configs/data.json
python -m src.train --config configs/train.json
python -m src.evaluate --config configs/evaluate.json
```

O notebook deixa de ser requisito do projeto. Jupyter pode ser usado apenas
como interface opcional para inspeção de resultados e gráficos, inclusive por
meio de uma porta encaminhada no NPAD.

**Validação:** executar um experimento completo via shell, sem abrir notebook,
e confirmar que os artefatos foram salvos em `results/`.

## Fase 8 — Demonstração local opcional

Docker não deve ser uma dependência do treinamento nem da avaliação. Se for
possível e útil no ambiente local, criar:

```text
docker/
├── Dockerfile
├── docker-compose.yml
└── dnsmasq.conf
```

Implementar `src/demo.py` para uso local, quando houver acesso ao log do
dnsmasq:

- ler o log do dnsmasq;
- extrair novos domínios;
- calcular os atributos;
- calcular a pontuação de anomalia;
- classificar como `normal` ou `suspeita`;
- exibir a pontuação e o horário da consulta.

O tráfego anômalo deve ser sintético e gerado somente por scripts locais.

**Validação:** executar a demonstração local sem alterar o pipeline principal.
Se Docker não estiver disponível no NPAD, isso não deve impedir os experimentos.

## Fase 9 — Relatório final

Documentar:

- objetivo e metodologia;
- arquitetura do autoencoder;
- origem e geração dos dados;
- regras de separação dos conjuntos;
- atributos utilizados;
- escolha do limiar;
- comparação com os baselines;
- resultado do teste de generalização;
- limitações e falsos positivos;
- instruções completas para reproduzir os experimentos.

Toda fonte, código ou dataset externo utilizado deve ser citado no `README.md`.

## Ordem recomendada

1. Criar a estrutura e as configurações.
2. Implementar a geração dos dados.
3. Implementar os atributos e os testes.
4. Treinar o primeiro autoencoder.
5. Adicionar avaliação e baselines.
6. Executar o experimento de generalização.
7. Validar a execução via Conda e shell no NPAD.
8. Adicionar a demonstração local opcional.
9. Consolidar os resultados no README e no relatório.

## Primeiro marco

O primeiro marco do projeto é:

> Gerar um dataset sintético sem vazamento, extrair os atributos e treinar um autoencoder capaz de separar consultas normais de uma família anômala, com métricas reproduzíveis.

Esse marco deve ser concluído antes da demonstração local opcional, pois estabelece a base experimental do projeto.

## Critérios de conclusão

- [ ] Ambiente reproduzível e documentado.
- [ ] Dados sintéticos gerados localmente.
- [ ] Separação entre treino, validação e teste sem vazamento.
- [ ] Extração de atributos coberta por testes.
- [ ] Autoencoder treinado somente com dados normais.
- [ ] Limiar definido usando validação.
- [ ] Comparação com entropia e Isolation Forest.
- [ ] Métricas e matriz de confusão salvas.
- [ ] Generalização entre diferentes codificações avaliada.
- [ ] Execução completa via Conda e shell funcionando no NPAD.
- [ ] Demonstração local com dnsmasq documentada, caso seja viável.
- [ ] Limitações e resultados negativos documentados.
