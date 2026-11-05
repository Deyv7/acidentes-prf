from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

b = SparkSession.builder.master("local[1]").config("spark.ui.enabled", "false")
s = configure_spark_with_delta_pip(b).getOrCreate()
print("Spark", s.version)
s.stop()
