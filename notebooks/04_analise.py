# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Análise: onde e quando os acidentes graves acontecem
# MAGIC
# MAGIC Lê `gold_graves_por_recorte` e compara cada valor de cada recorte com a média
# MAGIC do recorte (`src/analise.py`). A medida é a % de graves entre os acidentes,
# MAGIC com intervalo de 95%; contagem de acidentes não é risco, porque a fonte não
# MAGIC tem volume de tráfego. O texto da análise está em `docs/analise.md`.

# COMMAND ----------

# MAGIC %pip install -q --force-reinstall --no-deps /Volumes/portfolio/acidentes_prf/artefatos/acidentes_prf-0.1.0-py3-none-any.whl

# COMMAND ----------

import json

from pyspark.sql import functions as F

from src.analise import comparar, resumo

CATALOGO = "portfolio"
ESQUEMA = "acidentes_prf"
RECORTES = f"{CATALOGO}.{ESQUEMA}.gold_graves_por_recorte"
COMPARACAO = f"{CATALOGO}.{ESQUEMA}.analise_graves_por_recorte"

# COMMAND ----------

comparado = comparar(spark.table(RECORTES))
(comparado.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(COMPARACAO))
spark.sql(f"COMMENT ON TABLE {COMPARACAO} IS "
          "'Análise: cada valor de cada recorte comparado com a média do recorte (src/analise.py)'")
r = resumo(spark.table(COMPARACAO))
display(r)

# COMMAND ----------

# Exemplo de consulta: as 10 UFs, horas e trechos com maior limite inferior de % de graves.
for recorte in ("uf", "hora", "trecho_10km"):
    display(spark.table(COMPARACAO).where(F.col("recorte") == recorte)
            .where(F.col("posicao") <= 10).orderBy("posicao")
            .select("valor", "ocorrencias", "graves", "pct_graves", "ic95_inf", "ic95_sup",
                    "comparacao", "comparacao_com_vitima"))

# COMMAND ----------

dbutils.notebook.exit(json.dumps({"resumo": [x.asDict() for x in r.collect()]}))
