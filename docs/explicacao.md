# Explicação das decisões

Cada seção diz o que é a técnica, por que ela está no projeto e como eu explicaria numa entrevista. Os números citados saíram de `resultados/`.

## Arquitetura medallion

Medallion é organizar o dado em camadas, cada uma com um contrato:

| Camada | Tabela | Contrato |
|---|---|---|
| Bronze | `bronze_ocorrencias` | o CSV como veio, tudo texto, mais o arquivo de origem e a hora da ingestão |
| Silver | `silver_ocorrencias` | uma linha por ocorrência, com tipos certos, nulos tratados e regras de limpeza aplicadas |
| Gold | `gold_ocorrencias_modelo`, `gold_graves_por_recorte` | tabelas prontas para uma pergunta: uma linha por ocorrência para o modelo e agregados para a análise, de 2019 a 2025 |

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
- tabelas `bronze_ocorrencias`, `silver_ocorrencias`, `gold_ocorrencias_modelo` e `gold_graves_por_recorte` no mesmo schema.

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

`databricks/implantar.sh` faz tudo pela CLI: importa os notebooks, cria o schema e os volumes (`00_configurar`), sobe o wheel e os ZIPs de 2017 a 2025 e dispara o job de `databricks/job_pipeline.json`, com a bronze, a silver, a gold e a análise em sequência. O notebook `02_silver` confere que a silver tem o mesmo número de linhas da bronze vigente e devolve a contagem por ano como saída. O script busca essa saída pela CLI e `src/conferir_databricks.py` compara com a execução local: ocorrências, graves, com morto, coordenada inválida, id corrigido e classificação imputada batem nos nove anos (`resultados/fase1_conferencia_databricks.csv`, coluna `bate_com_local`). Os notebooks `03_gold` e `04_analise` fazem o mesmo com a qualidade, a gold e o resumo da análise, e todos os números batem (`resultados/fase2_conferencia_databricks.csv` e `fase3_conferencia_databricks.csv`, coluna `bate`).

Dois problemas de plataforma apareceram no caminho, e os dois mudaram o desenho.

**1. Arquivos do workspace instáveis no serverless.** A primeira versão subia o repositório inteiro para o workspace e os notebooks importavam `src/` de lá, como manda a documentação. O import falhava com `OSError: [Errno 5] Input/output error`. Um notebook de diagnóstico mostrou o padrão: dentro de uma sessão, cada arquivo era sempre lido ou nunca era, e o conjunto que falhava mudava de uma sessão para outra. Os mesmos arquivos num volume do Unity Catalog não falharam. Não guardei a saída desse diagnóstico, então fica como relato, sem número. A solução foi empacotar `src/` como wheel (`pyproject.toml`), guardar o wheel no volume `artefatos` e instalar com `%pip` no começo de cada notebook. Essa já é a forma recomendada para jobs, porque o código que roda fica versionado num arquivo só.

**2. Versão do ambiente serverless.** Sem configuração, o job rodou no ambiente serverless versão 1, que pela documentação do Databricks tem Python 3.10 e um cliente Spark anterior ao 4.0. O wheel exige Python 3.12, e o código usa `Column.try_cast`, que só existe no Spark 4. O job agora fixa o ambiente versão 4 (Python 3.12, Spark 4.0), o mesmo do `pyspark==4.0.1` dos testes locais. Assim os testes e a nuvem rodam a mesma versão do Spark.

Numa entrevista, eu diria: "Os dois erros apareceram porque eu conferia o resultado e não só se o job terminava. E as duas correções deixaram o projeto mais reprodutível: o código vai num artefato versionado e a versão do Spark é explícita nos dois ambientes."

## Testes de qualidade

`src/qualidade.py`. Os testes do pytest provam que o código faz o que eu quero com dados de exemplo. Os testes de qualidade rodam no pipeline, com o dado real, a cada execução. Cada regra descreve a condição de uma linha reprovada e é de um de dois tipos:

- **bloqueante**: se uma linha reprovar, o notebook `03_gold` para antes de gravar a gold. São coisas que eu não sei corrigir: `id` nulo ou repetido, data fora do ano do arquivo, dia da semana que não é o da data, contagem negativa ou nula, `feridos` diferente de leves mais graves, classificação que contradiz as contagens, `pessoas` maior que a soma, alvo `grave` nulo;
- **com tratamento**: a fonte real tem linhas assim, e a silver já fez algo com elas. A regra conta quantas são e diz o que foi feito.

| Regra com tratamento | O que a silver faz | Regra bloqueante que confere o tratamento |
|---|---|---|
| `coordenada_fora_do_brasil_ou_ausente` | anula latitude e longitude e marca `coord_valida = false`; a ocorrência fica | `coordenada_valida_fora_do_brasil` |
| `classificacao_ausente` | deriva a classificação das contagens e marca `classificacao_imputada` | `classificacao_incoerente`, que olha a classificação já derivada |
| `pessoas_menor_que_total` | cria `total_envolvidos`, que fecha com o arquivo por pessoa | `pessoas_maior_que_total` |

Uma condição que dá nulo conta como reprovada: uma regra que não consegue avaliar a linha não pode aprová-la.

Na silver real de 2017 a 2025, as regras bloqueantes reprovaram zero linhas. As três com tratamento reprovaram os mesmos números que a Fase 0 tinha contado com a biblioteca padrão: 57 coordenadas em 2017, 1 ou 2 classificações ausentes por ano e entre 3.098 e 4.572 linhas por ano com `pessoas` menor que a soma (`resultados/fase2_qualidade.csv`, uma linha por ano e regra).

Cada regra bloqueante tem um teste em `tests/test_qualidade.py` que estraga uma linha de uma silver válida e confere que a regra pega aquela linha e que `verificar` para. O dia da semana coerente com a data não estava na lista da Fase 0. Entrou porque o modelo vai usar o dia, e o teste custa uma linha.

## Gold

`src/gold.py`. Recorte de 2019 a 2025, filtrado por `ano` e não por `serie_estavel`: o filtro por série deixaria entrar 2018 de abril em diante, um ano pela metade.

**`gold_ocorrencias_modelo`**: uma linha por ocorrência, 473.813 linhas, com o alvo `grave`. As colunas ficam em grupos (`resultados/fase2_esquema_gold_modelo.csv`, coluna `papel`):

| Grupo | Colunas | Por quê |
|---|---|---|
| identificação | `id`, `data` | chave e data para separar treino e teste no tempo |
| contexto | ano, mês, dia da semana, fim de semana, hora, fase do dia, UF, BR, km, trecho de 10 km, município, coordenadas, sentido, tipo de pista, traçado, uso do solo, clima | onde e quando, conhecido antes do acidente |
| dinâmica | `causa_padronizada`, `tipo_padronizado`, `veiculos` | o que o policial registrou sobre o acidente. Não diz quantos se feriram, mas só existe depois do fato. Fica separado para o modelo poder ser treinado com e sem esse grupo |
| alvo | `grave` | `mortos > 0 ou feridos_graves > 0` |

Ficam fora, de propósito, as colunas de desfecho: contagens de mortos, feridos, ilesos e ignorados, `pessoas`, `total_envolvidos` e as classificações. Elas são o alvo escrito de outro jeito. Um modelo com `mortos` acertaria tudo e não serviria para nada. `verificar_modelo` falha se alguma dessas colunas aparecer na tabela, se um `id` se repetir, se houver ano fora do recorte ou alvo nulo.

**Causa e tipo padronizados.** Em janeiro de 2021 a PRF trocou a lista de causas e, entre janeiro e fevereiro, a de tipos de acidente (`docs/analise.md`, seções "Tipo de acidente" e "Causa"). No tipo, a lista nova só divide ou junta categorias, então juntar as finas nas amplas vale para os dois lados da troca: as três "Colisão lateral…" viram "Colisão lateral". Na causa, a lista antiga tinha ~30 causas amplas e a nova, ~70 mais finas, sem correspondência 1 para 1. Inventar uma correspondência seria pior que não ter o dado. Por isso `causa_padronizada` é nula antes de 2021, e o modelo que usar a causa vai treinar com 2021 em diante. Dentro da lista nova, três renomeações viram um nome só (`CAUSA_PADRONIZADA` em `src/regras.py`). A silver guarda os valores originais.

**`gold_graves_por_recorte`**: para cada recorte e valor, ocorrências, graves, ocorrências com morto, total de mortos, proporção de graves e intervalo de confiança de 95% pelo método de Wilson. Tem também a mesma proporção calculada só entre os acidentes com vítima, com o seu intervalo (ver "Análise" abaixo). Os recortes são ano, UF, BR, trecho de 10 km, município, hora, dia da semana, mês, fase do dia, clima, tipo de pista, causa e tipo de acidente.

- O trecho leva a UF no nome ("SP BR-116 km 220-230") porque o km de uma BR recomeça em cada estado. O município também leva a UF, porque há nomes repetidos entre estados.
- Valor ausente vira "(não informado)" em vez de sumir do agrupamento. Assim cada recorte soma o total da gold, o que é conferido em `resultados/fase2_recortes_gold.csv`.
- Por que proporção e não contagem: a fonte não tem volume de tráfego. Um trecho com muitos acidentes pode só ter muito carro. A proporção de graves entre os acidentes do recorte tem um denominador honesto: dos acidentes que aconteceram ali, quantos foram graves.
- Por que intervalo de Wilson: num exemplo inventado, um município com 3 acidentes e 2 graves tem 67% de graves, mas o intervalo vai de cerca de 21% a 94%. O intervalo mostra o quanto a proporção é incerta, e o Wilson não sai de 0 a 1 nem quando a amostra é pequena ou a proporção é 0 ou 1. A fórmula está duas vezes, em Python (`src/regras.py`) e em Spark (`src/gold.py`), e um teste confere que as duas dão o mesmo valor.

Um bug apareceu nos testes: com o número de ocorrências inteiro, `n * n` estoura o `int` a partir de 46.341, e o Spark 4 (com o modo ANSI ligado) para com erro. O teste com 72.529 ocorrências pegou o erro. O cálculo agora é feito em `double`.

Numa entrevista, eu diria: "A gold do modelo tem um teste que falha se uma coluna de desfecho entrar. Vazamento do alvo é o erro mais comum em modelo tabular, e é fácil de cometer quando a tabela tem `mortos` do lado de `grave`."

## Análise

`src/analise.py` lê `gold_graves_por_recorte` e compara cada valor com a média do recorte. O texto com os resultados está em `docs/analise.md`. Três decisões de método:

- **Comparar pelo intervalo, não pelo número.** Um valor está "acima" só se o intervalo de 95% inteiro estiver acima da média. Valores com menos de 100 acidentes não são comparados.
- **Ordenar pelo limite inferior do intervalo.** Ordenar pela proporção pura põe no topo os lugares com 2 acidentes e 2 graves. O limite inferior se lê como "pelo menos X% de graves, com 95% de confiança", e uma amostra pequena tem um limite inferior baixo.
- **Repetir a comparação só com acidentes com vítima.** A % de graves depende do denominador: um lugar que registra menos acidentes sem vítima parece mais grave. Entre os acidentes com vítima, esse efeito some. Na maioria dos recortes o resultado fica igual, mas em um a conclusão muda: o álcool do condutor fica abaixo da média entre todos os acidentes e acima dela entre os com vítima.

Numa entrevista, eu diria: "Antes de dizer que o Nordeste tem acidentes mais graves, eu testei se não era só o registro. O teste confirmou o Nordeste, mas mostrou que a minha conclusão sobre álcool estaria errada sem ele."

## Página

A página em `web/` segue a mesma regra dos documentos: nenhum número escrito à mão. O caminho é `resultados/` → `src/exportar_web.py` → `web/public/dados/*.json` → página. O exportador só usa a biblioteca padrão do Python e para com erro se algum recorte não somar o total da gold. As frases que dependem de um resultado ("acima da média", "mais que o dobro") são condicionais no código, então um dado novo não deixa o texto mentindo.

- **Mapa em grade, não por município.** O mapa divide o país em quadrados de 0,5° (`grade_mapa` em `src/analise.py`, saída em `resultados/fase3_grade_mapa.csv`) e usa a mesma comparação pelo intervalo, com o mesmo mínimo de 100 acidentes. Quadrados abaixo do mínimo aparecem apagados em vez de pintados, para não parecerem um resultado. Só entram acidentes com coordenada válida, por isso a média do mapa é calculada à parte.
- **Cor só para a comparação.** Vermelho é acima da média, azul abaixo e cinza indistinguível, sempre com legenda e com o selo escrito no explorador. A paleta é divergente e foi validada para daltonismo nos fundos claro e escuro. Âmbar e verde aparecem só no cenário (a faixa da pista e as placas), nunca num dado.
- **As duas contas em todo gráfico.** Cada gráfico tem o botão "Só com vítima", que troca a proporção, o intervalo e a média pelos da segunda conta.
- **Movimento.** GSAP ScrollTrigger fixa a seção e move os cards na horizontal enquanto a página rola; Lenis suaviza a rolagem. Com `prefers-reduced-motion`, ou em tela menor que 900 × 620 px, os cards ficam empilhados e nada se move sozinho. Em tela estreita os gráficos são desenhados na largura real, para o texto não encolher.

Numa entrevista, eu diria: "A página é a última camada do pipeline. Ela lê os mesmos arquivos que os documentos citam, e o exportador falha se os números não fecharem."

## Testes

São 152 testes em `tests/`, rodando no container. Para conferir que eles reprovam quando devem, estraguei regras de propósito e voltei o código depois: `grave` sem feridos graves, `total_envolvidos` sem ignorados, a leitura sem `escape='"'`, a expressão da hora aceitando `25:99:00`, a regra de coerência aceitando "Com Vítimas Feridas" com morto a gold do modelo com a coluna `mortos` e a análise ordenada pela proporção em vez do limite inferior do intervalo. Em todos os casos os testes da regra falharam.

## Revisão de código

Depois da primeira versão da Fase 1, o código passou por uma revisão. O que mudou por causa dela:

- `id` nulo ou repetido não é mais deduplicado em silêncio: para o pipeline;
- a bronze passou de `overwrite` para `append`, e a silver usa a ingestão mais recente de cada arquivo. Com `overwrite`, a deduplicação por ingestão mais recente não tinha efeito nenhum;
- formatos conferidos por expressão regular antes do `try_cast`;
- `escape='"'` na leitura do CSV;
- `_ingerido_em` em UTC explícito;
- `implantar.sh` grava os arquivos temporários em `dist/` (o `databricks.exe` do Windows não enxerga o `/tmp` do Git Bash) e gera a conferência do Databricks por código;
- números deste documento sem arquivo em `resultados/` foram tirados.
