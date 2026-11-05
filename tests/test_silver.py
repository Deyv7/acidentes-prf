"""Cada regra da silver tem um caso aqui, montado a partir do que a Fase 0 achou."""
from datetime import date

import pytest

from src.bronze import montar_bronze
from src.regras import CLASSIF_FATAL, CLASSIF_FERIDAS, CLASSIF_SEM
from src.silver import falhas_de_conversao, transformar
from tests.conftest import escrever_csv_prf, linha

INGESTAO = "2026-11-04T12:00:00"


@pytest.fixture
def silver_de(spark, tmp_path):
    """Escreve as linhas num CSV no formato da PRF e devolve a silver como dict por id."""
    contador = {"n": 0}

    def _silver(linhas, nome="datatran2025.csv", ingerido_em=INGESTAO):
        contador["n"] += 1
        csv = escrever_csv_prf(tmp_path / str(contador["n"]) / nome, linhas)
        bronze = montar_bronze(spark, [csv], ingerido_em)
        return bronze, {r["id"]: r for r in transformar(bronze).collect()}
    return _silver


def test_tipos(silver_de):
    _, s = silver_de([linha()])
    r = s[652493]
    assert r["data"] == date(2025, 1, 1)
    assert (r["ano"], r["mes"], r["hora"]) == (2025, 1, 6)
    assert r["br"] == 116 and r["km"] == 225.0
    assert r["latitude"] == pytest.approx(-23.48586772)
    assert r["longitude"] == pytest.approx(-46.54075317)
    assert r["mortos"] == 0 and r["feridos_leves"] == 1


def test_virgula_decimal_no_km(silver_de):
    _, s = silver_de([linha(km="34,9")])
    assert s[652493]["km"] == pytest.approx(34.9)


def test_renomeia_coluna_com_erro_de_grafia(silver_de):
    bronze, s = silver_de([linha()])
    r = s[652493]
    assert r["condicao_meteorologica"] == "Céu Claro"
    assert "condicao_metereologica" not in r.asDict()


def test_na_vira_nulo(silver_de):
    _, s = silver_de([linha(sentido_via="NA")])
    assert s[652493]["sentido_via"] is None


@pytest.mark.parametrize("lat,lon", [
    ("0", "0"),                        # 7 casos em 2017
    ("-22,41850506", "-405,96461356"),  # vírgula decimal perdida, 2017
    ("-7", "-34"),                     # arredondado, cai no mar (Recife, 2017)
])
def test_coordenada_fora_do_brasil_vira_nula(silver_de, lat, lon):
    _, s = silver_de([linha(latitude=lat, longitude=lon)])
    r = s[652493]
    assert r["coord_valida"] is False
    assert r["latitude"] is None and r["longitude"] is None
    # a ocorrência continua na tabela, com UF, BR e km
    assert r["uf"] == "SP" and r["br"] == 116


def test_fernando_de_noronha_e_valido(silver_de):
    # id 620583 de 2024: BR-363, km 1,5
    _, s = silver_de([linha(uf="PE", br="363", km="1,5", latitude="-3,841072", longitude="-32,406822")])
    r = s[652493]
    assert r["coord_valida"] is True
    assert r["longitude"] == pytest.approx(-32.406822)


def test_classificacao_nula_com_morto_vira_fatal(silver_de):
    # caso real de 2025 (id 652519): classificação NA e 1 morto
    _, s = silver_de([linha(classificacao_acidente="NA", mortos="1", feridos="1")])
    r = s[652493]
    assert r["classificacao_acidente"] is None
    assert r["classificacao"] == CLASSIF_FATAL
    assert r["classificacao_imputada"] is True


@pytest.mark.parametrize("mortos,feridos,esperado", [
    ("0", "2", CLASSIF_FERIDAS),
    ("0", "0", CLASSIF_SEM),
])
def test_classificacao_nula_sem_morto(silver_de, mortos, feridos, esperado):
    _, s = silver_de([linha(classificacao_acidente="NA", mortos=mortos, feridos=feridos)])
    assert s[652493]["classificacao"] == esperado


def test_classificacao_preenchida_nao_e_alterada(silver_de):
    _, s = silver_de([linha()])
    r = s[652493]
    assert r["classificacao"] == CLASSIF_FERIDAS
    assert r["classificacao_imputada"] is False


def test_total_envolvidos_usa_a_soma_e_nao_pessoas(silver_de):
    # caso real de 2025 (id 652519): pessoas = 6, mas 1 + 1 + 1 + 4 = 7
    _, s = silver_de([linha(pessoas="6", mortos="1", feridos="1", ilesos="1", ignorados="4")])
    r = s[652493]
    assert r["pessoas"] == 6
    assert r["total_envolvidos"] == 7


@pytest.mark.parametrize("mortos,feridos_graves,esperado", [
    ("0", "0", False), ("1", "0", True), ("0", "1", True), ("2", "3", True),
])
def test_grave(silver_de, mortos, feridos_graves, esperado):
    _, s = silver_de([linha(mortos=mortos, feridos_graves=feridos_graves)])
    assert s[652493]["grave"] is esperado


@pytest.mark.parametrize("data,esperado", [
    ("2018-03-31", False), ("2018-04-01", True), ("2017-06-15", False), ("2025-01-01", True),
])
def test_serie_estavel(silver_de, data, esperado):
    _, s = silver_de([linha(data_inversa=data)], nome=f"datatran{data[:4]}.csv")
    assert s[652493]["serie_estavel"] is esperado


def test_dia_semana_minusculo(silver_de):
    _, s = silver_de([linha(dia_semana="Quarta-feira")])
    assert s[652493]["dia_semana"] == "quarta-feira"


def test_deduplica_mantendo_a_ingestao_mais_recente(spark, tmp_path):
    antigo = escrever_csv_prf(tmp_path / "v1" / "datatran2025.csv", [linha(mortos="0")])
    novo = escrever_csv_prf(tmp_path / "v2" / "datatran2025.csv", [linha(mortos="1")])
    bronze = (montar_bronze(spark, [antigo], "2026-01-01T00:00:00")
              .unionByName(montar_bronze(spark, [novo], "2026-06-01T00:00:00")))
    linhas = transformar(bronze).collect()
    assert len(linhas) == 1
    assert linhas[0]["mortos"] == 1


def test_ids_diferentes_nao_sao_deduplicados(silver_de):
    _, s = silver_de([linha(id="1"), linha(id="2")])
    assert set(s) == {1, 2}


def test_id_em_notacao_cientifica_vira_inteiro(silver_de):
    # caso real: datatran2018.csv traz o id 100000 escrito como "1e+05"
    _, s = silver_de([linha(id="1e+05"), linha(id="99999")])
    assert set(s) == {100000, 99999}
    assert s[100000]["id_corrigido"] is True
    assert s[99999]["id_corrigido"] is False


def test_id_cientifico_nao_inteiro_e_falha(silver_de):
    # 1.5e+00 = 1,5: não é um id válido, tem que parar o pipeline
    bronze, _ = silver_de([linha(id="1.5e+00")])
    assert falhas_de_conversao(bronze).collect()[0]["colunas_com_falha"] == ["id"]


def test_falhas_de_conversao_vazio_na_linha_boa(silver_de):
    bronze, _ = silver_de([linha()])
    assert falhas_de_conversao(bronze).count() == 0


def test_falhas_de_conversao_acha_valor_que_nao_converte(silver_de):
    bronze, _ = silver_de([linha(id="1"), linha(id="2", mortos="um", data_inversa="01/01/2025")])
    falhas = falhas_de_conversao(bronze).collect()
    assert len(falhas) == 1
    assert falhas[0]["id"] == "2"
    assert set(falhas[0]["colunas_com_falha"]) == {"mortos", "data_inversa"}


def test_na_nao_conta_como_falha_de_conversao(silver_de):
    bronze, _ = silver_de([linha(latitude="NA", longitude="NA")])
    assert falhas_de_conversao(bronze).count() == 0
