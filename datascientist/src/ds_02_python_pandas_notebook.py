# Databricks notebook source
# MAGIC %md
# MAGIC # DS-B / DS-02: Python notebook environment (pandas)
# MAGIC
# MAGIC Proves a data scientist can pull platform data into the Python ecosystem they already
# MAGIC know, transform it with pandas, and write the result back as a governed Delta table.
# MAGIC
# MAGIC Serverless. Foundation is READ-ONLY; the output lands in the caller's own
# MAGIC `wksp_<user>` schema so ~20 participants can run this at once (spec §3.1).

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
import os
import sys

sys.path.insert(0, os.getcwd())
from _isolation import resolve_context

ctx = resolve_context(spark, dbutils)
GOLD, WORK = ctx["gold"], ctx["work"]
print(f"reading {GOLD} (read-only) | writing to {WORK}")

# COMMAND ----------
# MAGIC %md ## Spark -> pandas
# MAGIC A bounded sample: `toPandas()` collects to the driver, so the LIMIT is the point —
# MAGIC pandas is for the analyst's working subset, not the 5M-row fact. DS-05 covers the
# MAGIC full-scale path.
# COMMAND ----------
import numpy as np
import pandas as pd

enrollments = spark.sql(f"""
    SELECT student_id, course_id, term_id, grade, gpa_points
    FROM {GOLD}.enrollment_history
    WHERE gpa_points IS NOT NULL      -- withdrawals ('W') carry no grade points
    LIMIT 10000
""").toPandas()

print(f"loaded {len(enrollments):,} rows into pandas")

# COMMAND ----------
# MAGIC %md ## Transform
# MAGIC Two derived columns, both deliberately built to match the foundation's own semantics.
# COMMAND ----------
# The foundation's grade scale (foundation/src/10_generate_core.py GRADE_POINTS). All ten
# grades must appear: a partial map (A/B/C/D/F only) silently NaNs every +/- grade, which is
# 53% of this dataset.
GRADE_POINTS = {"A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7,
                "C+": 2.3, "C": 2.0, "D": 1.0, "F": 0.0, "W": np.nan}

enrollments["grade_points_check"] = enrollments["grade"].map(GRADE_POINTS)

# Rolling mean per student, ordered by term — a student's GPA trend over time. Rolling over
# the raw frame (unsorted, un-grouped) would average across unrelated students and mean
# nothing.
enrollments = enrollments.sort_values(["student_id", "term_id"])
enrollments["gpa_rolling_3term"] = (
    enrollments.groupby("student_id")["gpa_points"]
               .transform(lambda s: s.rolling(window=3, min_periods=1).mean())
)

print(enrollments[["gpa_points", "grade_points_check", "gpa_rolling_3term"]].describe())

# COMMAND ----------
# MAGIC %md ## pandas -> Delta
# COMMAND ----------
out = f"{WORK}.ds_02_pandas_output"
result = enrollments[["student_id", "term_id", "grade", "gpa_points",
                      "gpa_rolling_3term"]].drop_duplicates()
spark.createDataFrame(result).write.mode("overwrite").saveAsTable(out)
print(f"wrote {len(result):,} rows to {out}")

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
# The grade map must be total over this data — this is the check the plan's partial map fails.
unmapped = enrollments["grade_points_check"].isna().sum()
assert unmapped == 0, (
    f"{unmapped} rows have an unmapped grade: "
    f"{sorted(enrollments.loc[enrollments['grade_points_check'].isna(), 'grade'].unique())}"
)

# The derived column must agree with the fact's own gpa_points, proving we reproduced the
# platform's grade scale rather than inventing one.
mismatch = (enrollments["grade_points_check"] - enrollments["gpa_points"]).abs().max()
assert mismatch < 1e-9, f"grade map disagrees with gpa_points by up to {mismatch}"

# Rolling means stay inside the 0-4 scale.
lo, hi = enrollments["gpa_rolling_3term"].min(), enrollments["gpa_rolling_3term"].max()
assert 0.0 <= lo and hi <= 4.0, f"rolling GPA out of 0-4 range: {lo}-{hi}"

assert spark.table(out).count() == len(result), "persisted row count mismatch"
print("PASS: DS-02 pandas round-trip — all grades mapped, derived GPA matches the platform.")
