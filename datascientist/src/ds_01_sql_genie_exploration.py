# Databricks notebook source
# MAGIC %md
# MAGIC # DS-A: SQL + Genie exploration (DS-01)
# MAGIC Ad-hoc analysis over the shared foundation — the code path (SQL here) alongside the
# MAGIC no-code path (the Genie space in `datascientist/resources/genie_foundation.genie.yml`).
# MAGIC Demonstrates window functions, CTEs, and multi-table joins against Gold + Silver.
# MAGIC
# MAGIC Foundation tables are READ-ONLY (spec §3.1). The one table this notebook writes
# MAGIC lands in the caller's own `wksp_<user>` schema, so ~20 participants can run it
# MAGIC concurrently without colliding.

# COMMAND ----------
# MAGIC %md ## Context — widgets, read-only foundation, per-person write target
# COMMAND ----------
import os
import sys

# `_isolation.py` sits alongside this notebook in datascientist/src/. Databricks sets the
# working directory to the notebook's own folder, so add that explicitly rather than
# relying on implicit sys.path behaviour.
sys.path.insert(0, os.getcwd())
from _isolation import resolve_context

ctx = resolve_context(spark, dbutils)
SILVER, GOLD, WORK = ctx["silver"], ctx["gold"], ctx["work"]
print(f"reading {SILVER} + {GOLD} (read-only) | writing to {WORK}")

# COMMAND ----------
# MAGIC %md ## Query 1 — Top departments by enrollment volume (window function)
# MAGIC `rank() OVER` over a grouped subquery: the RFP's "ranking / control-break" shape.
# COMMAND ----------
q1 = f"""
SELECT dept_id, dept_name, enrollment_count,
       rank() OVER (ORDER BY enrollment_count DESC) AS dept_rank
FROM (
  SELECT d.dept_id, d.name AS dept_name, count(*) AS enrollment_count
  FROM {GOLD}.enrollment_history eh
  JOIN {SILVER}.department d ON eh.dept_id = d.dept_id
  GROUP BY d.dept_id, d.name
)
ORDER BY dept_rank
LIMIT 20
"""
top_departments = spark.sql(q1)
display(top_departments)

# COMMAND ----------
# MAGIC %md ## Query 2 — Student GPA by term vs. cohort average (CTE + aggregate)
# MAGIC Two-stage aggregation: per-student GPA in a CTE, then the term cohort average
# MAGIC around it. `gpa_points` is NULL for withdrawals (grade 'W'), which avg() skips.
# COMMAND ----------
q2 = f"""
WITH student_term_gpa AS (
  SELECT student_id, term_id, avg(gpa_points) AS avg_gpa
  FROM {GOLD}.enrollment_history
  WHERE gpa_points IS NOT NULL
  GROUP BY student_id, term_id
)
SELECT t.term_id, t.year, t.season,
       count(DISTINCT sg.student_id) AS students,
       round(avg(sg.avg_gpa), 3)     AS cohort_avg_gpa
FROM student_term_gpa sg
JOIN {SILVER}.term t ON sg.term_id = t.term_id
GROUP BY t.term_id, t.year, t.season
ORDER BY t.year, t.season
"""
gpa_by_term = spark.sql(q2)
display(gpa_by_term)

# COMMAND ----------
# MAGIC %md ## Query 3 — Faculty teaching load (multi-table join: inner + two left)
# MAGIC Faculty -> department (inner), -> course and -> fact (left, so faculty with no
# MAGIC course offering still appear rather than being dropped).
# COMMAND ----------
q3 = f"""
SELECT f.faculty_id, f.first_name, f.last_name, f.rank,
       d.name                            AS dept_name,
       count(DISTINCT c.course_id)       AS courses_taught,
       count(DISTINCT eh.student_id)     AS students_enrolled
FROM {SILVER}.faculty f
JOIN {SILVER}.department d       ON f.dept_id = d.dept_id
LEFT JOIN {SILVER}.course c      ON f.faculty_id = c.faculty_id
LEFT JOIN {GOLD}.enrollment_history eh ON c.course_id = eh.course_id
GROUP BY f.faculty_id, f.first_name, f.last_name, f.rank, d.name
ORDER BY students_enrolled DESC
LIMIT 20
"""
faculty_load = spark.sql(q3)
display(faculty_load)

# COMMAND ----------
# MAGIC %md ## Persist one result to the per-person schema
# MAGIC Gives the scenario a durable artifact to point at (and DS-H a table to chart)
# MAGIC without writing into the shared foundation.
# COMMAND ----------
out = f"{WORK}.ds_01_dept_enrollment_rank"
top_departments.write.mode("overwrite").saveAsTable(out)
print("wrote", out)

# COMMAND ----------
# MAGIC %md ## Assertions — the verification model is "run then assert", not eyeballing
# COMMAND ----------
assert top_departments.count() > 0, "Query 1 returned no departments"
assert gpa_by_term.count() > 0, "Query 2 returned no terms"
assert faculty_load.count() > 0, "Query 3 returned no faculty"

# rank() must start at 1 and the ordering must be genuinely descending.
ranked = top_departments.orderBy("dept_rank").collect()
assert ranked[0]["dept_rank"] == 1, f"rank should start at 1, got {ranked[0]['dept_rank']}"
assert all(
    ranked[i]["enrollment_count"] >= ranked[i + 1]["enrollment_count"]
    for i in range(len(ranked) - 1)
), "enrollment_count is not descending — window ORDER BY is wrong"

# GPA must land inside the 0.0-4.0 scale defined by the foundation's grade map.
from pyspark.sql import functions as F

bounds = gpa_by_term.agg(
    F.min("cohort_avg_gpa").alias("lo"), F.max("cohort_avg_gpa").alias("hi")
).first()
assert 0.0 <= bounds["lo"] and bounds["hi"] <= 4.0, f"GPA out of 0-4 range: {bounds}"

# The persisted table is readable and non-empty.
assert spark.table(out).count() == top_departments.count(), "persisted row count mismatch"

print("PASS: DS-01 exploration queries returned ranked, bounded, joinable results.")

# COMMAND ----------
# MAGIC %md ## No-code path — Genie prompts for the same questions
# MAGIC Paste these into the Genie space "[princeton_poc] Data Foundation". Each maps to
# MAGIC one query above, so the demo can show NL and SQL reaching the same answer.
# MAGIC
# MAGIC 1. *"Which departments have the most enrollments?"* (-> Query 1)
# MAGIC 2. *"Show me average student GPA by term"* (-> Query 2)
# MAGIC 3. *"Which faculty members teach the most students, and in what department?"* (-> Query 3)
# MAGIC 4. *"Compare enrollment trends term over term for each department"* (extension)
