"""Camada gold: tabelas prontas para uma pergunta.

- `gold_ocorrencias_modelo`: uma linha por ocorrência de 2019 a 2025, com o
  alvo `grave` e as colunas que um modelo de gravidade pode usar. Nenhuma
  coluna de desfecho (contagens de vítimas, classificação) entra, porque elas
  são o próprio alvo escrito de outro jeito.
- `gold_graves_por_recorte`: para cada recorte (UF, BR, trecho, hora...),
  ocorrências, graves e a proporção de graves com intervalo de Wilson de 95%.
  Contagem de acidentes não é risco (não há volume de tráfego); a proporção
  de graves entre os acidentes do recorte é a taxa com denominador honesto.

Recorte de anos: 2019 a 2025 (anos completos depois da quebra de abril de
2018). O filtro é por `ano`, não por `serie_estavel`, para não entrar o fim
de 2018 e deixar um ano pela metade.
"""
from __future__ import annotations

from functools import reduce

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from src.regras import ANOS_ANALISE, Z_95

ALVO = "grave"
IDENTIFICACAO = ["id", "data"]

# Contexto: onde, quando e em que via/clima. Conhecido antes do acidente.
CONTEXTO = ["ano", "mes", "dia_semana", "dia_semana_num", "fim_de_semana", "hora", "fase_dia",
            "uf", "br", "km", "trecho_km", "municipio", "latitude", "longitude", "coord_valida",
            "sentido_via", "tipo_pista", "tracado_via", "uso_solo", "condicao_meteorologica"]

# Dinâmica: o que o policial registrou sobre o acidente em si. Não é desfecho
# (não diz quantos morreram), mas só existe depois do acidente. Fica separado
# para o modelo poder ser treinado com e sem essas colunas.
DINAMICA = ["causa_acidente", "tipo_acidente", "veiculos"]

# Desfecho: nunca entra na gold do modelo (vazamento do alvo).
DESFECHO = ["classificacao_acidente", "classificacao", "classificacao_imputada", "pessoas",
            "mortos", "feridos_leves", "feridos_graves", "ilesos", "ignorados", "feridos",
            "total_envolvidos"]

TAMANHO_TRECHO_KM = 10
NAO_INFORMADO = "(não informado)"


class GoldInvalida(ValueError):
    """A gold não cumpre o contrato (id único, anos do recorte, alvo preenchido)."""


def preparar(silver: DataFrame) -> DataFrame:
    """Silver dos anos da análise com as colunas derivadas que a gold usa."""
    return (silver
            .where(F.col("ano").isin(ANOS_ANALISE))
            .withColumn("dia_semana_num", F.dayofweek("data"))  # 1 = domingo
            .withColumn("fim_de_semana", F.dayofweek("data").isin(1, 7))
            .withColumn("trecho_km",
                        (F.floor(F.col("km") / TAMANHO_TRECHO_KM) * TAMANHO_TRECHO_KM).cast("int")))


def montar_modelo(silver: DataFrame) -> DataFrame:
    return preparar(silver).select(*IDENTIFICACAO, *CONTEXTO, *DINAMICA, ALVO)


def verificar_modelo(modelo: DataFrame) -> dict:
    """Contrato da gold do modelo. Devolve as contagens; falha se algo não cumprir."""
    r = modelo.agg(
        F.count("*").alias("linhas"),
        F.count_distinct("id").alias("ids_distintos"),
        F.sum(F.col("id").isNull().cast("int")).alias("id_nulo"),
        F.sum((~F.col("ano").isin(ANOS_ANALISE)).cast("int")).alias("fora_dos_anos"),
        F.sum(F.col(ALVO).isNull().cast("int")).alias("alvo_nulo"),
    ).collect()[0].asDict()
    vazam = sorted(set(DESFECHO) & set(modelo.columns))
    if (r["linhas"] != r["ids_distintos"] or r["id_nulo"] or r["fora_dos_anos"]
            or r["alvo_nulo"] or vazam):
        raise GoldInvalida(f"gold do modelo fora do contrato: {r}, colunas de desfecho: {vazam}")
    return r


def intervalo_wilson(graves: Column, n: Column, z: float = Z_95) -> tuple[Column, Column]:
    """Intervalo de Wilson para graves/n. Mesmo cálculo de src.regras.wilson.

    Em double: com n inteiro, `n * n` estoura o int a partir de n = 46.341
    e o Spark 4 (modo ANSI) para com ARITHMETIC_OVERFLOW.
    """
    graves, n = graves.cast("double"), n.cast("double")
    p = graves / n
    denom = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / denom
    meia = z * F.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return F.greatest(F.lit(0.0), centro - meia), F.least(F.lit(1.0), centro + meia)


def _txt(c: str) -> Column:
    return F.coalesce(F.col(c).cast("string"), F.lit(NAO_INFORMADO))


def _br() -> Column:
    return F.concat(F.lit("BR-"), F.lpad(F.col("br").cast("string"), 3, "0"))


def recortes() -> dict[str, Column]:
    """Nome do recorte -> expressão que dá o valor (texto) de cada ocorrência.

    O trecho leva a UF junto: o km de uma BR recomeça em cada estado, então
    "BR-116 km 220" sozinho é ambíguo. O recorte "br" é a rodovia inteira.
    """
    return {
        "ano": _txt("ano"),
        "uf": _txt("uf"),
        "br": _br(),
        "trecho_10km": F.concat_ws(" ", _txt("uf"), _br(), F.lit("km"),
                                   F.concat(F.col("trecho_km").cast("string"), F.lit("-"),
                                            (F.col("trecho_km") + TAMANHO_TRECHO_KM).cast("string"))),
        "municipio": F.concat_ws("/", _txt("municipio"), _txt("uf")),
        "hora": F.lpad(F.col("hora").cast("string"), 2, "0"),
        "dia_semana": _txt("dia_semana"),
        "mes": F.lpad(F.col("mes").cast("string"), 2, "0"),
        "fase_dia": _txt("fase_dia"),
        "condicao_meteorologica": _txt("condicao_meteorologica"),
        "tipo_pista": _txt("tipo_pista"),
        "causa_acidente": _txt("causa_acidente"),
        "tipo_acidente": _txt("tipo_acidente"),
    }


def agregar(silver: DataFrame) -> DataFrame:
    """Uma linha por (recorte, valor): ocorrências, graves, com morto, % graves e IC 95%."""
    base = preparar(silver)
    partes = [
        base.select(F.lit(nome).alias("recorte"), expr.alias("valor"), ALVO, "mortos")
        for nome, expr in recortes().items()
    ]
    longo = reduce(DataFrame.unionByName, partes)
    agg = (longo.groupBy("recorte", "valor").agg(
        F.count("*").alias("ocorrencias"),
        F.sum(F.col(ALVO).cast("int")).alias("graves"),
        F.sum((F.col("mortos") > 0).cast("int")).alias("com_morto"),
        F.sum("mortos").alias("mortos"),
    ))
    inf, sup = intervalo_wilson(F.col("graves"), F.col("ocorrencias"))
    return (agg
            .withColumn("pct_graves", F.col("graves") / F.col("ocorrencias"))
            .withColumn("ic95_inf", inf)
            .withColumn("ic95_sup", sup))
