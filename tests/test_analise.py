"""Comparação com a média, amostra mínima, ordem e transição de listas."""
import pytest

from src import regras
from src.analise import comparar, resumo, transicao_por_mes
from src.gold import LISTA_ANTIGA


def agregado(spark, linhas):
    """linhas: (recorte, valor, ocorrencias, graves[, com_vitima]). IC calculado como na gold.
    Sem com_vitima, usa o dobro dos graves (limitado a ocorrencias)."""
    dados = []
    for rec, valor, n, g, *v in linhas:
        cv = v[0] if v else min(n, 2 * g)
        inf, sup = regras.wilson(g, n)
        inf_v, sup_v = regras.wilson(g, cv)
        dados.append((rec, valor, n, g, cv, g / n, inf, sup, g / cv, inf_v, sup_v))
    return spark.createDataFrame(
        dados, "recorte string, valor string, ocorrencias long, graves long, com_vitima long, "
               "pct_graves double, ic95_inf double, ic95_sup double, pct_graves_com_vitima double, "
               "ic95_inf_com_vitima double, ic95_sup_com_vitima double")


@pytest.fixture
def comparado(spark):
    a = agregado(spark, [
        ("uf", "A", 1000, 500),   # 50%: acima
        ("uf", "B", 1000, 100),   # 10%: abaixo
        ("uf", "C", 1000, 300),   # 30%: perto da média
        ("uf", "D", 10, 10),      # 100% com 10 ocorrências: amostra pequena
    ])
    return {r["valor"]: r for r in comparar(a, n_min=100).collect()}


def test_media_e_do_recorte_inteiro(comparado):
    assert comparado["A"]["media_recorte"] == pytest.approx(910 / 3010)


def test_comparacao(comparado):
    assert comparado["A"]["comparacao"] == "acima"
    assert comparado["B"]["comparacao"] == "abaixo"
    assert comparado["C"]["comparacao"] == "indistinguível"
    assert comparado["D"]["comparacao"] == "amostra pequena"


def test_amostra_pequena_nao_ganha_posicao(comparado):
    # D tem 100% de graves, mas não pode ficar em primeiro
    assert comparado["D"]["posicao"] is None
    assert [comparado[v]["posicao"] for v in "ACB"] == [1, 2, 3]


def test_ordem_pelo_limite_inferior(spark):
    # X tem proporção maior, mas Y tem mais certeza: Y fica na frente
    a = agregado(spark, [("hora", "X", 120, 60), ("hora", "Y", 5000, 2400)])
    c = {r["valor"]: r["posicao"] for r in comparar(a).collect()}
    assert c == {"Y": 1, "X": 2}


def test_lista_antiga_de_causas_fica_fora_da_media_e_da_ordem(spark):
    a = agregado(spark, [("causa_acidente", "nova", 1000, 300),
                         ("causa_acidente", LISTA_ANTIGA, 1000, 900)])
    c = {r["valor"]: r for r in comparar(a).collect()}
    assert c["nova"]["media_recorte"] == pytest.approx(0.3)
    assert c[LISTA_ANTIGA]["comparacao"] == "fora da comparação"
    assert c[LISTA_ANTIGA]["posicao"] is None


def test_resumo(spark):
    a = agregado(spark, [("uf", "A", 1000, 500), ("uf", "B", 1000, 100), ("uf", "D", 10, 10)])
    r = resumo(comparar(a)).collect()[0]
    assert (r["valores"], r["comparaveis"], r["acima"], r["abaixo"]) == (3, 2, 1, 1)
    assert (r["ocorrencias"], r["ocorrencias_comparaveis"]) == (2010, 2000)


def test_transicao_por_mes_acha_as_listas_no_dado(spark):
    s = spark.createDataFrame(
        [(2019, 1, "velha"), (2019, 1, "comum"), (2020, 12, "velha"), (2021, 1, "nova"),
         (2021, 1, "comum"), (2022, 1, "nova"), (2022, 1, "comum")],
        "ano int, mes int, causa string")
    r = {(x["ano"], x["mes"]): x for x in
         transicao_por_mes(s, "causa", [2019, 2020], [2022], [2020, 2021]).collect()}
    assert r[(2020, 12)]["valor_so_da_lista_antiga"] == 1
    assert r[(2021, 1)]["valor_so_da_lista_antiga"] == 0
    assert r[(2021, 1)]["ocorrencias"] == 2


def test_comparacao_entre_com_vitima(spark):
    # A tem muitos graves porque quase não registra acidente sem vítima.
    # Entre os com vítima, A é igual a B.
    a = agregado(spark, [("uf", "A", 1000, 500, 1000), ("uf", "B", 3000, 500, 1000)])
    c = {r["valor"]: r for r in comparar(a).collect()}
    assert c["A"]["comparacao"] == "acima"
    assert c["A"]["media_recorte_com_vitima"] == pytest.approx(0.5)
    assert c["A"]["comparacao_com_vitima"] == "indistinguível"
    assert resumo(comparar(a)).collect()[0]["mesmo_lado_com_vitima"] == 0
