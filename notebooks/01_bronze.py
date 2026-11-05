# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Bronze: o arquivo como veio
# MAGIC
# MAGIC Lê os ZIPs que estão no volume `bruto/zips`, extrai o CSV de cada um e grava
# MAGIC tudo como texto na tabela Delta `bronze_ocorrencias`, com o nome do arquivo
# MAGIC de origem e a hora da ingestão.
# MAGIC
# MAGIC A lógica está em `src/bronze.py`, testada com pytest fora do Databricks e
# MAGIC instalada aqui como wheel. Este notebook só chama as funções.

# COMMAND ----------

# MAGIC %pip install -q --force-reinstall --no-deps /Volumes/portfolio/acidentes_prf/artefatos/acidentes_prf-0.1.0-py3-none-any.whl

# COMMAND ----------

import os
from datetime import datetime, timezone

from src.bronze import extrair_zip, montar_bronze

CATALOGO = "portfolio"
ESQUEMA = "acidentes_prf"
VOLUME = f"/Volumes/{CATALOGO}/{ESQUEMA}/bruto"
TABELA = f"{CATALOGO}.{ESQUEMA}.bronze_ocorrencias"

# COMMAND ----------

zips = sorted(z for z in os.listdir(f"{VOLUME}/zips") if z.startswith("datatran") and z.endswith(".zip"))
print(len(zips), "arquivos:", zips)
assert zips, "Nenhum ZIP em bruto/zips. Ver README: subir os arquivos antes."

csvs = [str(extrair_zip(f"{VOLUME}/zips/{z}", f"{VOLUME}/csv")) for z in zips]

# COMMAND ----------

ingerido_em = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
bronze = montar_bronze(spark, csvs, ingerido_em)

(bronze.write
 .mode("overwrite")
 .option("overwriteSchema", "true")
 .saveAsTable(TABELA))

spark.sql(f"COMMENT ON TABLE {TABELA} IS "
          "'Bronze: CSVs agrupados por ocorrência da PRF, tudo como texto, mais arquivo de origem e hora da ingestão'")

# COMMAND ----------

display(spark.table(TABELA).groupBy("_ano_arquivo").count().orderBy("_ano_arquivo"))
