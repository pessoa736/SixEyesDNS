# Aplicações reais e limites de implantação

## O que o detector realmente observa

O SixEyesDNS calcula um score de anomalia a partir do **nome do domínio** da
consulta. Ele aprende a reconstruir padrões lexicais de domínios normais e usa o
erro de reconstrução para priorizar nomes fora desse padrão. Não inspeciona o
conteúdo da resposta, não descriptografa túneis e não prova que existe
exfiltração.

O tipo DNS, o IP e o cliente ficam de fora das features. Isso evita que o modelo
aprenda atalhos como “TXT é suspeito”. Em uma implantação real, esses metadados
ainda podem ser úteis para filtragem e investigação pelo analista, mas não
entram no score sem uma decisão nova de modelagem e uma reavaliação completa.

## Aplicações viáveis

### 1. Triagem de telemetria em um SOC

Logs de dnsmasq, BIND9 ou Unbound podem ser pontuados em lote e ordenados pelo
score. O analista investiga primeiro os casos mais anômalos e combina o resultado
com destino, processo origem, ativo, horário e outras evidências.

**Valor real:** reduzir a fila de consultas que merecem revisão humana.
**Condição:** o alerta não deve virar bloqueio automático sem validação local.

### 2. Baseline lexical de uma rede conhecida

Uma organização pode adaptar o autoencoder com consultas normais confirmadas do
seu próprio ambiente. O modelo passa a representar os padrões internos, nomes de
serviços e CDNs usados naquela rede, em vez dos domínios sintéticos do projeto.

**Valor real:** detectar mudanças de padrão e domínios que fogem da baseline.
**Condição:** tráfego de adaptação limpo, validação independente e monitoramento
de drift quando a infraestrutura mudar.

**Medido (24/11/2026):** sem essa adaptação o detector não serve fora do
laboratório. Aplicado aos 2.000 nomes mais populares do ranking Tranco, tratados
como normais, o CharAE sinaliza 1.999, o HybridAE 1.998 e o DenseAE 1.218
(`python -m source.external_check`). A adaptação é, portanto, condição e não
opção; sua eficácia em nomes reais ainda não foi medida.

### 3. Detector auxiliar em gateway ou resolvedor interno

Os checkpoints são pequenos e a inferência roda em CPU. Um resolvedor ou gateway
pode pontuar consultas e exportar score, domínio normalizado e erro por posição
para outro sistema de observabilidade.

**Valor real:** sinal adicional de baixo custo para investigação.
**Condição:** a coleta precisa acontecer em um ponto que veja os nomes das
consultas. Em tráfego DoH/DoT observado apenas na rede, sem acesso ao resolvedor,
os domínios podem não estar visíveis.

### 4. Pesquisa e ensino de segurança em DNS

O laboratório permite reproduzir famílias sintéticas, medir FPR, estudar falsos
positivos e comparar representações lexicais, numéricas e híbridas sem gerar
tráfego contra terceiros.

**Valor real:** benchmark controlado e explicação do mecanismo de autoencoders.
**Limite:** desempenho no laboratório não é evidência de desempenho em produção.

### 5. Enriquecimento de alertas, não fonte única de verdade

O score pode ser anexado a eventos de Zeek, Suricata, SIEM ou ferramentas de DNS
firewall como mais um sinal. O calor por caractere ajuda o analista a entender
por que uma string foi considerada incomum.

**Valor real:** explicabilidade e priorização complementar.
**Condição:** integração por logs/API própria; o projeto ainda não é um plugin
desses produtos.

## Onde ele não resolve o problema

- tunelamento ou C2 que use um domínio lexicalmente comum;
- exfiltração concentrada na resposta DNS, fora do nome consultado;
- tráfego direto por IP ou protocolos que não geram as consultas observadas;
- distinção confiável entre hashes legítimos de CDN e payloads semelhantes;
- bloqueio automático em redes com prevalência muito baixa de ataques sem uma
  medição local de falsos positivos;
- conclusões sobre tráfego criptografado quando o nome do domínio não está
  disponível no ponto de coleta.

## Pipeline recomendado para uma prova de conceito real

1. Coletar logs normais representativos de vários dias e tipos de ativos.
2. Separar um teste independente, com incidentes conhecidos e normais de outro
   período, antes de qualquer adaptação.
3. Adaptar o modelo somente aos normais de treino e calibrar o limiar pela meta
   operacional de FPR, não apenas pelo F1.
4. Medir precisão na prevalência esperada do ambiente e FPR por perfil de ativo.
5. Publicar primeiro em modo somente leitura, com revisão humana e versionamento
   do checkpoint, scaler e limiar.
6. Monitorar drift e repetir a avaliação antes de cada nova adaptação.

## Privacidade e governança

Consultas DNS revelam interesses e comportamento de usuários. Uma implantação
real precisa de política de retenção, controle de acesso, minimização dos logs e
avaliação das obrigações legais aplicáveis. O checkpoint também pode memorizar
padrões dos nomes usados no treino e deve receber o mesmo controle de acesso dos
dados de origem.
