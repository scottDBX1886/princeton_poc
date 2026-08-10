# Databricks notebook source
# MAGIC %md
# MAGIC # Raw source files writer — fully Spark-native
# MAGIC Renders the SAME core data in five formats onto the landing Volume, each with the
# MAGIC deliberate "gotcha" its ingestion scenario tests. All writes use native Spark
# MAGIC datasources — no external packages, no pandas, no local filesystem. Native writers
# MAGIC produce a directory of part-file(s); native readers read the directory transparently.
# MAGIC
# MAGIC | Output | Scenario | Gotcha |
# MAGIC |--------|----------|--------|
# MAGIC | students_csv | SE-04 | quoted field w/ embedded comma |
# MAGIC | enrollments_pipe | SE-04 | pipe-delimited; field containing a pipe |
# MAGIC | financial_aid.xlsx | SE-05 | target a *named* sheet (AidDetail), not the first |
# MAGIC | course_catalog_json | SE-06 | nested objects/arrays; optional keys omitted |
# MAGIC | faculty_xml | SE-07 | repeating elements; optional <tenure> node |
# MAGIC
# MAGIC Native Excel *reads* require DBR 17.1+. The Excel *writer* is not enabled here, so
# MAGIC the .xlsx setup file is built with openpyxl (installed below) — the one exception.

# COMMAND ----------
# MAGIC %pip install openpyxl
# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import io
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "princeton_poc")
dbutils.widgets.text("schema_suffix", "")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
SILVER = f"{CATALOG}.silver{SUFFIX}"
BASE = f"/Volumes/{CATALOG}/landing{SUFFIX}/files"

# COMMAND ----------
# MAGIC %md ## students_csv — embedded delimiter inside a quoted field (SE-04)
# MAGIC quoteAll ensures the comma inside "Doe, John" stays inside one quoted field.
# COMMAND ----------
students = (
    spark.table(f"{SILVER}.student").limit(2000)
    .withColumn("last_name",
                F.when(F.col("student_id") == 1, F.lit("Doe, John"))
                 .otherwise(F.col("last_name")))
)
(students.coalesce(1).write.mode("overwrite")
 .option("header", True).option("quoteAll", True)
 .format("csv").save(f"{BASE}/students_csv"))
print("students_csv written")

# COMMAND ----------
# MAGIC %md ## enrollments_pipe — pipe-delimited; one field contains a pipe (SE-04)
# COMMAND ----------
enroll = (
    spark.table(f"{SILVER}.enrollment").limit(2000)
    .withColumn("grade",
                F.when(F.col("enrollment_id") == 1, F.lit("A|provisional"))
                 .otherwise(F.col("grade")))
)
(enroll.coalesce(1).write.mode("overwrite")
 .option("header", True).option("sep", "|").option("quoteAll", True)
 .format("csv").save(f"{BASE}/enrollments_pipe"))
print("enrollments_pipe written")

# COMMAND ----------
# MAGIC %md ## financial_aid.xlsx — 3 sheets; AidDetail is the named target (SE-05)
# MAGIC NOTE: native Excel *reads* are GA (DBR 17.1+) and are what the SE-05 DEMO uses
# MAGIC (spark.read.excel). The native Excel *writer* is not enabled in this runtime
# MAGIC ([EXCEL_DATA_WRITER_NOT_ENABLED]), so this SETUP step builds the multi-sheet .xlsx
# MAGIC in-memory with openpyxl — the one isolated exception, used only to produce a file
# MAGIC for the native read to consume.
# COMMAND ----------
import pandas as pd  # setup-only; the SE-05 demonstration read is native spark.read.excel
fa = spark.table(f"{SILVER}.financial_aid").limit(1000).toPandas()
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as w:
    fa.head(5).to_excel(w, sheet_name="Summary", index=False)
    fa.to_excel(w, sheet_name="AidDetail", index=False)   # <- named target sheet
    fa.head(1).to_excel(w, sheet_name="Decoy", index=False)
# Land the .xlsx INSIDE its own directory (like the other four formats), so Auto Loader — which
# monitors a directory, not a file — can ingest it in the E1 SDP pipeline. The batch reader
# reads the file path directly; Auto Loader reads the directory.
dbutils.fs.mkdirs(f"{BASE}/financial_aid_xlsx")
with open(f"{BASE}/financial_aid_xlsx/financial_aid.xlsx", "wb") as f:  # single sequential write to Volume
    f.write(buf.getvalue())
print("financial_aid_xlsx/financial_aid.xlsx written: Summary / AidDetail / Decoy =", len(fa), "rows")

# COMMAND ----------
# MAGIC %md ## course_catalog_json — nested dept -> [courses] with arrays; optional key omitted (SE-06)
# MAGIC Genuinely nested via structs/arrays. ignoreNullFields (Spark default) omits the
# MAGIC prerequisite key where null -> "optional keys absent".
# COMMAND ----------
courses = (
    spark.table(f"{SILVER}.course")
    .withColumn("sections", F.array(
        F.struct(F.lit("A").alias("section"), F.lit(30).alias("seats")),
        F.struct(F.lit("B").alias("section"), F.lit(25).alias("seats"))))
    .withColumn("prerequisite",
                F.when(F.col("course_id") % 2 == 0, F.lit("None"))
                 .otherwise(F.lit(None).cast("string")))
)
grouped = (courses.groupBy("dept_id")
           .agg(F.collect_list(F.struct(
               "course_id", "title", "credits", "sections", "prerequisite")).alias("courses")))
nested = (spark.table(f"{SILVER}.department").limit(10)
          .join(grouped, "dept_id", "left")
          .select("dept_id", "name", "division", "courses"))
(nested.coalesce(1).write.mode("overwrite")
 .format("json").save(f"{BASE}/course_catalog_json"))
print("course_catalog_json written")

# COMMAND ----------
# MAGIC %md ## faculty_xml — repeating <faculty> children; optional <tenure> node (SE-07)
# MAGIC Native Spark XML. tenure is null on ~2/3 of rows -> element omitted, not row-dropped.
# COMMAND ----------
faculty = (
    spark.table(f"{SILVER}.faculty").limit(200)
    .withColumn("tenure",
                F.when(F.col("faculty_id") % 3 == 0, F.lit("true"))
                 .otherwise(F.lit(None).cast("string")))
    .select(F.col("faculty_id"),
            F.concat_ws(" ", "first_name", "last_name").alias("name"),
            F.col("rank"), F.col("tenure"))
)
(faculty.coalesce(1).write.mode("overwrite")
 .option("rowTag", "faculty").option("rootTag", "faculty_roster")
 .format("xml").save(f"{BASE}/faculty_xml"))
print("faculty_xml written")

# COMMAND ----------
# MAGIC %md ## Verify all five outputs landed
# COMMAND ----------
for f in dbutils.fs.ls(BASE):
    print(f.name, "(dir)" if f.isDir() else f"({f.size} bytes)")
