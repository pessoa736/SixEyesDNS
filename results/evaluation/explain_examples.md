# Exemplos explicados — AE híbrido

Limiar P99 da validação: 5.7159. Domínios sintéticos sem o sufixo `.test`.

## Verdadeiros positivos de maior score

- `qqqqqqqqqqqqqqqqqqqqq.catalog.nuvem` (low_entropy): score 588.78; atributos: char_freq_q=5598.60, entropy=19.94, alphanumeric_ratio=8.03; caracteres: 'l'@26=22.80, 'o'@27=16.68, 'q'@20=16.26
- `qqqqqqqqqqqq.updatehub` (low_entropy): score 462.38; atributos: char_freq_q=4429.68, entropy=19.84, alphanumeric_ratio=8.60; caracteres: 'p'@14=13.79, 'h'@19=11.20, 'a'@16=11.15
- `zzzzzzzzzzzzzzzzzzzzzz.br-south.api.atlas` (low_entropy): score 222.38; atributos: char_freq_z=1927.15, char_freq_x=19.58, entropy=8.00; caracteres: 'p'@33=19.15, '.'@35=18.70, 'i'@34=18.07
- `zzzzzzzzzzzzzzzzzzzzzz.br-south.web.brisa` (low_entropy): score 220.88; atributos: char_freq_z=1922.34, char_freq_x=19.67, entropy=7.97; caracteres: 'w'@32=20.38, '.'@35=18.68, '.'@31=17.08
- `qqqqqqqqqqqqqqq.us-east.dashboard.orbita` (low_entropy): score 176.14; atributos: char_freq_q=1538.13, entropy=6.19, char_freq_c=3.96; caracteres: 'h'@27=18.15, 'u'@16=17.10, 's'@17=16.55

## Falsos positivos (limiar P99)

- `f4bfff32c5.cdn.brisa` (normal_hard): score 8.57; atributos: char_freq_f=63.00, char_freq_4=2.48, char_freq_6=2.37; caracteres: 'f'@0=3.17, '4'@1=2.98, 'b'@2=2.79
- `6563f83586.cdn.pulsar` (normal_hard): score 8.26; atributos: char_freq_6=34.00, char_freq_5=9.63, char_freq_3=9.47; caracteres: '8'@8=3.36, 'f'@4=3.13, '6'@2=2.82
- `6222f8b896.cdn.nuvem` (normal_hard): score 7.41; atributos: char_freq_2=29.63, char_freq_6=13.63, char_freq_8=8.38; caracteres: 'b'@6=3.63, 'f'@4=3.20, '2'@2=3.01
- `dmss6vwj5m5lm5.cdn.atlas` (normal_hard): score 7.32; atributos: char_freq_5=27.91, char_freq_m=8.22, char_freq_s=1.75; caracteres: 's'@2=3.97, '5'@8=3.55, 'm'@9=3.53
- `d5de5o4gx54qy6.cdn.orbita` (normal_hard): score 6.63; atributos: char_freq_5=24.49, char_freq_4=7.44, char_freq_q=2.60; caracteres: 'd'@2=4.04, 'o'@5=3.88, '4'@10=3.73

## Falsos negativos de menor score (limiar P99)

- `wcjpaba.sa-east.dashboard.pulsar` (short): score 1.48; atributos: char_freq_a=2.22, char_freq_p=1.29, char_freq_w=1.24; caracteres: 'j'@2=10.88, 'a'@6=8.99, 'w'@0=5.74
- `rr3au7se.br-south.dashboard.lumen` (short): score 2.19; atributos: char_freq_r=2.62, char_freq_3=1.41, label_count=1.09; caracteres: '3'@2=10.12, '7'@5=8.35, 'u'@4=7.01
- `t7ioums7.us-west.dashboard.nuvem` (short): score 2.31; atributos: char_freq_7=5.33, char_freq_s=1.26, label_count=0.97; caracteres: '7'@1=5.91, 't'@0=5.53, 'm'@5=5.40
- `mppyfmq.br-south.dashboard.orbita` (short): score 3.98; atributos: char_freq_q=13.72, char_freq_m=2.36, char_freq_f=2.10; caracteres: 'f'@4=9.10, 'm'@5=8.26, 'p'@2=7.36
- `p6dcydi.us-west.dashboard.pulsar` (short): score 3.99; atributos: char_freq_d=4.80, char_freq_6=2.46, char_freq_y=2.16; caracteres: '6'@1=12.76, 'y'@4=11.54, 'd'@2=10.40
