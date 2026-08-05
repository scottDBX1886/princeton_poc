# Databricks notebook source
# MAGIC %md
# MAGIC # E8 · Task 1 — stage (chain root, SE-28)
# MAGIC Reads the shared foundation (read-only) and stages a working copy into the caller's
# MAGIC per-person `wksp_<user>` schema. This is the root of the orchestration DAG; every other
# MAGIC task depends (directly or transitively) on it. Nothing here mutates the foundation.

# COMMAND ----------
import re
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
SILVER = f"{CATALOG}.silver{SUFFIX}"

user = spark.sql("SELECT current_user()").first()[0]
WS = f"{CATALOG}.wksp_" + re.sub(r"[^a-zA-Z0-9]", "_", user)
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {WS}")

# Stage a lean working copy of student (foundation stays untouched)
stage = (spark.read.table(f"{SILVER}.student")
         .select("student_id", "dept_id", "status"))
stage.write.mode("overwrite").saveAsTable(f"{WS}.e8_students_stage")

n = spark.table(f"{WS}.e8_students_stage").count()
print(f"staged {n} students into {WS}.e8_students_stage")
assert n > 0, "stage produced zero rows"
