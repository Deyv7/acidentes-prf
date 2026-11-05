# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Gold: testes de qualidade, tabela do modelo e agregados
# MAGIC
# MAGIC 1. Roda as regras de `src/qualidade.py` na silver. Se uma regra bloqueante
# MAGIC    reprovar alguma linha, para aqui.
# MAGIC 2. Grava `gold_ocorrencias_modelo`: uma linha por ocorrência de 2019 a 2025,
# MAGIC    alvo `grave`, sem colunas de desfecho.
# MAGIC 3. Grava `gold_graves_por_recorte`: % de graves com intervalo de Wilson por
# MAGIC    UF, BR, trecho, município, hora, dia, mês, fase do dia, clima, pista e causa.

# COMMAND ----------

# MAGIC %pip install -q --force-reinstall --no-deps /Volumes/portfolio/acidentes_prf/artefatos/acidentes_prf-0.1.0-py3-none-any.whl

# COMMAND ----------

import json

from pyspark.sql import functions as F

from src.gold import agregar, montar_modelo, verificar_modelo
from src.qualidade import bloqueios, contar_violacoes

CATALOGO = "portfolio"
ESQUEMA = "acidentes_prf"
SILVER = f"{CATALOGO}.{ESQUEMA}.silver_ocorrencias"
MODELO = f"{CATALOGO}.{ESQUEMA}.gold_ocorrencias_modelo"
RECORTES = f"{CATALOGO}.{ESQUEMA}.gold_graves_por_recorte"

# COMMAND ----------

silver = spark.table(SILVER)
contagens = contar_violacoes(silver)
display(spark.createDataFrame(contagens))
falhas = bloqueios(contagens)
assert not falhas, f"regras bloqueantes reprovaram linhas: {falhas}"

# COMMAND ----------

(montar_modelo(silver).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(MODELO))
spark.sql(f"COMMENT ON TABLE {MODELO} IS "
          "'Gold: uma linha por ocorrência de 2019 a 2025, alvo grave, sem colunas de desfecho. Ver src/gold.py'")
contrato = verificar_modelo(spark.table(MODELO))

(agregar(silver).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(RECORTES))
spark.sql(f"COMMENT ON TABLE {RECORTES} IS "
          "'Gold: ocorrências, graves e % de graves com IC 95% (Wilson) por recorte, 2019 a 2025'")

# COMMAND ----------

por_ano = (spark.table(MODELO).groupBy("ano")
           .agg(F.count("*").alias("ocorrencias"), F.sum(F.col("grave").cast("int")).alias("graves"))
           .orderBy("ano").collect())
por_recorte = (spark.table(RECORTES).groupBy("recorte")
               .agg(F.count("*").alias("valores"), F.sum("ocorrencias").alias("ocorrencias"),
                    F.sum("graves").alias("graves"))
               .orderBy("recorte").collect())

# Volta para quem disparou o job; src/conferir_databricks.py compara com resultados/fase2_*.csv.
dbutils.notebook.exit(json.dumps({
    "qualidade": [{k: c[k] for k in ("ano", "regra", "linhas_reprovadas")} for c in contagens],
    "contrato": contrato,
    "por_ano": [r.asDict() for r in por_ano],
    "por_recorte": [r.asDict() for r in por_recorte],
}))
