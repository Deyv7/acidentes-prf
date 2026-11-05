# Onde e quando os acidentes graves acontecem

Rodovias federais, 2019 a 2025. Todos os números saem de `resultados/fase3_*.csv`, gerados por `src/executar_local.py` a partir de `gold_graves_por_recorte`. O mesmo cálculo roda no Databricks (`notebooks/04_analise.py`), e o resumo bate com o local em todos os recortes (`resultados/fase3_conferencia_databricks.csv`).

## Como ler os números

A medida é a proporção de graves entre os acidentes do recorte. Grave é o acidente com pelo menos um morto ou ferido grave. Como a fonte não tem volume de tráfego, não dá para dizer onde é mais arriscado dirigir: um trecho com muitos acidentes pode só ter muito carro. Os dados respondem a uma pergunta mais estreita: dado que houve um acidente ali, qual a chance de ele ter sido grave?

Cada valor é comparado com a média do seu recorte. "Acima" quer dizer que o intervalo de 95% inteiro está acima da média, e "abaixo", que está inteiro abaixo. Se o intervalo contém a média, o valor é "indistinguível". Valores com menos de 100 acidentes não são comparados (`N_MIN` em `src/analise.py`).

As listas são ordenadas pelo limite inferior do intervalo, e não pela proporção, para que um município com 3 acidentes e 3 graves não fique em primeiro.

Toda comparação foi repetida só entre os acidentes com vítima. Um lugar que registra menos acidentes sem vítima tem uma % de graves maior sem que os seus acidentes sejam mais graves, e entre os acidentes com vítima esse efeito some. Quando o texto diz que um padrão "se mantém", o valor continua do mesmo lado da média nessa segunda conta (`comparacao_com_vitima`).

Na média, 28,0% dos acidentes de 2019 a 2025 foram graves: 132.637 de 473.813 (`fase3_resumo_recortes.csv`, `fase2_recortes_gold.csv`). Entre os acidentes com vítima, 33,7% (`media_recorte_com_vitima` em `fase3_recorte_uf.csv`).

## Ano

A proporção ficou estável: 27,1% em 2019, 27,4% em 2020 e entre 28,1% e 28,5% de 2021 a 2025 (`fase3_recorte_ano.csv`). A diferença entre o menor e o maior ano é pequena perto das diferenças entre lugares e horários, então os sete anos são analisados juntos.

## UF

É o recorte com a maior diferença. No Maranhão, 45,2% dos acidentes foram graves (intervalo de 44,2% a 46,3%), seguido de Pará (40,8%), Piauí (39,8%) e Alagoas (39,3%). No outro extremo estão São Paulo (18,5%), Distrito Federal (18,7%), Rio de Janeiro (21,1%) e Rio Grande do Sul (22,2%). São 18 UFs acima da média, 6 abaixo e 3 indistinguíveis (`fase3_recorte_uf.csv`, `fase3_resumo_recortes.csv`).

O padrão se mantém entre os acidentes com vítima, com 55,3% no Maranhão e 22,2% em São Paulo. Das 24 UFs acima ou abaixo da média, 23 ficam do mesmo lado, então a diferença regional não se explica pelo registro de menos acidentes leves no Nordeste.

O dado não diz o porquê. Hipóteses que não testei: mais pista simples, atendimento médico mais demorado, outra frota (mais motocicletas).

## Hora, dia e fase do dia

As 12 horas entre 18h e 5h estão todas acima da média, e as 12 entre 6h e 17h, todas abaixo. A maior proporção é às 19h (33,5%) e a menor, às 8h (22,5%). Entre os acidentes com vítima, o pico passa para a madrugada: 42,6% às 2h e 42,5% às 3h. As 24 horas ficam do mesmo lado nas duas contas (`fase3_recorte_hora.csv`). Na fase do dia, "Plena Noite" tem 32,4% de graves e "Pleno dia", 24,9% (`fase3_recorte_fase_dia.csv`).

Domingo (30,4%) e sábado (29,8%) estão acima da média, e os cinco dias úteis, abaixo, entre 26,5% e 27,6%. O padrão se mantém entre os acidentes com vítima (`fase3_recorte_dia_semana.csv`).

O mês quase não importa. Oito meses são indistinguíveis da média; o maior é maio (28,8%) e o menor, fevereiro (26,7%) (`fase3_recorte_mes.csv`).

## Via e clima

Na pista simples, 33,3% dos acidentes são graves, contra 23,1% na dupla e 21,5% na múltipla (`fase3_recorte_tipo_pista.csv`). Uma explicação plausível, que não testei: sem separação física, uma invasão da contramão vira colisão frontal.

Com chuva, 23,8% dos acidentes são graves, e com garoa, 22,2%, contra 29,1% com céu claro (`fase3_recorte_condicao_meteorologica.csv`). Isso não diz que a chuva deixa a estrada mais segura, porque sem saber quantos carros rodam na chuva não dá para comparar risco. Diz que os acidentes na chuva são, em proporção, menos graves, talvez porque a velocidade é menor. Não verifiquei essa explicação.

## Tipo de acidente

Atropelamento de pedestre (67,7%) e colisão frontal (62,5%) têm mais que o dobro da média de graves. A colisão frontal também é o tipo com mais mortos em números absolutos, 12.205 de 2019 a 2025 (`fase3_recorte_tipo_acidente.csv`).

A lista de tipos mudou entre janeiro e fevereiro de 2021: "Colisão lateral" foi dividida por sentido, e as colisões com objeto parado e em movimento foram unidas (`fase3_categorias_por_ano.csv`, `fase3_transicao_por_mes.csv`). A análise junta as categorias finas nas amplas (`TIPO_PADRONIZADO` em `src/regras.py`), o que vale para os dois lados da troca.

## Causa

A lista de causas mudou em janeiro de 2021. As causas que só existem na lista antiga somam 4.574 acidentes em dezembro de 2020 e zero em janeiro de 2021 (`fase3_transicao_por_mes.csv`). A lista antiga tinha causas amplas, como "Falta de Atenção à Condução", com 25.030 acidentes em 2019, que a nova divide em causas mais finas, como "Reação tardia ou ineficiente do condutor" e "Ausência de reação do condutor" (`fase3_categorias_por_ano.csv`). Como as duas listas não têm correspondência 1 para 1, a causa só é comparada de 2021 a 2025, e os acidentes de 2019 e 2020 ficam num grupo à parte, fora da comparação.

De 2021 a 2025, as causas com mais graves envolvem pedestre ou contramão (`fase3_recorte_causa_acidente.csv`):

| Causa | Acidentes | % graves | Mortos |
|---|---|---|---|
| Pedestre andava na pista | 3.262 | 75,4 | 1.395 |
| Entrada inopinada do pedestre | 3.327 | 68,7 | 1.009 |
| Pedestre cruzava a pista fora da faixa | 2.868 | 66,5 | 751 |
| Transitar na contramão | 11.146 | 60,2 | 4.163 |
| Ultrapassagem indevida | 8.335 | 46,2 | 1.891 |

"Suicídio (presumido)" tem a maior proporção (81,3%, em 438 acidentes), mas é outro fenômeno.

No álcool do condutor, a conta só com vítimas muda a conclusão. Entre todos os acidentes, a ingestão de álcool pelo condutor tem 20,8% de graves, abaixo da média. Entre os acidentes com vítima tem 35,2%, acima dela. Muitos acidentes com condutor alcoolizado são registrados sem vítima; talvez a polícia seja chamada por causa do crime mesmo quando ninguém se fere, mas não verifiquei. Sem a segunda conta, eu teria concluído que álcool tem menos graves.

## Rodovia, município e trecho

Nestes três recortes há duas listas. A proporção mostra onde um acidente tem mais chance de ser grave; o número de graves mostra onde acontece a maior parte deles.

Entre as BRs, as primeiras na proporção são rodovias curtas do Nordeste e do Norte, com poucas centenas de acidentes. Entre as rodovias grandes, a BR-316 tem 43,7% de graves em 8.111 acidentes, com 1.323 mortos. No número de graves lideram a BR-101 (21.022) e a BR-116 (16.645), ambas com proporção abaixo da média: 25,9% e 23,2% (`fase3_recorte_br.csv`).

Entre os municípios, Timon (MA) lidera a proporção com 61,4%. Entre os 15 primeiros há 7 municípios de Pernambuco, todos no agreste ou no sertão: Sanharó, Pesqueira, Custódia, Caetés, Belo Jardim, Araripina e Lajedo. No número de graves lideram Brasília (1.323) e Curitiba (1.142), com 18,7% e 19,6%, abaixo da média (`fase3_recorte_municipio.csv`). Só 930 dos 2.129 municípios têm 100 acidentes ou mais e entram na comparação (`fase3_resumo_recortes.csv`).

Entre os trechos de 10 km, o primeiro na proporção é MA BR-316 km 610-620, com 57,4% de graves em 136 acidentes, e a BR-232 em Pernambuco aparece três vezes entre os 15 primeiros (km 50-60, 170-180 e 250-260). No número de graves, o primeiro é SC BR-101 km 200-210, com 698 graves e 17,9% de proporção (`fase3_recorte_trecho_10km.csv`). São 1.108 trechos com 100 acidentes ou mais, de 6.682.

Nos três recortes, os lugares com mais acidentes graves em número costumam ter proporção baixa: têm muito tráfego e muitos acidentes de todo tipo. Onde a proporção é alta há menos acidentes, e eles são mais violentos. Uma decisão sobre onde agir precisa olhar as duas listas.

## Limitações

1. Sem volume de tráfego, a proporção de graves mede a gravidade dos acidentes que aconteceram num lugar, e não o risco de dirigir ali.
2. A análise olha um recorte de cada vez. Noite, fim de semana, pista simples e Nordeste podem andar juntos, e ela não separa o efeito de cada um. Isso fica para o modelo, que vai usar `gold_ocorrencias_modelo`.
3. Com 1.108 trechos comparáveis, alguns ficam "acima" da média só por acaso. As listas de trechos e municípios apontam lugares para investigar, e não conclusões sobre cada um.
4. A causa é escolhida pelo policial, uma por acidente, numa lista que mudou em 2021.
5. Só entram os acidentes que a PRF registrou. A conta só com vítimas reduz o efeito de registros diferentes de acidentes leves, mas não o elimina.
