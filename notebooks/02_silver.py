# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Silver: limpa, tipada e deduplicada
# MAGIC
# MAGIC Lê `bronze_ocorrencias`, para se algum valor não converter para o tipo
# MAGIC esperado, aplica as regras de `src/silver.py` e grava `silver_ocorrencias`,
# MAGIC com uma linha por ocorrência.

# COMMAND ----------

# MAGIC %pip install -q --force-reinstall --no-deps /Volumes/portfolio/acidentes_prf/artefatos/acidentes_prf-0.1.0-py3-none-any.whl

# COMMAND ----------

import json

from pyspark.sql import functions as F

from src.silver import falhas_de_conversao, transformar

CATALOGO = "portfolio"
ESQUEMA = "acidentes_prf"
BRONZE = f"{CATALOGO}.{ESQUEMA}.bronze_ocorrencias"
SILVER = f"{CATALOGO}.{ESQUEMA}.silver_ocorrencias"

# COMMAND ----------

bronze = spark.table(BRONZE)

falhas = falhas_de_conversao(bronze)
n_falhas = falhas.count()
if n_falhas:
    display(falhas)
    raise ValueError(f"{n_falhas} linhas com valor que não converte. A fonte mudou: investigar antes de seguir.")

# COMMAND ----------

silver = transformar(bronze)

(silver.write
 .mode("overwrite")
 .option("overwriteSchema", "true")
 .saveAsTable(SILVER))

spark.sql(f"COMMENT ON TABLE {SILVER} IS "
          "'Silver: uma linha por ocorrência, tipada e limpa. Regras em src/silver.py'")

# COMMAND ----------

# Mesma conferência de src/executar_local.py: tem que bater com resultados/fase1_conferencia_silver.csv
conferencia = (spark.table(SILVER).groupBy("ano").agg(
    F.count("*").alias("ocorrencias"),
    F.sum(F.col("grave").cast("int")).alias("graves"),
    F.sum((F.col("mortos") > 0).cast("int")).alias("com_morto"),
    F.sum((~F.col("coord_valida")).cast("int")).alias("coord_invalida"),
    F.sum(F.col("id_corrigido").cast("int")).alias("id_corrigido"),
    F.sum(F.col("classificacao_imputada").cast("int")).alias("classificacao_imputada"),
).orderBy("ano"))
display(conferencia)

# A saída do notebook volta para quem disparou o job (CLI), para comparar com a execução local.
dbutils.notebook.exit(json.dumps([r.asDict() for r in conferencia.collect()]))
