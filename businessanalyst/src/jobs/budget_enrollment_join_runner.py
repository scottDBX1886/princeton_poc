# Databricks notebook source
# MAGIC %md
# MAGIC # BA-04 / BA-05 / BA-08 — Budget-enriched enrollment (upload + join + transform, reusable)
# MAGIC
# MAGIC The no-code Lakeflow Designer canvas an analyst builds (upload budget file → join to
# MAGIC enrollment → filter → rename → derive → save) compiles to exactly these steps. This
# MAGIC notebook is the **saved, reusable job** form (BA-08) and the pre-built fallback if the
# MAGIC analyst doesn't want to drag the canvas.
# MAGIC
# MAGIC **Isolation:** writes to the caller's own `wksp_<user>` schema — NOT shared `silver_dev`
# MAGIC (the plan's original target) — so ~20 analysts can run it concurrently without collision.

# COMMAND ----------
import re
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
dbutils.widgets.text("upload_file", "departments_budget_fy2025.csv")
dbutils.widgets.text("status_filter", "active")   # BA-05 variation: change/relax the filter
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
UPLOAD = dbutils.widgets.get("upload_file")
STATUS = dbutils.widgets.get("status_filter")

user = spark.sql("SELECT current_user()").first()[0]
WS = f"{CATALOG}.wksp_" + re.sub(r"[^a-zA-Z0-9]", "_", user)
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {WS}")
TARGET = f"{WS}.ba_dept_budget_enrollment_summary"
# The landing volume is named `files`; the BA self-service uploads live under files/uploads/.
UPLOAD_PATH = f"/Volumes/{CATALOG}/landing{SUFFIX}/files/uploads/{UPLOAD}"

# COMMAND ----------
# MAGIC %md ## Step 1 — read the uploaded budget file (BA-04 "Add Data")
# COMMAND ----------
budget = (spark.read.option("header", True).option("inferSchema", True).csv(UPLOAD_PATH))
print(f"budget rows: {budget.count()} from {UPLOAD_PATH}")
budget.show(3, truncate=False)

# COMMAND ----------
# MAGIC %md ## Step 2 — join budget → course(dept) → enrollment; join student for status
# COMMAND ----------
enrollment = spark.table(f"{CATALOG}.silver{SUFFIX}.enrollment")
course = spark.table(f"{CATALOG}.silver{SUFFIX}.course").select("course_id", "dept_id")
student = spark.table(f"{CATALOG}.silver{SUFFIX}.student").select("student_id", "status")

joined = (enrollment
          .join(course, "course_id")
          .join(student, "student_id")
          .join(budget, course.dept_id == budget.dept_id))

# COMMAND ----------
# MAGIC %md ## Step 3 — filter (BA-05: parameterized; e.g. active students)
# COMMAND ----------
filtered = joined.filter(F.col("status") == STATUS)
print(f"rows after status='{STATUS}' filter: {filtered.count()}")

# COMMAND ----------
# MAGIC %md ## Step 4 — rename columns (BA-04 "Rename")
# COMMAND ----------
renamed = (filtered
           .withColumnRenamed("dept_name", "department")
           .withColumnRenamed("budget_amount", "total_budget")
           .withColumnRenamed("approved_date", "budget_approved"))

# COMMAND ----------
# MAGIC %md ## Step 5 — derive budget_per_student (BA-04 "Add Column")
# COMMAND ----------
# distinct students per department (Spark disallows countDistinct in a window, so aggregate
# separately then join back — the same result, correctly).
students_per_dept = (renamed.groupBy("department")
                     .agg(F.countDistinct("student_id").alias("_distinct_students")))
derived = (renamed.join(students_per_dept, "department")
           .withColumn("budget_per_student",
                       F.round(F.col("total_budget") / F.col("_distinct_students"), 2))
           .drop("_distinct_students"))

# COMMAND ----------
# MAGIC %md ## Step 6 — save to my wksp schema (isolation-safe)
# COMMAND ----------
(derived.select("department", "total_budget", "budget_approved",
                "enrollment_id", "student_id", "course_id", "term_id",
                "grade", "gpa_points", "budget_per_student")
        .write.mode("overwrite").saveAsTable(TARGET))

n = spark.table(TARGET).count()
print(f"wrote {n} rows to {TARGET}")

# COMMAND ----------
# MAGIC %md ## Verify — one row per department with budget + derived per-student
# COMMAND ----------
(spark.table(TARGET)
      .groupBy("department", "total_budget", "budget_per_student")
      .agg(F.count("*").alias("enrollment_count"))
      .orderBy(F.desc("enrollment_count")).show(5, truncate=False))
assert n > 0, "BA join produced zero rows"
print(f"PASS: BA-04/05/08 budget-enrollment join -> {TARGET}")
