# Validação da fonte

Validação feita em 04/11/2026 com `python -I src/validar_fonte.py --dados <pasta> --saida resultados`. O script lê os ZIPs direto, sem extrair, e usa só a biblioteca padrão do Python. Todo número deste documento está em um arquivo de `resultados/` com prefixo `fase0_`. Rodar o script duas vezes gera os mesmos arquivos.

## Fonte

Os dados são os boletins de acidente da Polícia Rodoviária Federal, publicados na página [Dados abertos da PRF](https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf). Cada ano vem num ZIP com um CSV dentro, hospedado no Google Drive, em três versões:

| Versão | Grão | Anos |
|---|---|---|
| Agrupados por ocorrência (`datatran<ano>.csv`) | um acidente por linha | 2007 a 2026 |
| Agrupados por pessoa (`acidentes<ano>.csv`) | uma pessoa envolvida por linha | 2007 a 2026 |
| Por pessoa, todas as causas e tipos | uma pessoa por causa e tipo | 2017 a 2026 |

No [dados.gov.br](https://dados.gov.br), o conjunto aparece como **"SINISTROS DE TRÂNSITO - PRF"**, com dois recursos. Cada recurso é uma pasta do Google Drive com um ZIP por ano, de 2007 a 2026:

| Recurso | Pasta no Drive | Arquivos |
|---|---|---|
| Agrupados por ocorrência | `1eI64p7H7LRc-wWDnwjIdYmYbWurMbwbT` | `datatran2007.zip` … `datatran2026.zip` |
| Agrupados por pessoa | `1p46CseT7BcPvbk_TeTSf4L3Sc3_RmUpi` | `acidentes2007.zip` … `acidentes2026.zip` (o de 2016 se chama `acidentes2016_atual.zip`) |

Conferi os 11 arquivos baixados nesta fase: os IDs de Drive são os mesmos listados nessas pastas. Ou seja, o portal e a página da PRF apontam para os mesmos arquivos. Na Fase 1, a ingestão vai usar as pastas como lista dos anos disponíveis. O portal também tem "Sistema BR-Brasil - Boletins de Ocorrências em Rodovias Federais", atualizado em 22/12/2017, que é o sistema antigo e fica fora do recorte.

A página do dicionário diz que o sistema BR-Brasil foi usado de 2007 a 2016 e que o sistema BAT é usado desde 2017. O projeto usa **2017 em diante**, só com dados do BAT, para não misturar dois sistemas de registro.

Arquivos baixados (fora do repositório, em `C:\Users\Deyvid-PC\dados-prf\bruto\`), com SHA-256 em `fase0_perfil_<ano>.json`:

| Arquivo | ZIP (bytes) | CSV (bytes) | Data do CSV no ZIP | Linhas |
|---|---|---|---|---|
| ocorrência 2017 | 4.248.009 | 24.887.945 | 2024-09-27 | 89.567 |
| ocorrência 2018 | 3.294.461 | 19.481.431 | 2024-09-27 | 69.333 |
| ocorrência 2019 | 3.237.669 | 19.101.686 | 2024-09-27 | 67.558 |
| ocorrência 2020 | 3.075.980 | 18.042.979 | 2024-09-27 | 63.585 |
| ocorrência 2021 | 3.217.660 | 18.675.025 | 2024-09-27 | 64.567 |
| ocorrência 2022 | 3.227.721 | 18.723.306 | 2024-08-15 | 64.606 |
| ocorrência 2023 | 3.397.281 | 19.770.946 | 2024-08-15 | 67.766 |
| ocorrência 2024 | 3.783.609 | 21.365.616 | 2026-09-23 | 73.202 |
| ocorrência 2025 | 3.727.148 | 21.143.436 | 2026-03-18 | 72.529 |
| ocorrência 2026 | 2.818.326 | 15.992.292 | 2026-10-27 | 54.895 |
| pessoa 2025 | 9.349.289 | 72.881.148 | 2026-03-18 | 194.629 |

O ano de 2026 está incompleto: as datas vão de 2026-01-01 a 2026-09-30 (`fase0_resumo_por_ano.csv`). A PRF republica os arquivos de anos anteriores (o de 2017 tem data de 2024 e o de 2024 foi refeito em setembro de 2026), então o SHA-256 é o que garante que dá para reproduzir com o mesmo arquivo.

## Licença

No dados.gov.br, o campo de licença do conjunto "SINISTROS DE TRÂNSITO - PRF" indica uso gratuito. Consultei pelo navegador em 04/11/2026, porque a API do portal exige login. Por isso o projeto usa os dados e cita a fonte (veja "Referência dos dados" no fim deste documento). Outras informações sobre o uso:

- o rodapé da página da PRF e da página do dicionário diz "Creative Commons Atribuição-SemDerivações 3.0 Não Adaptada". Esse texto vale para o conteúdo do site e não fala dos arquivos de dados;
- o Plano de Dados Abertos da PRF 2022–2024 diz que os dados são publicados "sob licença aberta que permita sua livre utilização, consumo ou cruzamento, limitando-se a creditar a autoria ou a fonte".

Cuidados adotados: citar a PRF como fonte, **não versionar nem redistribuir os CSVs originais** (quem quiser os arquivos baixa direto da fonte) e publicar só tabelas derivadas e agregados.

## Formato

O formato é igual nos dez anos analisados (2017 a 2026) (`fase0_perfil_<ano>.json`):

| Item | Valor |
|---|---|
| Codificação | latin-1. Não é UTF-8 válido, não tem BOM e não tem bytes 0x80–0x9F, então latin-1 e cp1252 dão o mesmo texto |
| Separador | `;` |
| Aspas | texto entre aspas duplas, números sem aspas |
| Decimal | vírgula (`km`, `latitude`, `longitude`), por exemplo `-28,5071196` |
| Fim de linha | CRLF |
| Nulo | `NA` sem aspas |
| Data | `data_inversa` em `AAAA-MM-DD` |
| Hora | `horario` em `HH:MM:SS` |
| Linhas com número errado de campos | 0 |

O `tracado_via` pode ter vários valores separados por `;` dentro das aspas, por exemplo `"Reta;Declive"`. Isso acontece em 5.526 linhas de 2017, 7.568 de 2022, 16.550 de 2023 e 18.741 de 2025 (`linhas_tracado_via_multivalor`). O salto entre 2022 e 2023 sugere uma mudança no preenchimento desse campo. Por isso o traçado vai ser comparado entre anos com cuidado. Com um leitor de CSV que respeite as aspas, o campo não quebra a linha.

## Colunas

O arquivo por ocorrência tem 30 colunas, **com o mesmo nome e a mesma ordem em todos os anos de 2017 a 2026** (`fase0_layout_por_ano.csv`).

Tipos inferidos em 2025 (`fase0_colunas_2025.csv`):

| Grupo | Colunas | Tipo no arquivo |
|---|---|---|
| Identificação | `id` | inteiro, 72.529 distintos (um por linha) |
| Quando | `data_inversa`, `dia_semana`, `horario` | data ISO, texto, hora |
| Onde | `uf`, `br`, `km`, `municipio`, `latitude`, `longitude` | texto, inteiro, decimal com vírgula, texto, decimal com vírgula |
| Circunstância | `causa_acidente` (69 valores), `tipo_acidente` (17), `fase_dia` (4), `sentido_via` (3), `condicao_metereologica` (9), `tipo_pista` (3), `tracado_via`, `uso_solo` (2) | texto |
| Desfecho | `classificacao_acidente` (3 valores + 1 nulo) | texto |
| Contagens | `pessoas`, `mortos`, `feridos_leves`, `feridos_graves`, `ilesos`, `ignorados`, `feridos`, `veiculos` | inteiro, sem nulos |
| Responsável | `regional`, `delegacia`, `uop` | texto |

Fora `classificacao_acidente`, nenhuma coluna de 2025 tem nulo. O nome `condicao_metereologica` vem errado na fonte (deveria ser "meteorológica"). Na silver ele vai ser renomeado.

Pontos para tratar na silver:

- `condicao_metereologica` tem "Sol" (4.201) e "Céu Claro" (46.375) como categorias separadas, além de "Ignorado" (1.000) e uma ocorrência de "Neve" em 2025;
- `sentido_via` tem "Não Informado" em 167 linhas de 2025;
- `municipio` vem em maiúsculas e sem acento, sem código IBGE.

## Latitude e longitude

| Ano | Nula ou inválida | Fora do Brasil | Detalhe |
|---|---|---|---|
| 2017 | 0 | 57 | 7 em (0, 0), 33 com magnitude impossível (como `-405,96`, vírgula decimal perdida) e o resto em outro lugar fora da caixa |
| 2018 a 2026 | 0 | 0 | |

"Fora do Brasil" usa duas caixas: a dos pontos extremos do território continental (latitude entre −33,76 e 5,28, longitude entre −74,00 e −34,78) e uma pequena só para Fernando de Noronha (latitude entre −3,95 e −3,80, longitude entre −32,55 e −32,35).

A caixa de Noronha surgiu na validação de 2024. Na primeira versão, só com a caixa continental, um acidente caía fora: id 620583, BR-363, km 1,5, em Fernando de Noronha (PE), longitude −32,41. Era um acidente real, porque o arquipélago tem rodovia federal. A primeira correção que testei foi alargar o limite leste até −32,35, mas assim passavam quatro coordenadas erradas de 2017 no mar, três delas arredondadas para (−7, −34) ou (−6, −34) em Recife, João Pessoa e Cabedelo. Por isso o arquipélago ganhou uma caixa própria. `fase0_coord_leste_da_costa.csv` lista os cinco pontos e mostra que só o de Noronha é aceito. A caixa não pega um ponto que esteja no Brasil mas na UF errada. `fase0_coord_por_uf_<ano>.csv` traz os percentis 1 e 99 de cada UF, para enxergar esses casos. Na Fase 1 vou comparar a coordenada com o centroide do município (código IBGE pelo nome), que é um teste mais fino.

## Definição de acidente grave

**Acidente grave = ocorrência com pelo menos um morto ou um ferido grave: `mortos > 0 OR feridos_graves > 0`.**

Por que não usar só `classificacao_acidente`: ela tem três valores, "Sem Vítimas", "Com Vítimas Feridas" e "Com Vítimas Fatais", e "Com Vítimas Feridas" junta ferido leve e ferido grave. Em 2025 foram 56.181 ocorrências "Com Vítimas Feridas": 15.283 tinham ferido grave e 40.898 só ferido leve (`fase0_grave_x_classificacao_2025.csv`). A classificação não separa essas duas situações. As contagens separam.

A classificação e as contagens concordam. Nos dez anos não há nenhuma linha "Com Vítimas Fatais" com `mortos = 0`, nenhuma com morto classificada como outra coisa, nenhuma "Sem Vítimas" com morto ou ferido e nenhuma "Com Vítimas Feridas" com `feridos = 0`. Por isso a definição pelas contagens equivale a "Com Vítimas Fatais" mais "Com Vítimas Feridas que tiveram ferido grave".

| Ano | Ocorrências | Graves | % graves | Com morto | % sem vítimas |
|---|---|---|---|---|---|
| 2017 | 89.567 | 18.663 | 20,84 | 5.184 | 34,26 |
| 2018 | 69.333 | 17.535 | 25,29 | 4.508 | 22,0 |
| 2019 | 67.558 | 18.309 | 27,1 | 4.599 | 17,29 |
| 2020 | 63.585 | 17.452 | 27,45 | 4.525 | 18,25 |
| 2021 | 64.567 | 18.118 | 28,06 | 4.665 | 18,11 |
| 2022 | 64.606 | 18.409 | 28,49 | 4.664 | 17,81 |
| 2023 | 67.766 | 19.212 | 28,35 | 4.858 | 16,18 |
| 2024 | 73.202 | 20.644 | 28,2 | 5.225 | 16,1 |
| 2025 | 72.529 | 20.493 | 28,25 | 5.210 | 15,36 |
| 2026 (até set.) | 54.895 | 15.312 | 27,89 | 3.928 | 15,59 |

**Quebra na série em abril de 2018.** A série mensal (`fase0_sem_vitimas_por_mes.csv`) mostra a proporção de "Sem Vítimas" entre 31% e 37% em todos os meses de 2017, 29,65% em março de 2018 e 18,14% em abril de 2018. De abril de 2018 em diante ela fica entre 15% e 19%. No mesmo mês o total de ocorrências cai de 6.684 para 5.530, enquanto as ocorrências com morto continuam no mesmo patamar (376 em março e 385 em abril). Ou seja, deixaram de entrar na base cerca de mil acidentes sem vítima por mês, e o número de acidentes graves não mudou. A explicação mais provável é uma mudança no registro de acidentes sem vítima a partir de abril de 2018, mas **eu não verifiquei isso** em nenhum documento da PRF.

Consequência: contagens totais e a % de graves de antes de abril de 2018 não são comparáveis com as de depois. Decisão proposta: a bronze e a silver guardam tudo, de 2017 a 2025, com uma coluna que marca o período depois da quebra (`data >= 2018-04-01`). A análise e a gold usam os **anos completos de 2019 a 2025**, quando o registro já é estável. O 2026, ainda parcial, fica de fora até o ano fechar.

O arquivo por pessoa de 2025 confirma as contagens. As 72.529 ocorrências aparecem nos dois arquivos, nenhum `id` sobra em um lado só, e a soma de mortos, feridos graves, feridos leves e ilesos por `id` no arquivo por pessoa é igual à do arquivo por ocorrência em todas elas (`fase0_pessoa_vs_ocorrencia_2025.json`).

## Testes de qualidade na fonte real

Linhas reprovadas em cada ano (`fase0_qualidade_<ano>.csv`):

Os testes abaixo deram 0 linhas reprovadas em todos os anos de 2017 a 2026, e o teste vai falhar se alguma aparecer: `id` nulo, `id` duplicado, coordenada nula ou inválida, data inválida ou fora do ano do arquivo, contagem de vítimas negativa ou nula, "Com Vítimas Fatais" com `mortos = 0`, "Sem Vítimas" com morto ou ferido e `feridos ≠ feridos_leves + feridos_graves`.

Os que reprovam linhas:

| Teste | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | O que fazer |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Coordenada fora do Brasil | 57 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | na silver, lat/lon viram nulas e uma coluna `coord_valida = false` marca a linha. A ocorrência fica, porque UF, BR e km continuam bons |
| `id` que não é número inteiro | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0 | 1 | ver "O id em notação científica" abaixo |
| Morto com classificação diferente de fatal | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | as duas linhas têm classificação `NA`. Na silver, a classificação é derivada das contagens quando vier nula, e o teste aceita só esses casos (exceção com `id`) |
| Classificação nula | 1 | 1 | 1 | 2 | 1 | 1 | 1 | 1 | 1 | 1 | igual ao item anterior |
| `pessoas < mortos + feridos + ilesos + ignorados` | 4.572 | 3.519 | 3.098 | 3.340 | 3.517 | 3.547 | 3.767 | 3.887 | 3.823 | 2.898 | ver abaixo |

### O id em notação científica

A primeira versão desta validação não pegou este problema. Ele apareceu na primeira execução da silver, quando a checagem de conversão de tipos parou o pipeline com 5 linhas.

Em seis arquivos, o único id redondo do ano está escrito em notação científica: `1e+05` em 2018, `2e+05` em 2019, `3e+05` em 2020, `4e+05` em 2021, `6e+05` em 2024 e `8e+05` em 2026 (`id_nao_inteiro_valores` em `fase0_perfil_<ano>.json`). É o que acontece quando um CSV é gravado pelo R com a configuração padrão, que escreve 100000 como `1e+05`. A Fase 0 não viu o problema porque conferia o id como texto: `"1e+05"` não é nulo nem repetido.

Para confirmar que `1e+05` é mesmo o id 100000, verifiquei duas coisas na bronze de 2017 a 2025 (`fase1_ids_corrigidos.csv`). Primeiro, nenhum desses ids aparece também escrito por extenso. Segundo, os vizinhos são do mesmo dia: o id anterior (99999, 199999 etc.) existe em todos os casos, e o seguinte existe em todos menos no 400000, que não tem 400001. A silver converte esse formato para inteiro só quando o resultado é exato e marca a linha com `id_corrigido = true`. Um id que não seja inteiro, como `1.5e+00`, continua parando o pipeline. A contagem por ano está em `fase1_conferencia_silver.csv`.

### A coluna `pessoas`

Em cerca de 5% das ocorrências de cada ano, `pessoas` é menor que `mortos + feridos + ilesos + ignorados`. Nunca é maior. No arquivo por pessoa de 2025, o número de linhas de cada ocorrência é igual a `mortos + feridos + ilesos + ignorados` em todas as 72.529, e igual a `pessoas` em 68.706. O `ignorados` é igual, em todas, ao número de pessoas com `estado_fisico` "NA" ou "Não Informado" (`fase0_pessoa_vs_ocorrencia_2025.json`).

Conclusão: a soma das contagens fecha com o arquivo por pessoa, e a coluna `pessoas` não fecha. Não sei por que a PRF calcula `pessoas` assim. A silver mantém a coluna original e cria `total_envolvidos = mortos + feridos + ilesos + ignorados`, que é a usada nas análises. O teste confere que `pessoas <= total_envolvidos`. Ele falharia se algum dia `pessoas` passasse da soma.

## A fonte serve?

Serve. O `id` é único e sem nulos (depois de corrigir 1 id por ano em notação científica, em alguns anos), as contagens são completas e coerentes com a classificação e com o arquivo por pessoa, as coordenadas de 2018 em diante estão todas dentro do Brasil e o layout é o mesmo em todos os anos de 2017 a 2026. As limitações que ficam:

1. Não há volume de tráfego. Contagem de acidentes não é risco. A única taxa honesta é a proporção de graves entre os acidentes de um mesmo recorte.
2. Em abril de 2018 a série de "Sem Vítimas" quebra, o que afeta as contagens totais e a proporção de graves. A análise usa 2019 a 2025.

## Referência dos dados

Polícia Rodoviária Federal (PRF). *Sinistros de trânsito: boletins de acidentes em rodovias federais, agrupados por ocorrência e por pessoa (sistema BAT, 2017–2026)*. Brasília: PRF, 2026. Disponível em: <https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf> e no Portal Brasileiro de Dados Abertos (<https://dados.gov.br>), conjunto "SINISTROS DE TRÂNSITO - PRF". Acesso em: 4 nov. 2026.
