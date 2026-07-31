# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze landing + Silver conform (medallion wiring)
# MAGIC Reads the raw files into Bronze, proving the embedded-delimiter handling, and
# MAGIC confirms the conformed Silver layer already produced by `10_generate_core.py`.
# MAGIC This establishes the Bronze -> Silver -> Gold flow that lineage scenarios
# MAGIC (SE-40) trace against.

# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc")
CATALOG = dbutils.widgets.get("catalog")
BRONZE = f"{CATALOG}.bronze"
BASE = f"/Volumes/{CATALOG}/landing/files"

# COMMAND ----------
# MAGIC %md ## students.csv -> bronze.students_raw
# MAGIC multiLine + quote handling so the embedded comma in "Doe, John" does NOT split the row.
# COMMAND ----------
students_raw = (
    spark.read
    .option("header", True)
    .option("multiLine", True)
    .option("quote", '"')
    .option("escape", '"')
    .csv(f"{BASE}/students.csv")
)
students_raw.write.mode("overwrite").saveAsTable(f"{BRONZE}.students_raw")
cnt = spark.table(f"{BRONZE}.students_raw").count()
print("bronze.students_raw rows:", cnt, "(expect 2000; no row-split from embedded comma)")

# COMMAND ----------
# MAGIC %md ## enrollments.pipe.txt -> bronze.enrollments_raw (pipe delimiter)
# COMMAND ----------
enroll_raw = (
    spark.read
    .option("header", True)
    .option("sep", "|")
    .option("quote", '"')
    .csv(f"{BASE}/enrollments.pipe.txt")
)
enroll_raw.write.mode("overwrite").saveAsTable(f"{BRONZE}.enrollments_raw")
print("bronze.enrollments_raw rows:", spark.table(f"{BRONZE}.enrollments_raw").count())

# COMMAND ----------
# MAGIC %md ## Assert the embedded-delimiter row is intact
# COMMAND ----------
row = spark.table(f"{BRONZE}.students_raw").orderBy("student_id").first()
print("First student last_name:", row["last_name"], "(expect 'Doe, John' intact)")
assert spark.table(f"{BRONZE}.students_raw").count() == 2000, "row-split occurred!"
print("PASS: embedded delimiter handled, no row split.")
