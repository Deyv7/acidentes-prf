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
from itertools import chain

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F

from src.regras import (ANOS_ANALISE, CAUSA_PADRONIZADA, INICIO_LISTA_CAUSAS,
                        TIPO_PADRONIZADO, Z_95)

ALVO = "grave"
IDENTIFICACAO = ["id", "data"]

# Contexto: onde, quando e em que via/clima. Conhecido antes do acidente.
CONTEXTO = ["ano", "mes", "dia_semana", "dia_semana_num", "fim_de_semana", "hora", "fase_dia",
            "uf", "br", "km", "trecho_km", "municipio", "latitude", "longitude", "coord_valida",
            "sentido_via", "tipo_pista", "tracado_via", "uso_solo", "condicao_meteorologica"]

# Dinâmica: o que o policial registrou sobre o acidente em si. Não é desfecho
# (não diz quantos morreram), mas só existe depois do acidente. Fica separado
# para o modelo poder ser treinado com e sem essas colunas.
# Causa e tipo entram padronizados (ver src/regras.py): a causa é nula antes
# de 2021, porque a lista antiga não tem correspondência com a nova.
DINAMICA = ["causa_padronizada", "tipo_padronizado", "veiculos"]

# Desfecho: nunca entra na gold do modelo (vazamento do alvo).
DESFECHO = ["classificacao_acidente", "classificacao", "classificacao_imputada", "pessoas",
            "mortos", "feridos_leves", "feridos_graves", "ilesos", "ignorados", "feridos",
            "total_envolvidos"]

TAMANHO_TRECHO_KM = 10
NAO_INFORMADO = "(não informado)"
LISTA_ANTIGA = f"(lista de causas anterior a {INICIO_LISTA_CAUSAS})"


class GoldInvalida(ValueError):
    """A gold não cumpre o contrato (id único, anos do recorte, alvo preenchido)."""


def _padronizar(coluna: str, mapa: dict[str, str]) -> Column:
    m = F.create_map(*[F.lit(x) for x in chain.from_iterable(mapa.items())])
    return F.coalesce(m[F.col(coluna)], F.col(coluna))


def preparar(silver: DataFrame) -> DataFrame:
    """Silver dos anos da análise com as colunas derivadas que a gold usa."""
    return (silver
            .where(F.col("ano").isin(ANOS_ANALISE))
            .withColumn("causa_padronizada",
                        F.when(F.col("ano") >= INICIO_LISTA_CAUSAS,
                               _padronizar("causa_acidente", CAUSA_PADRONIZADA)))
            .withColumn("tipo_padronizado", _padronizar("tipo_acidente", TIPO_PADRONIZADO))
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
        # 2019-2020 ficam num grupo só: a lista de causas era outra
        "causa_acidente": F.when(F.col("ano") < INICIO_LISTA_CAUSAS, F.lit(LISTA_ANTIGA))
                           .otherwise(_txt("causa_padronizada")),
        "tipo_acidente": _txt("tipo_padronizado"),
    }


def agregar(silver: DataFrame) -> DataFrame:
    """Uma linha por (recorte, valor): ocorrências, graves, com morto, % graves e IC 95%,
    e a mesma proporção calculada só entre os acidentes com vítima."""
    base = preparar(silver)
    partes = [
        base.select(F.lit(nome).alias("recorte"), expr.alias("valor"), ALVO, "mortos", "feridos")
        for nome, expr in recortes().items()
    ]
    longo = reduce(DataFrame.unionByName, partes)
    agg = (longo.groupBy("recorte", "valor").agg(
        F.count("*").alias("ocorrencias"),
        F.sum(F.col(ALVO).cast("int")).alias("graves"),
        F.sum((F.col("mortos") > 0).cast("int")).alias("com_morto"),
        F.sum("mortos").alias("mortos"),
        F.sum(((F.col("mortos") > 0) | (F.col("feridos") > 0)).cast("int")).alias("com_vitima"),
    ))
    inf, sup = intervalo_wilson(F.col("graves"), F.col("ocorrencias"))
    # Robustez: % de graves só entre acidentes com vítima. Não depende de
    # quantos acidentes sem vítima chegam a ser registrados em cada lugar.
    inf_v, sup_v = intervalo_wilson(F.col("graves"), F.col("com_vitima"))
    tem_vitima = F.col("com_vitima") > 0
    return (agg
            .withColumn("pct_graves", F.col("graves") / F.col("ocorrencias"))
            .withColumn("ic95_inf", inf)
            .withColumn("ic95_sup", sup)
            .withColumn("pct_graves_com_vitima", F.when(tem_vitima, F.col("graves") / F.col("com_vitima")))
            .withColumn("ic95_inf_com_vitima", F.when(tem_vitima, inf_v))
            .withColumn("ic95_sup_com_vitima", F.when(tem_vitima, sup_v)))
