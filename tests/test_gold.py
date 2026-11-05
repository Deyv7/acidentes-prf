"""Contrato da gold: recorte de anos, sem vazamento do alvo, agregados que fecham."""
import pytest
from pyspark.sql import functions as F

from src import regras
from src.bronze import montar_bronze
from src.gold import (ALVO, CONTEXTO, DESFECHO, DINAMICA, NAO_INFORMADO, GoldInvalida,
                      agregar, intervalo_wilson, montar_modelo, recortes, verificar_modelo)
from src.silver import transformar
from tests.conftest import INGESTAO, escrever_csv_prf, linha


@pytest.fixture
def silver_de(spark, tmp_path):
    contador = {"n": 0}

    def _silver(por_ano: dict[int, list[dict]]):
        contador["n"] += 1
        pasta = tmp_path / str(contador["n"])
        csvs = [escrever_csv_prf(pasta / f"datatran{ano}.csv", ls) for ano, ls in por_ano.items()]
        return transformar(montar_bronze(spark, csvs, INGESTAO))
    return _silver


# ---------- gold do modelo ----------

def test_modelo_so_tem_anos_da_analise(silver_de):
    s = silver_de({2018: [linha(id="1", data_inversa="2018-12-31", dia_semana="segunda-feira")],
                   2019: [linha(id="2", data_inversa="2019-01-01", dia_semana="terça-feira")],
                   2025: [linha(id="3")]})
    assert sorted(r["id"] for r in montar_modelo(s).collect()) == [2, 3]


def test_modelo_nao_tem_coluna_de_desfecho(silver_de):
    colunas = montar_modelo(silver_de({2025: [linha()]})).columns
    assert not set(DESFECHO) & set(colunas)
    assert ALVO in colunas
    assert set(CONTEXTO) | set(DINAMICA) <= set(colunas)


def test_grupos_de_colunas_nao_se_sobrepoem():
    grupos = [set(CONTEXTO), set(DINAMICA), set(DESFECHO), {ALVO}]
    assert sum(len(g) for g in grupos) == len(set().union(*grupos))


@pytest.mark.parametrize("km,trecho", [("225", 220), ("9,9", 0), ("10", 10), ("0", 0)])
def test_trecho_de_10_km(silver_de, km, trecho):
    assert montar_modelo(silver_de({2025: [linha(km=km)]})).collect()[0]["trecho_km"] == trecho


@pytest.mark.parametrize("data,dia,fim_de_semana,num", [
    ("2025-01-04", "sábado", True, 7), ("2025-01-05", "domingo", True, 1),
    ("2025-01-06", "segunda-feira", False, 2),
])
def test_dia_da_semana(silver_de, data, dia, fim_de_semana, num):
    r = montar_modelo(silver_de({2025: [linha(data_inversa=data, dia_semana=dia)]})).collect()[0]
    assert (r["fim_de_semana"], r["dia_semana_num"]) == (fim_de_semana, num)


def test_verificar_modelo_passa(silver_de):
    r = verificar_modelo(montar_modelo(silver_de({2025: [linha(id="1"), linha(id="2")]})))
    assert r["linhas"] == r["ids_distintos"] == 2


@pytest.mark.parametrize("estragar", [
    lambda m: m.unionByName(m),                                   # id repetido
    lambda m: m.withColumn("ano", F.lit(2018)),                   # fora do recorte
    lambda m: m.withColumn(ALVO, F.lit(None).cast("boolean")),   # alvo nulo
    lambda m: m.withColumn("mortos", F.lit(0)),                   # vazamento
])
def test_verificar_modelo_falha(silver_de, estragar):
    m = montar_modelo(silver_de({2025: [linha()]}))
    with pytest.raises(GoldInvalida):
        verificar_modelo(estragar(m))


# ---------- agregados ----------

@pytest.mark.parametrize("graves,n", [(5, 10), (0, 10), (10, 10), (1, 1), (20493, 72529)])
def test_wilson_igual_em_python_e_spark(spark, graves, n):
    inf, sup = intervalo_wilson(F.lit(graves), F.lit(n))
    r = spark.range(1).select(inf.alias("i"), sup.alias("s")).collect()[0]
    assert (r["i"], r["s"]) == pytest.approx(regras.wilson(graves, n))


def test_wilson_valores_conhecidos():
    assert regras.wilson(5, 10) == pytest.approx((0.2366, 0.7634), abs=1e-4)
    assert regras.wilson(0, 10) == pytest.approx((0.0, 0.2775), abs=1e-4)


@pytest.fixture
def agregado(silver_de):
    s = silver_de({2025: [
        linha(id="1", mortos="1", feridos="0", feridos_leves="0", ilesos="1",
              classificacao_acidente="Com Vítimas Fatais"),          # grave, com morto
        linha(id="2", feridos_graves="1", feridos_leves="0"),          # grave
        linha(id="3"),                                                  # não grave
        linha(id="4", uf="RJ", condicao_metereologica="NA"),          # não grave
    ]})
    return {(r["recorte"], r["valor"]): r for r in agregar(s).collect()}


def test_cada_recorte_soma_o_total(agregado):
    for nome in recortes():
        linhas = [r for (rec, _), r in agregado.items() if rec == nome]
        assert sum(r["ocorrencias"] for r in linhas) == 4, nome
        assert sum(r["graves"] for r in linhas) == 2, nome


def test_proporcao_e_intervalo(agregado):
    sp = agregado[("uf", "SP")]
    assert (sp["ocorrencias"], sp["graves"], sp["com_morto"], sp["mortos"]) == (3, 2, 1, 1)
    assert sp["pct_graves"] == pytest.approx(2 / 3)
    assert (sp["ic95_inf"], sp["ic95_sup"]) == pytest.approx(regras.wilson(2, 3))


def test_valor_ausente_vira_nao_informado(agregado):
    assert agregado[("condicao_meteorologica", NAO_INFORMADO)]["ocorrencias"] == 1


def test_trecho_e_br_levam_a_uf(agregado):
    # o km recomeça em cada estado: a UF faz parte do nome do trecho
    assert ("trecho_10km", "SP BR-116 km 220-230") in agregado
    assert ("trecho_10km", "RJ BR-116 km 220-230") in agregado
    assert ("municipio", "GUARULHOS/SP") in agregado
