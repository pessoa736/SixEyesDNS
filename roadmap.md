# Roadmap do SixEyesDNS

## Objetivo e prazo

Concluir o projeto individual da Unidade III de **Aprendizado Profundo
2026.2**, categoria **Autoencoders para Anomalias e Ruído**.

- apresentação presencial: 08, 10 ou 15/12/2026;
- texto no repositório: 15/12/2026;
- demonstração offline ou local como entrega central da apresentação.

O requisito acadêmico está em
[doc/info/Descricao_do_Trabalho.md](doc/info/Descricao_do_Trabalho.md).

## Diagnóstico concluído

- [x] Confirmar que o repositório usa `source/`, não `src/`.
- [x] Localizar o gerador em `docker/generator/gerador_queries.py`.
- [x] Confirmar que o dataset versionado possui 50.000 registros.
- [x] Regenerar o dataset limpo com 10.000 consultas do laboratório ampliado.
- [x] Confirmar 42 atributos lexicais e 58 colunas no schema atual.
- [x] Confirmar que `.test` é removido da coluna de domínio processada.
- [x] Confirmar ausência de interseção de domínios entre os splits atuais.
- [x] Identificar somente 126 domínios normais únicos no gerador atual.
- [x] Identificar log concatenado: 60.000 consultas para 50.000 rótulos.
- [x] Identificar que o casamento atual usa domínio e tipo, sem timestamp.
- [x] Planejar e implementar serviços fictícios, Nginx e dashboard local.
- [x] Ampliar famílias sintéticas e perfis normais difíceis sem tráfego externo.
- [ ] Confirmar funcionamento da porta `127.0.0.1:6767` com uma ferramenta DNS
      disponível.

## Fase 1 — Estrutura e schema

Status: pendente.

- [ ] Trabalhar na branch `ajustes-u3`.
- [ ] Adicionar `source/__init__.py`.
- [ ] Consolidar em `source/features.py` a normalização, tokenização, vocabulário
      e os 42 atributos numéricos.
- [ ] Separar explicitamente features e metadados.
- [ ] Rejeitar automaticamente `label`, `family`, `query_type`, `seed`, IP e
      cliente na matriz de entrada.
- [ ] Fazer `process_raw.py` e `split_dataset.py` funcionarem com
      `python -m source.<modulo>`.
- [ ] Adicionar `--holdout-family`.
- [ ] Expandir `summary.json` com linhas e domínios únicos por split, classe e
      família.
- [ ] Adicionar testes de determinismo, ausência de metadados e ausência de
      interseção.
- [ ] Mover `VL.py` para `scripts/check_env.py`.
- [ ] Fixar dependências e incluir pytest, scikit-learn e matplotlib quando
      realmente usados.

## Fase 2 — Dados

Status: diagnóstico concluído; implementação pendente.

- [ ] Corrigir o alinhamento entre logs e rótulos e documentar o tratamento de
      execuções concatenadas e duplicatas.
- [ ] Alinhar README, compose e scripts quanto a `QUERY_COUNT`,
      `ANOMALY_RATE` e `SEED`.
- [ ] Decidir se o dataset versionado será regenerado; se sim, fazer isso em
      commit separado.
- [ ] Adicionar fonte opcional local `data/external/tranco_top.csv`, ignorada
      pelo Git, com fallback interno.
- [x] Adicionar normais difíceis com subdomínios semelhantes a hashes de CDN.
- [x] Adicionar anomalias de baixa entropia, labels curtos e codificações mistas.
- [x] Registrar sequência, timestamp UTC, serviço e perfil no arquivo de
      rótulos para auditoria sem usá-los como features.
- [x] Adicionar Nginx, API fictícia e dashboard local de coleta.
- [x] Adicionar aplicações backend sintéticas e telemetria de requisições.
- [ ] Garantir que o tráfego continue sintético, local e em `.test`.

## Fase 3 — Modelos, treino e avaliação

Status: implementação pendente; não há métricas finais.

- [ ] Implementar `DenseAE` para 42 atributos e score MSE.
- [ ] Implementar `CharAE` com tokens, convoluções e perda CE ignorando PAD.
- [ ] Implementar `HybridAE` com score combinado CE/MSE.
- [ ] Implementar `source/train.py` com seed 42, CPU, Adam, early stopping e
      treino somente com normais.
- [x] Combinar no treinamento o erro lexical CE e o MSE numérico por
      `z(CE) + lambda*z(MSE)`, com `lambda` configurável.
- [ ] Salvar artefatos completos: modelo, scaler, vocabulário, configuração,
      limiares e curva de perda.
- [ ] Implementar `source/scoring.py` com limiar P99 e melhor F1 calibrados
      somente na validação.
- [ ] Implementar baselines de entropia e Isolation Forest.
- [ ] Implementar `source/evaluate.py` com métricas, figuras, prevalência,
      recall a FPR de 1% e recall por família.
- [ ] Avaliar leave-one-family-out sem escolher limiar no teste.
- [ ] Adicionar explicabilidade por atributo e por caractere.
- [ ] Testar shapes, parâmetros, treino de uma época e avaliação em dataset
      mínimo.
- [ ] Gerar tabela de ablação em `results/`.

## Fase 4 — Demonstração

Status: pendente; entrega central.

- [ ] Criar `source/demo.py` usando a mesma normalização e features do treino.
- [ ] Criar `scripts/demo.sh`.
- [ ] Implementar modo ao vivo para log do dnsmasq quando a conectividade for
      confirmada.
- [ ] Implementar `--replay <log>` para apresentação sem Docker.
- [ ] Exibir score, classificação e mapa de erro por caractere.
- [ ] Documentar a alternativa dentro da rede Docker se a porta do host não
      funcionar.
- [x] Disponibilizar dashboard local em `http://127.0.0.1:8080`.
- [x] Monitorar aplicações, serviços, rotas, erros e latência no dashboard.
- [x] Adicionar gráficos visuais de famílias DNS, aplicações e serviços.
- [x] Simular navegação orgânica somente em sites sintéticos `.test`, com
      sessões, pesos, pausas e telemetria por site.

## Fase 5 — Relatório e apresentação

Status: diagnóstico documental concluído; consolidação pendente.

- [ ] Organizar o README com Introdução, Desenvolvimento/Técnicas, Resultados,
      Reprodução, Segurança/Ética e Referências.
- [ ] Incluir somente números gerados e verificáveis; usar
      `TODO(resultados)` enquanto faltarem.
- [ ] Incluir pipeline e arquitetura híbrida em Mermaid.
- [ ] Criar `docs/roteiro-apresentacao.md` para 10 minutos:
      introdução 1,5; pipeline 2; modelos 2; resultados 3; demo 1,5.
- [ ] Listar as figuras necessárias para a apresentação.
- [ ] Atualizar referências apenas para fontes realmente utilizadas.
- [ ] Sugerir, sem executar, os comandos `gh repo edit` e criação da tag
      `entrega-u3` no dia da entrega.

## Critérios de aceitação

- [ ] `./scripts/process-data.sh` roda do zero e falha em caso de interseção.
- [ ] `python -m source.train --model dense|char|hybrid` roda em CPU em poucos
      minutos com o dataset versionado.
- [ ] `python -m source.evaluate` roda em CPU no dataset mínimo e no dataset
      versionado.
- [ ] `pytest` passa.
- [ ] Nenhuma feature usa `label`, `family`, `query_type`, `seed`, IP ou
      cliente.
- [ ] O README não contém métricas inventadas.
- [ ] O texto cobre introdução, técnicas, resultados, análise crítica e
      conclusões.
- [ ] A demo funciona ao vivo ou em replay offline.

## Ordem de execução

1. Corrigir estrutura e schema.
2. Corrigir e documentar os dados.
3. Implementar modelos, treino e avaliação.
4. Implementar a demonstração offline/local.
5. Executar testes e gerar resultados.
6. Consolidar README, roteiro e figuras.
7. Fazer revisão final antes da apresentação e do prazo do texto.
