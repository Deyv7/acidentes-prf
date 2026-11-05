"""Camada bronze: o arquivo como veio, mais a informação de onde ele veio.

Nenhuma coluna da fonte é convertida, renomeada ou limpa aqui. Tudo é lido
como texto, inclusive "NA", para que a bronze seja uma cópia fiel do CSV e a
silver possa ser refeita a qualquer momento a partir dela.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

from src.regras import COLUNAS_FONTE

# Esquema explícito: 30 colunas de texto. Sem inferSchema, o Spark não
# "adivinha" tipos e não muda nada do que está no arquivo.
ESQUEMA_FONTE = StructType([StructField(c, StringType(), True) for c in COLUNAS_FONTE])



class LayoutInesperado(ValueError):
    """O cabeçalho do CSV não é o layout conhecido da PRF."""


def extrair_zip(caminho_zip: str | Path, destino: str | Path) -> Path:
    """Extrai o único CSV de um ZIP da PRF e devolve o caminho do CSV.

    Recusa ZIP com mais de um arquivo ou com caminho que sairia do destino
    (o arquivo vem da internet e é tratado como não confiável).
    """
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(caminho_zip) as z:
        membros = [m for m in z.infolist() if not m.is_dir()]
        if len(membros) != 1:
            raise ValueError(f"{caminho_zip}: esperava 1 arquivo, achei {len(membros)}")
        nome = Path(membros[0].filename).name
        if not nome.lower().endswith(".csv"):
            raise ValueError(f"{caminho_zip}: o arquivo de dentro não é CSV ({nome})")
        saida = destino / nome
        with z.open(membros[0]) as origem, open(saida, "wb") as f:
            while bloco := origem.read(1 << 20):
                f.write(bloco)
    return saida


def conferir_cabecalho(caminho_csv: str | Path) -> None:
    """Falha se a primeira linha do CSV não tiver as 30 colunas esperadas, na ordem."""
    with open(caminho_csv, "rb") as f:
        primeira = f.readline().decode("latin-1").strip()
    colunas = [c.strip('"') for c in primeira.split(";")]
    if colunas != COLUNAS_FONTE:
        faltam = [c for c in COLUNAS_FONTE if c not in colunas]
        sobram = [c for c in colunas if c not in COLUNAS_FONTE]
        raise LayoutInesperado(
            f"{caminho_csv}: layout diferente. Faltam {faltam}, sobram {sobram}"
            + ("" if faltam or sobram else ", ordem diferente"))


def ler_csv_prf(spark: SparkSession, caminhos: str | list[str]) -> DataFrame:
    """Lê um ou mais CSVs agrupados por ocorrência da PRF como texto.

    Formato verificado na Fase 0: latin-1, separador ';', texto entre aspas,
    CRLF, nulo como NA. "NA" fica como texto: quem decide o que é nulo é a silver.
    """
    df = (spark.read
          .option("header", "true")
          .option("sep", ";")
          .option("quote", '"')
          .option("encoding", "ISO-8859-1")
          .option("mode", "FAILFAST")  # linha com campo a mais ou a menos: erro
          .schema(ESQUEMA_FONTE)
          .csv(caminhos))
    return df


def adicionar_metadados(df: DataFrame, ingerido_em: str) -> DataFrame:
    """Acrescenta de onde veio cada linha e quando ela foi ingerida.

    `_metadata.file_path` é a coluna oculta que o Spark preenche com o arquivo
    de origem; funciona no Spark local e no Databricks.
    """
    caminho = F.col("_metadata.file_path")
    return (df
            .withColumn("_arquivo_origem", F.regexp_extract(caminho, r"([^/]+)$", 1))
            .withColumn("_ano_arquivo",
                        F.regexp_extract(caminho, r"datatran(\d{4})\.csv$", 1).cast("int"))
            .withColumn("_ingerido_em", F.to_timestamp(F.lit(ingerido_em))))


def montar_bronze(spark: SparkSession, caminhos_csv: list[str], ingerido_em: str) -> DataFrame:
    """Confere o cabeçalho de cada arquivo e devolve a bronze de todos eles."""
    for c in caminhos_csv:
        conferir_cabecalho(c)
    return adicionar_metadados(ler_csv_prf(spark, caminhos_csv), ingerido_em)
