"""Camada silver: limpa, tipada, uma linha por ocorrência.

Cada regra aqui veio de algo medido na Fase 0, na primeira execução da silver
ou na revisão de código (docs/validacao-fonte.md e docs/explicacao.md):
- usa só a ingestão mais recente de cada arquivo (a bronze acumula versões);
- "NA" e texto vazio viram nulo;
- id em notação científica ("1e+05") vira inteiro, com `id_corrigido = true`;
- vírgula decimal em km, latitude e longitude;
- coordenada fora do Brasil vira nula, com `coord_valida = false`;
- classificação nula é derivada das contagens, com `classificacao_imputada = true`;
- `total_envolvidos` substitui a coluna `pessoas`, que não fecha com a soma;
- `serie_estavel` marca o período depois da quebra de abril de 2018.

Antes de transformar, `validar_bronze` para o pipeline se algum valor estiver
fora do formato esperado, se faltar campo obrigatório ou se um id se repetir.
A silver não escolhe entre linhas repetidas: id repetido é erro da fonte.
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

INTEIROS = ["br", *CONTAGENS]
DECIMAIS = ["km", "latitude", "longitude"]

# Campos que a Fase 0 achou sempre preenchidos e sem os quais a linha não serve.
# Latitude e longitude podem faltar: a linha fica com coord_valida = false.
OBRIGATORIOS = ["id", "data_inversa", "horario", "uf", "br", "km", *CONTAGENS]

# Formatos estritos. try_cast sozinho aceita coisas que não estão na fonte:
# "2025" vira 2025-01-01, "NaN" vira NaN, "-1" vira -1.
RE_INTEIRO = r"^\d+$"
RE_NOTACAO_CIENTIFICA = r"^\d+(\.\d+)?[eE]\+\d+$"
RE_DECIMAL = r"^-?\d+(,\d+)?$"
RE_DATA = r"^\d{4}-\d{2}-\d{2}$"
RE_HORA = r"^([01]\d|2[0-3]):[0-5]\d:[0-5]\d$"


class BronzeInvalida(ValueError):
    """A bronze tem valor fora do formato, campo obrigatório vazio ou id repetido."""


def _texto(c: str) -> Column:
    v = F.trim(F.col(c))
    return F.when((v == "") | (v == "NA"), None).otherwise(v)


def _inteiro(c: str) -> Column:
    v = _texto(c)
    return F.when(v.rlike(RE_INTEIRO), v.try_cast("int"))


def _decimal(c: str) -> Column:
    v = _texto(c)
    return F.when(v.rlike(RE_DECIMAL), F.regexp_replace(v, ",", ".").try_cast("double"))


def _data() -> Column:
    v = _texto("data_inversa")
    return F.when(v.rlike(RE_DATA), v.try_cast("date"))  # 2025-02-30 também vira nulo


def _horario() -> Column:
    v = _texto("horario")
    return F.when(v.rlike(RE_HORA), v)


def _id() -> Column:
    """id como inteiro. Alguns arquivos trazem o id redondo em notação científica
    ("1e+05" para 100000), jeito de CSV gravado pelo R. Converte via double só
    se o resultado for inteiro exato.
    """
    v = _texto("id")
    cientifico = v.try_cast("double")
    return (F.when(v.rlike(RE_INTEIRO), v.try_cast("long"))
             .when(v.rlike(RE_NOTACAO_CIENTIFICA) & (cientifico == F.floor(cientifico)),
                   cientifico.cast("long")))


def dentro_do_brasil(lat: Column, lon: Column) -> Column:
    """Mesma regra de src.regras.dentro_do_brasil, em Column (testado que batem)."""
    continente = lat.between(LAT_MIN, LAT_MAX) & lon.between(LON_MIN, LON_MAX)
    noronha = lat.between(NORONHA[0], NORONHA[1]) & lon.between(NORONHA[2], NORONHA[3])
    return F.coalesce(continente | noronha, F.lit(False))


def ultima_ingestao(bronze: DataFrame) -> DataFrame:
    """Só as linhas da ingestão mais recente de cada arquivo (ano).

    Se um ano foi ingerido duas vezes, vale a versão mais nova do arquivo
    inteiro. Não se mistura linha de uma versão com linha de outra.
    """
    janela = Window.partitionBy("_ano_arquivo")
    return (bronze
            .withColumn("_mais_recente", F.max("_ingerido_em").over(janela))
            .where(F.col("_ingerido_em") == F.col("_mais_recente"))
            .drop("_mais_recente"))


def problemas_por_linha(bronze: DataFrame) -> DataFrame:
    """Linhas com valor fora do formato esperado ou campo obrigatório vazio.

    Na fonte real de 2017 a 2025 isso dá zero (depois da correção do id em
    notação científica). Se der mais que zero, a fonte mudou e o pipeline
    para, em vez de transformar o valor em nulo calado.
    """
    convertidos = {"id": _id(), "data_inversa": _data(), "horario": _horario()}
    convertidos |= {c: _inteiro(c) for c in INTEIROS}
    convertidos |= {c: _decimal(c) for c in DECIMAIS}

    problemas = [F.when(_texto(c).isNotNull() & conv.isNull(), F.lit(f"{c}: formato"))
                 for c, conv in convertidos.items()]
    problemas += [F.when(_texto(c).isNull(), F.lit(f"{c}: vazio")) for c in OBRIGATORIOS]
    return (ultima_ingestao(bronze)
            .withColumn("problemas", F.array_compact(F.array(*problemas)))
            .where(F.size("problemas") > 0)
            .select("id", "_arquivo_origem", "problemas"))


def ids_repetidos(bronze: DataFrame) -> DataFrame:
    """ids (já convertidos) que aparecem mais de uma vez na ingestão vigente."""
    return (ultima_ingestao(bronze)
            .select(_id().alias("id"), "_arquivo_origem")
            .where(F.col("id").isNotNull())
            .groupBy("id")
            .agg(F.count("*").alias("vezes"),
                 F.array_sort(F.collect_set("_arquivo_origem")).alias("arquivos"))
            .where("vezes > 1"))


def validar_bronze(bronze: DataFrame) -> None:
    """Para o pipeline se a bronze vigente não puder virar silver sem perda."""
    n_problemas = problemas_por_linha(bronze).count()
    n_repetidos = ids_repetidos(bronze).count()
    if n_problemas or n_repetidos:
        raise BronzeInvalida(
            f"{n_problemas} linhas com problema de formato ou campo vazio e "
            f"{n_repetidos} ids repetidos. Ver problemas_por_linha e ids_repetidos.")


def transformar(bronze: DataFrame) -> DataFrame:
    """Bronze -> silver. Não faz ação (count, collect): só descreve a transformação.

    Supõe que `validar_bronze` passou; sem isso, valor inválido vira nulo.
    """
    df = ultima_ingestao(bronze).select(
        _id().alias("id"),
        _texto("id").rlike(RE_NOTACAO_CIENTIFICA).alias("id_corrigido"),
        _data().alias("data"),
        _horario().alias("horario"),
        *[_texto(c).alias(c) for c in TEXTOS],
        *[_inteiro(c).alias(c) for c in INTEIROS],
        *[_decimal(c).alias(c) for c in DECIMAIS],
        "_arquivo_origem", "_ano_arquivo", "_ingerido_em",
    )

    coord_ok = dentro_do_brasil(F.col("latitude"), F.col("longitude"))
    classif = (F.when(F.col("classificacao_acidente").isNotNull(), F.col("classificacao_acidente"))
               .when(F.col("mortos") > 0, F.lit(CLASSIF_FATAL))
               .when(F.col("feridos") > 0, F.lit(CLASSIF_FERIDAS))
               .otherwise(F.lit(CLASSIF_SEM)))

    return (df
            .withColumnRenamed("condicao_metereologica", "condicao_meteorologica")
            .withColumn("dia_semana", F.lower("dia_semana"))
            .withColumn("ano", F.year("data"))
            .withColumn("mes", F.month("data"))
            .withColumn("hora", F.substring("horario", 1, 2).cast("int"))
            .withColumn("coord_valida", coord_ok)
            .withColumn("latitude", F.when(coord_ok, F.col("latitude")))
            .withColumn("longitude", F.when(coord_ok, F.col("longitude")))
            .withColumn("classificacao_imputada", F.col("classificacao_acidente").isNull())
            .withColumn("classificacao", classif)
            .withColumn("total_envolvidos",
                        F.col("mortos") + F.col("feridos") + F.col("ilesos") + F.col("ignorados"))
            .withColumn("grave", (F.col("mortos") > 0) | (F.col("feridos_graves") > 0))
            .withColumn("serie_estavel", F.col("data") >= F.lit(INICIO_SERIE_ESTAVEL)))
