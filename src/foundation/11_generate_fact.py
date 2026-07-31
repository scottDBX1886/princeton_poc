# Databricks notebook source
# MAGIC %md
# MAGIC # Fact generator — `enrollment_history` (scalable)
# MAGIC Grain: one student x one course x one term. Volume controlled by the `row_count`
# MAGIC widget (default 5M internal; override to ~50M for the POC). Liquid-clustered on
# MAGIC (term_id, dept_id). Powers DS-05 (large dataset) and PA-13..18 (compute/capacity).
# MAGIC
# MAGIC dept_id is carried from the sampled student so the RLS key stays consistent with
# MAGIC the dimensions. Uses seeded rand() for reproducibility.

# COMMAND ----------
dbutils.widgets.text("row_count", "5000000")
N = int(dbutils.widgets.get("row_count"))
SEED = 42
CATALOG = "princeton_poc"
SILVER = f"{CATALOG}.silver"
GOLD = f"{CATALOG}.gold"

from pyspark.sql import functions as F

# COMMAND ----------
# MAGIC %md ## Cardinalities from the dimensions (keeps FKs in range)
# COMMAND ----------
n_students = spark.table(f"{SILVER}.student").count()
n_courses = spark.table(f"{SILVER}.course").count()
n_terms = spark.table(f"{SILVER}.term").count()
print(f"students={n_students} courses={n_courses} terms={n_terms} target_rows={N}")

grades = ["A", "A-", "B+", "B", "B-", "C+", "C", "D", "F", "W"]

# COMMAND ----------
# MAGIC %md ## Build N rows via seeded sampling, then resolve dept_id from student
# COMMAND ----------
base = (
    spark.range(N)
    .withColumn("student_id", (F.rand(SEED) * n_students).cast("int") + 1)
    .withColumn("course_id", (F.rand(SEED + 1) * n_courses).cast("int") + 1)
    .withColumn("term_id", (F.rand(SEED + 2) * n_terms).cast("int") + 1)
    .withColumn("grade_idx", (F.rand(SEED + 3) * len(grades)).cast("int"))
    .withColumn("grade", F.element_at(F.array(*[F.lit(g) for g in grades]),
                                      F.col("grade_idx") + 1))
    .withColumn("gpa_points",
                F.when(F.col("grade") == "A", 4.0).when(F.col("grade") == "A-", 3.7)
                 .when(F.col("grade") == "B+", 3.3).when(F.col("grade") == "B", 3.0)
                 .when(F.col("grade") == "B-", 2.7).when(F.col("grade") == "C+", 2.3)
                 .when(F.col("grade") == "C", 2.0).when(F.col("grade") == "D", 1.0)
                 .when(F.col("grade") == "F", 0.0).otherwise(F.lit(None).cast("double")))
    .withColumnRenamed("id", "enrollment_id")
    .withColumn("load_ts", F.current_timestamp())
)

# Resolve dept_id from the sampled student (RLS key consistency)
students = spark.table(f"{SILVER}.student").select("student_id", "dept_id")
fact = (base.join(F.broadcast(students), "student_id", "left")
            .select("enrollment_id", "student_id", "course_id", "term_id",
                    "dept_id", "grade", "gpa_points", "load_ts"))

# COMMAND ----------
(fact.write.mode("overwrite")
     .clusterBy("term_id", "dept_id")
     .saveAsTable(f"{GOLD}.enrollment_history"))

# COMMAND ----------
print("enrollment_history rows:", spark.table(f"{GOLD}.enrollment_history").count())
