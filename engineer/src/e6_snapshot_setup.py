# Databricks notebook source
# MAGIC %md
# MAGIC # E6 setup — two student snapshots for CDC/SCD (feeds the E6 SDP)
# MAGIC Creates v1 (baseline) and v2 (baseline + planted changes) student snapshots in the
# MAGIC engineer's own schema. The E6 pipeline diffs these via apply_changes_from_snapshot,
# MAGIC which is the isolation-safe, declarative form of the day-2 change script — it does
# MAGIC NOT mutate the shared foundation.
# MAGIC
# MAGIC Planted changes v1→v2: 10 inserts, 20 status updates, 5 deletes (known-answer oracle).

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

# COMMAND ----------
# MAGIC %md ## v1 — baseline snapshot (a modest, deterministic slice of students)
# COMMAND ----------
base = (spark.read.table(f"{SILVER}.student")
        .select("student_id", "first_name", "last_name", "dept_id", "status")
        .orderBy("student_id").limit(1000))
base.write.mode("overwrite").saveAsTable(f"{WS}.student_snapshot_v1")
print("v1 rows:", spark.table(f"{WS}.student_snapshot_v1").count())

# COMMAND ----------
# MAGIC %md ## v2 — baseline + planted changes (10 insert / 20 update / 5 delete)
# COMMAND ----------
v1 = spark.table(f"{WS}.student_snapshot_v1")

# 5 DELETES: drop the 5 highest student_ids
delete_ids = [r.student_id for r in v1.orderBy(F.desc("student_id")).limit(5).collect()]
# 20 UPDATES: flip status -> 'graduated' on 20 specific ids (distinct from deletes)
update_ids = [r.student_id for r in v1.filter(~F.col("student_id").isin(delete_ids))
              .orderBy("student_id").limit(20).collect()]
# 10 INSERTS: net-new students with offset ids
inserts = (v1.orderBy("student_id").limit(10)
           .withColumn("student_id", F.col("student_id") + 900000)
           .withColumn("status", F.lit("active")))

v2 = (v1.filter(~F.col("student_id").isin(delete_ids))                       # apply deletes
      .withColumn("status", F.when(F.col("student_id").isin(update_ids), F.lit("graduated"))
                             .otherwise(F.col("status")))                    # apply updates
      .unionByName(inserts))                                                 # apply inserts
v2.write.mode("overwrite").saveAsTable(f"{WS}.student_snapshot_v2")

print("v2 rows:", spark.table(f"{WS}.student_snapshot_v2").count(),
      "(expect 1000 - 5 deletes + 10 inserts = 1005)")
print("planted: 10 inserts / 20 updates / 5 deletes")
