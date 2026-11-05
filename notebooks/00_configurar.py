# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Configurar schema e volumes
# MAGIC
# MAGIC No Unity Catalog, todo dado tem um endereço de três partes: `catalogo.schema.objeto`.
# MAGIC No Free Edition o workspace já vem com um catálogo padrão; nesta conta ele se chama
# MAGIC `portfolio`, o nome do workspace. Aqui criamos o schema do projeto e dois **volumes**,
# MAGIC que são pastas de arquivos governadas pelo Unity Catalog:
# MAGIC
# MAGIC - `bruto`: os ZIPs da PRF como vieram e os CSVs extraídos;
# MAGIC - `artefatos`: o wheel com o código de `src/`, que os outros notebooks instalam.
# MAGIC
# MAGIC Rodar uma vez. Pode rodar de novo sem efeito (`IF NOT EXISTS`).

# COMMAND ----------

CATALOGO = "portfolio"  # se mudar, mude também o caminho do %pip nos notebooks 01 e 02
ESQUEMA = "acidentes_prf"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOGO}.{ESQUEMA} "
          "COMMENT 'Acidentes nas rodovias federais (dados abertos da PRF)'")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOGO}.{ESQUEMA}.bruto "
          "COMMENT 'ZIPs da PRF como baixados e CSVs extraídos'")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOGO}.{ESQUEMA}.artefatos "
          "COMMENT 'Wheel do código do projeto (src/)'")

# COMMAND ----------

import os

VOLUME = f"/Volumes/{CATALOGO}/{ESQUEMA}/bruto"
for pasta in ["zips", "csv"]:
    os.makedirs(f"{VOLUME}/{pasta}", exist_ok=True)
print(os.listdir(VOLUME))
