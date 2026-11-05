"""A bronze tem que ser uma cópia fiel do CSV: mesmas colunas, mesmo texto."""
import zipfile
from datetime import datetime, timezone

import pytest
from pyspark.errors import PySparkException
from py4j.protocol import Py4JJavaError

from src.bronze import (LayoutInesperado, conferir_cabecalho, extrair_zip,
                        montar_bronze, zips_do_recorte)
from src.regras import COLUNAS_FONTE
from tests.conftest import INGESTAO, escrever_csv_prf, linha

# Erro do Spark ao ler linha malformada com FAILFAST. Dependendo do caminho
# (JVM ou Python), vem como um ou outro tipo.
ERRO_SPARK = (PySparkException, Py4JJavaError)


def test_le_texto_como_veio(spark, tmp_path):
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha()])
    r = montar_bronze(spark, [csv], INGESTAO).collect()[0]

    # acento do latin-1 preservado
    assert r["causa_acidente"] == "Reação tardia ou ineficiente do condutor"
    # ';' dentro das aspas não quebra a coluna
    assert r["tracado_via"] == "Reta;Declive"
    # nada é convertido: vírgula decimal continua texto
    assert r["latitude"] == "-23,48586772"
    # o CRLF não deixa '\r' grudado na última coluna
    assert r["uop"] == "UOP01-DEL01-SP"


def test_aspas_dobradas_dentro_do_campo(spark, tmp_path):
    # padrão CSV: aspas dentro do campo vêm dobradas. Sem escape='"', o Spark
    # usaria '\' como escape e guardaria as aspas dobradas na bronze.
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha(municipio='SAO ""X"" Y')])
    r = montar_bronze(spark, [csv], INGESTAO).collect()[0]
    assert r["municipio"] == 'SAO "X" Y'
    assert r["uop"] == "UOP01-DEL01-SP"


def test_barra_invertida_no_fim_do_campo(spark, tmp_path):
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha(municipio="SAO X\\")])
    r = montar_bronze(spark, [csv], INGESTAO).collect()[0]
    assert r["municipio"] == "SAO X\\"
    assert r["causa_acidente"] == "Reação tardia ou ineficiente do condutor"


def test_na_continua_texto_na_bronze(spark, tmp_path):
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha(classificacao_acidente="NA")])
    r = montar_bronze(spark, [csv], INGESTAO).collect()[0]
    assert r["classificacao_acidente"] == "NA"


def test_todas_as_colunas_sao_texto_e_metadados_existem(spark, tmp_path):
    csv = escrever_csv_prf(tmp_path / "datatran2024.csv", [linha()])
    df = montar_bronze(spark, [csv], INGESTAO)
    tipos = dict(df.dtypes)
    assert all(tipos[c] == "string" for c in COLUNAS_FONTE)
    r = df.collect()[0]
    assert r["_arquivo_origem"] == "datatran2024.csv"
    assert r["_ano_arquivo"] == 2024


def test_ingerido_em_e_utc_independente_do_fuso_da_sessao(spark, tmp_path):
    # a sessão de teste está em America/Sao_Paulo (conftest), como o Spark local
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha()])
    r = montar_bronze(spark, [csv], "2026-11-04T12:00:00Z").collect()[0]
    esperado = datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
    assert r["_ingerido_em"].astimezone(timezone.utc) == esperado


def test_ingerido_em_sem_fuso_e_recusado(spark, tmp_path):
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha()])
    with pytest.raises(ValueError, match="UTC"):
        montar_bronze(spark, [csv], "2026-11-04T12:00:00")


def test_le_varios_anos_juntos(spark, tmp_path):
    a = escrever_csv_prf(tmp_path / "a" / "datatran2024.csv", [linha(id="1")])
    b = escrever_csv_prf(tmp_path / "b" / "datatran2025.csv", [linha(id="2"), linha(id="3")])
    df = montar_bronze(spark, [a, b], INGESTAO)
    anos = {r["id"]: r["_ano_arquivo"] for r in df.collect()}
    assert anos == {"1": 2024, "2": 2025, "3": 2025}


def test_nome_fora_do_padrao_falha_com_mensagem_clara(spark, tmp_path):
    csv = escrever_csv_prf(tmp_path / "acidentes2025.csv", [linha()])
    with pytest.raises(ValueError, match="datatran<ano>.csv"):
        montar_bronze(spark, [csv], INGESTAO)


def test_zips_do_recorte():
    nomes = ["datatran2016.zip", "datatran2017.zip", "datatran2025.zip", "datatran2026.zip",
             "acidentes2025.zip", "datatran2020.csv", "leia-me.txt"]
    assert zips_do_recorte(nomes) == ["datatran2017.zip", "datatran2025.zip"]


def test_cabecalho_com_coluna_a_menos_falha(tmp_path):
    colunas = [c for c in COLUNAS_FONTE if c != "feridos_graves"]
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha()], colunas=colunas)
    with pytest.raises(LayoutInesperado, match="feridos_graves"):
        conferir_cabecalho(csv)


def test_cabecalho_em_outra_ordem_falha(tmp_path):
    colunas = COLUNAS_FONTE[1:] + COLUNAS_FONTE[:1]
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha()], colunas=colunas)
    with pytest.raises(LayoutInesperado, match="ordem"):
        conferir_cabecalho(csv)


def test_linha_com_campo_a_mais_falha_na_leitura(spark, tmp_path):
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha()])
    with open(csv, "ab") as f:
        f.write(b"999;" * 31 + b"\r\n")
    with pytest.raises(ERRO_SPARK, match="(?i)malformed"):
        montar_bronze(spark, [csv], INGESTAO).collect()


def test_linha_com_campo_a_menos_falha_na_leitura(spark, tmp_path):
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha()])
    with open(csv, "ab") as f:
        f.write(b"999;2025-01-02\r\n")
    with pytest.raises(ERRO_SPARK, match="(?i)malformed"):
        montar_bronze(spark, [csv], INGESTAO).collect()


def test_extrair_zip(tmp_path):
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha()])
    zp = tmp_path / "ocorrencia_2025.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.write(csv, "datatran2025.csv")
    saida = extrair_zip(zp, tmp_path / "extraido")
    assert saida.name == "datatran2025.csv"
    assert saida.read_bytes() == open(csv, "rb").read()


def test_extrair_zip_recusa_mais_de_um_arquivo(tmp_path):
    zp = tmp_path / "x.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("a.csv", "x")
        z.writestr("b.csv", "y")
    with pytest.raises(ValueError, match="esperava 1"):
        extrair_zip(zp, tmp_path / "out")


def test_extrair_zip_nao_escreve_fora_do_destino(tmp_path):
    zp = tmp_path / "x.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("../../fora.csv", "x")
    saida = extrair_zip(zp, tmp_path / "out")
    assert saida.parent == tmp_path / "out"
