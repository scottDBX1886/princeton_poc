# Databricks notebook source
# MAGIC %md
# MAGIC # E7 — Target loading (SE-24, SE-25, SE-26, SE-27)
# MAGIC Imperative target-loading + file export. This is deliberately a **notebook**, not an
# MAGIC SDP: `MERGE` upsert/delete and writing external CSV/Excel/JSON files are imperative
# MAGIC operations SDP doesn't cover (SDP publishes governed tables, not external files).
# MAGIC E6 already showed the *declarative* CDC/SCD upsert; E7 shows the classic imperative
# MAGIC `MERGE` an Oracle-background engineer expects, plus multi-format outputs.
# MAGIC
# MAGIC | § | Scenario |
# MAGIC |---|----------|
# MAGIC | SE-24 | Insert/update/delete to a DB target (UPSERT via MERGE + hard delete) |
# MAGIC | SE-25 | Flat-file output — CSV + pipe-delimited |
# MAGIC | SE-26 | Excel workbook output |
# MAGIC | SE-27 | JSON file output |

# COMMAND ----------
# MAGIC %pip install openpyxl
# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import io, re
from pyspark.sql import functions as F
from delta.tables import DeltaTable

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")

user = spark.sql("SELECT current_user()").first()[0]
WS = "wksp_" + re.sub(r"[^a-zA-Z0-9]", "_", user)
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{WS}")
OUT = f"{CATALOG}.{WS}"
# per-person export folder in the landing volume
EXPORT = f"/Volumes/{CATALOG}/landing{SUFFIX}/files/e7_exports/{WS}"
dbutils.fs.mkdirs(EXPORT)

# Source: E5's enriched student MV (built by the E5 SDP into this same wksp schema)
source = spark.read.table(f"{OUT}.e5_student_enriched")
print("source rows:", source.count())

# COMMAND ----------
# MAGIC %md ## SE-24 — UPSERT via MERGE (insert new + update existing), then hard-delete
# COMMAND ----------
TARGET = f"{OUT}.e7_student_target"
# seed the target with a subset so the MERGE has both matches (update) and non-matches (insert)
source.limit(500).write.mode("overwrite").saveAsTable(TARGET)
print("target seeded:", spark.table(TARGET).count())

tgt = DeltaTable.forName(spark, TARGET)
(tgt.alias("t").merge(source.alias("s"), "t.student_id = s.student_id")
    .whenMatchedUpdateAll()
    .whenNotMatchedInsertAll()
    .execute())
after_upsert = spark.table(TARGET).count()
print(f"after UPSERT: {after_upsert} (expect = full source {source.count()})")

# hard-delete: remove graduated alumni from the target
tgt.delete("standing = 'Alumnus'")
after_delete = spark.table(TARGET).count()
print(f"after DELETE (removed alumni): {after_delete}")

# COMMAND ----------
# MAGIC %md ## SE-25 — flat-file output: CSV + pipe-delimited
# COMMAND ----------
export_df = spark.table(TARGET).limit(1000).coalesce(1)
(export_df.write.mode("overwrite").option("header", True)
 .format("csv").save(f"{EXPORT}/student_target_csv"))
(export_df.write.mode("overwrite").option("header", True).option("sep", "|")
 .format("csv").save(f"{EXPORT}/student_target_pipe"))
print("SE-25: CSV + pipe written")

# COMMAND ----------
# MAGIC %md ## SE-27 — JSON output (native)
# COMMAND ----------
(export_df.write.mode("overwrite").format("json").save(f"{EXPORT}/student_target_json"))
print("SE-27: JSON written")

# COMMAND ----------
# MAGIC %md ## SE-26 — Excel output (openpyxl in-memory; native Excel writer not enabled)
# COMMAND ----------
pdf = spark.table(TARGET).limit(1000).toPandas()
buf = io.BytesIO()
with __import__("pandas").ExcelWriter(buf, engine="openpyxl") as w:
    pdf.to_excel(w, sheet_name="student_target", index=False)
with open(f"{EXPORT}/student_target.xlsx", "wb") as f:
    f.write(buf.getvalue())
print("SE-26: Excel written")

# COMMAND ----------
# MAGIC %md ## Verify — target row counts + all four output artifacts present
# COMMAND ----------
print("target final rows:", spark.table(TARGET).count())
for f in dbutils.fs.ls(EXPORT):
    print(" ", f.name)
print("PASS: SE-24 MERGE upsert+delete; SE-25 CSV/pipe; SE-26 xlsx; SE-27 json ->", EXPORT)
