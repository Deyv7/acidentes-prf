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

O Unity Catalog é a camada de governança do Databricks: cada tabela e cada pasta de arquivos tem um nome de três partes (`catalogo.schema.objeto`) e permissões. A documentação do Free Edition chama o catálogo padrão de `workspace`, mas nesta conta ele recebeu o nome do workspace, `portfolio`. Por isso o catálogo é um parâmetro (widget `catalogo`) nos notebooks. O projeto usa:

- schema `portfolio.acidentes_prf`;
- volume `portfolio.acidentes_prf.bruto`, uma pasta de arquivos (ZIP e CSV) dentro do Unity Catalog, acessível como `/Volumes/portfolio/acidentes_prf/bruto/...`;
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
- `ler_csv_prf`: lê com esquema explícito (30 colunas de texto), latin-1, `;`, aspas e `mode=FAILFAST`. Uma linha com campo a mais ou a menos é erro, não linha descartada em silêncio;
- `adicionar_metadados`: `_arquivo_origem`, `_ano_arquivo` e `_ingerido_em`, a partir da coluna oculta `_metadata.file_path` do Spark.

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
| uma linha por `id`, ficando a ingestão mais recente | proteção para reprocessamento; a fonte não tem id repetido |

`falhas_de_conversao` roda antes da silver e para o pipeline se algum valor preenchido não converter para o tipo esperado. Sem ela, `try_cast` transformaria o valor em nulo sem avisar. Foi essa checagem que achou os ids em notação científica.

Numa entrevista, eu diria: "Eu uso `try_cast` para não quebrar no meio da escrita, mas antes conto quantos valores não converteriam. Se for mais que zero, eu paro. Converter para nulo em silêncio é o pior caso, porque o número sai errado e ninguém percebe."

## Conferência com a Fase 0

`src/executar_local.py` roda bronze e silver nos ZIPs reais de 2017 a 2025 e compara com o que o script da Fase 0 contou com a biblioteca padrão do Python, sem Spark. Ocorrências, graves e acidentes com morto batem nos nove anos (`resultados/fase1_conferencia_silver.csv`, coluna `bate_com_fase0`).

Por que isso importa: são duas leituras independentes do mesmo arquivo. Se o Spark lesse o CSV de outro jeito (aspas, `;` dentro do `tracado_via`, CRLF), os números não bateriam.

## Execução no Databricks

`databricks/implantar.sh` faz tudo pela CLI: importa os notebooks, cria o schema e os volumes (`00_configurar`), sobe o wheel e os ZIPs de 2017 a 2025 e dispara o job de `databricks/job_bronze_silver.json`, com a bronze e depois a silver. O notebook `02_silver` devolve a conferência por ano como saída, e eu comparo com a execução local. Os nove anos bateram em todas as colunas (`resultados/fase1_conferencia_databricks.csv`).

Dois problemas de plataforma apareceram no caminho, e os dois mudaram o desenho.

**1. Arquivos do workspace instáveis no serverless.** A primeira versão subia o repositório inteiro para o workspace e os notebooks importavam `src/` de lá, como manda a documentação. O import falhava com `OSError: [Errno 5] Input/output error`. Um notebook de diagnóstico mostrou o padrão: dentro de uma sessão, cada arquivo era sempre lido ou nunca era, e o conjunto que falhava mudava de uma sessão para outra. Arquivos num volume do Unity Catalog foram lidos 15 vezes em 15 tentativas. A solução foi empacotar `src/` como wheel (`pyproject.toml`), guardar o wheel no volume `artefatos` e instalar com `%pip` no começo de cada notebook. Essa já é a forma recomendada para jobs, porque o código que roda fica versionado num arquivo só.

**2. Versão do ambiente serverless.** Sem configuração, o job rodou no ambiente serverless versão 1, que tem Python 3.10 e um cliente Spark anterior ao 4.0. O wheel exige Python 3.12, e o código usa `Column.try_cast`, que só existe no Spark 4. O job agora fixa o ambiente versão 4 (Python 3.12, Spark 4.0), o mesmo do `pyspark==4.0.1` dos testes locais. Assim os testes e a nuvem rodam a mesma versão do Spark.

Numa entrevista, eu diria: "Os dois erros apareceram porque eu conferia o resultado e não só se o job terminava. E as duas correções deixaram o projeto mais reprodutível: o código vai num artefato versionado e a versão do Spark é explícita nos dois ambientes."

## Testes

São 39 testes em `tests/`, rodando no container. Para conferir que eles reprovam quando devem, estraguei duas regras de propósito (`grave` sem feridos graves e `total_envolvidos` sem ignorados): os testes dessas regras falharam, e voltei o código.
