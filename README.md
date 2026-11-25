

# SixEyesDNS

**Detecção de Anomalias em Consultas DNS com Autoencoders para Identificação de
Tunelamento e Exfiltração de Dados**

Davi dos Santos Passos · Aprendizado Profundo 2026.2, Unidade III · categoria
*Autoencoders para Anomalias e Ruído* · [requisitos](doc/info/Descricao_do_Trabalho.md)
· [roteiro](doc/roteiro-apresentacao.md) · [roadmap](roadmap.md)

## 1. Introdução

Tunelamento DNS esconde dados em nomes de domínio (subdomínios longos em base32,
hex ou base64) e aproveita que o DNS quase sempre atravessa o firewall. Como há
poucos ataques rotulados, o projeto aprende como é o tráfego **normal**: um
autoencoder treinado só com consultas normais usa o **erro de reconstrução** como
score de anomalia. O modelo vê somente o **nome** da consulta (IP, cliente, rótulo
e tipo DNS não são features) e o tráfego é sintético, local e `.test`. O score
serve para **priorizar análise humana**, não para bloquear.

## 2. Desenvolvimento e técnicas

### 2.1 Laboratório e dados

![Pipeline do projeto](doc/figures/pipeline.png)

Um gerador consulta dnsmasq, BIND9 e Unbound em Docker; os logs são alinhados aos
rótulos (`source/process_raw.py`) e divididos em treino, validação e teste **sem
domínio repetido entre eles**. O dataset-v2 (24/11/2026) tem 20.000 registros e
10.971 domínios únicos, com 15% de suspeitas (37,1% no teste) em sete famílias
(`base32`, `hex`, `base64`, `mixed`, `low_entropy`, `dictionary`, `short`) **sem
sufixo fixo**. O dataset anterior tinha todas as suspeitas em `.tunnel`, um atalho
medido e removido ([roadmap](roadmap.md)). Mais em [doc/laboratorio.md](doc/laboratorio.md).

### 2.2 Modelos e treino

![Arquiteturas comparadas](doc/figures/architectures.png)

Entrada: 64 caracteres e 42 atributos lexicais; espaço latente de 16 dimensões.
**DenseAE** reconstrói os atributos (score = MSE); **CharAE** reconstrói a
sequência (entropia cruzada); **HybridAE** combina os dois, `z(CE) + λ·z(MSE)` com λ = 1.
Baselines: entropia de Shannon e Isolation Forest. Treino com Adam, seed 42, só
com normais, máscara e ruído na entrada e early stopping; o limiar é o **P99 dos
normais da validação** e o teste nunca o escolhe ([doc/arquitetura.md](doc/arquitetura.md)).

### 2.3 Nomes reais: o ranking Tranco

O vocabulário do gerador é fechado (serviços e organizações fictícios). O gerador
aceita um recorte local do [ranking Tranco](https://tranco-list.eu/)
(`data/external/`, fora do Git): até 2.000 domínios entram em 15% das consultas
normais como `<domínio>.test` (perfil `normal_tranco`). O Tranco mede
**popularidade, não segurança**, e não diz quais domínios são acessados juntos. A
lista de 24/11/2026 (ID `JZW4Y`) foi baixada, mas **o dataset-v2 foi gerado sem
ela**. `python -m source.external_check` trata os 2.000 primeiros nomes como
normais e mede a fração sinalizada (P99, por domínio único):

| Sistema | normais do teste | top-2000 Tranco | mesmos nomes, TLD do laboratório |
|---|---:|---:|---:|
| CharAE | 2,3% | 99,95% | 95,8% |
| HybridAE | 1,2% | 99,9% | 88,1% |
| DenseAE | 1,1% | 60,9% | 25,9% |

Trocar o TLD real ajuda pouco nos autoencoders de caracteres: o problema é
sobretudo o vocabulário. Misturar o Tranco é o próximo passo, e as anomalias também precisam usar TLDs reais, senão o TLD separa
as classes (o erro do `.tunnel`). Fonte e filtros: [data/external/README.md](data/external/README.md).

### 2.4 Demonstração

`./scripts/demo/gradio.sh` abre uma interface para classificar um domínio (com
mapa de erro por caractere) e para **adaptar** o modelo a um log normal do próprio
ambiente. Publicação no Space: [doc/demonstracao.md](doc/demonstracao.md).

## 3. Resultados

Teste por registro, limiar P99 ([`metrics.csv`](results/evaluation/metrics.csv)):

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Entropia | 0.9174 | 0.3384 | 0.4944 | 0.0179 | 0.7613 |
| Isolation Forest | 0.8936 | 0.3225 | 0.4740 | 0.0226 | 0.8116 |
| DenseAE | 0.9811 | 0.4477 | 0.6148 | 0.0051 | 0.9492 |
| CharAE | 0.9817 | 0.9921 | 0.9868 | 0.0109 | 0.9997 |
| HybridAE | 0.9906 | 0.9808 | 0.9857 | 0.0055 | 0.9993 |

Os autoencoders de caracteres superam os baselines e se separam: o **CharAE tem
mais recall** (0,9921 contra 0,9808); o **HybridAE tem metade do FPR** (14 falsos
positivos contra 28, todos hashes de CDN) e generaliza melhor (FPR teste/treino de
0,76× contra 3,02×, [`overfitting.csv`](results/evaluation/overfitting.csv)).
Nenhum é estritamente melhor. O teste tem 37,1% de suspeitas, muito acima do
tráfego real: com 1% de suspeitas a precisão esperada do HybridAE cai para 0,64 e,
com 0,1%, para 0,15. Demais tabelas: [`summary.md`](results/evaluation/summary.md).

## 4. Análise crítica

- **Nomes reais (medido):** o detector sinaliza 99,9% a 99,95% dos nomes populares
  do Tranco (seção 2.3), o que indica que decorou o vocabulário do laboratório e,
  sem adaptação ao ambiente, não serve para tráfego real. Não medi ainda se o
  fine-tuning resolve.
- **Dataset sintético, uma seed, um split:** sem intervalo de confiança; os splits
  compartilham os moldes do gerador.
- **Falsos positivos:** hashes legítimos de CDN parecem payloads
  (`6222f8b896.cdn.nuvem`); com ataques raros, a maioria dos alertas seria falsa.
- **Fine-tuning:** um log contaminado ensina o modelo a reconstruir o túnel.
- **Escopo lexical:** não vê resposta, volume nem tempo e não prova exfiltração.

## 5. Conclusões

1. CharAE e HybridAE superam os baselines e nenhum é estritamente melhor
   ([hipótese do híbrido](roadmap.md#hipótese-do-híbrido)). Limiar e prevalência
   pesam tanto quanto a arquitetura.
2. Os dois controles (`.tunnel` e Tranco) indicam um detector de novidade: o que é
   "normal" vem inteiro dos dados de treino.
3. Uso responsável hoje: priorizar análise humana num ambiente conhecido, depois
   de adaptar o modelo ([aplicações e limites](doc/aplicacoes.md)). Próximos
   passos: Tranco com anomalias de TLD real, várias seeds e medir a adaptação.

## Como reproduzir

```bash
conda env create -f environment.yml && conda activate sixeyesdns
./scripts/model/train-hybrid.sh        # e train-lexical.sh, train-semantic.sh
./scripts/evaluate/evaluate.sh
python -m source.external_check        # exige data/external/tranco_top.csv
python -m pytest -q
```

Dados: [doc/laboratorio.md](doc/laboratorio.md). Figuras: `python -m source.doc_figures`.

### Treino em GPU

`--device auto` (padrão) usa GPU NVIDIA (CUDA) ou AMD (ROCm) quando o PyTorch a
enxerga e cai para CPU; `DEVICE=cpu` dá execução determinística. O `torch` do PyPI
é a build CUDA: em GPU AMD instale a ROCm
(`pip install torch --index-url https://download.pytorch.org/whl/rocm7.2`).
Treinos longos aquecem a GPU: acompanhe a temperatura.

## Segurança e ética

Tráfego apenas local, sintético e `.test`; nenhuma exfiltração real. Sem
credenciais, dados pessoais nem datasets externos no Git (o Tranco fica fora). Logs
DNS são sensíveis e o score não autoriza bloqueio automático.

## Referências

- V. Le Pochat, T. Van Goethem, S. Tajalizadehkhoob, M. Korczyński e W. Joosen,
  [*Tranco: A Research-Oriented Top Sites Ranking Hardened Against
  Manipulation*](https://tranco-list.eu/assets/tranco-ndss19.pdf), NDSS 2019;
  lista usada: ID `JZW4Y`, 24/11/2026.
- [PyTorch](https://pytorch.org/), [scikit-learn](https://scikit-learn.org/),
  [NumPy](https://numpy.org/), [Matplotlib](https://matplotlib.org/) e
  [Gradio](https://www.gradio.app/); laboratório com
  [Dnsmasq](http://thekelleys.org.uk/dnsmasq/), [BIND9](https://www.isc.org/bind/),
  [Unbound](https://nlnetlabs.nl/projects/unbound/) e [Kea](https://kea.isc.org/).
