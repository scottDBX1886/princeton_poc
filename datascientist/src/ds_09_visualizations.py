# Databricks notebook source
# MAGIC %md
# MAGIC # DS-H / DS-09: Visualization and charting within the platform
# MAGIC
# MAGIC Proves a data scientist can go from query to chart to shareable dashboard without
# MAGIC leaving the platform or exporting to a BI tool.
# MAGIC
# MAGIC Serverless. Foundation is READ-ONLY; the dashboard-backing views land in the caller's
# MAGIC own `wksp_<user>` schema (spec §3.1).
# MAGIC
# MAGIC ## Two visualization surfaces, deliberately
# MAGIC | Surface | For | Shown here |
# MAGIC |---|---|---|
# MAGIC | **Notebook charts** | the analyst, mid-exploration | `display()` on each result below |
# MAGIC | **AI/BI dashboard** | stakeholders who never open a notebook | views + `ds_09_dashboard.dashboard.yml` |
# MAGIC
# MAGIC The notebook is where charting happens *while thinking*; the dashboard is the durable
# MAGIC artifact. Both read the same governed tables, so there is no extract to drift.
# MAGIC
# MAGIC **To chart a result:** run the cell, then in the output click **+ → Visualization** and
# MAGIC pick the type noted above each query. `display()` renders a table by default — the chart
# MAGIC is one click, and it persists with the notebook.

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
import os
import sys

sys.path.insert(0, os.getcwd())
from _isolation import resolve_context

ctx = resolve_context(spark, dbutils)
SILVER, GOLD, WORK = ctx["silver"], ctx["gold"], ctx["work"]
print(f"reading {GOLD} + {SILVER} (read-only) | views -> {WORK}")

# COMMAND ----------
# MAGIC %md ## Chart 1 — GPA distribution → **Bar chart**
# MAGIC X = `gpa_band`, Y = `enrollments`.
# MAGIC
# MAGIC Bands are ordered by an explicit `band_order` column. Sorting by `gpa_points` would
# MAGIC fail — it isn't in the GROUP BY, so it can't be referenced in ORDER BY
# MAGIC (`UNRESOLVED_COLUMN`). Alphabetical ordering would also be wrong: 'A' before 'Below C'
# MAGIC is luck, not intent.
# COMMAND ----------
gpa_distribution = spark.sql(f"""
    SELECT
        CASE
            WHEN gpa_points >= 3.7 THEN 'A  (3.7-4.0)'
            WHEN gpa_points >= 3.3 THEN 'A- (3.3-3.7)'
            WHEN gpa_points >= 3.0 THEN 'B+ (3.0-3.3)'
            WHEN gpa_points >= 2.7 THEN 'B  (2.7-3.0)'
            WHEN gpa_points >= 2.0 THEN 'C  (2.0-2.7)'
            WHEN gpa_points IS NULL THEN 'W  (withdrawn)'
            ELSE                        'D/F (below 2.0)'
        END AS gpa_band,
        CASE
            WHEN gpa_points >= 3.7 THEN 1
            WHEN gpa_points >= 3.3 THEN 2
            WHEN gpa_points >= 3.0 THEN 3
            WHEN gpa_points >= 2.7 THEN 4
            WHEN gpa_points >= 2.0 THEN 5
            WHEN gpa_points IS NULL THEN 7
            ELSE                        6
        END AS band_order,
        count(*) AS enrollments
    FROM {GOLD}.enrollment_history
    GROUP BY gpa_band, band_order
    ORDER BY band_order
""")
display(gpa_distribution)

# COMMAND ----------
# MAGIC %md ## Chart 2 — Enrollments by department → **Bar chart, or Scatter for the trade-off**
# MAGIC Bar: X = `department`, Y = `enrollments`.
# MAGIC Scatter: X = `enrollments`, Y = `avg_gpa` — shows whether large departments grade
# MAGIC differently, which is the more interesting question.
# COMMAND ----------
enrollments_by_dept = spark.sql(f"""
    SELECT
        d.name                          AS department,
        d.division,
        count(*)                        AS enrollments,
        round(avg(eh.gpa_points), 3)    AS avg_gpa,
        count(DISTINCT eh.student_id)   AS distinct_students
    FROM {GOLD}.enrollment_history eh
    JOIN {SILVER}.department d ON eh.dept_id = d.dept_id
    GROUP BY d.name, d.division
    ORDER BY enrollments DESC
    LIMIT 15
""")
display(enrollments_by_dept)

# COMMAND ----------
# MAGIC %md ## Chart 3 — Enrollment trend by term → **Line chart**
# MAGIC X = `term_label`, Y = `enrollments`. `term_label` is built so the axis reads
# MAGIC "2018 Fall" rather than an opaque `term_id`, while `term_id` still drives the sort —
# MAGIC seasons are not alphabetical (Fall, Spring, Summer would mis-order the academic year).
# COMMAND ----------
enrollment_trend = spark.sql(f"""
    SELECT
        t.term_id,
        concat(t.year, ' ', t.season)   AS term_label,
        t.year,
        t.season,
        count(*)                        AS enrollments,
        round(avg(eh.gpa_points), 3)    AS avg_gpa,
        count(DISTINCT eh.student_id)   AS distinct_students
    FROM {GOLD}.enrollment_history eh
    JOIN {SILVER}.term t ON eh.term_id = t.term_id
    GROUP BY t.term_id, t.year, t.season
    ORDER BY t.term_id
""")
display(enrollment_trend)

# COMMAND ----------
# MAGIC %md ## Persist the dashboard-backing views
# MAGIC The AI/BI dashboard reads views, not ad-hoc SQL, so the dashboard definition stays
# MAGIC readable and the query lives in one place.
# MAGIC
# MAGIC These are created in the caller's own schema. The phase-2 plan wrote
# MAGIC `CREATE OR REPLACE VIEW {catalog}.gold_dev.ds_09_enrollment_trend` — into the shared,
# MAGIC read-only foundation, where ~20 participants would overwrite each other's view on the
# MAGIC same name (spec §3.1 forbids writing to the foundation at all).
# MAGIC
# MAGIC It also built the view body from `df._jdf.sql()`, an internal API that does not reliably
# MAGIC return runnable SQL. The view text is declared explicitly instead.
# COMMAND ----------
views = {
    "ds_09_enrollment_trend": f"""
        SELECT t.term_id,
               concat(t.year, ' ', t.season)  AS term_label,
               t.year, t.season,
               count(*)                       AS enrollments,
               round(avg(eh.gpa_points), 3)   AS avg_gpa,
               count(DISTINCT eh.student_id)  AS distinct_students
        FROM {GOLD}.enrollment_history eh
        JOIN {SILVER}.term t ON eh.term_id = t.term_id
        GROUP BY t.term_id, t.year, t.season
    """,
    "ds_09_dept_summary": f"""
        SELECT d.dept_id, d.name AS department, d.division,
               count(*)                       AS enrollments,
               round(avg(eh.gpa_points), 3)   AS avg_gpa,
               count(DISTINCT eh.student_id)  AS distinct_students
        FROM {GOLD}.enrollment_history eh
        JOIN {SILVER}.department d ON eh.dept_id = d.dept_id
        GROUP BY d.dept_id, d.name, d.division
    """,
}
for name, body in views.items():
    spark.sql(f"CREATE OR REPLACE VIEW {WORK}.{name} AS {body}")
    print(f"created view {WORK}.{name}")

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
# Every enrollment must land in exactly one band — a CASE gap would silently drop rows.
banded = gpa_distribution.agg({"enrollments": "sum"}).first()[0]
fact_rows = spark.table(f"{GOLD}.enrollment_history").count()
assert banded == fact_rows, (
    f"bands cover {banded:,} of {fact_rows:,} enrollments — the CASE has a gap"
)

# Withdrawals have NULL gpa_points and must be their own band, not silently bucketed as D/F.
bands = {r["gpa_band"]: r["enrollments"] for r in gpa_distribution.collect()}
assert any("withdrawn" in b for b in bands), "withdrawals are not represented as a band"

# Band ordering must be monotonic — the fix for the plan's unresolvable ORDER BY.
orders = [r["band_order"] for r in gpa_distribution.collect()]
assert orders == sorted(orders), f"bands are not in GPA order: {orders}"

# Chart 2 must return the requested top-N, not fewer.
assert enrollments_by_dept.count() == 15, \
    f"expected 15 departments, got {enrollments_by_dept.count()}"

# Chart 3 must cover every term, ordered chronologically.
n_terms = spark.table(f"{SILVER}.term").count()
trend_rows = enrollment_trend.collect()
assert len(trend_rows) == n_terms, f"expected {n_terms} terms, got {len(trend_rows)}"
assert [r["term_id"] for r in trend_rows] == sorted(r["term_id"] for r in trend_rows), \
    "trend is not in term order — a line chart would zigzag"

# Views must be queryable and land in the per-person schema, not the foundation.
for name in views:
    assert spark.table(f"{WORK}.{name}").count() > 0, f"{name} returned no rows"
leaked = [t.name for t in spark.catalog.listTables(f"{GOLD.split('.')[0]}.{GOLD.split('.')[1]}")
          if t.name.startswith("ds_09")]
assert not leaked, f"ds_09 objects leaked into the shared foundation: {leaked}"

print(f"PASS: DS-09 — {len(bands)} GPA bands covering all {fact_rows:,} enrollments, "
      f"15 departments, {len(trend_rows)} terms in order; "
      f"{len(views)} dashboard views in {WORK}, foundation clean.")
