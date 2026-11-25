# Instruções do Copilot — SixEyesDNS

## Contexto e fonte de verdade

Este é o trabalho individual da Unidade III de **Aprendizado Profundo 2026.2**,
categoria 7, sobre autoencoders para detecção de anomalias e ruído. Os
requisitos da disciplina estão em [doc/info/Descricao_do_Trabalho.md](../doc/info/Descricao_do_Trabalho.md).
O texto entregue deve ficar no README ou em PDF versionado; não invente métricas.

Antes de alterar código, leia a implementação e os dados versionados. A
estrutura real usa `source/`, `docker/generator/` e `docker-compose.yml`; não
presuma que existam `src/`, `configs/` ou `source.generate_data`.

## Estado confirmado dos dados

- `data/processed/dataset.csv` (dataset-v2, 24/11/2026) tem 20.000 linhas e
  59 colunas.
- O schema atual tem `query`, 6 escalares, 36 frequências de caracteres,
  7 indicadores de tipo DNS, 4 indicadores de família e os metadados
  `query_type`, `family`, `profile`, `label` e `seed`.
- A parte lexical contém 42 atributos: tamanho, entropia, razão de dígitos,
  quantidade de rótulos, maior rótulo, razão alfanumérica e 36 frequências.
- `query` já é normalizada e não contém `.test`.
- O gerador (`docker/generator/traffic_profiles.py`) produz anomalias **sem
  sufixo fixo**: a zona do túnel imita a infraestrutura normal (70%) ou usa
  uma zona própria (30%). O dataset-v2 usa `QUERY_COUNT=20000`,
  `ANOMALY_RATE=0.15` e `SEED=42` (padrões do `docker-compose.yml`).
- Os splits atuais não compartilham domínios entre si. O summary detalha
  domínios por split, classe e família (`data/processed/splits/summary.json`).
- O alinhamento (`source/process_raw.py`) casa por servidor-alvo, IP do
  gerador, janela de tempo e `(query, tipo)`; o relatório fica em
  `data/processed/alignment.json`. O dataset-v1 (9.911 linhas, anomalias
  sempre em `.tunnel`) fica no histórico do git.

## Regras de dados e modelos

- O autoencoder deve treinar somente com exemplos `normal`; `label`, `family`,
  `query_type`, `seed`, IP e cliente são metadados, nunca features.
- A única fonte da verdade para normalização e atributos deve ser reutilizada
  por processamento, treino, avaliação e demo. Remova `.test` antes das
  features.
- Toda lista de features deve ser explícita e acompanhada de uma verificação
  que rejeite metadados. Não use padrões como “todas as colunas menos label”.
- Use apenas tráfego sintético e local em zonas `.test`; anomalias são strings
  codificadas geradas pelo laboratório.
- Preserve splits sem interseção de domínios e falhe explicitamente em caso de
  sobreposição ou casamento ambíguo de rótulos.
- Fixe seed 42. O treino roda na GPU por padrão (`--device auto`) e cai para a
  CPU automaticamente quando não há GPU disponível; a CPU também é um caminho
  suportado quando forçada com `--device cpu`.
- Compare autoencoder com limiar de entropia e Isolation Forest. Calibre
  limiares somente na validação e reporte precisão, recall, F1, ROC-AUC,
  matriz de confusão, FPR e limitações.

## Estrutura e convenções

- Responda e documente em português; use nomes de variáveis e funções em inglês.
- Use Python 3, tipagem, docstrings curtas e módulos executáveis com
  `python -m source.<modulo>`.
- Use argumentos de CLI e caminhos relativos; hiperparâmetros devem ficar em
  configurações versionadas quando aplicável.
- Use `random`, NumPy e PyTorch de forma determinística quando possível.
- Prefira mudanças simples, legíveis e compatíveis com o código existente.
- Antes de criar helper, procure reutilização em `source/` e scripts existentes.
- Valide com os menores testes relevantes; não alegue que Docker ou a porta
  `127.0.0.1:6767` funcionam sem testar.
- Trabalhe na branch atual do repositório (verifique com `git branch`; não
  presuma `ajustes-u3`, já mergeada), sem push ou force-push. Preserve
  alterações não relacionadas e faça commits por fase, com prefixos `feat:`,
  `fix:`, `docs:`, `data:` ou `refactor:`, quando o usuário solicitar
  implementação.

## Segurança e documentação

- O uso é exclusivamente defensivo e educacional. Não implemente exfiltração
  real, persistência, evasão ou automação contra terceiros.
- Não inclua credenciais, dados pessoais ou domínios reais sensíveis.
- Cite somente fontes, bibliotecas e datasets realmente usados.
- Números no README devem vir de arquivos gerados em `results/`; antes disso,
  use `TODO(resultados)`.
- Registre explicitamente riscos de vazamento entre treino e teste, falsos
  positivos, limitações e decisões que dependam do usuário.
