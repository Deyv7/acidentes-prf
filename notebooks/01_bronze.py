# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Bronze: o arquivo como veio
# MAGIC
# MAGIC Lê os ZIPs que estão no volume `bruto/zips`, extrai o CSV de cada um e grava
# MAGIC tudo como texto na tabela Delta `bronze_ocorrencias`, com o nome do arquivo
# MAGIC de origem e a hora da ingestão. A tabela é acumulativa (append).
# MAGIC
# MAGIC A lógica está em `src/bronze.py`, testada com pytest fora do Databricks e
# MAGIC instalada aqui como wheel. Este notebook só chama as funções.

# COMMAND ----------

# MAGIC %pip install -q --force-reinstall --no-deps /Volumes/portfolio/acidentes_prf/artefatos/acidentes_prf-0.1.0-py3-none-any.whl

# COMMAND ----------

import os

from src.bronze import agora_utc, extrair_zip, montar_bronze, zips_do_recorte

CATALOGO = "portfolio"
ESQUEMA = "acidentes_prf"
VOLUME = f"/Volumes/{CATALOGO}/{ESQUEMA}/bruto"
TABELA = f"{CATALOGO}.{ESQUEMA}.bronze_ocorrencias"

# COMMAND ----------

zips = zips_do_recorte(os.listdir(f"{VOLUME}/zips"))  # só datatran<ano>.zip de 2017 a 2025
print(len(zips), "arquivos:", zips)
assert zips, "Nenhum ZIP em bruto/zips. Ver README: subir os arquivos antes."

csvs = [str(extrair_zip(f"{VOLUME}/zips/{z}", f"{VOLUME}/csv")) for z in zips]

# COMMAND ----------

# Bronze acumulativa: cada execução acrescenta uma versão dos arquivos com o
# seu _ingerido_em (UTC). A silver usa a versão mais recente de cada ano.
bronze = montar_bronze(spark, csvs, agora_utc())
bronze.write.mode("append").saveAsTable(TABELA)

spark.sql(f"COMMENT ON TABLE {TABELA} IS "
          "'Bronze: CSVs agrupados por ocorrência da PRF, tudo como texto, mais arquivo de origem e hora da ingestão'")

# COMMAND ----------

display(spark.table(TABELA).groupBy("_ano_arquivo", "_ingerido_em").count().orderBy("_ano_arquivo", "_ingerido_em"))
