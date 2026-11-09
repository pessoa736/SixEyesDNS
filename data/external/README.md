# Fontes externas opcionais

Este diretório guarda arquivos locais que o gerador de consultas pode usar de
forma opcional. Somente este README é versionado: o `.gitignore` ignora todo o
resto (`data/external/*`), e nenhum dataset externo deve ser commitado.

## `tranco_top.csv` (opcional)

Ranking local de domínios populares, usado para criar consultas **normais** com
nomes mais próximos de tráfego real (perfil `normal_tranco`). O objetivo é
medir falsos positivos em domínios fora do padrão sintético do laboratório.

- **Caminho:** `data/external/tranco_top.csv`. O `docker-compose.yml` o monta
  somente leitura em `/external/tranco_top.csv` no container `generator`.
- **Formato:** uma linha `rank,domain` por registro, **sem cabeçalho**, em
  ordem de rank. Exemplo:

  ```text
  1,exemplo-um.com
  2,exemplo-dois.org
  3,sub.exemplo-tres.net
  ```

- **Obtenção:** baixe manualmente a lista no site do Tranco
  (<https://tranco-list.eu>) e salve-a nesse formato. Como a lista completa é
  grande, um recorte basta, por exemplo
  `head -n 10000 <arquivo-baixado>.csv > data/external/tranco_top.csv`. O
  repositório não baixa nem versiona esse arquivo.
- **Citação:** se o arquivo for usado em experimentos, cite a fonte (Tranco,
  <https://tranco-list.eu>), a data ou o identificador da lista baixada e os
  valores de `TRANCO_LIMIT` e `TRANCO_RATE` no relatório.

### Como o gerador usa o arquivo

1. Ao iniciar, o gerador lê até `TRANCO_LIMIT` domínios (padrão `2000`),
   normaliza para minúsculas, remove o ponto final e descarta linhas inválidas
   (rank não numérico, caracteres fora de `a-z`, `0-9`, `-` e `.`, partes do
   nome entre pontos que começam ou terminam com `-`), duplicados e nomes com
   mais de 48 caracteres. A ordem de rank é preservada.
2. Uma fração aproximada de `TRANCO_RATE` (padrão `0.15`) das consultas normais
   que não são `PTR` passa a usar um desses domínios. A decisão e a escolha do
   domínio são determinísticas, calculadas por hash de `(SEED, índice da
   consulta)`, e **não consomem** o gerador pseudoaleatório principal: tipos,
   servidores e anomalias continuam exatamente os mesmos.
3. O nome consultado é `<domínio>.test`, com `profile=normal_tranco`,
   `family=normal` e `label=normal`. O nome real é só texto dentro do
   laboratório: a zona `.test` é resolvida localmente e nenhuma consulta sai
   para a Internet. Consultas reversas continuam usando `reverse_name`.

### Fallback interno

Se o arquivo não existir, o perfil `normal_tranco` fica desligado e o gerador
usa apenas os perfis internos; a saída é idêntica à de uma execução sem esta
funcionalidade. Se o arquivo existir mas nenhuma linha for válida, o perfil
também fica desligado e o gerador apenas avisa com uma linha `tranco_aviso=...`
no log.

As variáveis podem ser definidas no ambiente ao subir o laboratório:

```bash
TRANCO_RATE=0.2 TRANCO_LIMIT=5000 ./scripts/lab/docker-run.sh
```

Os domínios do Tranco entram no dataset como mais um perfil normal; depois de
usá-los, processe os dados novamente (`./scripts/data/process-data.sh`) e
retreine os modelos.
