# Resultados no teste

Teste: 3344 registros, 2438 domínios únicos, prevalência de suspeitas 0.7760. Limiares calibrados somente na validação.

Com essa prevalência, marcar tudo como suspeito já rende precisão 0.7760, recall 1 e F1 0.8739; compare também FPR, ROC-AUC e PR-AUC.

## Teste por registro — limiar P99 dos normais da validação

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC | PR-AUC | Recall a FPR ≤ 1% | Linhas |
|---|---|---|---|---|---|---|---|---|
| Limiar de entropia | 0.9838 | 0.1873 | 0.3147 | 0.0107 | 0.6712 | 0.8977 | 0.1464 | 3344 |
| Isolation Forest | 0.9840 | 0.4513 | 0.6188 | 0.0254 | 0.9396 | 0.9784 | 0.3730 | 3344 |
| AE denso (atributos) | 0.9986 | 0.5592 | 0.7169 | 0.0027 | 0.9901 | 0.9966 | 0.7368 | 3344 |
| AE lexical (caracteres) | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 3344 |
| AE híbrido | 0.9973 | 1.0000 | 0.9987 | 0.0093 | 1.0000 | 1.0000 | 1.0000 | 3344 |

## Teste por registro — limiar melhor F1 da validação

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC | PR-AUC | Recall a FPR ≤ 1% | Linhas |
|---|---|---|---|---|---|---|---|---|
| Limiar de entropia | 0.7600 | 0.8605 | 0.8072 | 0.9413 | 0.6712 | 0.8977 | 0.1464 | 3344 |
| Isolation Forest | 0.9357 | 0.9869 | 0.9606 | 0.2350 | 0.9396 | 0.9784 | 0.3730 | 3344 |
| AE denso (atributos) | 0.9774 | 0.9842 | 0.9808 | 0.0788 | 0.9901 | 0.9966 | 0.7368 | 3344 |
| AE lexical (caracteres) | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 3344 |
| AE híbrido | 0.9996 | 1.0000 | 0.9998 | 0.0013 | 1.0000 | 1.0000 | 1.0000 | 3344 |

## Teste por domínio único — limiar P99 dos normais da validação

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC | PR-AUC | Recall a FPR ≤ 1% | Linhas |
|---|---|---|---|---|---|---|---|---|
| Limiar de entropia | 0.9838 | 0.2432 | 0.3900 | 0.0182 | 0.7880 | 0.9424 | 0.1807 | 2438 |
| Isolation Forest | 0.9932 | 0.5861 | 0.7372 | 0.0182 | 0.9582 | 0.9895 | 0.5125 | 2438 |
| AE denso (atributos) | 0.9982 | 0.5470 | 0.7068 | 0.0045 | 0.9820 | 0.9955 | 0.6667 | 2438 |
| AE lexical (caracteres) | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 2438 |
| AE híbrido | 0.9965 | 1.0000 | 0.9983 | 0.0159 | 1.0000 | 1.0000 | 1.0000 | 2438 |

## Teste por domínio único — limiar melhor F1 da validação

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC | PR-AUC | Recall a FPR ≤ 1% | Linhas |
|---|---|---|---|---|---|---|---|---|
| Limiar de entropia | 0.8219 | 0.9980 | 0.9014 | 0.9818 | 0.7880 | 0.9424 | 0.1807 | 2438 |
| Isolation Forest | 0.9379 | 0.9830 | 0.9599 | 0.2955 | 0.9582 | 0.9895 | 0.5125 | 2438 |
| AE denso (atributos) | 0.9712 | 0.9795 | 0.9753 | 0.1318 | 0.9820 | 0.9955 | 0.6667 | 2438 |
| AE lexical (caracteres) | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 2438 |
| AE híbrido | 0.9995 | 1.0000 | 0.9997 | 0.0023 | 1.0000 | 1.0000 | 1.0000 | 2438 |

## Quase-duplicatas em relação ao treino

Maior similaridade de Jaccard de trigramas de caracteres com um domínio normal do treino; indica vazamento por molde do gerador, não por domínio idêntico.

| Split | Classe | Domínios | Mediana | P90 | Fração ≥ limiar | Limiar |
|---|---|---|---|---|---|---|
| validation | normal | 439 | 0.6364 | 0.7500 | 0.0319 | 0.8000 |
| validation | suspeita | 1998 | 0.0556 | 0.1176 | 0.0000 | 0.8000 |
| test | normal | 440 | 0.6364 | 0.7500 | 0.0364 | 0.8000 |
| test | suspeita | 1998 | 0.0556 | 0.1176 | 0.0000 | 0.8000 |
