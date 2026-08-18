# Databricks notebook source
# MAGIC %md
# MAGIC # DS-B / DS-04: Bring your own data — ad-hoc file upload + blend
# MAGIC
# MAGIC Proves an analyst can bring a file the platform has never seen (a spreadsheet from a
# MAGIC colleague, an external benchmark extract) and join it to governed platform data
# MAGIC without a pipeline or an ETL request.
# MAGIC
# MAGIC Serverless. Foundation is READ-ONLY.
# MAGIC
# MAGIC **Isolation note:** the uploaded file goes to a *per-person* folder under the landing
# MAGIC volume (`files/uploads/wksp_<user>/`), not to `files/` itself. The shared landing root
# MAGIC holds the foundation's own source files (`students_csv`, `financial_aid.xlsx`, …) —
# MAGIC writing a fixed filename there would collide across ~20 concurrent participants and
# MAGIC could shadow foundation inputs. Mirrors the BA-04 `files/uploads/` convention.

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
import os
import sys

sys.path.insert(0, os.getcwd())
from _isolation import resolve_context

ctx = resolve_context(spark, dbutils)
CATALOG, SUFFIX = ctx["catalog"], ctx["suffix"]
SILVER, GOLD, WORK = ctx["silver"], ctx["gold"], ctx["work"]

# Per-person upload folder, derived from the same wksp_<user> name as the output schema.
USER_DIR = WORK.split(".")[-1]
UPLOAD_DIR = f"/Volumes/{CATALOG}/landing{SUFFIX}/files/uploads/{USER_DIR}"
UPLOAD_FILE = f"{UPLOAD_DIR}/external_dept_rankings.csv"

dbutils.fs.mkdirs(UPLOAD_DIR)
print(f"upload dir: {UPLOAD_DIR}\nwriting results to: {WORK}")

# COMMAND ----------
# MAGIC %md ## Stand in for the upload
# MAGIC In the live demo the analyst drags a CSV into the Volume via Catalog Explorer (or
# MAGIC `databricks fs cp`). This cell generates an equivalent file so the notebook is
# MAGIC self-contained and re-runnable — the *ingestion* path below is identical either way.
# MAGIC
# MAGIC Deliberate real-world wrinkles: the file references only a handful of departments
# MAGIC (so the join must be a LEFT join, not INNER), and includes one `dept_id` that does
# MAGIC not exist in the platform (a stale external extract).
# COMMAND ----------
import pandas as pd

external = pd.DataFrame({
    "dept_id": [1, 5, 12, 24, 35, 999],
    "external_rank": [12, 4, 31, 1, 2, 77],
    "benchmark_score": [76.4, 91.2, 58.9, 95.2, 93.8, 10.0],
})
external.to_csv(UPLOAD_FILE, index=False)
print(f"staged {len(external)} rows -> {UPLOAD_FILE}")

# COMMAND ----------
# MAGIC %md ## Read the uploaded file
# MAGIC Explicit schema rather than `inferSchema` — an uploaded CSV is untrusted input, and
# MAGIC inference would type `dept_id` inconsistently with the platform's `bigint` and break
# MAGIC the join silently.
# COMMAND ----------
from pyspark.sql.types import DoubleType, IntegerType, LongType, StructField, StructType

upload_schema = StructType([
    StructField("dept_id", LongType(), True),
    StructField("external_rank", IntegerType(), True),
    StructField("benchmark_score", DoubleType(), True),
])

df_external = (spark.read
               .option("header", True)
               .schema(upload_schema)
               .csv(UPLOAD_FILE))
print(f"read {df_external.count()} external rows")
display(df_external)

# COMMAND ----------
# MAGIC %md ## Platform side — enrollment volume per department
# COMMAND ----------
df_internal = spark.sql(f"""
    SELECT d.dept_id, d.name AS dept_name, d.division,
           count(*) AS enrollment_count
    FROM {GOLD}.enrollment_history eh
    JOIN {SILVER}.department d ON eh.dept_id = d.dept_id
    GROUP BY d.dept_id, d.name, d.division
""")
print(f"platform departments: {df_internal.count()}")

# COMMAND ----------
# MAGIC %md ## Blend
# MAGIC LEFT join from the platform side: every department stays in the result, and the ones
# MAGIC absent from the external file get NULL benchmarks rather than disappearing.
# COMMAND ----------
df_blended = df_internal.join(df_external, on="dept_id", how="left")
out = f"{WORK}.ds_04_byo_blended"
df_blended.write.mode("overwrite").saveAsTable(out)
print(f"wrote {df_blended.count()} rows to {out}")
display(spark.sql(f"SELECT * FROM {out} WHERE external_rank IS NOT NULL ORDER BY external_rank"))

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
n_internal = df_internal.count()
n_blended = spark.table(out).count()

# A LEFT join must not change the platform-side row count. If this trips, the external file
# had duplicate dept_ids and fanned the result out.
assert n_blended == n_internal, (
    f"join changed cardinality: {n_internal} platform rows -> {n_blended} blended"
)

# Some departments must have matched, or the join keys are the wrong type.
matched = spark.table(out).filter("external_rank IS NOT NULL").count()
assert matched > 0, "no departments matched — check dept_id types on both sides"

# The stale dept_id 999 must NOT appear: a LEFT join from the platform side drops external
# keys with no platform counterpart.
assert spark.table(out).filter("dept_id = 999").count() == 0, \
    "dept_id 999 leaked in — join direction is wrong"

# The unmatched departments must survive as NULLs, which is the point of the LEFT join.
unmatched = spark.table(out).filter("external_rank IS NULL").count()
assert matched + unmatched == n_internal, "matched + unmatched should cover every department"

print(f"PASS: DS-04 blended {matched} externally-ranked departments with "
      f"{unmatched} unranked retained; stale external key correctly excluded.")
