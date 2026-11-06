# Instruções do Copilot — SixEyesDNS

## Contexto do projeto

Este repositório contém o trabalho individual da Unidade III da disciplina
**Aprendizado Profundo 2026.2**, categoria 7 — **Autoencoders para Anomalias e
Ruído**.

O objetivo é detectar tunelamento e exfiltração de dados por DNS. O sistema
deve aprender o comportamento de consultas normais com um autoencoder e usar o
erro de reconstrução para sinalizar consultas suspeitas.

## Entrada, saída e dados

- Converter cada nome de domínio em atributos numéricos:
  - tamanho total do nome;
  - entropia de Shannon dos caracteres;
  - proporção de dígitos;
  - número de rótulos;
  - tamanho do maior rótulo;
  - frequências de caracteres.
- Produzir a pontuação de anomalia, preferencialmente MSE, e o rótulo
  `normal` ou `suspeita` com limiar ajustado na validação.
- Treinar o autoencoder somente com dados normais.
- Usar domínios sintéticos inspirados em serviços, plataformas e instituições
  como dados normais, sempre em zonas reservadas como `.test`.
- Gerar dados anômalos somente por scripts locais, codificando bytes aleatórios
  em subdomínios com base32, hex, base64 e variações.
- Separar treino, validação e teste sem vazamento entre conjuntos, domínios ou
  famílias de exemplos.
- Remover a zona artificial `.test` antes de calcular as features, para evitar
  viés de distribuição quando o modelo receber domínios reais.
- Não usar IP, cliente, perfil de risco ou qualquer metadado de origem como
  entrada do modelo; o objetivo é analisar o domínio.

## Modelos e avaliação

- Implementar o autoencoder principal em PyTorch, com camadas densas pequenas.
- Comparar com um limiar simples de entropia e Isolation Forest.
- Avaliar generalização treinando com um tipo de codificação e testando com
  outro, por exemplo base32 contra hex.
- Reportar precisão, recall, F1, ROC-AUC, matriz de confusão, limiar usado e
  taxa de falsos positivos.
- Mostrar resultados honestos, incluindo falhas, limitações e possíveis casos
  de falso positivo.

## Estrutura preferida

Manter, quando aplicável, esta organização:

```text
SixEyesDNS/
├── README.md
├── requirements.txt
├── data/
│   ├── raw/
│   └── processed/
├── source/
│   ├── process_raw.py
│   └── split_dataset.py
├── scripts/
├── results/
└── docker/
```

O laboratório local usa Docker com `dnsmasq` registrando consultas. A execução
principal do treinamento e da avaliação deve ser feita por arquivos Python e
shell, especialmente no NPAD; Jupyter é opcional.

## Convenções de implementação

- Responder e documentar em português.
- Usar Python 3, tipagem e docstrings curtas.
- Manter nomes de variáveis e funções em inglês.
- Fixar sementes de `random`, `numpy` e `torch` quando o treinamento for
  implementado.
- Configurar scripts por argumentos de linha de comando; não usar caminhos
  absolutos ou fixos no código.
- Preferir soluções simples, legíveis e adequadas ao prazo curto.
- Reutilizar `source/process_raw.py` e a mesma normalização de domínio para
  evitar diferenças entre treino, avaliação e demonstração.
- Antes de sugerir código novo, procurar a estrutura e os helpers existentes.
- Validar mudanças com os testes, linters ou comandos de execução disponíveis.

## Segurança e responsabilidade

- Uso exclusivamente defensivo e educacional.
- O tráfego de tunelamento deve ser sintético, gerado por scripts e mantido no
  ambiente local.
- Não enviar dados para servidores externos nem implementar exfiltração real,
  persistência, evasão ou automação contra terceiros.
- Não incluir credenciais, dados pessoais ou domínios reais sensíveis nos
  exemplos e resultados.
- Citar no `README.md` toda fonte, código ou dataset externo utilizado.
- Sinalizar explicitamente qualquer sugestão que possa causar vazamento entre
  treino e teste.

## Como o Copilot deve ajudar

- Sugerir primeiro a solução mais simples que cumpra o requisito.
- Ao gerar código, respeitar a estrutura acima e explicar brevemente escolhas
  relevantes de modelagem.
- Preservar reprodutibilidade e registrar configurações importantes.
- Ao alterar métricas ou limiares, indicar como a mudança afeta a comparação.
- Não mascarar resultados ruins; ajudar a analisá-los de forma crítica.
