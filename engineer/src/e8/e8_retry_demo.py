# Databricks notebook source
# MAGIC %md
# MAGIC # E8 · Task 5 — automated retry on failure (SE-30)
# MAGIC Simulates a transient failure that recovers on retry, so the job demonstrates the
# MAGIC retry policy honestly AND still ends green.
# MAGIC
# MAGIC **Mechanism:** a marker file on the Volume, keyed to this job run. On the first
# MAGIC attempt the marker is absent → we create it and raise (transient failure). The task's
# MAGIC `max_retries` kicks in; on the retry the marker exists → we succeed and clean it up.
# MAGIC `job.run_id` is stable across a run's retries but fresh for each new run, so every
# MAGIC fresh run fails-once-then-succeeds (not just the very first ever).

# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
dbutils.widgets.text("run_id", "manual")   # bound to {{job.run_id}} in the job yml
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
RUN_ID = dbutils.widgets.get("run_id")

marker_dir = f"/Volumes/{CATALOG}/landing{SUFFIX}/files/e8_retry_markers"
marker = f"{marker_dir}/attempt_{RUN_ID}.marker"
dbutils.fs.mkdirs(marker_dir)

def marker_exists(path):
    try:
        dbutils.fs.ls(path)
        return True
    except Exception:
        return False

if marker_exists(marker):
    # This is a retry — the transient condition has "cleared".
    dbutils.fs.rm(marker)   # clean up so the next fresh run starts clean
    print(f"SE-30: retry attempt for run {RUN_ID} — transient condition cleared, succeeding.")
else:
    # First attempt — record it and fail so the retry policy engages.
    dbutils.fs.put(marker, f"first attempt for run {RUN_ID}", overwrite=True)
    raise RuntimeError(
        f"SE-30 simulated transient failure (run {RUN_ID}, attempt 1). "
        "The task's retry policy should re-run this and succeed.")
