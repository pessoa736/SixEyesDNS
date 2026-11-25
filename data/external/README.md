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
  grande, um recorte basta. O repositório não baixa nem versiona esse arquivo.
  - **Lista padrão (pública, sem conta):** o ID da lista mais recente sai de
    `https://tranco-list.eu/api/lists/date/latest`, e o recorte do topo de
    `https://tranco-list.eu/download/<ID>/10000` (CSV `rank,domain`, sem
    cabeçalho; remova o `\r` das quebras de linha com `tr -d '\r'`).
  - **Lista filtrada (exige conta gratuita):** o Tranco só permite
    personalizar a lista, por exemplo com o filtro do Google Safe Browsing, a
    usuários logados (<https://tranco-list.eu/configure>); a API de criação
    (`/api/lists/create`) também exige autenticação. Gere a lista, anote o ID e
    baixe-a pelo mesmo endereço `download/<ID>/10000`.
- **Popularidade não é segurança:** o ranking agrega Cisco Umbrella, Majestic,
  Farsight, CrUX e Cloudflare Radar por 30 dias, mas os próprios autores
  mostram que rankings podem ser manipulados e oferecem filtros contra domínios
  maliciosos. Os 2.000 primeiros nomes são os mais conhecidos; o fim de um
  recorte maior parece ter nomes mais obscuros (observação minha, sem
  verificação) e não passou por nenhum filtro de segurança. O recorte
  inclui sites adultos (por exemplo, domínios sob o TLD `.xxx`); decida se
  quer filtrá-los antes de versionar um dataset derivado, que carregaria esses
  nomes como texto.
- **Não há co-acesso:** o ranking lista domínios isolados e não diz quais são
  acessados juntos na mesma sessão.

### Lista usada

| Campo | Valor |
|---|---|
| Lista | Tranco padrão (diária), ID `JZW4Y`, 24/11/2026 |
| Janela | 26/10/2026 a 24/11/2026 (30 dias) |
| Provedores | CrUX, Farsight, Majestic, Cloudflare Radar, Cisco Umbrella |
| Filtros | nenhum de segurança (`filterPLD` ligado: só domínios registrados) |
| Recorte | `data/external/tranco_top.csv`: ranks 1 a 10.000; 9.998 nomes válidos |
| Uso | **ainda não usado no dataset**: o dataset-v2 foi gerado sem o arquivo |

Para citar: V. Le Pochat, T. Van Goethem, S. Tajalizadehkhoob, M. Korczyński e
W. Joosen, *Tranco: A Research-Oriented Top Sites Ranking Hardened Against
Manipulation* (NDSS 2019), e o ID da lista acima. Os provedores têm licenças
próprias (incluindo CC BY-NC e CC BY-SA); por isso o arquivo não é versionado.

### Medição com nomes reais

Antes de misturar a lista ao dataset, `python -m source.external_check` aplica
os três checkpoints ao recorte como se fosse tráfego normal e grava só
contagens em `results/evaluation/external_check.csv`. Com o dataset-v2, dos
2.000 primeiros nomes o CharAE sinaliza 1.999, o HybridAE 1.998 e o DenseAE
1.218 (60,9%), contra 28 de 1.194 (2,3%), 14 (1,2%) e 13 (1,1%) dos domínios
normais do teste; trocar o TLD real por uma zona do laboratório os deixa em
95,8%, 88,1% e 25,9%. Os ranks 2.001 a 4.000 dão o mesmo padrão
(`--skip 2000`). Ou seja, o laboratório sozinho não ensina o que é um nome
normal fora dele.

**Cuidado ao misturar:** acrescentar só normais com TLD real cria um atalho (o
TLD passaria a separar as classes, como o `.tunnel` do dataset-v1). O gerador
precisa emitir anomalias também sob TLDs reais, e a avaliação deve usar nomes
que ele nunca viu (`--skip` igual ao `TRANCO_LIMIT`).
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
