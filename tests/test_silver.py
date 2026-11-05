"""Cada regra da silver tem um caso aqui, montado a partir do que a Fase 0,
a primeira execução e a revisão de código acharam."""
from datetime import date

import pytest

from src import regras
from src.bronze import montar_bronze
from src.regras import CLASSIF_FATAL, CLASSIF_FERIDAS, CLASSIF_SEM
from src.silver import (BronzeInvalida, dentro_do_brasil, ids_repetidos,
                        problemas_por_linha, transformar, validar_bronze)
from tests.conftest import INGESTAO, escrever_csv_prf, linha


@pytest.fixture
def bronze_de(spark, tmp_path):
    """Escreve as linhas num CSV no formato da PRF e devolve a bronze."""
    contador = {"n": 0}

    def _bronze(linhas, nome="datatran2025.csv", ingerido_em=INGESTAO):
        contador["n"] += 1
        csv = escrever_csv_prf(tmp_path / str(contador["n"]) / nome, linhas)
        return montar_bronze(spark, [csv], ingerido_em)
    return _bronze


@pytest.fixture
def silver_de(bronze_de):
    """Bronze -> validação -> silver, devolvida como dict por id."""
    def _silver(linhas, **kw):
        bronze = bronze_de(linhas, **kw)
        validar_bronze(bronze)
        return {r["id"]: r for r in transformar(bronze).collect()}
    return _silver


def problemas(bronze):
    return {r["id"]: set(r["problemas"]) for r in problemas_por_linha(bronze).collect()}


# ---------- tipos e limpeza ----------

def test_tipos(silver_de):
    r = silver_de([linha()])[652493]
    assert r["data"] == date(2025, 1, 1)
    assert (r["ano"], r["mes"], r["hora"]) == (2025, 1, 6)
    assert r["br"] == 116 and r["km"] == 225.0
    assert r["latitude"] == pytest.approx(-23.48586772)
    assert r["longitude"] == pytest.approx(-46.54075317)
    assert r["mortos"] == 0 and r["feridos_leves"] == 1


def test_virgula_decimal_no_km(silver_de):
    assert silver_de([linha(km="34,9")])[652493]["km"] == pytest.approx(34.9)


def test_renomeia_coluna_com_erro_de_grafia(silver_de):
    r = silver_de([linha()])[652493]
    assert r["condicao_meteorologica"] == "Céu Claro"
    assert "condicao_metereologica" not in r.asDict()


def test_na_vira_nulo(silver_de):
    assert silver_de([linha(sentido_via="NA")])[652493]["sentido_via"] is None


def test_dia_semana_minusculo(silver_de):
    assert silver_de([linha(dia_semana="Quarta-feira")])[652493]["dia_semana"] == "quarta-feira"


def test_hora_vem_do_horario(silver_de):
    assert silver_de([linha(horario="23:59:00")])[652493]["hora"] == 23


# ---------- coordenadas ----------

@pytest.mark.parametrize("lat,lon", [
    ("0", "0"),                        # 7 casos em 2017
    ("-22,41850506", "-405,96461356"),  # vírgula decimal perdida, 2017
    ("-7", "-34"),                     # arredondado, cai no mar (Recife, 2017)
    ("NA", "NA"),                      # sem coordenada
])
def test_coordenada_invalida_vira_nula(silver_de, lat, lon):
    r = silver_de([linha(latitude=lat, longitude=lon)])[652493]
    assert r["coord_valida"] is False
    assert r["latitude"] is None and r["longitude"] is None
    # a ocorrência continua na tabela, com UF, BR e km
    assert r["uf"] == "SP" and r["br"] == 116


def test_fernando_de_noronha_e_valido(silver_de):
    # id 620583 de 2024: BR-363, km 1,5
    r = silver_de([linha(uf="PE", br="363", km="1,5",
                         latitude="-3,841072", longitude="-32,406822")])[652493]
    assert r["coord_valida"] is True
    assert r["longitude"] == pytest.approx(-32.406822)


# Pontos nos limites exatos das caixas e logo fora deles.
PONTOS = [
    (-33.76, -53.0), (-33.7601, -53.0), (5.28, -60.0), (5.2801, -60.0),
    (-10.0, -74.0), (-10.0, -74.0001), (-10.0, -34.78), (-10.0, -34.7799),
    (-3.95, -32.55), (-3.80, -32.35), (-3.9501, -32.45), (-3.87, -32.3499),
    (-3.87, -33.5),  # entre a costa e Noronha: mar
]


@pytest.mark.parametrize("lat,lon", PONTOS)
def test_caixa_do_brasil_igual_em_python_e_spark(spark, lat, lon):
    # src/regras.py (Fase 0) e src/silver.py (Spark) têm a mesma regra escrita
    # duas vezes; este teste garante que elas não divergem.
    from pyspark.sql import functions as F
    em_spark = (spark.range(1)
                .select(dentro_do_brasil(F.lit(lat), F.lit(lon)).alias("ok"))
                .collect()[0]["ok"])
    assert em_spark is regras.dentro_do_brasil(lat, lon)


# ---------- classificação, total, grave, série ----------

def test_classificacao_nula_com_morto_vira_fatal(silver_de):
    # caso real de 2025 (id 652519): classificação NA e 1 morto
    r = silver_de([linha(classificacao_acidente="NA", mortos="1", feridos="1")])[652493]
    assert r["classificacao_acidente"] is None
    assert r["classificacao"] == CLASSIF_FATAL
    assert r["classificacao_imputada"] is True


@pytest.mark.parametrize("mortos,feridos,esperado", [
    ("0", "2", CLASSIF_FERIDAS),
    ("0", "0", CLASSIF_SEM),
])
def test_classificacao_nula_sem_morto(silver_de, mortos, feridos, esperado):
    r = silver_de([linha(classificacao_acidente="NA", mortos=mortos, feridos=feridos)])[652493]
    assert r["classificacao"] == esperado


def test_classificacao_preenchida_nao_e_alterada(silver_de):
    r = silver_de([linha()])[652493]
    assert r["classificacao"] == CLASSIF_FERIDAS
    assert r["classificacao_imputada"] is False


def test_total_envolvidos_usa_a_soma_e_nao_pessoas(silver_de):
    # caso real de 2025 (id 652519): pessoas = 6, mas 1 + 1 + 1 + 4 = 7
    r = silver_de([linha(pessoas="6", mortos="1", feridos="1", ilesos="1", ignorados="4")])[652493]
    assert r["pessoas"] == 6
    assert r["total_envolvidos"] == 7


@pytest.mark.parametrize("mortos,feridos_graves,esperado", [
    ("0", "0", False), ("1", "0", True), ("0", "1", True), ("2", "3", True),
])
def test_grave(silver_de, mortos, feridos_graves, esperado):
    assert silver_de([linha(mortos=mortos, feridos_graves=feridos_graves)])[652493]["grave"] is esperado


@pytest.mark.parametrize("data,esperado", [
    ("2018-03-31", False), ("2018-04-01", True), ("2017-06-15", False), ("2025-01-01", True),
])
def test_serie_estavel(silver_de, data, esperado):
    r = silver_de([linha(data_inversa=data)], nome=f"datatran{data[:4]}.csv")[652493]
    assert r["serie_estavel"] is esperado


# ---------- id ----------

def test_id_em_notacao_cientifica_vira_inteiro(silver_de):
    # caso real: datatran2018.csv traz o id 100000 escrito como "1e+05"
    s = silver_de([linha(id="1e+05"), linha(id="99999")])
    assert set(s) == {100000, 99999}
    assert s[100000]["id_corrigido"] is True
    assert s[99999]["id_corrigido"] is False


def test_id_cientifico_nao_inteiro_e_problema(bronze_de):
    # 1.5e+00 = 1,5: não é um id válido
    b = bronze_de([linha(id="1.5e+00")])
    assert problemas(b) == {"1.5e+00": {"id: formato"}}


def test_id_nulo_e_problema(bronze_de):
    # antes da revisão, dois ids NA viravam uma linha só, sem aviso
    b = bronze_de([linha(id="NA"), linha(id="NA", mortos="1")])
    assert problemas_por_linha(b).count() == 2
    with pytest.raises(BronzeInvalida, match="2 linhas"):
        validar_bronze(b)


def test_id_repetido_no_mesmo_arquivo_para_o_pipeline(bronze_de):
    b = bronze_de([linha(id="7"), linha(id="7", mortos="1"), linha(id="8")])
    rep = ids_repetidos(b).collect()
    assert [(r["id"], r["vezes"]) for r in rep] == [(7, 2)]
    with pytest.raises(BronzeInvalida, match="1 ids repetidos"):
        validar_bronze(b)


def test_id_repetido_entre_formatos_e_detectado(bronze_de):
    # "1e+05" e "100000" são o mesmo id depois da conversão
    b = bronze_de([linha(id="1e+05"), linha(id="100000")])
    assert ids_repetidos(b).count() == 1


# ---------- versões do arquivo (bronze acumulativa) ----------

def test_usa_so_a_ingestao_mais_recente_de_cada_arquivo(spark, tmp_path):
    v1 = escrever_csv_prf(tmp_path / "v1" / "datatran2025.csv",
                          [linha(id="1", mortos="0"), linha(id="2")])
    v2 = escrever_csv_prf(tmp_path / "v2" / "datatran2025.csv", [linha(id="1", mortos="1")])
    outro_ano = escrever_csv_prf(tmp_path / "v1" / "datatran2024.csv", [linha(id="3")])
    bronze = (montar_bronze(spark, [v1, outro_ano], "2026-01-01T00:00:00Z")
              .unionByName(montar_bronze(spark, [v2], "2026-06-01T00:00:00Z")))
    validar_bronze(bronze)  # o id 1 está nas duas versões, mas só vale a nova
    s = {r["id"]: r for r in transformar(bronze).collect()}
    # id 2 sumiu na versão nova do arquivo de 2025: não volta da versão antiga
    assert set(s) == {1, 3}
    assert s[1]["mortos"] == 1


# ---------- formatos estritos (o que try_cast aceitaria em silêncio) ----------

@pytest.mark.parametrize("campo,valor,problema", [
    ("mortos", "-1", "mortos: formato"),
    ("mortos", "um", "mortos: formato"),
    ("mortos", "NA", "mortos: vazio"),
    ("feridos_graves", "NA", "feridos_graves: vazio"),
    ("br", "116.0", "br: formato"),
    ("horario", "25:99:00", "horario: formato"),
    ("horario", "6:20", "horario: formato"),
    ("data_inversa", "2025", "data_inversa: formato"),
    ("data_inversa", "2025-02", "data_inversa: formato"),
    ("data_inversa", "2025-01-01 lixo", "data_inversa: formato"),
    ("data_inversa", "2025-02-30", "data_inversa: formato"),
    ("data_inversa", "01/01/2025", "data_inversa: formato"),
    ("km", "NaN", "km: formato"),
    ("km", "Infinity", "km: formato"),
    ("km", "1e5", "km: formato"),
    ("latitude", "NaN", "latitude: formato"),
    ("uf", "NA", "uf: vazio"),
])
def test_valor_fora_do_formato_e_problema(bronze_de, campo, valor, problema):
    b = bronze_de([linha(**{campo: valor})])
    assert problemas(b) == {"652493": {problema}}
    with pytest.raises(BronzeInvalida):
        validar_bronze(b)


def test_varios_problemas_na_mesma_linha(bronze_de):
    b = bronze_de([linha(id="1"), linha(id="2", mortos="um", data_inversa="01/01/2025")])
    assert problemas(b) == {"2": {"mortos: formato", "data_inversa: formato"}}


def test_linha_boa_nao_tem_problema(bronze_de):
    assert problemas_por_linha(bronze_de([linha()])).count() == 0


def test_coordenada_na_nao_e_problema(bronze_de):
    # latitude e longitude podem faltar: a linha fica com coord_valida = false
    assert problemas_por_linha(bronze_de([linha(latitude="NA", longitude="NA")])).count() == 0
