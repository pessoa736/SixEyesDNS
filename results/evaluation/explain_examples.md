# Exemplos explicados — AE híbrido

Limiar P99 da validação: 4.4130. Domínios sintéticos sem o sufixo `.test`.

## Verdadeiros positivos de maior score

- `xy4wxxemcnajq.tunnel` (base32): score 192.77; atributos: char_freq_x=2007.08, char_freq_q=190.39, char_freq_o=7.10; caracteres: '4'@2=28.73, 'x'@4=23.30, 'x'@5=23.24
- `4fuhvfcxqv_lbxxu_xdgiw.tunnel` (base64): score 155.42; atributos: char_freq_x=1583.50, char_freq_q=88.22, char_freq_f=12.31; caracteres: 'f'@1=29.30, 'b'@12=25.19, '_'@10=24.73
- `c3btxupeo26xgluzx8hxea.tunnel` (base64): score 150.75; atributos: char_freq_x=1604.75, char_freq_u=5.97, alphanumeric_ratio=4.81; caracteres: '2'@9=34.63, 'l'@13=29.03, '3'@1=29.02
- `txhtqmxi5q-26.tunnel` (mixed): score 132.27; atributos: char_freq_x=1121.80, char_freq_q=313.04, char_freq_6=7.58; caracteres: '5'@8=25.06, '2'@11=24.80, 'x'@6=23.40
- `qkxtzadqtrxuw.tunnel` (base32): score 131.77; atributos: char_freq_x=1116.60, char_freq_q=315.31, char_freq_t=5.82; caracteres: 'z'@4=23.79, 'w'@12=21.96, 'q'@7=21.40

## Falsos positivos (limiar P99)

- `f4bfff32c5.cdn.brisa` (normal_hard): score 6.82; atributos: char_freq_f=67.89, char_freq_8=3.56, char_freq_6=3.46; caracteres: 'b'@2=3.71, '4'@1=3.32, '2'@7=3.24
- `552499598c.cdn.lumen` (normal_hard): score 5.88; atributos: char_freq_9=35.22, char_freq_5=28.07, char_freq_6=4.58; caracteres: '8'@8=3.19, '2'@2=3.00, '5'@1=2.74
- `93ca696868.cdn.cobalto` (normal_hard): score 5.68; atributos: char_freq_6=34.50, char_freq_8=10.99, char_freq_9=10.21; caracteres: 'a'@3=3.76, '9'@0=3.60, '9'@5=3.30
- `c1a6486862.cdn.nuvem` (normal_hard): score 5.43; atributos: char_freq_6=39.51, char_freq_8=12.67, char_freq_f=4.43; caracteres: '1'@1=3.25, '6'@6=3.20, 'a'@2=3.03
- `4a333356cf.cdn.lumen` (normal_hard): score 5.41; atributos: char_freq_3=58.18, char_freq_8=3.84, char_freq_9=2.35; caracteres: '3'@5=3.27, '3'@4=3.02, '4'@0=2.45

## Falsos negativos de menor score (limiar P99)

Nenhum caso no teste.
