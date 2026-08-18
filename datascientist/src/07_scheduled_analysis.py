# Databricks notebook source
# MAGIC %md
# MAGIC # DS-F / DS-07: Scheduling and operationalizing a notebook
# MAGIC
# MAGIC Proves an ad-hoc analysis becomes a governed, scheduled, monitored production job
# MAGIC without rewriting it in another tool — the same notebook a data scientist developed
# MAGIC interactively is what runs on the schedule.
# MAGIC
# MAGIC Serverless. Foundation is READ-ONLY; the summary table lands in the caller's own
# MAGIC `wksp_<user>` schema (spec §3.1). The job is declared in
# MAGIC `datascientist/resources/ds_07_scheduled.job.yml`, so the schedule itself is
# MAGIC version-controlled and deploys with the bundle — not clicked together in the UI.
# MAGIC
# MAGIC ## Idempotency
# MAGIC The job appends one row per run so history accumulates — that's the point of a
# MAGIC schedule. But a re-run on the same day would double-count, so the write deletes any
# MAGIC existing row for `run_date` first. Re-running is therefore safe and the table stays
# MAGIC one-row-per-day, which is what makes the trend query below meaningful.

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
import os
import sys

sys.path.insert(0, os.getcwd())
from _isolation import resolve_context

ctx = resolve_context(spark, dbutils)
GOLD, WORK = ctx["gold"], ctx["work"]
OUT = f"{WORK}.ds_07_daily_summary"
print(f"reading {GOLD} (read-only) | appending to {OUT}")

# COMMAND ----------
# MAGIC %md ## Compute today's summary
# MAGIC `approx_percentile` rather than an exact percentile: on a multi-million-row fact the
# MAGIC approximate version is dramatically cheaper and the difference is irrelevant for a
# MAGIC daily trend metric.
# COMMAND ----------
summary = spark.sql(f"""
    SELECT
        current_date()                          AS run_date,
        count(*)                                AS total_enrollments,
        count(DISTINCT student_id)              AS unique_students,
        count(DISTINCT course_id)               AS unique_courses,
        round(avg(gpa_points), 4)               AS avg_gpa,
        round(approx_percentile(gpa_points, 0.5), 4) AS median_gpa,
        sum(CASE WHEN gpa_points IS NULL THEN 1 ELSE 0 END) AS withdrawals,
        current_timestamp()                     AS computed_at
    FROM {GOLD}.enrollment_history
""")
summary.cache()
display(summary)

# COMMAND ----------
# MAGIC %md ## Write — create if absent, replace today's row if present
# MAGIC `saveAsTable(mode="append")` alone would duplicate on re-run. Creating the table on
# MAGIC first run and deleting the current `run_date` before appending makes the job safely
# MAGIC repeatable, which matters because a scheduled job WILL be re-run manually during a demo.
# COMMAND ----------
if not spark.catalog.tableExists(OUT):
    summary.write.saveAsTable(OUT)
    print(f"created {OUT}")
else:
    run_date = summary.first()["run_date"]
    spark.sql(f"DELETE FROM {OUT} WHERE run_date = '{run_date}'")
    summary.write.mode("append").saveAsTable(OUT)
    print(f"replaced the row for {run_date} in {OUT}")

# COMMAND ----------
# MAGIC %md ## Verify + show the accumulating trend
# MAGIC After several scheduled runs this is the operational artifact: a daily series a data
# MAGIC scientist can chart or alert on, produced by a notebook nobody has to run by hand.
# COMMAND ----------
display(spark.sql(f"""
    SELECT run_date, total_enrollments, unique_students, avg_gpa, median_gpa, computed_at
    FROM {OUT}
    ORDER BY run_date DESC
    LIMIT 14
"""))

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
row = summary.first()

# The summary must reflect the real fact table, not an empty or partial read.
fact_rows = spark.table(f"{GOLD}.enrollment_history").count()
assert row["total_enrollments"] == fact_rows, (
    f"summary counted {row['total_enrollments']:,} but the fact has {fact_rows:,}"
)

# GPA metrics must sit on the foundation's 0-4 scale.
assert 0.0 <= row["avg_gpa"] <= 4.0, f"avg_gpa {row['avg_gpa']} outside 0-4"
assert 0.0 <= row["median_gpa"] <= 4.0, f"median_gpa {row['median_gpa']} outside 0-4"

# Withdrawals ('W') are the only rows with NULL gpa_points — a sanity check that the
# grade distribution is intact rather than everything being null.
assert 0 < row["withdrawals"] < fact_rows, (
    f"withdrawals={row['withdrawals']:,} looks wrong against {fact_rows:,} rows"
)

# Idempotency: exactly one row per run_date, however many times the job has run.
dupes = spark.sql(f"""
    SELECT run_date, count(*) AS n FROM {OUT} GROUP BY run_date HAVING count(*) > 1
""").count()
assert dupes == 0, f"{dupes} run_date(s) have duplicate rows — the job is not idempotent"

print(f"PASS: DS-07 — summarised {fact_rows:,} enrollments to one row for "
      f"{row['run_date']}; {spark.table(OUT).count()} day(s) of history, no duplicates.")
