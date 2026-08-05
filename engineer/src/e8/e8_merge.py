# Databricks notebook source
# MAGIC %md
# MAGIC # E8 · Task 3 — fan-in merge (SE-28)
# MAGIC Depends on BOTH parallel legs; the scheduler holds this until leg A and leg B finish.
# MAGIC Demonstrates a join point in the DAG (the "chain" narrowing back to one task).

# COMMAND ----------
import re
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "princeton_poc_dev")
CATALOG = dbutils.widgets.get("catalog")
user = spark.sql("SELECT current_user()").first()[0]
WS = f"{CATALOG}.wksp_" + re.sub(r"[^a-zA-Z0-9]", "_", user)

by_dept = spark.read.table(f"{WS}.e8_by_dept")
by_status = spark.read.table(f"{WS}.e8_by_status")

summary = spark.createDataFrame(
    [("departments", by_dept.count(), by_dept.agg(F.sum("n_students")).first()[0]),
     ("statuses",    by_status.count(), by_status.agg(F.sum("n_students")).first()[0])],
    ["dimension", "n_groups", "n_students"])
summary.write.mode("overwrite").saveAsTable(f"{WS}.e8_summary")

summary.show()
total = summary.agg(F.max("n_students")).first()[0]
print(f"merge: both parallel legs reconciled; {total} students each way -> {WS}.e8_summary")
