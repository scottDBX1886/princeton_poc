# Databricks notebook source
# MAGIC %md
# MAGIC # E8 · Task 2b — parallel leg B (SE-29)
# MAGIC Independent of leg A; runs in parallel. Leg B = per-status counts.

# COMMAND ----------
import re
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "princeton_poc_dev")
CATALOG = dbutils.widgets.get("catalog")
user = spark.sql("SELECT current_user()").first()[0]
WS = f"{CATALOG}.wksp_" + re.sub(r"[^a-zA-Z0-9]", "_", user)

stage = spark.read.table(f"{WS}.e8_students_stage")
by_status = stage.groupBy("status").agg(F.count("*").alias("n_students"))
by_status.write.mode("overwrite").saveAsTable(f"{WS}.e8_by_status")

print(f"leg B: wrote {by_status.count()} status rows to {WS}.e8_by_status")
