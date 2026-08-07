# Databricks notebook source
# MAGIC %md
# MAGIC # DS-C / DS-05: Large-dataset handling on the multi-million-row fact
# MAGIC
# MAGIC Proves an analyst can run a genuinely heavy analytical query — full scan, join,
# MAGIC aggregate, window — over `gold.enrollment_history` (5M rows at `row_count` default,
# MAGIC ~50M in the POC) and *see why it was fast*: Photon, file pruning from liquid
# MAGIC clustering, and a broadcast join, all read back from the platform's own telemetry.
# MAGIC
# MAGIC Serverless. This notebook is almost entirely READ-ONLY over the foundation; the one
# MAGIC table it writes (its own timing record) goes to the caller's `wksp_<user>` schema.
# MAGIC
# MAGIC ## A note on measuring
# MAGIC Two sources of truth, used deliberately:
# MAGIC
# MAGIC | Source | When it's available | Used here for |
# MAGIC |---|---|---|
# MAGIC | `EXPLAIN` / `df.explain()` | immediately, in-session | plan shape: Photon, join strategy, column pruning |
# MAGIC | `DESCRIBE DETAIL` | immediately | file layout + clustering columns |
# MAGIC | `system.query.history` | **~15 min lag** | post-hoc bytes/files/rows metrics |
# MAGIC
# MAGIC The lag matters: `system.query.history` **cannot** verify a query in the same run
# MAGIC (measured ~16 min behind on this workspace). So the in-run assertions use wall-clock
# MAGIC timing and `EXPLAIN`, and the history query at the end is provided for the *demo
# MAGIC narrative* — run it a few minutes later, or against an earlier run.
# MAGIC
# MAGIC The phase-2 plan's `SET spark.databricks.queryProfile.enabled = true` and
# MAGIC `DESCRIBE QUERY PROFILE` are not real Databricks SQL — both error out
# MAGIC (`CONFIG_NOT_AVAILABLE`, `TABLE_OR_VIEW_NOT_FOUND`). Replaced with the above.

# COMMAND ----------

# MAGIC %md ## Context

# COMMAND ----------

import os
import sys
import time

sys.path.insert(0, os.getcwd())
from _isolation import resolve_context

ctx = resolve_context(spark, dbutils)
SILVER, GOLD, WORK = ctx["silver"], ctx["gold"], ctx["work"]
FACT = f"{GOLD}.enrollment_history"
print(f"fact: {FACT} | writing timings to {WORK}")

# COMMAND ----------

# MAGIC %md ## 1. Scale of the table
# MAGIC Establish that this is genuinely a large dataset before claiming anything about speed.

# COMMAND ----------

scale = spark.sql(f"""
    SELECT count(*)                  AS n_rows,
           count(DISTINCT student_id) AS n_students,
           count(DISTINCT term_id)    AS n_terms,
           count(DISTINCT dept_id)    AS n_depts
    FROM {FACT}
""").first()
print(f"rows={scale['n_rows']:,}  students={scale['n_students']:,}  "
      f"terms={scale['n_terms']}  depts={scale['n_depts']}")

# Physical layout — Delta metadata, available immediately.
detail = spark.sql(f"DESCRIBE DETAIL {FACT}").first()
print(f"files={detail['numFiles']}  size={detail['sizeInBytes']/1024**2:,.1f} MiB  "
      f"clusteringColumns={detail['clusteringColumns']}")

# COMMAND ----------

# MAGIC %md ## 2. The heavy query
# MAGIC Mirrors `foundation/src/heavy_query.sql` — the reusable analytical load the Admin
# MAGIC compute/cost scenarios (PA-13…18) also use, so timings are comparable across personas.
# MAGIC Catalog names come from widgets here; the shipped .sql file hardcodes prod names.

# COMMAND ----------

heavy_sql = f"""
SELECT d.division,
       eh.dept_id,
       eh.term_id,
       count(*)                                                      AS enrollments,
       avg(eh.gpa_points)                                            AS avg_gpa,
       count(DISTINCT eh.student_id)                                 AS distinct_students,
       rank() OVER (PARTITION BY eh.term_id ORDER BY count(*) DESC)  AS dept_rank_in_term
FROM {FACT} eh
JOIN {SILVER}.department d ON eh.dept_id = d.dept_id
WHERE eh.gpa_points IS NOT NULL
GROUP BY d.division, eh.dept_id, eh.term_id
ORDER BY eh.term_id, dept_rank_in_term
"""

# COMMAND ----------

# MAGIC %md ### Plan first — what the optimiser decided, before running it
# MAGIC `PhotonScan` + a projected `ReadSchema` narrower than the table = column pruning.
# MAGIC `PhotonBroadcastHashJoin` = the 40-row dimension was broadcast rather than shuffled.

# COMMAND ----------

import io
import contextlib

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    spark.sql(heavy_sql).explain(mode="formatted")
plan = buf.getvalue()
print(plan[:2500])

# COMMAND ----------

# MAGIC %md ### Run it, timed
# MAGIC `.collect()` forces full execution — a bare `spark.sql()` only builds a plan, so
# MAGIC timing it would measure nothing.

# COMMAND ----------

start = time.time()
rows = spark.sql(heavy_sql).collect()
elapsed = time.time() - start
print(f"{len(rows):,} result rows over {scale['n_rows']:,} fact rows in {elapsed:.2f}s "
      f"({scale['n_rows']/max(elapsed, 1e-9)/1e6:.1f}M rows/sec scanned)")
display(spark.createDataFrame(rows[:50]))

# COMMAND ----------

# MAGIC %md ## 3. Liquid clustering — does filtering a clustered column pay off?
# MAGIC `enrollment_history` is clustered on (term_id, dept_id). A filter on those columns
# MAGIC should touch far less data than a full scan. Timed side by side.

# COMMAND ----------

t0 = time.time()
full_scan = spark.sql(f"SELECT count(*) AS c FROM {FACT} WHERE gpa_points IS NOT NULL").first()["c"]
t_full = time.time() - t0

t0 = time.time()
clustered = spark.sql(
    f"SELECT count(*) AS c FROM {FACT} WHERE term_id = 5 AND dept_id = 24"
).first()["c"]
t_clustered = time.time() - t0

print(f"full scan      : {full_scan:,} rows in {t_full:.2f}s")
print(f"clustered filter: {clustered:,} rows in {t_clustered:.2f}s")
print(f"-> clustered read is {t_full/max(t_clustered, 1e-9):.1f}x faster on wall clock")

# MEASURED (2026-08-06, row_count=5000000): full scan 0.66s vs clustered filter 0.63s —
# effectively no difference. Expected, and worth saying out loud rather than spinning:
# `DESCRIBE DETAIL` above reports numFiles=1, so the entire 5M-row fact is a single 34 MiB
# file and there is nothing for file pruning to skip. Liquid clustering IS declared on
# (term_id, dept_id) and the plan confirms Photon, but the payoff only appears once the
# table spans many files.
#
# To make this a real comparison for the customer read-out, regenerate the fact at POC
# scale first:
#   databricks bundle run foundation_build -t dev --var row_count=50000000 --profile <PROFILE>
# Do NOT present the 5M numbers as a clustering win — at one file it is measuring noise.

# COMMAND ----------

# MAGIC %md ## 4. Record the timing (per-person table)
# MAGIC A durable artifact for the read-out, and the baseline the Admin cost scenarios
# MAGIC (PA-19…25) compare against.

# COMMAND ----------

from datetime import datetime, timezone

metrics = spark.createDataFrame([{
    "query_name": "heavy_enrollment_summary",
    "fact_rows": int(scale["n_rows"]),
    "result_rows": len(rows),
    "elapsed_seconds": round(elapsed, 2),
    "full_scan_seconds": round(t_full, 2),
    "clustered_filter_seconds": round(t_clustered, 2),
    "num_files": int(detail["numFiles"]),
    "size_mib": round(detail["sizeInBytes"] / 1024**2, 1),
    "run_at": datetime.now(timezone.utc),
}])
out = f"{WORK}.ds_05_query_metrics"
metrics.write.mode("overwrite").saveAsTable(out)
print(f"wrote timings to {out}")

# COMMAND ----------

# MAGIC %md ## 5. Assertions

# COMMAND ----------

# This scenario is meaningless on a small table — assert we really are at scale.
assert scale["n_rows"] >= 1_000_000, \
    f"DS-05 needs a multi-million-row fact; found {scale['n_rows']:,}. Run foundation_build."

# The query must return the full department x term grid, not a truncated sample.
assert len(rows) == scale["n_depts"] * scale["n_terms"], (
    f"expected {scale['n_depts']} depts x {scale['n_terms']} terms = "
    f"{scale['n_depts'] * scale['n_terms']} rows, got {len(rows)}"
)

# rank() must restart within each term partition.
per_term_top = [r for r in rows if r["dept_rank_in_term"] == 1]
assert len(per_term_top) == scale["n_terms"], (
    f"expected one rank-1 department per term ({scale['n_terms']}), got {len(per_term_top)}"
)

# GPA stays on the foundation's 0-4 scale.
gpas = [r["avg_gpa"] for r in rows if r["avg_gpa"] is not None]
assert gpas and 0.0 <= min(gpas) and max(gpas) <= 4.0, \
    f"avg_gpa outside 0-4: {min(gpas)}-{max(gpas)}"

# The plan must confirm Photon and a broadcast join — the "why it was fast" claim.
assert "Photon" in plan, "query did not run on Photon — check the compute type"
assert "BroadcastHashJoin" in plan or "EXECUTOR_BROADCAST" in plan, \
    "the 40-row department dimension should have been broadcast, not shuffled"

assert spark.table(out).count() == 1, "timing row not persisted"

print(f"PASS: DS-05 — {scale['n_rows']:,} rows aggregated to {len(rows)} groups in "
      f"{elapsed:.2f}s on Photon with a broadcast join; clustered filter "
      f"{t_full/max(t_clustered, 1e-9):.1f}x faster than full scan.")

# COMMAND ----------

# MAGIC %md ## 6. Post-hoc metrics from `system.query.history` (run ~15 min later)
# MAGIC The platform records bytes read, files pruned, and durations for every statement.
# MAGIC **This lags ~15 minutes**, so it will likely return nothing for the run above — that
# MAGIC is expected, not a failure. Re-run this cell later, or during the demo point at a
# MAGIC previous run. `pruned_files` vs `read_files` is the clustering payoff in the
# MAGIC platform's own numbers.

# COMMAND ----------

display(spark.sql(f"""
    SELECT start_time,
           left(statement_text, 60) AS statement,
           execution_duration_ms,
           read_rows, produced_rows,
           read_files, pruned_files,
           round(read_bytes / 1024 / 1024, 1) AS read_mib,
           round(spilled_local_bytes / 1024 / 1024, 1) AS spilled_mib
    FROM system.query.history
    WHERE executed_by = '{ctx["user"]}'
      AND statement_text LIKE '%enrollment_history%'
      AND statement_text NOT LIKE '%system.query.history%'
    ORDER BY start_time DESC
    LIMIT 10
"""))
