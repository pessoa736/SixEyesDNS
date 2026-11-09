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
- [x] Confirmar funcionamento da porta `127.0.0.1:6767` com uma ferramenta DNS
      disponível (consulta crua UDP/TCP; no Docker Desktop foi preciso ligar o
      dnsmasq à rede de borda `lab-edge`, pois portas de containers presos só
      à rede interna não chegam ao host).

## Fase 1 — Estrutura e schema

Status: implementada; modelos retreinados sem os indicadores de tipo DNS.

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

## Fase 2 — Dados

Status: laboratório, dataset sintético e alinhamento logs-rótulos
implementados; a regeneração do dataset versionado depende de decisão.

- [x] Corrigir o alinhamento entre logs e rótulos e documentar o tratamento de
      execuções concatenadas e duplicatas (`source/process_raw.py`: casa por
      servidor-alvo, IP do gerador, janela de tempo e `(query, tipo)`; falha em
      rótulos concatenados ou conflitantes; relatório em `alignment.json`).
- [x] Alinhar README, compose e scripts quanto a `QUERY_COUNT`,
      `ANOMALY_RATE` e `SEED`.
- [ ] Decidir se o dataset versionado será regenerado; se sim, fazer isso em
      commit separado. **Decisão do autor:** o alinhamento novo gera 10.000
      linhas em vez de 9.911 (as 89 que faltam são normais), mas os splits com
      seed 42 mudam, o que invalida os checkpoints atuais e a release
      `hybrid-v1`; regenerar exige retreinar os três modelos (viável com a
      GPU) e reavaliar.
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

## Fase 3 — Modelos, treino e avaliação

Status: treino lexical, semântico (DenseAE) e híbrido, baselines e avaliação
completa implementados; faltam a regeneração do dataset (decisão do autor) e a
diversificação dos normais difíceis.

- [x] Implementar `DenseAE` para 42 atributos e score MSE (modo `semantic`).
- [x] Implementar submodelo lexical independente com tokens, convoluções e
      reconstrução de caracteres.
- [x] Implementar `HybridAutoencoder` com score combinado CE/MSE.
- [x] Implementar `source/train.py` com seed 42, Adam e treino somente com
      exemplos normais; CPU como caminho de referência e GPU opcional
      (`--device auto`: NVIDIA/CUDA ou AMD/ROCm, com fallback para CPU).
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
      falsos positivos por domínio (híbrido no teste atual: 7 domínios
      `normal_hard` parecidos com hashes de CDN no limiar P99).
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
- [ ] Diversificar os perfis normais difíceis e avaliar famílias não vistas
      para reduzir o FPR do lexical/híbrido no teste. Parcial: o
      leave-one-family-out já avalia famílias omitidas da calibração e o
      gerador ganhou normais temáticos e a fonte Tranco opcional; reduzir o FPR
      do híbrido (7 domínios `normal_hard` no teste) exige regenerar o dataset
      e retreinar, o que depende da decisão da Fase 2.

## Fase 4 — Demonstração

Status: dashboard pronto; demo do modelo pendente.

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
- [x] Adicionar scripts de teste para pytest, checkpoint e geração de plots.

## Fase 5 — Relatório e apresentação

Status: documentação inicial concluída; consolidação final pendente.

- [ ] Organizar o README com Introdução, Desenvolvimento/Técnicas, Resultados,
      Reprodução, Segurança/Ética e Referências.
- [ ] Incluir somente números gerados e verificáveis; usar
      `TODO(resultados)` enquanto faltarem.
- [ ] Incluir pipeline e arquitetura híbrida em Mermaid.
- [ ] Criar mapa Mermaid do fluxo de desenvolvimento (fases, branches e
      commits por fase).
- [ ] Criar mapa Mermaid do fluxo de treinamento (dados, features, modos
      lexical/semântico/híbrido, checkpoints e gráficos).
- [ ] Criar mapa Mermaid da estrutura de classes (modelos, encoders,
      decoders e relações entre os módulos de `source/`).
- [ ] Criar mapa Mermaid do fluxo de execução (processamento, split, treino,
      avaliação e demo, de ponta a ponta).
- [ ] Criar mapa Mermaid dos casos de uso (atores, laboratório local, treino,
      avaliação, demonstração e apresentação).
- [ ] Criar `docs/roteiro-apresentacao.md` para 10 minutos:
      introdução 1,5; pipeline 2; modelos 2; resultados 3; demo 1,5.
- [ ] Listar as figuras necessárias para a apresentação.
- [ ] Atualizar referências apenas para fontes realmente utilizadas.
- [x] Versionar os resultados gráficos dos treinamentos lexical, semântico e
      híbrido produzidos localmente.
- [ ] Sugerir, sem executar, os comandos `gh repo edit` e criação da tag
      `entrega-u3` no dia da entrega.

## Critérios de aceitação

- [x] `./scripts/data/process-data.sh` roda do zero e falha em caso de
      interseção (verificado com os logs reais, saída fora de `data/processed/`;
      `split_dataset` verifica a interseção em tempo de execução).
- [x] `python -m source.train --mode lexical|semantic|hybrid` roda em CPU em
      poucos minutos com o dataset versionado (100 épocas do híbrido: 121 s).
- [x] `python -m source.evaluate` roda em CPU no dataset mínimo e no dataset
      versionado.
- [x] `pytest` passa.
- [x] Nenhuma feature usa `label`, `family`, `query_type`, `seed`, IP ou
      cliente.
- [x] O README não contém métricas inventadas (as tabelas de resultados foram
      conferidas célula a célula contra `results/evaluation/metrics.csv`).
- [ ] O texto cobre introdução, técnicas, resultados, análise crítica e
      conclusões.
- [ ] A demo funciona ao vivo ou em replay offline.

## Ordem de execução

1. Corrigir estrutura e schema restantes.
2. Corrigir e documentar o alinhamento dos dados.
3. Implementar `DenseAE`, scoring, baselines e avaliação completa.
4. Executar a suíte de testes no ambiente AMD/CPU configurado.
5. Implementar a demonstração offline/local.
6. Consolidar README, roteiro, métricas e figuras.
7. Fazer revisão final antes da apresentação e do prazo do texto.
