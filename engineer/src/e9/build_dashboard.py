#!/usr/bin/env python3
"""Generate the E9 workload-monitoring dashboard serialization (e9_monitoring.lvdash.json).

Runs locally (no Databricks connection needed) — it only emits JSON. Every query was tested
against the live system tables on the dev warehouse before this file was written.

The dashboard reads Databricks system tables, so it works with NO custom ingestion — the
platform captures telemetry automatically. It covers ALL THREE workload types:
  - Jobs      -> system.lakeflow.job_run_timeline      (scoped by job name LIKE '%princeton_poc%')
  - Pipelines -> system.lakeflow.pipeline_update_timeline (scoped by pipeline name LIKE '%princeton_poc%')
  - Notebooks -> system.query.history query_source.notebook_id (scoped by POC SQL warehouse)

Notebook statements aren't tagged with a catalog, so they're scoped by the POC SQL warehouse
id. That id is baked into the JSON at generation time (dashboards have no runtime variables).
Regenerate for another target with its warehouse:
    python engineer/src/e9/build_dashboard.py --warehouse <warehouse_id>
"""
import argparse, json, pathlib

ap = argparse.ArgumentParser()
ap.add_argument("--warehouse", default="a94a22f8652d85c1",
                help="POC SQL warehouse id used to scope notebook-origin statements")
WH = ap.parse_args().warehouse

# --- Shared CTEs (verified 2026-08-05) -------------------------------------------------
# Timeline tables are one row per state-period; result_state is only on the terminal row,
# so GROUP BY run + MAX(CASE WHEN result_state IS NOT NULL ...). The jobs/pipelines tables
# are SCD (change_time/delete_time) -> ROW_NUMBER picks the current name. Durations come
# from period timestamps (serverless leaves *_duration_seconds at 0). Notebook rows come
# from query.history where query_source.notebook_id is set, scoped to the POC warehouse.
UNIFIED_CTE = f"""
WITH jn AS (
  SELECT job_id, name, ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY change_time DESC) rn
  FROM system.lakeflow.jobs WHERE delete_time IS NULL),
job_runs AS (
  SELECT 'Job' AS workload_type, jn.name AS name, r.run_id,
         MIN(r.period_start_time) AS start_time, MAX(r.period_end_time) AS end_time,
         MAX(CASE WHEN r.result_state IS NOT NULL THEN r.result_state END) AS raw_state
  FROM system.lakeflow.job_run_timeline r JOIN jn ON r.job_id=jn.job_id AND jn.rn=1
  WHERE jn.name LIKE '%princeton_poc%' GROUP BY jn.name, r.run_id),
pn AS (
  SELECT pipeline_id, name, ROW_NUMBER() OVER (PARTITION BY pipeline_id ORDER BY change_time DESC) rn
  FROM system.lakeflow.pipelines WHERE delete_time IS NULL),
pipe_runs AS (
  SELECT 'Pipeline' AS workload_type, pn.name AS name, u.update_id AS run_id,
         MIN(u.period_start_time) AS start_time, MAX(u.period_end_time) AS end_time,
         MAX(CASE WHEN u.result_state IS NOT NULL THEN u.result_state END) AS raw_state
  FROM system.lakeflow.pipeline_update_timeline u JOIN pn ON u.pipeline_id=pn.pipeline_id AND pn.rn=1
  WHERE pn.name LIKE '%princeton_poc%' GROUP BY pn.name, u.update_id),
nb_runs AS (
  SELECT 'Notebook' AS workload_type,
         concat('Notebook: ', substr(regexp_replace(statement_text, '\\\\s+', ' '), 1, 40)) AS name,
         statement_id AS run_id, start_time, end_time, execution_status AS raw_state
  FROM system.query.history
  WHERE query_source.notebook_id IS NOT NULL AND compute.warehouse_id = '{WH}'
    AND start_time >= date_sub(current_date(), 30)),
unioned AS (
  SELECT * FROM job_runs WHERE raw_state IS NOT NULL
  UNION ALL SELECT * FROM pipe_runs WHERE raw_state IS NOT NULL
  UNION ALL SELECT * FROM nb_runs),
runs AS (
  SELECT workload_type, name, run_id, start_time, end_time,
    CASE WHEN raw_state IN ('SUCCEEDED','FINISHED','COMPLETED') THEN 'Succeeded'
         WHEN raw_state IN ('ERROR','FAILED','TIMEDOUT') THEN 'Failed'
         WHEN raw_state IN ('CANCELED','CANCELLED') THEN 'Canceled'
         ELSE 'Other' END AS status, raw_state,
    round((unix_timestamp(end_time)-unix_timestamp(start_time))/60.0, 2) AS duration_min
  FROM unioned)
""".strip()

RUNS = UNIFIED_CTE + """
SELECT workload_type, name, run_id, start_time, status, raw_state, duration_min
FROM runs ORDER BY start_time DESC LIMIT 500
"""

KPI = UNIFIED_CTE + """
SELECT count(*) AS total_runs,
  sum(CASE WHEN status='Succeeded' THEN 1 ELSE 0 END) AS succeeded,
  sum(CASE WHEN status='Failed' THEN 1 ELSE 0 END) AS failed,
  round(100.0*sum(CASE WHEN status='Succeeded' THEN 1 ELSE 0 END)/count(*), 1) AS success_pct
FROM runs
"""

BY_TYPE = UNIFIED_CTE + """
SELECT workload_type, status, count(*) AS n FROM runs GROUP BY workload_type, status
"""

# Job task detail stays job-only (tasks are a jobs concept) — retry visibility for E8.
TASKS = [
    "WITH jn AS (",
    "  SELECT job_id, name, ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY change_time DESC) rn",
    "  FROM system.lakeflow.jobs WHERE delete_time IS NULL),",
    "tasks AS (",
    "  SELECT job_id, job_run_id, task_key, MIN(period_start_time) task_start,",
    "         MAX(period_end_time) task_end,",
    "         MAX(CASE WHEN result_state IS NOT NULL THEN result_state END) result_state",
    "  FROM system.lakeflow.job_task_run_timeline GROUP BY job_id, job_run_id, task_key)",
    "SELECT jn.name AS job_name, t.task_key, t.result_state,",
    "  round((unix_timestamp(t.task_end)-unix_timestamp(t.task_start))/60.0, 2) AS duration_min,",
    "  t.task_start",
    "FROM tasks t JOIN jn ON t.job_id=jn.job_id AND jn.rn=1",
    "WHERE jn.name LIKE '%princeton_poc%' AND t.result_state IS NOT NULL",
    "  AND t.task_start >= date_sub(current_date(), 30)",
    "ORDER BY t.task_start DESC",
]


def lines(sql):
    return [l + "\n" for l in sql.strip().splitlines()]


def counter(name, dataset, field, title, x):
    return {"widget": {"name": name,
            "queries": [{"name": "main_query", "query": {"datasetName": dataset,
                "fields": [{"name": field, "expression": f"`{field}`"}], "disaggregated": True}}],
            "spec": {"version": 2, "widgetType": "counter",
                     "encodings": {"value": {"fieldName": field, "displayName": title}},
                     "frame": {"title": title, "showTitle": True}}},
            "position": {"x": x, "y": 2, "width": 2, "height": 3}}


def text(name, line, y):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": [line]}},
            "position": {"x": 0, "y": y, "width": 6, "height": 1}}


dashboard = {
    "datasets": [
        {"name": "kpi", "displayName": "KPI summary (all workloads, 30d)", "queryLines": lines(KPI)},
        {"name": "by_type", "displayName": "Runs by workload type & status", "queryLines": lines(BY_TYPE)},
        {"name": "runs", "displayName": "Run history (all workloads, 30d)", "queryLines": lines(RUNS)},
        {"name": "tasks", "displayName": "Job task detail (30d)", "queryLines": [l + "\n" for l in TASKS]},
    ],
    "pages": [{
        "name": "monitoring",
        "displayName": "Workload Monitoring",
        "pageType": "PAGE_TYPE_CANVAS",
        "layout": [
            text("title", "## Princeton POC — Workload Monitoring (SE-34)", 0),
            text("subtitle",
                 "Jobs, pipelines & notebook runs — sourced live from `system.lakeflow` and "
                 "`system.query.history` (no custom ingestion). Last 30 days.", 1),
            counter("kpi-total", "kpi", "total_runs", "Total runs", 0),
            counter("kpi-failed", "kpi", "failed", "Failed", 2),
            counter("kpi-success-pct", "kpi", "success_pct", "Success %", 4),
            # Runs by workload type, colored by status (cardinality: 3 types x 4 statuses)
            {"widget": {"name": "runs-by-type",
                "queries": [{"name": "main_query", "query": {"datasetName": "by_type",
                    "fields": [{"name": "workload_type", "expression": "`workload_type`"},
                               {"name": "status", "expression": "`status`"},
                               {"name": "sum(n)", "expression": "SUM(`n`)"}],
                    "disaggregated": False}}],
                "spec": {"version": 3, "widgetType": "bar",
                         "encodings": {
                             "x": {"fieldName": "workload_type", "scale": {"type": "categorical"}, "displayName": "Workload type"},
                             "y": {"fieldName": "sum(n)", "scale": {"type": "quantitative"}, "displayName": "Runs"},
                             "color": {"fieldName": "status", "scale": {"type": "categorical"}, "displayName": "Status"}},
                         "frame": {"title": "Runs by workload type & status", "showTitle": True}}},
             "position": {"x": 0, "y": 5, "width": 3, "height": 5}},
            # Avg job-task duration (E8 DAG, incl. retry_demo)
            {"widget": {"name": "task-durations",
                "queries": [{"name": "main_query", "query": {"datasetName": "tasks",
                    "fields": [{"name": "task_key", "expression": "`task_key`"},
                               {"name": "avg(duration_min)", "expression": "AVG(`duration_min`)"}],
                    "disaggregated": False}}],
                "spec": {"version": 3, "widgetType": "bar",
                         "encodings": {
                             "x": {"fieldName": "task_key", "scale": {"type": "categorical"}, "displayName": "Task"},
                             "y": {"fieldName": "avg(duration_min)", "scale": {"type": "quantitative"}, "displayName": "Avg min"}},
                         "frame": {"title": "Avg job-task duration (min)", "showTitle": True}}},
             "position": {"x": 3, "y": 5, "width": 3, "height": 5}},
            text("runs-header", "### Recent runs — jobs, pipelines & notebooks", 10),
            {"widget": {"name": "runs-table",
                "queries": [{"name": "main_query", "query": {"datasetName": "runs",
                    "fields": [{"name": "workload_type", "expression": "`workload_type`"},
                               {"name": "name", "expression": "`name`"},
                               {"name": "start_time", "expression": "`start_time`"},
                               {"name": "status", "expression": "`status`"},
                               {"name": "raw_state", "expression": "`raw_state`"},
                               {"name": "duration_min", "expression": "`duration_min`"}],
                    "disaggregated": True}}],
                "spec": {"version": 2, "widgetType": "table",
                         "encodings": {"columns": [
                             {"fieldName": "workload_type", "displayName": "Type"},
                             {"fieldName": "name", "displayName": "Name"},
                             {"fieldName": "start_time", "displayName": "Started"},
                             {"fieldName": "status", "displayName": "Status"},
                             {"fieldName": "raw_state", "displayName": "Raw state"},
                             {"fieldName": "duration_min", "displayName": "Duration (min)"}]},
                         "frame": {"title": "Run history — all workloads (last 30 days)", "showTitle": True}}},
             "position": {"x": 0, "y": 11, "width": 6, "height": 7}},
        ],
    }],
}

out = pathlib.Path(__file__).parent / "e9_monitoring.lvdash.json"
out.write_text(json.dumps(dashboard, indent=2))
print(f"wrote {out} ({len(json.dumps(dashboard))} bytes); notebook warehouse scope = {WH}")
