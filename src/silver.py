"""Camada silver: limpa, tipada e deduplicada. Uma linha por ocorrência.

Cada regra aqui veio de algo medido na Fase 0 ou na primeira execução da
silver (docs/validacao-fonte.md):
- "NA" e texto vazio viram nulo;
- id em notação científica ("1e+05") vira inteiro, com `id_corrigido = true`;
- vírgula decimal em km, latitude e longitude;
- coordenada fora do Brasil vira nula, com `coord_valida = false`;
- classificação nula é derivada das contagens, com `classificacao_imputada = true`;
- `total_envolvidos` substitui a coluna `pessoas`, que não fecha com a soma;
- `serie_estavel` marca o período depois da quebra de abril de 2018.
"""
from __future__ import annotations

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

from src.regras import (CLASSIF_FATAL, CLASSIF_FERIDAS, CLASSIF_SEM, CONTAGENS,
                        INICIO_SERIE_ESTAVEL, LAT_MAX, LAT_MIN, LON_MAX, LON_MIN,
                        NORONHA)

TEXTOS = ["dia_semana", "uf", "municipio", "causa_acidente", "tipo_acidente",
          "classificacao_acidente", "fase_dia", "sentido_via", "condicao_metereologica",
          "tipo_pista", "tracado_via", "uso_solo", "regional", "delegacia", "uop"]

# Conversões de tipo. Cada uma usa try_cast: valor que não converte vira nulo,
# e `falhas_de_conversao` conta esses casos para o pipeline parar.
INTEIROS = ["br", *CONTAGENS]
DECIMAIS = ["km", "latitude", "longitude"]


def _texto(c: str) -> Column:
    v = F.trim(F.col(c))
    return F.when((v == "") | (v == "NA"), None).otherwise(v)


def _decimal(c: str) -> Column:
    return F.regexp_replace(_texto(c), ",", ".").try_cast("double")


RE_NOTACAO_CIENTIFICA = r"^\d+(\.\d+)?[eE]\+\d+$"


def _id() -> Column:
    """id como inteiro. Cinco arquivos trazem o id redondo em notação científica
    ("1e+05" para 100000, em 2018, 2019, 2020, 2021 e 2024), jeito de CSV
    gravado pelo R. Converte via double só se o resultado for inteiro exato.
    """
    v = _texto("id")
    cientifico = v.try_cast("double")
    return (F.when(v.rlike(r"^\d+$"), v.try_cast("long"))
             .when(v.rlike(RE_NOTACAO_CIENTIFICA) & (cientifico == F.floor(cientifico)),
                   cientifico.cast("long")))


def _dentro_do_brasil(lat: Column, lon: Column) -> Column:
    continente = lat.between(LAT_MIN, LAT_MAX) & lon.between(LON_MIN, LON_MAX)
    noronha = lat.between(NORONHA[0], NORONHA[1]) & lon.between(NORONHA[2], NORONHA[3])
    return F.coalesce(continente | noronha, F.lit(False))


def falhas_de_conversao(bronze: DataFrame) -> DataFrame:
    """Linhas em que um valor preenchido não converteu para o tipo esperado.

    Na fonte real isso deu zero. Se um dia der mais que zero, a fonte mudou e
    o pipeline deve parar em vez de transformar o valor em nulo calado.
    """
    checagens = {"id": _id(),
                 "data_inversa": _texto("data_inversa").try_cast("date"),
                 "horario": F.when(_texto("horario").rlike(r"^\d{2}:\d{2}:\d{2}$"), 1)}
    checagens |= {c: _texto(c).try_cast("int") for c in INTEIROS}
    checagens |= {c: _decimal(c) for c in DECIMAIS}
    falhou = [F.when(_texto(c).isNotNull() & conv.isNull(), F.lit(c)) for c, conv in checagens.items()]
    return (bronze
            .withColumn("colunas_com_falha", F.array_compact(F.array(*falhou)))
            .where(F.size("colunas_com_falha") > 0)
            .select("id", "_arquivo_origem", "colunas_com_falha"))


def transformar(bronze: DataFrame) -> DataFrame:
    """Bronze -> silver. Não faz ação (count, collect): só descreve a transformação."""
    df = bronze.select(
        _id().alias("id"),
        _texto("id").rlike(RE_NOTACAO_CIENTIFICA).alias("id_corrigido"),
        _texto("data_inversa").try_cast("date").alias("data"),
        _texto("horario").alias("horario"),
        *[_texto(c).alias(c) for c in TEXTOS],
        *[_texto(c).try_cast("int").alias(c) for c in INTEIROS],
        *[_decimal(c).alias(c) for c in DECIMAIS],
        "_arquivo_origem", "_ano_arquivo", "_ingerido_em",
    )

    coord_ok = _dentro_do_brasil(F.col("latitude"), F.col("longitude"))
    classif = (F.when(F.col("classificacao_acidente").isNotNull(), F.col("classificacao_acidente"))
               .when(F.col("mortos") > 0, F.lit(CLASSIF_FATAL))
               .when(F.col("feridos") > 0, F.lit(CLASSIF_FERIDAS))
               .otherwise(F.lit(CLASSIF_SEM)))

    df = (df
          .withColumnRenamed("condicao_metereologica", "condicao_meteorologica")
          .withColumn("dia_semana", F.lower("dia_semana"))
          .withColumn("ano", F.year("data"))
          .withColumn("mes", F.month("data"))
          .withColumn("hora", F.substring("horario", 1, 2).try_cast("int"))
          .withColumn("coord_valida", coord_ok)
          .withColumn("latitude", F.when(coord_ok, F.col("latitude")))
          .withColumn("longitude", F.when(coord_ok, F.col("longitude")))
          .withColumn("classificacao_imputada", F.col("classificacao_acidente").isNull())
          .withColumn("classificacao", classif)
          .withColumn("total_envolvidos",
                      F.col("mortos") + F.col("feridos") + F.col("ilesos") + F.col("ignorados"))
          .withColumn("grave", (F.col("mortos") > 0) | (F.col("feridos_graves") > 0))
          .withColumn("serie_estavel", F.col("data") >= F.lit(INICIO_SERIE_ESTAVEL)))

    return deduplicar(df)


def deduplicar(df: DataFrame) -> DataFrame:
    """Uma linha por id. Se o mesmo id vier duas vezes (por exemplo, o arquivo
    republicado e ingerido de novo), fica a ingestão mais recente.

    Na fonte real não há id repetido; a regra existe para reprocessamentos.
    """
    janela = Window.partitionBy("id").orderBy(F.col("_ingerido_em").desc(),
                                              F.col("_arquivo_origem").desc())
    return (df.withColumn("_ordem", F.row_number().over(janela))
              .where("_ordem = 1")
              .drop("_ordem"))
