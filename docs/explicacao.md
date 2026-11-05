# Explicação das decisões

Cada seção diz o que é a técnica, por que ela está no projeto e como eu explicaria numa entrevista. Os números citados saíram de `resultados/`.

## Arquitetura medallion

Medallion é organizar o dado em camadas, cada uma com um contrato:

| Camada | Tabela | Contrato |
|---|---|---|
| Bronze | `bronze_ocorrencias` | o CSV como veio, tudo texto, mais o arquivo de origem e a hora da ingestão |
| Silver | `silver_ocorrencias` | uma linha por ocorrência, com tipos certos, nulos tratados e regras de limpeza aplicadas |
| Gold | (Fase 2) | tabelas prontas para uma pergunta: uma linha por ocorrência para o modelo e agregados para a análise |

Por que separar: se uma regra da silver estiver errada, eu corrijo o código e reprocesso a partir da bronze, sem baixar nada de novo. E a bronze serve de prova do que a fonte mandou. Foi assim que achei o id em notação científica: a bronze guardou `"1e+05"` exatamente como veio.

Numa entrevista, eu diria: "A bronze não interpreta nada. Até o `NA` fica como texto. Quem decide que `NA` é nulo é a silver, e essa decisão tem teste."

## Delta Lake

Delta é o formato das tabelas: arquivos Parquet mais um log de transações (`_delta_log`). O log dá três coisas que um Parquet solto não dá:

- escrita atômica: se o job cair no meio de um `overwrite`, quem lê continua vendo a versão anterior inteira;
- histórico (time travel): dá para ler a tabela como ela estava numa versão anterior, o que ajuda quando um reprocessamento dá resultado estranho;
- esquema registrado: escrever uma coluna com tipo diferente falha, a menos que eu peça `overwriteSchema`.

No Databricks, Delta é o formato padrão das tabelas. No projeto, os testes e a execução local também gravam Delta (`delta-spark`), para o código ser o mesmo nos dois lugares.

## Unity Catalog e volumes

O Unity Catalog é a camada de governança do Databricks: cada tabela e cada pasta de arquivos tem um nome de três partes (`catalogo.schema.objeto`) e permissões. A documentação do Free Edition chama o catálogo padrão de `workspace`, mas nesta conta ele recebeu o nome do workspace, `portfolio`. O nome está numa constante `CATALOGO` no começo de cada notebook. O projeto usa:

- schema `portfolio.acidentes_prf`;
- volume `portfolio.acidentes_prf.bruto`, uma pasta de arquivos (ZIP e CSV) dentro do Unity Catalog, acessível como `/Volumes/portfolio/acidentes_prf/bruto/...`;
- volume `portfolio.acidentes_prf.artefatos`, onde fica o wheel com o código de `src/`;
- tabelas `bronze_ocorrencias` e `silver_ocorrencias` no mesmo schema.

Por que volume e não baixar direto no notebook: o Free Edition restringe o acesso à internet de saída. Os ZIPs sobem da minha máquina para o volume pela CLI, e o notebook lê de lá.

## Computação serverless

No Free Edition só existe computação serverless: eu não crio cluster, o Databricks aloca a máquina quando o notebook ou o job roda. Há uma cota diária de uso; se passar, a computação fica desligada até o dia seguinte. Por isso os testes rodam fora do Databricks.

## Lógica fora do notebook

As transformações ficam em `src/bronze.py` e `src/silver.py`, como funções que recebem e devolvem DataFrame. Os notebooks em `notebooks/` só montam o caminho, chamam as funções e gravam a tabela.

Por quê:

- teste: pytest roda as mesmas funções com Spark local, sem gastar cota;
- revisão: um diff de `.py` é legível, um diff de notebook com saída não é;
- reuso: `src/executar_local.py` roda o mesmo pipeline nos dados reais fora do Databricks.

Os testes rodam num container Linux (`docker/Dockerfile.testes`), porque o Spark no Windows precisa do `winutils.exe`, um binário de terceiros. O container roda sem rede (`--network none`): os jars do Delta são baixados quando a imagem é construída.

## Bronze

`src/bronze.py`:

- `extrair_zip`: extrai o único CSV do ZIP. Recusa ZIP com mais de um arquivo e ignora pastas no nome, então um ZIP malicioso não escreve fora do destino;
- `conferir_cabecalho`: compara a primeira linha com as 30 colunas esperadas, na ordem. Se a PRF mudar o layout, o pipeline para com uma mensagem dizendo o que falta ou sobra;
- `zips_do_recorte` e `conferir_nome`: só entram arquivos `datatran<ano>` de 2017 a 2025. Um ZIP de 2026 esquecido no volume ou um arquivo com outro nome ficam de fora;
- `ler_csv_prf`: lê com esquema explícito (30 colunas de texto), latin-1, `;`, aspas e `mode=FAILFAST`. Uma linha com campo a mais ou a menos é erro, não linha descartada em silêncio. O escape é a própria aspa (`escape='"'`), como no CSV padrão; o padrão do Spark é a barra invertida, que guardaria aspas dobradas na bronze;
- `adicionar_metadados`: `_arquivo_origem`, `_ano_arquivo` e `_ingerido_em`, a partir da coluna oculta `_metadata.file_path` do Spark. `_ingerido_em` chega em UTC com o `Z` no fim; sem o fuso, o mesmo instante seria gravado diferente no Spark local (America/Sao_Paulo) e no Databricks (UTC).

A bronze é acumulativa: cada execução faz `append` com o seu `_ingerido_em`. A PRF republica arquivos de anos anteriores, então a bronze guarda as versões e a silver usa a mais recente de cada arquivo.

Por que esquema explícito e não `inferSchema`: com inferência, o Spark leria `1e+05` como número e o problema sumiria. Também leria `-23,48` como texto num ano e erraria de outro jeito em outro ano.

## Silver

`src/silver.py`. Cada regra tem pelo menos um teste em `tests/test_silver.py`:

| Regra | Por quê |
|---|---|
| `NA` e texto vazio viram nulo | é assim que a PRF escreve nulo |
| vírgula decimal em `km`, `latitude` e `longitude` | formato brasileiro |
| `id` em notação científica vira inteiro, com `id_corrigido` | 5 ids de 2018 a 2024 vieram como `1e+05`, `2e+05` etc. (`resultados/fase1_ids_corrigidos.csv`) |
| coordenada fora do Brasil vira nula, com `coord_valida = false` | 57 linhas em 2017. A ocorrência fica, porque UF, BR e km continuam bons |
| Fernando de Noronha é válido | tem BR-363 e um acidente real em 2024 |
| classificação nula é derivada das contagens, com `classificacao_imputada` | 1 ou 2 por ano |
| `total_envolvidos = mortos + feridos + ilesos + ignorados` | a coluna `pessoas` fica abaixo dessa soma em cerca de 5% das linhas, e o arquivo por pessoa fecha com a soma |
| `grave = mortos > 0 ou feridos_graves > 0` | definição do projeto (docs/validacao-fonte.md) |
| `serie_estavel = data >= 2018-04-01` | quebra no registro de acidentes sem vítima |
| só a ingestão mais recente de cada arquivo (`ultima_ingestao`) | a bronze acumula versões; não se mistura linha de uma versão com linha de outra |

`validar_bronze` roda antes da silver e para o pipeline em três casos:

- valor fora do formato esperado (`problemas_por_linha`). O formato é conferido por expressão regular antes do `try_cast`, porque o `try_cast` sozinho aceita coisas que não existem na fonte: `"2025"` vira 2025-01-01, `"NaN"` vira NaN e `"-1"` vira -1. Hora tem que ser `HH:MM:SS` válida, data tem que ser `AAAA-MM-DD` que existe no calendário, contagem tem que ser inteiro sem sinal;
- campo obrigatório vazio: `id`, data, hora, UF, BR, km e as contagens de vítimas. Latitude e longitude podem faltar: a linha fica com `coord_valida = false`;
- `id` repetido na ingestão vigente (`ids_repetidos`), inclusive entre formatos: `"1e+05"` e `"100000"` são o mesmo id depois da conversão.

A silver não escolhe entre linhas repetidas. Na primeira versão havia uma deduplicação por `id`, e a revisão de código mostrou que ela juntava em silêncio duas ocorrências com `id` nulo numa só. Id repetido agora é erro da fonte e para o pipeline. Na fonte real de 2017 a 2025, os três casos dão zero.

Numa entrevista, eu diria: "Converter para nulo em silêncio é o pior caso, porque o número sai errado e ninguém percebe. Então eu confiro o formato antes, e se aparecer um valor que eu não conheço, o pipeline para e mostra a linha."

## Conferência com a Fase 0

`src/executar_local.py` roda bronze e silver nos ZIPs reais de 2017 a 2025 e compara com o que o script da Fase 0 contou com a biblioteca padrão do Python, sem Spark. Duas conferências:

- bronze: para cada ano e cada uma das 30 colunas, o número de campos vazios, de `NA` e de valores distintos contados pelo Spark é igual ao da Fase 0 (`resultados/fase1_conferencia_bronze_colunas.csv`, coluna `bate`);
- silver: linhas da bronze vigente, ocorrências, graves e acidentes com morto batem nos nove anos (`resultados/fase1_conferencia_silver.csv`, coluna `bate_com_fase0`).

O script termina com erro se alguma das duas não bater.

Por que isso importa: são duas leituras independentes do mesmo arquivo. Se o Spark lesse o CSV de outro jeito (aspas, `;` dentro do `tracado_via`, CRLF), os números não bateriam.

## Execução no Databricks

`databricks/implantar.sh` faz tudo pela CLI: importa os notebooks, cria o schema e os volumes (`00_configurar`), sobe o wheel e os ZIPs de 2017 a 2025 e dispara o job de `databricks/job_bronze_silver.json`, com a bronze e depois a silver. O notebook `02_silver` confere que a silver tem o mesmo número de linhas da bronze vigente e devolve a contagem por ano como saída. O script busca essa saída pela CLI e `src/conferir_databricks.py` compara com a execução local: ocorrências, graves, com morto, coordenada inválida, id corrigido e classificação imputada batem nos nove anos (`resultados/fase1_conferencia_databricks.csv`, coluna `bate_com_local`).

Dois problemas de plataforma apareceram no caminho, e os dois mudaram o desenho.

**1. Arquivos do workspace instáveis no serverless.** A primeira versão subia o repositório inteiro para o workspace e os notebooks importavam `src/` de lá, como manda a documentação. O import falhava com `OSError: [Errno 5] Input/output error`. Um notebook de diagnóstico mostrou o padrão: dentro de uma sessão, cada arquivo era sempre lido ou nunca era, e o conjunto que falhava mudava de uma sessão para outra. Os mesmos arquivos num volume do Unity Catalog não falharam. Não guardei a saída desse diagnóstico, então fica como relato, sem número. A solução foi empacotar `src/` como wheel (`pyproject.toml`), guardar o wheel no volume `artefatos` e instalar com `%pip` no começo de cada notebook. Essa já é a forma recomendada para jobs, porque o código que roda fica versionado num arquivo só.

**2. Versão do ambiente serverless.** Sem configuração, o job rodou no ambiente serverless versão 1, que pela documentação do Databricks tem Python 3.10 e um cliente Spark anterior ao 4.0. O wheel exige Python 3.12, e o código usa `Column.try_cast`, que só existe no Spark 4. O job agora fixa o ambiente versão 4 (Python 3.12, Spark 4.0), o mesmo do `pyspark==4.0.1` dos testes locais. Assim os testes e a nuvem rodam a mesma versão do Spark.

Numa entrevista, eu diria: "Os dois erros apareceram porque eu conferia o resultado e não só se o job terminava. E as duas correções deixaram o projeto mais reprodutível: o código vai num artefato versionado e a versão do Spark é explícita nos dois ambientes."

## Testes

São 80 testes em `tests/`, rodando no container. Para conferir que eles reprovam quando devem, estraguei regras de propósito e voltei o código depois: `grave` sem feridos graves, `total_envolvidos` sem ignorados, a leitura sem `escape='"'` e a expressão da hora aceitando `25:99:00`. Em todos os casos os testes da regra falharam.

## Revisão de código

Depois da primeira versão da Fase 1, pedi uma revisão a outro agente. O que mudou por causa dela:

- `id` nulo ou repetido não é mais deduplicado em silêncio: para o pipeline;
- a bronze passou de `overwrite` para `append`, e a silver usa a ingestão mais recente de cada arquivo. Com `overwrite`, a deduplicação por ingestão mais recente não tinha efeito nenhum;
- formatos conferidos por expressão regular antes do `try_cast`;
- `escape='"'` na leitura do CSV;
- `_ingerido_em` em UTC explícito;
- `implantar.sh` grava os arquivos temporários em `dist/` (o `databricks.exe` do Windows não enxerga o `/tmp` do Git Bash) e gera a conferência do Databricks por código;
- números deste documento sem arquivo em `resultados/` foram tirados.
