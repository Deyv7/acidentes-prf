"""Cada regra de qualidade tem que reprovar a linha errada, e só ela.

A base é uma silver válida, montada pelo pipeline a partir de uma linha da
PRF. Cada caso estraga um campo depois da silver, porque várias dessas
coisas a silver já impede antes (formato, id repetido): aqui o teste é da
regra de qualidade em si, que é a última defesa antes da gold.
"""
import pytest
from pyspark.sql import functions as F

from src.bronze import montar_bronze
from src.qualidade import (REGRAS, QualidadeReprovada, contar_violacoes,
                           linhas_reprovadas, verificar)
from src.regras import CLASSIF_FATAL, CLASSIF_SEM
from src.silver import transformar
from tests.conftest import INGESTAO, escrever_csv_prf, linha


@pytest.fixture
def silver(spark, tmp_path):
    """Duas ocorrências válidas de 2025 (quarta-feira, 1º de janeiro)."""
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha(id="1"), linha(id="2")])
    return transformar(montar_bronze(spark, [csv], INGESTAO))


def reprovadas(df) -> dict[str, int]:
    return {c["regra"]: c["linhas_reprovadas"] for c in contar_violacoes(df) if c["linhas_reprovadas"]}


def so_no_id_1(df, coluna, valor):
    return df.withColumn(coluna, F.when(F.col("id") == 1, valor).otherwise(F.col(coluna)))


def test_silver_valida_passa_em_todas(silver):
    assert reprovadas(silver) == {}
    contagens = verificar(silver)
    assert len(contagens) == len(REGRAS)  # um ano x todas as regras


def test_nomes_de_regra_unicos():
    nomes = [r.nome for r in REGRAS]
    assert len(nomes) == len(set(nomes))


# Cada caso: o que estragar na linha de id 1 e qual regra bloqueante tem que pegar.
BLOQUEANTES = [
    ("id_nulo", lambda df: so_no_id_1(df, "id", F.lit(None).cast("long"))),
    ("id_duplicado", lambda df: df.withColumn("id", F.lit(1).cast("long"))),
    ("data_fora_do_ano_do_arquivo", lambda df: so_no_id_1(df, "_ano_arquivo", F.lit(2024))),
    ("data_fora_do_ano_do_arquivo", lambda df: so_no_id_1(df, "data", F.lit(None).cast("date"))),
    ("dia_semana_incoerente", lambda df: so_no_id_1(df, "dia_semana", F.lit("segunda-feira"))),
    ("contagem_negativa_ou_nula", lambda df: so_no_id_1(df, "veiculos", F.lit(-1))),
    ("contagem_negativa_ou_nula", lambda df: so_no_id_1(df, "ilesos", F.lit(None).cast("int"))),
    ("feridos_diferente_de_leves_mais_graves", lambda df: so_no_id_1(df, "feridos_leves", F.lit(3))),
    # "Com Vítimas Feridas" com um morto
    ("classificacao_incoerente", lambda df: so_no_id_1(df, "mortos", F.lit(1))),
    ("classificacao_incoerente", lambda df: so_no_id_1(df, "classificacao", F.lit(CLASSIF_FATAL))),
    ("classificacao_incoerente", lambda df: so_no_id_1(df, "classificacao", F.lit(CLASSIF_SEM))),
    ("classificacao_incoerente", lambda df: so_no_id_1(df, "classificacao", F.lit("Outra"))),
    ("coordenada_valida_fora_do_brasil", lambda df: so_no_id_1(df, "latitude", F.lit(10.0))),
    ("coordenada_valida_fora_do_brasil", lambda df: so_no_id_1(df, "latitude", F.lit(None).cast("double"))),
    ("pessoas_maior_que_total", lambda df: so_no_id_1(df, "pessoas", F.lit(9))),
    ("grave_nulo", lambda df: so_no_id_1(df, "grave", F.lit(None).cast("boolean"))),
]


@pytest.mark.parametrize("regra,estragar", BLOQUEANTES)
def test_regra_bloqueante_reprova_e_para(silver, regra, estragar):
    ruim = estragar(silver)
    esperado = 2 if regra == "id_duplicado" else 1  # as duas linhas ficam com id 1
    assert reprovadas(ruim).get(regra) == esperado
    with pytest.raises(QualidadeReprovada, match=regra):
        verificar(ruim)


def test_linhas_reprovadas_mostra_a_linha(silver):
    ruim = so_no_id_1(silver, "dia_semana", F.lit("segunda-feira"))
    assert [r["id"] for r in linhas_reprovadas(ruim, "dia_semana_incoerente").collect()] == [1]


@pytest.mark.parametrize("campos,regra", [
    (dict(latitude="0", longitude="0"), "coordenada_fora_do_brasil_ou_ausente"),
    (dict(latitude="NA", longitude="NA"), "coordenada_fora_do_brasil_ou_ausente"),
    (dict(classificacao_acidente="NA"), "classificacao_ausente"),
    (dict(pessoas="1"), "pessoas_menor_que_total"),
])
def test_regra_com_tratamento_conta_mas_nao_para(spark, tmp_path, campos, regra):
    # casos que existem na fonte real; a silver já tratou a linha
    csv = escrever_csv_prf(tmp_path / "datatran2025.csv", [linha(id="1", **campos), linha(id="2")])
    s = transformar(montar_bronze(spark, [csv], INGESTAO))
    assert reprovadas(s) == {regra: 1}
    verificar(s)  # não levanta


def test_contagem_por_ano_do_arquivo(spark, tmp_path):
    a = escrever_csv_prf(tmp_path / "a" / "datatran2024.csv",
                         [linha(id="1", data_inversa="2024-01-03", latitude="0", longitude="0")])
    b = escrever_csv_prf(tmp_path / "b" / "datatran2025.csv", [linha(id="2")])
    s = transformar(montar_bronze(spark, [a, b], INGESTAO))
    c = {(x["ano"], x["regra"]): x for x in contar_violacoes(s)}
    assert c[(2024, "coordenada_fora_do_brasil_ou_ausente")]["linhas_reprovadas"] == 1
    assert c[(2025, "coordenada_fora_do_brasil_ou_ausente")]["linhas_reprovadas"] == 0
    assert c[(2024, "id_nulo")]["linhas"] == 1
