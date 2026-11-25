# Resultados no teste

Teste: 4073 registros, 2703 domínios únicos, prevalência de suspeitas 0.3707. Limiares calibrados somente na validação.

Com essa prevalência, marcar tudo como suspeito já rende precisão 0.3707, recall 1 e F1 0.5409; compare também FPR, ROC-AUC e PR-AUC.

## Teste por registro — limiar P99 dos normais da validação

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC | PR-AUC | Recall a FPR ≤ 1% | Linhas |
|---|---|---|---|---|---|---|---|---|
| Limiar de entropia | 0.9174 | 0.3384 | 0.4944 | 0.0179 | 0.7613 | 0.7479 | 0.2815 | 4073 |
| Isolation Forest | 0.8936 | 0.3225 | 0.4740 | 0.0226 | 0.8116 | 0.7531 | 0.2079 | 4073 |
| AE denso (atributos) | 0.9811 | 0.4477 | 0.6148 | 0.0051 | 0.9492 | 0.9244 | 0.5225 | 4073 |
| AE lexical (caracteres) | 0.9817 | 0.9921 | 0.9868 | 0.0109 | 0.9997 | 0.9995 | 0.9914 | 4073 |
| AE híbrido | 0.9906 | 0.9808 | 0.9857 | 0.0055 | 0.9993 | 0.9990 | 0.9868 | 4073 |

## Teste por registro — limiar melhor F1 da validação

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC | PR-AUC | Recall a FPR ≤ 1% | Linhas |
|---|---|---|---|---|---|---|---|---|
| Limiar de entropia | 0.6012 | 0.6907 | 0.6428 | 0.2700 | 0.7613 | 0.7479 | 0.2815 | 4073 |
| Isolation Forest | 0.6774 | 0.6550 | 0.6660 | 0.1838 | 0.8116 | 0.7531 | 0.2079 | 4073 |
| AE denso (atributos) | 0.8022 | 0.8623 | 0.8312 | 0.1252 | 0.9492 | 0.9244 | 0.5225 | 4073 |
| AE lexical (caracteres) | 0.9993 | 0.9887 | 0.9940 | 0.0004 | 0.9997 | 0.9995 | 0.9914 | 4073 |
| AE híbrido | 0.9906 | 0.9808 | 0.9857 | 0.0055 | 0.9993 | 0.9990 | 0.9868 | 4073 |

## Teste por domínio único — limiar P99 dos normais da validação

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC | PR-AUC | Recall a FPR ≤ 1% | Linhas |
|---|---|---|---|---|---|---|---|---|
| Limiar de entropia | 0.9174 | 0.3386 | 0.4947 | 0.0385 | 0.6922 | 0.7966 | 0.2372 | 2703 |
| Isolation Forest | 0.9365 | 0.3227 | 0.4800 | 0.0276 | 0.8033 | 0.8464 | 0.2054 | 2703 |
| AE denso (atributos) | 0.9811 | 0.4473 | 0.6145 | 0.0109 | 0.9333 | 0.9458 | 0.4361 | 2703 |
| AE lexical (caracteres) | 0.9816 | 0.9920 | 0.9868 | 0.0235 | 0.9994 | 0.9995 | 0.9901 | 2703 |
| AE híbrido | 0.9906 | 0.9808 | 0.9857 | 0.0117 | 0.9986 | 0.9990 | 0.9801 | 2703 |

## Teste por domínio único — limiar melhor F1 da validação

| Sistema | Precisão | Recall | F1 | FPR | ROC-AUC | PR-AUC | Recall a FPR ≤ 1% | Linhas |
|---|---|---|---|---|---|---|---|---|
| Limiar de entropia | 0.6720 | 0.6912 | 0.6815 | 0.4263 | 0.6922 | 0.7966 | 0.2372 | 2703 |
| Isolation Forest | 0.8039 | 0.6547 | 0.7217 | 0.2018 | 0.8033 | 0.8464 | 0.2054 | 2703 |
| AE denso (atributos) | 0.8685 | 0.8622 | 0.8653 | 0.1650 | 0.9333 | 0.9458 | 0.4361 | 2703 |
| AE lexical (caracteres) | 0.9993 | 0.9887 | 0.9940 | 0.0008 | 0.9994 | 0.9995 | 0.9901 | 2703 |
| AE híbrido | 0.9906 | 0.9808 | 0.9857 | 0.0117 | 0.9986 | 0.9990 | 0.9801 | 2703 |

## Quase-duplicatas em relação ao treino

Maior similaridade de Jaccard de trigramas de caracteres com um domínio normal do treino; indica vazamento por molde do gerador, não por domínio idêntico.

| Split | Classe | Domínios | Mediana | P90 | Fração ≥ limiar | Limiar |
|---|---|---|---|---|---|---|
| validation | normal | 1193 | 0.6400 | 0.7638 | 0.0453 | 0.8000 |
| validation | suspeita | 1508 | 0.4062 | 0.7066 | 0.0411 | 0.8000 |
| test | normal | 1194 | 0.6615 | 0.7576 | 0.0310 | 0.8000 |
| test | suspeita | 1509 | 0.4062 | 0.7083 | 0.0477 | 0.8000 |
