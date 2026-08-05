# Databricks notebook source
# MAGIC %md
# MAGIC # E8 · Task 2a — parallel leg A (SE-29)
# MAGIC Independent of leg B; both depend only on `stage`, so the scheduler runs them in
# MAGIC parallel. Leg A = per-department counts.

# COMMAND ----------
import re
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "princeton_poc_dev")
CATALOG = dbutils.widgets.get("catalog")
user = spark.sql("SELECT current_user()").first()[0]
WS = f"{CATALOG}.wksp_" + re.sub(r"[^a-zA-Z0-9]", "_", user)

stage = spark.read.table(f"{WS}.e8_students_stage")
by_dept = stage.groupBy("dept_id").agg(F.count("*").alias("n_students"))
by_dept.write.mode("overwrite").saveAsTable(f"{WS}.e8_by_dept")

print(f"leg A: wrote {by_dept.count()} dept rows to {WS}.e8_by_dept")
