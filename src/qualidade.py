"""Testes de qualidade da silver, rodados no pipeline (não só no pytest).

Cada regra descreve a condição de uma linha REPROVADA. Há dois tipos:

- bloqueante (`tratamento=None`): se qualquer linha reprovar, o pipeline para.
  São coisas que a silver não sabe corrigir: id nulo ou repetido, data fora
  do ano do arquivo, contagem negativa, classificação que contradiz as contagens.
- com tratamento: a fonte real tem linhas assim, e a silver já fez algo com
  elas (anulou a coordenada, derivou a classificação). A regra conta quantas
  são, e a regra bloqueante "irmã" confere que o tratamento foi aplicado.

`contar_violacoes` devolve, por ano do arquivo e por regra, quantas linhas
reprovaram. É essa tabela que vai para resultados/fase2_qualidade.csv.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from operator import or_
from typing import Callable

from pyspark.sql import Column, DataFrame, Window
from pyspark.sql import functions as F

from src.regras import CLASSIF_FATAL, CLASSIF_FERIDAS, CLASSIF_SEM, CONTAGENS, DIAS_SEMANA
from src.silver import dentro_do_brasil


class QualidadeReprovada(ValueError):
    """Alguma regra bloqueante reprovou linhas."""


@dataclass(frozen=True)
class Regra:
    nome: str
    descricao: str
    violacao: Callable[[], Column]  # função: Column só pode ser criada com sessão ativa
    tratamento: str | None = None   # None = bloqueante

    @property
    def bloqueante(self) -> bool:
        return self.tratamento is None


def _dia_esperado() -> Column:
    nomes = F.array(*[F.lit(d) for d in DIAS_SEMANA])
    return F.element_at(nomes, F.dayofweek("data"))


def _classificacao_incoerente() -> Column:
    c, m, f = F.col("classificacao"), F.col("mortos"), F.col("feridos")
    coerente = (((c == CLASSIF_FATAL) & (m > 0))
                | ((c == CLASSIF_FERIDAS) & (m == 0) & (f > 0))
                | ((c == CLASSIF_SEM) & (m == 0) & (f == 0)))
    return ~F.coalesce(coerente, F.lit(False))


REGRAS: list[Regra] = [
    Regra("id_nulo", "id ausente", lambda: F.col("id").isNull()),
    Regra("id_duplicado", "mesmo id em mais de uma linha",
          lambda: F.col("id").isNotNull() & (F.col("_vezes_id") > 1)),
    Regra("data_fora_do_ano_do_arquivo", "data nula ou de outro ano que não o do arquivo",
          lambda: ~F.coalesce(F.year("data") == F.col("_ano_arquivo"), F.lit(False))),
    Regra("dia_semana_incoerente", "dia da semana escrito não é o dia da data",
          lambda: ~F.coalesce(F.col("dia_semana") == _dia_esperado(), F.lit(False))),
    Regra("contagem_negativa_ou_nula", "alguma contagem de pessoas ou veículos negativa ou nula",
          lambda: reduce(or_, [F.col(c).isNull() | (F.col(c) < 0) for c in CONTAGENS])),
    Regra("feridos_diferente_de_leves_mais_graves", "feridos != feridos_leves + feridos_graves",
          lambda: F.col("feridos") != F.col("feridos_leves") + F.col("feridos_graves")),
    Regra("classificacao_incoerente",
          "classificação (original ou derivada) contradiz mortos e feridos",
          _classificacao_incoerente),
    Regra("classificacao_ausente", "classificacao_acidente veio NA",
          lambda: F.col("classificacao_imputada"),
          tratamento="classificação derivada das contagens; classificacao_imputada = true"),
    Regra("coordenada_fora_do_brasil_ou_ausente", "latitude/longitude ausente ou fora das caixas do Brasil",
          lambda: ~F.col("coord_valida"),
          tratamento="latitude e longitude anuladas; a ocorrência fica (UF, BR e km são bons)"),
    Regra("coordenada_valida_fora_do_brasil", "linha marcada coord_valida com ponto nulo ou fora do Brasil",
          lambda: F.col("coord_valida") & ~dentro_do_brasil(F.col("latitude"), F.col("longitude"))),
    Regra("pessoas_menor_que_total", "pessoas < mortos + feridos + ilesos + ignorados",
          lambda: F.col("pessoas") < F.col("total_envolvidos"),
          tratamento="as análises usam total_envolvidos, que fecha com o arquivo por pessoa"),
    Regra("pessoas_maior_que_total", "pessoas > mortos + feridos + ilesos + ignorados",
          lambda: F.col("pessoas") > F.col("total_envolvidos")),
    Regra("grave_nulo", "alvo grave sem valor", lambda: F.col("grave").isNull()),
]


def _com_contagem_de_id(df: DataFrame) -> DataFrame:
    return df.withColumn("_vezes_id", F.count("*").over(Window.partitionBy("id")))


def linhas_reprovadas(df: DataFrame, nome: str) -> DataFrame:
    """As linhas que uma regra reprova, para investigar."""
    regra = next(r for r in REGRAS if r.nome == nome)
    return _com_contagem_de_id(df).where(F.coalesce(regra.violacao(), F.lit(True))).drop("_vezes_id")


def contar_violacoes(df: DataFrame, regras: list[Regra] = REGRAS) -> list[dict]:
    """Uma linha por (ano do arquivo, regra) com o número de linhas reprovadas.

    Condição que dá nulo conta como reprovada: uma regra que não consegue
    avaliar a linha não pode aprová-la.
    """
    aggs = [F.sum(F.coalesce(r.violacao(), F.lit(True)).cast("int")).alias(r.nome) for r in regras]
    por_ano = (_com_contagem_de_id(df).groupBy("_ano_arquivo").agg(F.count("*").alias("_linhas"), *aggs)
               .orderBy("_ano_arquivo").collect())
    return [{"ano": a["_ano_arquivo"], "regra": r.nome, "linhas": a["_linhas"],
             "linhas_reprovadas": a[r.nome], "bloqueante": r.bloqueante,
             "tratamento": r.tratamento or ""}
            for a in por_ano for r in regras]


def bloqueios(contagens: list[dict]) -> dict[str, int]:
    """Total de linhas reprovadas por regra bloqueante, só as que reprovaram algo."""
    total: dict[str, int] = {}
    for c in contagens:
        if c["bloqueante"] and c["linhas_reprovadas"]:
            total[c["regra"]] = total.get(c["regra"], 0) + c["linhas_reprovadas"]
    return total


def verificar(df: DataFrame, regras: list[Regra] = REGRAS) -> list[dict]:
    """Conta as violações e para o pipeline se alguma regra bloqueante reprovou linhas."""
    contagens = contar_violacoes(df, regras)
    falhas = bloqueios(contagens)
    if falhas:
        raise QualidadeReprovada(f"regras bloqueantes reprovaram linhas: {falhas}. "
                                 "Ver qualidade.linhas_reprovadas(df, regra).")
    return contagens
