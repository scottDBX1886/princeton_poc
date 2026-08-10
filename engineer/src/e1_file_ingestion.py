# Databricks notebook source
# MAGIC %md
# MAGIC # E1 — Multi-format file ingestion (SE-04, SE-05, SE-06, SE-07)
# MAGIC Reads the shared foundation's five source formats from the landing Volume into a
# MAGIC per-person Bronze schema. Proves the platform ingests CSV (quoted/embedded
# MAGIC delimiters), pipe-delimited text, multi-sheet Excel (named sheet), nested JSON,
# MAGIC and XML with optional nodes — all with native readers.
# MAGIC
# MAGIC **Foundation is read-only.** Outputs go to your own `wksp_<you>` schema so ~20
# MAGIC people can run this concurrently without collisions.

# COMMAND ----------
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")

# Per-person output schema derived from the runner's identity (multi-user isolation).
user = spark.sql("SELECT current_user()").first()[0]
import re
USER_SCHEMA = "wksp_" + re.sub(r"[^a-zA-Z0-9]", "_", user)
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{USER_SCHEMA}")
OUT = f"{CATALOG}.{USER_SCHEMA}"

LANDING = f"/Volumes/{CATALOG}/landing{SUFFIX}/files"
print(f"reading from: {LANDING}")
print(f"writing to:   {OUT}.e1_*")

# COMMAND ----------
# MAGIC %md ## 1. CSV — quoted fields with embedded commas (SE-04)
# MAGIC `quote`/`escape` + multiLine keep `"Doe, John"` in one field instead of splitting the row.
# COMMAND ----------
students = (spark.read
  .option("header", True).option("multiLine", True)
  .option("quote", '"').option("escape", '"')
  .format("csv").load(f"{LANDING}/students_csv"))
students.write.mode("overwrite").saveAsTable(f"{OUT}.e1_students_raw")
print("students:", students.count())
# gotcha check: the injected embedded-comma value survived as one field
display(students.filter(F.col("last_name") == "Doe, John").select("student_id", "last_name"))

# COMMAND ----------
# MAGIC %md ## 2. Pipe-delimited — field containing a pipe (SE-04)
# COMMAND ----------
enrollments = (spark.read
  .option("header", True).option("sep", "|").option("quote", '"')
  .format("csv").load(f"{LANDING}/enrollments_pipe"))
enrollments.write.mode("overwrite").saveAsTable(f"{OUT}.e1_enrollments_raw")
print("enrollments:", enrollments.count())

# COMMAND ----------
# MAGIC %md ## 3. Excel — target a NAMED sheet, not the first (SE-05)
# MAGIC Native Excel reader (DBR 17.1+). `dataAddress` selects the `AidDetail` sheet;
# MAGIC the workbook also has `Summary` and `Decoy` sheets we deliberately skip.
# COMMAND ----------
aid = (spark.read.format("excel")
  .option("headerRows", 1)
  .option("dataAddress", "AidDetail")   # bare sheet name (matches how it was written)
  .load(f"{LANDING}/financial_aid_xlsx/financial_aid.xlsx"))
aid.write.mode("overwrite").saveAsTable(f"{OUT}.e1_financial_aid_raw")
print("financial_aid (AidDetail sheet):", aid.count())

# COMMAND ----------
# MAGIC %md ## 4. Nested JSON — arrays of structs, optional keys (SE-06)
# MAGIC dept -> courses[] -> sections[]; `prerequisite` present on only some records.
# COMMAND ----------
catalog = (spark.read.option("multiLine", True)
  .format("json").load(f"{LANDING}/course_catalog_json"))
catalog.write.mode("overwrite").saveAsTable(f"{OUT}.e1_course_catalog_raw")
print("course_catalog (departments):", catalog.count())
# show the nesting + optional field surviving as null where absent
display(catalog.select("dept_id", "name", F.size("courses").alias("n_courses")))

# COMMAND ----------
# MAGIC %md ## 5. XML — repeating elements, optional <tenure> node (SE-07)
# MAGIC rowTag=faculty; `tenure` is null on records where the node was absent (no row drop).
# COMMAND ----------
faculty = (spark.read.format("xml")
  .option("rowTag", "faculty")
  .load(f"{LANDING}/faculty_xml"))
faculty.write.mode("overwrite").saveAsTable(f"{OUT}.e1_faculty_raw")
print("faculty:", faculty.count())
display(faculty.groupBy(F.col("tenure").isNotNull().alias("has_tenure")).count())

# COMMAND ----------
# MAGIC %md ## Verify — all five formats landed
# COMMAND ----------
for t in ["e1_students_raw", "e1_enrollments_raw", "e1_financial_aid_raw",
          "e1_course_catalog_raw", "e1_faculty_raw"]:
    c = spark.table(f"{OUT}.{t}").count()
    print(f"{t}: {c}")
    assert c > 0, f"{t} is empty!"
print("PASS: all five file formats ingested to", OUT)
