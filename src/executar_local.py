"""Roda bronze e silver no Spark local, nos ZIPs reais, e confere com a Fase 0.

É o mesmo caminho que os notebooks do Databricks fazem, só que com Delta em
disco local. Serve para provar que a leitura com Spark bate com a contagem
feita na Fase 0 com a biblioteca padrão (src/validar_fonte.py).

Uso (dentro do container de testes, ver README):
    python -m src.executar_local --dados /dados/bruto --lake /lake --resultados resultados
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from src.bronze import extrair_zip, montar_bronze
from src.regras import ANO_INICIAL
from src.silver import falhas_de_conversao, transformar


def sessao_local(lake: Path) -> SparkSession:
    b = (SparkSession.builder.master("local[*]").appName("acidentes-prf")
         .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
         .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
         .config("spark.sql.warehouse.dir", str(lake / "warehouse"))
         .config("spark.sql.session.timeZone", "America/Sao_Paulo")
         .config("spark.driver.memory", "2g")
         .config("spark.ui.enabled", "false"))
    return configure_spark_with_delta_pip(b).getOrCreate()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", type=Path, required=True)
    ap.add_argument("--lake", type=Path, required=True)
    ap.add_argument("--resultados", type=Path, default=Path("resultados"))
    ap.add_argument("--ano-final", type=int, default=2025)
    args = ap.parse_args()

    zips = sorted(z for z in args.dados.glob("ocorrencia_*/ocorrencia_*.zip")
                  if ANO_INICIAL <= int(z.stem.split("_")[1]) <= args.ano_final)
    csvs = [str(extrair_zip(z, args.lake / "csv")) for z in zips]

    spark = sessao_local(args.lake)
    ingerido_em = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    bronze = montar_bronze(spark, csvs, ingerido_em)
    bronze.write.format("delta").mode("overwrite").save(str(args.lake / "bronze_ocorrencias"))
    bronze = spark.read.format("delta").load(str(args.lake / "bronze_ocorrencias"))

    n_falhas = falhas_de_conversao(bronze).count()
    if n_falhas:
        raise SystemExit(f"{n_falhas} linhas com valor que não converte; ver falhas_de_conversao")

    silver = transformar(bronze)
    (silver.write.format("delta").mode("overwrite")
     .save(str(args.lake / "silver_ocorrencias")))
    silver = spark.read.format("delta").load(str(args.lake / "silver_ocorrencias"))

    # Ids corrigidos (notação científica): o mesmo número existe escrito por
    # extenso em outra linha? Os vizinhos (id-1 e id+1) são do mesmo dia?
    corrigidos = silver.where("id_corrigido").select("id", "data", "_arquivo_origem").collect()
    ids_bronze = bronze.select("id", F.col("data_inversa").alias("data_viz"))
    evid = []
    for c in corrigidos:
        viz = {r["id"]: r["data_viz"] for r in
               ids_bronze.where(F.col("id").isin(str(c["id"]), str(c["id"] - 1), str(c["id"] + 1))).collect()}
        evid.append({"id": c["id"], "arquivo": c["_arquivo_origem"], "data": str(c["data"]),
                     "mesmo_id_por_extenso": str(c["id"]) in viz,
                     "data_id_menos_1": viz.get(str(c["id"] - 1), ""),
                     "data_id_mais_1": viz.get(str(c["id"] + 1), "")})
    args.resultados.mkdir(exist_ok=True)
    with open(args.resultados / "fase1_ids_corrigidos.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "arquivo", "data", "mesmo_id_por_extenso",
                                          "data_id_menos_1", "data_id_mais_1"], lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(evid, key=lambda r: r["id"]))

    # Conferência por ano: tudo que a Fase 0 contou, agora contado pelo Spark.
    por_ano_bronze = {r["_ano_arquivo"]: r["n"] for r in
                      bronze.groupBy("_ano_arquivo").agg(F.count("*").alias("n")).collect()}
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
    args.resultados.mkdir(exist_ok=True)
    with open(args.resultados / "fase1_conferencia_silver.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(saida[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(saida)

    with open(args.resultados / "fase1_esquema_silver.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["coluna", "tipo"])
        w.writerows(silver.dtypes)

    for r in saida:
        print(r)
    spark.stop()


if __name__ == "__main__":
    main()
