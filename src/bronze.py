"""Camada bronze: o arquivo como veio, mais a informação de onde ele veio.

Nenhuma coluna da fonte é convertida, renomeada ou limpa aqui. Tudo é lido
como texto, inclusive "NA", para que a bronze seja uma cópia fiel do CSV e a
silver possa ser refeita a qualquer momento a partir dela.

A bronze é acumulativa: cada ingestão acrescenta linhas com o seu
`_ingerido_em`. A PRF republica arquivos de anos anteriores (o de 2024 foi
refeito em setembro de 2026), então a bronze guarda as versões e a silver usa
a mais recente de cada arquivo.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

from src.regras import ANO_FINAL, ANO_INICIAL, COLUNAS_FONTE

# Esquema explícito: 30 colunas de texto. Sem inferSchema, o Spark não
# "adivinha" tipos e não muda nada do que está no arquivo.
ESQUEMA_FONTE = StructType([StructField(c, StringType(), True) for c in COLUNAS_FONTE])

RE_CSV = re.compile(r"^datatran(\d{4})\.csv$")
RE_ZIP = re.compile(r"^datatran(\d{4})\.zip$")
RE_INGESTAO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class LayoutInesperado(ValueError):
    """O cabeçalho do CSV não é o layout conhecido da PRF."""


def zips_do_recorte(nomes: list[str], ano_inicial: int = ANO_INICIAL,
                    ano_final: int = ANO_FINAL) -> list[str]:
    """Dos nomes de arquivo de uma pasta, os ZIPs `datatran<ano>.zip` do recorte.

    Um ZIP de 2026 esquecido no volume não entra; um arquivo com outro nome
    também não.
    """
    escolhidos = []
    for n in nomes:
        m = RE_ZIP.match(n)
        if m and ano_inicial <= int(m.group(1)) <= ano_final:
            escolhidos.append(n)
    return sorted(escolhidos)


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


def conferir_nome(caminho_csv: str | Path) -> int:
    """Devolve o ano do nome `datatran<ano>.csv` ou falha com mensagem clara."""
    nome = Path(caminho_csv).name
    m = RE_CSV.match(nome)
    if not m:
        raise ValueError(f"{caminho_csv}: nome fora do padrão datatran<ano>.csv")
    return int(m.group(1))


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

    `escape='"'`: no CSV padrão, aspas dentro de um campo vêm dobradas.
    O padrão do Spark é a barra invertida, que guardaria as aspas dobradas
    na bronze e quebraria a leitura de um campo terminado em barra invertida.
    """
    df = (spark.read
          .option("header", "true")
          .option("sep", ";")
          .option("quote", '"')
          .option("escape", '"')
          .option("encoding", "ISO-8859-1")
          .option("mode", "FAILFAST")  # linha com campo a mais ou a menos: erro
          .schema(ESQUEMA_FONTE)
          .csv(caminhos))
    return df


def adicionar_metadados(df: DataFrame, ingerido_em: str) -> DataFrame:
    """Acrescenta de onde veio cada linha e quando ela foi ingerida.

    `ingerido_em` precisa vir em UTC com o "Z" no fim (ex.: 2026-11-04T12:00:00Z).
    Sem o fuso explícito, o Spark interpreta o texto no fuso da sessão, e o
    mesmo instante seria gravado diferente no Spark local (America/Sao_Paulo)
    e no Databricks (UTC).

    `_metadata.file_path` é a coluna oculta que o Spark preenche com o arquivo
    de origem; funciona no Spark local e no Databricks.
    """
    if not RE_INGESTAO_UTC.match(ingerido_em):
        raise ValueError(f"ingerido_em deve ser UTC no formato AAAA-MM-DDTHH:MM:SSZ, veio {ingerido_em!r}")
    caminho = F.col("_metadata.file_path")
    return (df
            .withColumn("_arquivo_origem", F.regexp_extract(caminho, r"([^/]+)$", 1))
            .withColumn("_ano_arquivo",
                        F.regexp_extract(caminho, r"datatran(\d{4})\.csv$", 1).cast("int"))
            .withColumn("_ingerido_em",
                        F.to_timestamp(F.lit(ingerido_em), "yyyy-MM-dd'T'HH:mm:ssX")))


def agora_utc() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def montar_bronze(spark: SparkSession, caminhos_csv: list[str], ingerido_em: str) -> DataFrame:
    """Confere nome e cabeçalho de cada arquivo e devolve a bronze de todos eles."""
    for c in caminhos_csv:
        conferir_nome(c)
        conferir_cabecalho(c)
    return adicionar_metadados(ler_csv_prf(spark, caminhos_csv), ingerido_em)
