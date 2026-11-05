# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Silver: limpa, tipada, uma linha por ocorrência
# MAGIC
# MAGIC Lê `bronze_ocorrencias` e usa só a ingestão mais recente de cada arquivo.
# MAGIC Para se algum valor estiver fora do formato, faltar campo obrigatório ou
# MAGIC um id se repetir. Depois aplica as regras de `src/silver.py` e grava
# MAGIC `silver_ocorrencias`.

# COMMAND ----------

# MAGIC %pip install -q --force-reinstall --no-deps /Volumes/portfolio/acidentes_prf/artefatos/acidentes_prf-0.1.0-py3-none-any.whl

# COMMAND ----------

import json

from pyspark.sql import functions as F

from src.silver import (BronzeInvalida, ids_repetidos, problemas_por_linha,
                        transformar, ultima_ingestao, validar_bronze)

CATALOGO = "portfolio"
ESQUEMA = "acidentes_prf"
BRONZE = f"{CATALOGO}.{ESQUEMA}.bronze_ocorrencias"
SILVER = f"{CATALOGO}.{ESQUEMA}.silver_ocorrencias"

# COMMAND ----------

bronze = spark.table(BRONZE)

try:
    validar_bronze(bronze)
except BronzeInvalida:
    display(problemas_por_linha(bronze).limit(100))
    display(ids_repetidos(bronze).limit(100))
    raise

# COMMAND ----------

silver = transformar(bronze)

(silver.write
 .mode("overwrite")
 .option("overwriteSchema", "true")
 .saveAsTable(SILVER))

spark.sql(f"COMMENT ON TABLE {SILVER} IS "
          "'Silver: uma linha por ocorrência, tipada e limpa. Regras em src/silver.py'")

# COMMAND ----------

# Nenhuma linha da ingestão vigente pode sumir nem aparecer na silver.
n_bronze = ultima_ingestao(bronze).count()
n_silver = spark.table(SILVER).count()
assert n_bronze == n_silver, f"bronze vigente {n_bronze} linhas, silver {n_silver}"

# Mesma conferência de src/executar_local.py. A saída volta para quem disparou
# o job e src/conferir_databricks.py compara com resultados/fase1_conferencia_silver.csv.
conferencia = (spark.table(SILVER).groupBy("ano").agg(
    F.count("*").alias("ocorrencias"),
    F.sum(F.col("grave").cast("int")).alias("graves"),
    F.sum((F.col("mortos") > 0).cast("int")).alias("com_morto"),
    F.sum((~F.col("coord_valida")).cast("int")).alias("coord_invalida"),
    F.sum(F.col("id_corrigido").cast("int")).alias("id_corrigido"),
    F.sum(F.col("classificacao_imputada").cast("int")).alias("classificacao_imputada"),
).orderBy("ano"))
display(conferencia)

dbutils.notebook.exit(json.dumps({"linhas_bronze_vigente": n_bronze,
                                  "por_ano": [r.asDict() for r in conferencia.collect()]}))
