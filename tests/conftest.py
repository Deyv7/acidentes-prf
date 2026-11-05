"""Spark local com Delta para os testes. Não usa Databricks nem internet
(depois que os jars do Delta estão no cache do Ivy)."""
from __future__ import annotations

import pytest
from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

from src.regras import COLUNAS_FONTE


@pytest.fixture(scope="session")
def spark(tmp_path_factory):
    armazem = tmp_path_factory.mktemp("warehouse")
    construtor = (SparkSession.builder
                  .master("local[1]")
                  .appName("testes-acidentes-prf")
                  .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
                  .config("spark.sql.catalog.spark_catalog",
                          "org.apache.spark.sql.delta.catalog.DeltaCatalog")
                  .config("spark.sql.warehouse.dir", str(armazem))
                  .config("spark.sql.shuffle.partitions", "1")
                  .config("spark.sql.session.timeZone", "America/Sao_Paulo")
                  .config("spark.ui.enabled", "false"))
    sessao = configure_spark_with_delta_pip(construtor).getOrCreate()
    yield sessao
    sessao.stop()


# Uma linha "boa", copiada do formato real de 2025 (id 652493). Os testes
# alteram só o campo que interessa a cada caso.
LINHA_BASE = {
    "id": "652493", "data_inversa": "2025-01-01", "dia_semana": "quarta-feira",
    "horario": "06:20:00", "uf": "SP", "br": "116", "km": "225", "municipio": "GUARULHOS",
    "causa_acidente": "Reação tardia ou ineficiente do condutor", "tipo_acidente": "Tombamento",
    "classificacao_acidente": "Com Vítimas Feridas", "fase_dia": "Pleno dia",
    "sentido_via": "Decrescente", "condicao_metereologica": "Céu Claro", "tipo_pista": "Múltipla",
    "tracado_via": "Reta;Declive", "uso_solo": "Sim", "pessoas": "2", "mortos": "0",
    "feridos_leves": "1", "feridos_graves": "0", "ilesos": "0", "ignorados": "1", "feridos": "1",
    "veiculos": "2", "latitude": "-23,48586772", "longitude": "-46,54075317",
    "regional": "SPRF-SP", "delegacia": "DEL01-SP", "uop": "UOP01-DEL01-SP",
}

NUMERICAS_SEM_ASPAS = {"id", "br", "km", "pessoas", "mortos", "feridos_leves", "feridos_graves",
                       "ilesos", "ignorados", "feridos", "veiculos", "latitude", "longitude",
                       "data_inversa"}


def linha(**mudancas) -> dict:
    return {**LINHA_BASE, **mudancas}


def escrever_csv_prf(caminho, linhas: list[dict], colunas: list[str] = COLUNAS_FONTE) -> str:
    """Grava no mesmo formato da PRF: latin-1, ';', aspas no texto, CRLF, NA sem aspas."""
    def campo(c, v):
        if v == "NA" or c in NUMERICAS_SEM_ASPAS:
            return v
        return f'"{v}"'
    texto = ";".join(f'"{c}"' for c in colunas) + "\r\n"
    for r in linhas:
        texto += ";".join(campo(c, r[c]) for c in colunas) + "\r\n"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(texto.encode("latin-1"))
    return str(caminho)
