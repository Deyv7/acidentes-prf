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

Conferi os seis arquivos baixados nesta fase: os IDs de Drive são os mesmos listados nessas pastas. Ou seja, o portal e a página da PRF apontam para os mesmos arquivos. Na Fase 1, a ingestão vai usar as pastas como lista dos anos disponíveis. O portal também tem "Sistema BR-Brasil - Boletins de Ocorrências em Rodovias Federais", atualizado em 22/12/2017, que é o sistema antigo e fica fora do recorte.

A página do dicionário diz que o sistema BR-Brasil foi usado de 2007 a 2016 e que o sistema BAT é usado desde 2017. O projeto usa **2017 em diante**, só com dados do BAT, para não misturar dois sistemas de registro.

Arquivos baixados (fora do repositório, em `C:\Users\Deyvid-PC\dados-prf\bruto\`), com SHA-256 em `fase0_perfil_<ano>.json`:

| Arquivo | ZIP (bytes) | CSV (bytes) | Data do CSV no ZIP | Linhas |
|---|---|---|---|---|
| ocorrência 2017 | 4.248.009 | 24.887.945 | 2024-09-27 | 89.567 |
| ocorrência 2020 | 3.075.980 | 18.042.979 | 2024-09-27 | 63.585 |
| ocorrência 2023 | 3.397.281 | 19.770.946 | 2024-08-15 | 67.766 |
| ocorrência 2025 | 3.727.148 | 21.143.436 | 2026-03-18 | 72.529 |
| ocorrência 2026 | 2.818.326 | 15.992.292 | 2026-10-27 | 54.895 |
| pessoa 2025 | 9.349.289 | 72.881.148 | 2026-03-18 | 194.629 |

O ano de 2026 está incompleto: as datas vão de 2026-01-01 a 2026-09-30 (`fase0_resumo_por_ano.csv`). A PRF republica os arquivos de anos anteriores (o de 2017 tem data de 2024), então o SHA-256 é o que garante que dá para reproduzir com o mesmo arquivo.

## Licença

No dados.gov.br, o campo de licença do conjunto "SINISTROS DE TRÂNSITO - PRF" indica uso gratuito. Consultei pelo navegador em 04/11/2026, porque a API do portal exige login. Por isso o projeto usa os dados e cita a fonte (veja "Referência dos dados" no fim deste documento). Outras informações sobre o uso:

- o rodapé da página da PRF e da página do dicionário diz "Creative Commons Atribuição-SemDerivações 3.0 Não Adaptada". Esse texto vale para o conteúdo do site e não fala dos arquivos de dados;
- o Plano de Dados Abertos da PRF 2022–2024 diz que os dados são publicados "sob licença aberta que permita sua livre utilização, consumo ou cruzamento, limitando-se a creditar a autoria ou a fonte".

Cuidados adotados: citar a PRF como fonte, **não versionar nem redistribuir os CSVs originais** (quem quiser os arquivos baixa direto da fonte) e publicar só tabelas derivadas e agregados.

## Formato

O formato é igual nos cinco anos analisados (`fase0_perfil_<ano>.json`):

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

O `tracado_via` pode ter vários valores separados por `;` dentro das aspas, por exemplo `"Reta;Declive"`. Isso acontece em 18.741 linhas de 2025, contra 5.526 em 2017 (`linhas_tracado_via_multivalor`). Com um leitor de CSV que respeite as aspas, o campo não quebra a linha.

## Colunas

O arquivo por ocorrência tem 30 colunas, **com o mesmo nome e a mesma ordem em 2017, 2020, 2023, 2025 e 2026** (`fase0_layout_por_ano.csv`). Os anos 2018, 2019, 2021, 2022 e 2024 não foram baixados nesta fase. A Fase 1 vai ingerir todos e o teste de layout vai rodar neles.

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
| 2020 | 0 | 0 | |
| 2023 | 0 | 0 | |
| 2025 | 0 | 0 | |
| 2026 | 0 | 0 | |

"Fora do Brasil" usa a caixa dos pontos extremos do território continental: latitude entre −33,76 e 5,28 e longitude entre −74,00 e −34,78. A caixa não pega um ponto que esteja no Brasil mas na UF errada. `fase0_coord_por_uf_<ano>.csv` traz os percentis 1 e 99 de cada UF, para enxergar esses casos. Na Fase 1 vou comparar a coordenada com o centroide do município (código IBGE pelo nome), que é um teste mais fino.

## Definição de acidente grave

**Acidente grave = ocorrência com pelo menos um morto ou um ferido grave: `mortos > 0 OR feridos_graves > 0`.**

Por que não usar só `classificacao_acidente`: ela tem três valores, "Sem Vítimas", "Com Vítimas Feridas" e "Com Vítimas Fatais", e "Com Vítimas Feridas" junta ferido leve e ferido grave. Em 2025 foram 56.181 ocorrências "Com Vítimas Feridas": 15.283 tinham ferido grave e 40.898 só ferido leve (`fase0_grave_x_classificacao_2025.csv`). A classificação não separa essas duas situações. As contagens separam.

A classificação e as contagens concordam. Nos cinco anos não há nenhuma linha "Com Vítimas Fatais" com `mortos = 0`, nenhuma com morto classificada como outra coisa, nenhuma "Sem Vítimas" com morto ou ferido e nenhuma "Com Vítimas Feridas" com `feridos = 0`. Por isso a definição pelas contagens equivale a "Com Vítimas Fatais" mais "Com Vítimas Feridas que tiveram ferido grave".

| Ano | Ocorrências | Graves | % graves | Com morto |
|---|---|---|---|---|
| 2017 | 89.567 | 18.663 | 20,84 | 5.184 |
| 2020 | 63.585 | 17.452 | 27,45 | 4.525 |
| 2023 | 67.766 | 19.212 | 28,35 | 4.858 |
| 2025 | 72.529 | 20.493 | 28,25 | 5.210 |
| 2026 (até set.) | 54.895 | 15.312 | 27,89 | 3.928 |

**Cuidado com a série histórica.** A proporção de "Sem Vítimas" cai de 34,26% em 2017 para 18,25% em 2020 e fica entre 15% e 16% depois disso. O número de acidentes com morto muda pouco no período. A explicação mais provável é uma mudança no registro de acidentes sem vítima, mas **eu não verifiquei isso**. Consequência: a % de graves de 2017 não é comparável à dos anos seguintes. A análise vai tratar esse corte de forma explícita, e a Fase 1 vai localizar o ano exato com os anos que faltam.

O arquivo por pessoa de 2025 confirma as contagens. As 72.529 ocorrências aparecem nos dois arquivos, nenhum `id` sobra em um lado só, e a soma de mortos, feridos graves, feridos leves e ilesos por `id` no arquivo por pessoa é igual à do arquivo por ocorrência em todas elas (`fase0_pessoa_vs_ocorrencia_2025.json`).

## Testes de qualidade na fonte real

Linhas reprovadas em cada ano (`fase0_qualidade_<ano>.csv`):

| Teste | 2017 | 2020 | 2023 | 2025 | 2026 | O que fazer |
|---|---|---|---|---|---|---|
| `id` nulo | 0 | 0 | 0 | 0 | 0 | o teste falha se aparecer |
| `id` duplicado | 0 | 0 | 0 | 0 | 0 | o teste falha se aparecer |
| Coordenada nula ou inválida | 0 | 0 | 0 | 0 | 0 | o teste falha se aparecer |
| Coordenada fora do Brasil | 57 | 0 | 0 | 0 | 0 | na silver, lat/lon viram nulas e uma coluna `coord_valida = false` marca a linha. A ocorrência fica, porque UF, BR e km continuam bons |
| Data inválida ou fora do ano do arquivo | 0 | 0 | 0 | 0 | 0 | o teste falha se aparecer |
| Contagem de vítimas negativa ou nula | 0 | 0 | 0 | 0 | 0 | o teste falha se aparecer |
| "Com Vítimas Fatais" com `mortos = 0` | 0 | 0 | 0 | 0 | 0 | o teste falha se aparecer |
| Morto com classificação diferente de fatal | 0 | 0 | 0 | 1 | 1 | as duas linhas têm classificação `NA`. Na silver, a classificação é derivada das contagens quando vier nula, e o teste aceita só esses casos (exceção com `id`) |
| Classificação nula | 1 | 2 | 1 | 1 | 1 | igual ao item anterior |
| "Sem Vítimas" com morto ou ferido | 0 | 0 | 0 | 0 | 0 | o teste falha se aparecer |
| `feridos ≠ feridos_leves + feridos_graves` | 0 | 0 | 0 | 0 | 0 | o teste falha se aparecer |
| `pessoas < mortos + feridos + ilesos + ignorados` | 4.572 | 3.340 | 3.767 | 3.823 | 2.898 | ver abaixo |

### A coluna `pessoas`

Em cerca de 5% das ocorrências de cada ano, `pessoas` é menor que `mortos + feridos + ilesos + ignorados`. Nunca é maior. No arquivo por pessoa de 2025, o número de linhas de cada ocorrência é igual a `mortos + feridos + ilesos + ignorados` em todas as 72.529, e igual a `pessoas` em 68.706. O `ignorados` é igual, em todas, ao número de pessoas com `estado_fisico` "NA" ou "Não Informado" (`fase0_pessoa_vs_ocorrencia_2025.json`).

Conclusão: a soma das contagens fecha com o arquivo por pessoa, e a coluna `pessoas` não fecha. Não sei por que a PRF calcula `pessoas` assim. A silver mantém a coluna original e cria `total_envolvidos = mortos + feridos + ilesos + ignorados`, que é a usada nas análises. O teste confere que `pessoas <= total_envolvidos`. Ele falharia se algum dia `pessoas` passasse da soma.

## A fonte serve?

Serve. O `id` é único e sem nulos, as contagens são completas e coerentes com a classificação e com o arquivo por pessoa, as coordenadas de 2020 em diante estão todas dentro do Brasil e o layout é o mesmo desde 2017. As limitações que ficam:

1. Não há volume de tráfego. Contagem de acidentes não é risco. A única taxa honesta é a proporção de graves entre os acidentes de um mesmo recorte.
2. Há uma quebra na série de "Sem Vítimas" entre 2017 e 2020, que afeta a proporção de graves.

## Referência dos dados

Polícia Rodoviária Federal (PRF). *Sinistros de trânsito: boletins de acidentes em rodovias federais, agrupados por ocorrência e por pessoa (sistema BAT, 2017–2026)*. Brasília: PRF, 2026. Disponível em: <https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf> e no Portal Brasileiro de Dados Abertos (<https://dados.gov.br>), conjunto "SINISTROS DE TRÂNSITO - PRF". Acesso em: 4 nov. 2026.
