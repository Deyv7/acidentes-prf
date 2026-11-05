"""Análise: onde e quando os acidentes graves acontecem, a partir da gold.

A medida é a proporção de graves entre os acidentes de um recorte (a fonte
não tem volume de tráfego, então contagem não é risco). Cada valor de um
recorte é comparado com a média do recorte inteiro:

- "acima": o intervalo de 95% inteiro está acima da média;
- "abaixo": o intervalo inteiro está abaixo da média;
- "indistinguível": o intervalo contém a média;
- "amostra pequena": menos de N_MIN ocorrências, não é comparado.

Robustez: a mesma comparação é feita com a % de graves entre os acidentes
com vítima (`comparacao_com_vitima`). Se um lugar registra menos acidentes
sem vítima, a % de graves sobe sem que os acidentes sejam mais graves; entre
os com vítima, esse efeito some.

A ordem é pelo limite inferior do intervalo (ic95_inf): "pelo menos X% de
graves, com 95% de confiança". Ordenar pela proporção pura colocaria no topo
municípios com 2 acidentes e 2 graves.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from src.gold import LISTA_ANTIGA
from src.regras import ANOS_ANALISE

# Mínimo de ocorrências para um valor ser comparado. Com 100 ocorrências e
# 28% de graves, o intervalo de 95% tem cerca de ±9 pontos percentuais.
N_MIN = 100


def media_do_recorte(agregado: DataFrame) -> DataFrame:
    """% de graves de cada recorte inteiro (sem o grupo da lista antiga de causas),
    entre todos os acidentes e entre os com vítima."""
    return (agregado.where(F.col("valor") != LISTA_ANTIGA)
            .groupBy("recorte")
            .agg((F.sum("graves") / F.sum("ocorrencias")).alias("media_recorte"),
                 (F.sum("graves") / F.sum("com_vitima")).alias("media_recorte_com_vitima")))


def _comparacao(n: str, inf: str, sup: str, media: str, n_min: int):
    return (F.when(F.col("valor") == LISTA_ANTIGA, F.lit("fora da comparação"))
            .when(F.col(n) < n_min, F.lit("amostra pequena"))
            .when(F.col(inf) > F.col(media), F.lit("acima"))
            .when(F.col(sup) < F.col(media), F.lit("abaixo"))
            .otherwise(F.lit("indistinguível")))


def comparar(agregado: DataFrame, n_min: int = N_MIN) -> DataFrame:
    """Agregado com a média do recorte, a comparação e a posição dentro do recorte."""
    comparacao = _comparacao("ocorrencias", "ic95_inf", "ic95_sup", "media_recorte", n_min)
    comparacao_v = _comparacao("com_vitima", "ic95_inf_com_vitima", "ic95_sup_com_vitima",
                               "media_recorte_com_vitima", n_min)
    comparaveis = F.col("comparacao").isin("acima", "abaixo", "indistinguível")
    ordem = Window.partitionBy("recorte", comparaveis).orderBy(
        F.col("ic95_inf").desc(), F.col("ocorrencias").desc(), F.col("valor"))
    return (agregado.join(media_do_recorte(agregado), "recorte")
            .withColumn("comparacao", comparacao)
            .withColumn("comparacao_com_vitima", comparacao_v)
            .withColumn("posicao", F.when(comparaveis, F.row_number().over(ordem))))


def resumo(comparado: DataFrame) -> DataFrame:
    """Por recorte: quantos valores, quantos comparáveis, acima, abaixo."""
    return (comparado.groupBy("recorte", "media_recorte").agg(
        F.count("*").alias("valores"),
        F.sum(F.col("posicao").isNotNull().cast("int")).alias("comparaveis"),
        F.sum((F.col("comparacao") == "acima").cast("int")).alias("acima"),
        F.sum((F.col("comparacao") == "abaixo").cast("int")).alias("abaixo"),
        F.sum((F.col("comparacao") == "indistinguível").cast("int")).alias("indistinguiveis"),
        # quantos "acima" ou "abaixo" ficam do mesmo lado entre os acidentes com vítima
        F.sum((F.col("comparacao").isin("acima", "abaixo")
               & (F.col("comparacao") == F.col("comparacao_com_vitima"))).cast("int"))
         .alias("mesmo_lado_com_vitima"),
        F.sum("ocorrencias").alias("ocorrencias"),
        F.sum(F.when(F.col("posicao").isNotNull(), F.col("ocorrencias"))).alias("ocorrencias_comparaveis"),
    ).orderBy("recorte"))


def categorias_por_ano(silver: DataFrame, coluna: str) -> DataFrame:
    """Contagem de cada valor original de uma coluna por ano (evidência da troca de lista)."""
    return (silver.where(F.col("ano").isin(ANOS_ANALISE))
            .groupBy(F.lit(coluna).alias("coluna"), F.col(coluna).alias("valor"), "ano")
            .count())


def transicao_por_mes(silver: DataFrame, coluna: str, anos_antes: list[int],
                      anos_depois: list[int], anos_mostrados: list[int]) -> DataFrame:
    """Por mês, quantas ocorrências usam um valor que só existe na lista antiga.

    "Só da lista antiga" = aparece em `anos_antes` e nunca em `anos_depois`.
    A lista sai do próprio dado, não de uma lista escrita à mão. Não há a
    conta inversa ("só da lista nova") porque vários nomes novos já aparecem
    uma ou duas vezes em 2019 e 2020, e a conta ficaria enganosa.
    """
    def valores(anos):
        return {r[0] for r in silver.where(F.col("ano").isin(anos)).select(coluna).distinct().collect()}
    antes, depois = valores(anos_antes), valores(anos_depois)
    so_antiga = sorted(antes - depois - {None})
    return (silver.where(F.col("ano").isin(anos_mostrados))
            .groupBy(F.lit(coluna).alias("coluna"), "ano", "mes")
            .agg(F.count("*").alias("ocorrencias"),
                 F.sum(F.col(coluna).isin(so_antiga).cast("int")).alias("valor_so_da_lista_antiga"))
            .orderBy("ano", "mes"))
