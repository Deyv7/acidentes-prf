"""Roda bronze e silver no Spark local, nos ZIPs reais, e confere com a Fase 0.

É o mesmo caminho que os notebooks do Databricks fazem, só que com Delta em
disco local. Serve para provar que a leitura com Spark bate com a contagem
feita na Fase 0 com a biblioteca padrão (src/validar_fonte.py).

Uso (dentro do container de testes, ver README):
    python -m src.executar_local --dados /dados/bruto --lake /lake --resultados resultados

Saídas em resultados/:
- fase1_conferencia_bronze_colunas.csv: por ano e coluna, vazios, NA e
  distintos contados pelo Spark na bronze contra os da Fase 0;
- fase1_conferencia_silver.csv: por ano, contagens da silver contra a Fase 0;
- fase1_esquema_silver.csv: colunas e tipos da silver;
- fase1_ids_corrigidos.csv: evidência para cada id em notação científica;
- fase2_qualidade.csv: por ano e regra de src/qualidade.py, linhas reprovadas;
- fase2_conferencia_gold.csv: ocorrências e graves por ano, silver x gold;
- fase2_recortes_gold.csv: cada recorte do agregado soma o total da gold;
- fase2_esquema_gold_modelo.csv: colunas, tipos e papel de cada coluna;
- fase3_*.csv: análise (ver docs/analise.md).
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from delta import configure_spark_with_delta_pip
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from src.bronze import agora_utc, extrair_zip, montar_bronze, zips_do_recorte
from src.regras import COLUNAS_FONTE
from src.analise import categorias_por_ano, comparar, resumo, transicao_por_mes
from src.gold import ALVO, CONTEXTO, DINAMICA, agregar, montar_modelo, verificar_modelo
from src.qualidade import bloqueios, contar_violacoes
from src.silver import transformar, ultima_ingestao, validar_bronze


def sessao_local(lake: Path) -> SparkSession:
    b = (SparkSession.builder.master("local[*]").appName("acidentes-prf")
         .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
         .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
         .config("spark.sql.warehouse.dir", str(lake / "warehouse"))
         .config("spark.sql.session.timeZone", "America/Sao_Paulo")
         .config("spark.driver.memory", "2g")
         .config("spark.ui.enabled", "false"))
    return configure_spark_with_delta_pip(b).getOrCreate()


def gravar_csv(caminho: Path, linhas: list[dict]) -> None:
    caminho.parent.mkdir(exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)


def conferir_colunas_bronze(bronze: DataFrame, resultados: Path) -> list[dict]:
    """Vazios, NA e distintos por coluna e ano, contra resultados/fase0_colunas_<ano>.csv.

    Na Fase 0, "vazios" é o campo vazio no CSV; o Spark lê campo vazio como
    nulo. "distintos" conta valores que não são vazio nem NA.
    """
    aggs = []
    for c in COLUNAS_FONTE:
        aggs += [F.sum(F.col(c).isNull().cast("int")).alias(f"{c}__vazios"),
                 F.sum((F.col(c) == "NA").cast("int")).alias(f"{c}__na"),
                 F.count_distinct(F.when(F.col(c) != "NA", F.col(c))).alias(f"{c}__distintos")]
    por_ano = {r["_ano_arquivo"]: r for r in bronze.groupBy("_ano_arquivo").agg(*aggs).collect()}

    saida = []
    for ano in sorted(por_ano):
        spark_ano = por_ano[ano]
        fase0 = {r["coluna"]: r for r in
                 csv.DictReader(open(resultados / f"fase0_colunas_{ano}.csv", encoding="utf-8"))}
        for c in COLUNAS_FONTE:
            linha = {"ano": ano, "coluna": c}
            bate = True
            for medida in ("vazios", "na", "distintos"):
                s, f0 = spark_ano[f"{c}__{medida}"] or 0, int(fase0[c][medida])
                linha[f"{medida}_bronze"], linha[f"{medida}_fase0"] = s, f0
                bate &= s == f0
            linha["bate"] = bate
            saida.append(linha)
    gravar_csv(resultados / "fase1_conferencia_bronze_colunas.csv", saida)
    return saida


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", type=Path, required=True)
    ap.add_argument("--lake", type=Path, required=True)
    ap.add_argument("--resultados", type=Path, default=Path("resultados"))
    args = ap.parse_args()

    # Os ZIPs locais estão em ocorrencia_<ano>/ocorrencia_<ano>.zip; o nome
    # usado no Databricks é datatran<ano>.zip. zips_do_recorte decide o recorte.
    locais = {f"datatran{z.stem.split('_')[1]}.zip": z
              for z in args.dados.glob("ocorrencia_*/ocorrencia_*.zip")}
    zips = [locais[n] for n in zips_do_recorte(list(locais))]
    csvs = [str(extrair_zip(z, args.lake / "csv")) for z in zips]

    spark = sessao_local(args.lake)

    # Bronze acumulativa (append), como no Databricks.
    caminho_bronze = str(args.lake / "bronze_ocorrencias")
    montar_bronze(spark, csvs, agora_utc()).write.format("delta").mode("append").save(caminho_bronze)
    bronze = spark.read.format("delta").load(caminho_bronze)

    validar_bronze(bronze)  # para aqui se houver formato errado, campo vazio ou id repetido
    vigente = ultima_ingestao(bronze)

    colunas = conferir_colunas_bronze(vigente, args.resultados)
    divergentes = [c for c in colunas if not c["bate"]]
    print(f"bronze x Fase 0: {len(colunas)} pares ano/coluna, {len(divergentes)} divergentes")
    for c in divergentes:
        print("  ", c)

    silver = transformar(bronze)
    (silver.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
     .save(str(args.lake / "silver_ocorrencias")))
    silver = spark.read.format("delta").load(str(args.lake / "silver_ocorrencias"))

    # Ids corrigidos (notação científica): o mesmo número existe escrito por
    # extenso em outra linha? Os vizinhos (id-1 e id+1) são do mesmo dia?
    corrigidos = silver.where("id_corrigido").select("id", "data", "_arquivo_origem").collect()
    ids_bronze = vigente.select("id", F.col("data_inversa").alias("data_viz"))
    evid = []
    for c in corrigidos:
        viz = {r["id"]: r["data_viz"] for r in
               ids_bronze.where(F.col("id").isin(str(c["id"]), str(c["id"] - 1), str(c["id"] + 1))).collect()}
        evid.append({"id": c["id"], "arquivo": c["_arquivo_origem"], "data": str(c["data"]),
                     "mesmo_id_por_extenso": str(c["id"]) in viz,
                     "data_id_menos_1": viz.get(str(c["id"] - 1), ""),
                     "data_id_mais_1": viz.get(str(c["id"] + 1), "")})
    gravar_csv(args.resultados / "fase1_ids_corrigidos.csv", sorted(evid, key=lambda r: r["id"]))

    # Conferência por ano: tudo que a Fase 0 contou, agora contado pelo Spark.
    por_ano_bronze = {r["_ano_arquivo"]: r["n"] for r in
                      vigente.groupBy("_ano_arquivo").agg(F.count("*").alias("n")).collect()}
    linhas = (silver.groupBy("ano").agg(
        F.count("*").alias("ocorrencias_silver"),
        F.sum(F.col("grave").cast("int")).alias("graves"),
        F.sum((F.col("mortos") > 0).cast("int")).alias("com_morto"),
        F.sum((~F.col("coord_valida")).cast("int")).alias("coord_invalida"),
        F.sum(F.col("id_corrigido").cast("int")).alias("id_corrigido"),
        F.sum(F.col("classificacao_imputada").cast("int")).alias("classificacao_imputada"),
        F.sum((F.col("pessoas") < F.col("total_envolvidos")).cast("int")).alias("pessoas_menor_que_total"),
        F.sum((~F.col("serie_estavel")).cast("int")).alias("antes_da_quebra"),
    ).orderBy("ano").collect())

    fase0 = {int(r["ano"]): r for r in
             csv.DictReader(open(args.resultados / "fase0_resumo_por_ano.csv", encoding="utf-8"))}
    saida = []
    for r in linhas:
        f0 = fase0[r["ano"]]
        saida.append({
            "ano": r["ano"],
            "linhas_bronze": por_ano_bronze[r["ano"]],
            "ocorrencias_silver": r["ocorrencias_silver"],
            "ocorrencias_fase0": int(f0["ocorrencias"]),
            "graves_silver": r["graves"], "graves_fase0": int(f0["graves"]),
            "com_morto_silver": r["com_morto"], "com_morto_fase0": int(f0["com_morto"]),
            "coord_invalida": r["coord_invalida"],
            "id_corrigido": r["id_corrigido"],
            "classificacao_imputada": r["classificacao_imputada"],
            "pessoas_menor_que_total": r["pessoas_menor_que_total"],
            "antes_da_quebra": r["antes_da_quebra"],
            "bate_com_fase0": (por_ano_bronze[r["ano"]] == r["ocorrencias_silver"]
                               == int(f0["ocorrencias"])
                               and r["graves"] == int(f0["graves"])
                               and r["com_morto"] == int(f0["com_morto"])),
        })
    gravar_csv(args.resultados / "fase1_conferencia_silver.csv", saida)

    with open(args.resultados / "fase1_esquema_silver.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["coluna", "tipo"])
        w.writerows(silver.dtypes)

    for r in saida:
        print(r)
    if divergentes or not all(r["bate_com_fase0"] for r in saida):
        raise SystemExit("conferência com a Fase 0 falhou: ver resultados/fase1_conferencia_*.csv")

    fase2(spark, silver, args.lake, args.resultados)
    fase3(spark, silver, args.lake, args.resultados)
    spark.stop()


def fase2(spark: SparkSession, silver: DataFrame, lake: Path, resultados: Path) -> None:
    # Testes de qualidade na silver inteira (2017 a 2025). A contagem é gravada
    # antes de decidir, para que uma reprovação fique registrada.
    contagens = contar_violacoes(silver)
    gravar_csv(resultados / "fase2_qualidade.csv", contagens)
    falhas = bloqueios(contagens)
    print("qualidade, regras com reprovação:",
          {c["regra"] for c in contagens if c["linhas_reprovadas"]}, "bloqueios:", falhas)
    if falhas:
        raise SystemExit(f"regras bloqueantes reprovaram linhas: {falhas}")

    montar_modelo(silver).write.format("delta").mode("overwrite").option("overwriteSchema", "true")         .save(str(lake / "gold_ocorrencias_modelo"))
    modelo = spark.read.format("delta").load(str(lake / "gold_ocorrencias_modelo"))
    contrato = verificar_modelo(modelo)
    print("gold do modelo:", contrato)

    agregar(silver).write.format("delta").mode("overwrite").option("overwriteSchema", "true")         .save(str(lake / "gold_graves_por_recorte"))
    agregado = spark.read.format("delta").load(str(lake / "gold_graves_por_recorte"))

    # silver x gold por ano: nenhuma ocorrência dos anos da análise some ou aparece.
    s = {r["ano"]: r for r in silver.groupBy("ano").agg(
        F.count("*").alias("n"), F.sum(F.col("grave").cast("int")).alias("g")).collect()}
    conf = []
    for r in modelo.groupBy("ano").agg(F.count("*").alias("n"),
                                       F.sum(F.col("grave").cast("int")).alias("g")).orderBy("ano").collect():
        conf.append({"ano": r["ano"], "ocorrencias_silver": s[r["ano"]]["n"], "ocorrencias_gold": r["n"],
                     "graves_silver": s[r["ano"]]["g"], "graves_gold": r["g"],
                     "bate": (s[r["ano"]]["n"], s[r["ano"]]["g"]) == (r["n"], r["g"])})
    gravar_csv(resultados / "fase2_conferencia_gold.csv", conf)

    total_n, total_g = contrato["linhas"], sum(c["graves_gold"] for c in conf)
    rec = [{"recorte": r["recorte"], "valores": r["valores"], "ocorrencias": r["n"], "graves": r["g"],
            "bate_com_total": (r["n"], r["g"]) == (total_n, total_g)}
           for r in agregado.groupBy("recorte").agg(
               F.count("*").alias("valores"), F.sum("ocorrencias").alias("n"),
               F.sum("graves").alias("g")).orderBy("recorte").collect()]
    gravar_csv(resultados / "fase2_recortes_gold.csv", rec)

    papel = {c: "contexto" for c in CONTEXTO} | {c: "dinamica" for c in DINAMICA} | {ALVO: "alvo"}
    gravar_csv(resultados / "fase2_esquema_gold_modelo.csv",
               [{"coluna": c, "tipo": t, "papel": papel.get(c, "identificacao")} for c, t in modelo.dtypes])

    for c in conf + rec:
        print(c)
    if not all(c["bate"] for c in conf) or not all(r["bate_com_total"] for r in rec):
        raise SystemExit("gold não fecha com a silver: ver resultados/fase2_*.csv")



def fase3(spark: SparkSession, silver: DataFrame, lake: Path, resultados: Path) -> None:
    # Evidência da troca de lista de causas e de tipos em 2021.
    linhas = []
    for coluna in ("causa_acidente", "tipo_acidente"):
        cont = {}
        for r in categorias_por_ano(silver, coluna).collect():
            cont.setdefault(r["valor"], {})[r["ano"]] = r["count"]
        for valor in sorted(cont, key=str):
            linhas.append({"coluna": coluna, "valor": valor,
                           **{str(a): cont[valor].get(a, 0) for a in range(2019, 2026)}})
    gravar_csv(resultados / "fase3_categorias_por_ano.csv", linhas)
    trans = [r.asDict() for c in ("causa_acidente", "tipo_acidente")
             for r in transicao_por_mes(silver, c, [2019, 2020], [2022, 2023, 2024, 2025],
                                        [2020, 2021]).collect()]
    gravar_csv(resultados / "fase3_transicao_por_mes.csv", trans)

    agregado = spark.read.format("delta").load(str(lake / "gold_graves_por_recorte"))
    comparado = comparar(agregado).cache()
    gravar_csv(resultados / "fase3_resumo_recortes.csv", [r.asDict() for r in resumo(comparado).collect()])
    colunas = ["valor", "ocorrencias", "graves", "pct_graves", "ic95_inf", "ic95_sup", "media_recorte",
               "comparacao", "posicao", "com_vitima", "pct_graves_com_vitima", "ic95_inf_com_vitima",
               "ic95_sup_com_vitima", "media_recorte_com_vitima", "comparacao_com_vitima",
               "com_morto", "mortos"]
    for (nome,) in comparado.select("recorte").distinct().collect():
        rows = (comparado.where(F.col("recorte") == nome)
                .orderBy(F.col("posicao").asc_nulls_last(), F.col("ocorrencias").desc(), "valor")
                .select(*colunas).collect())
        gravar_csv(resultados / f"fase3_recorte_{nome}.csv",
                   [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.asDict().items()}
                    for r in rows])
    print("fase 3: resultados gravados")


if __name__ == "__main__":
    main()
