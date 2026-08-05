#!/usr/bin/env python3
"""Generate the E9 job-monitoring dashboard serialization (e9_monitoring.lvdash.json).

Runs locally (no Databricks connection needed) — it only emits JSON. The queries were all
tested against system.lakeflow on the dev warehouse before this file was written.

The dashboard reads Databricks system tables (system.lakeflow.*), so it works with NO custom
ingestion — job telemetry is captured by the platform automatically. Scoped to the POC jobs
via a name LIKE '%princeton_poc%' filter. Regenerate with:  python engineer/src/e9/build_dashboard.py
"""
import json, pathlib

# --- Datasets (all verified against system.lakeflow on 2026-08-05) ---------------------
# Timeline tables have one row per state-period; result_state is set only on the terminal
# row, so we GROUP BY run and take MAX(CASE WHEN result_state IS NOT NULL ...). The jobs
# table is SCD (change_time/delete_time), so ROW_NUMBER picks the current name per job_id.
# Duration is computed from timestamps (serverless leaves *_duration_seconds at 0).

RUNS = [
    "WITH jn AS (",
    "  SELECT job_id, name, ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY change_time DESC) rn",
    "  FROM system.lakeflow.jobs WHERE delete_time IS NULL),",
    "runs AS (",
    "  SELECT job_id, run_id, MIN(period_start_time) run_start, MAX(period_end_time) run_end,",
    "         MAX(CASE WHEN result_state IS NOT NULL THEN result_state END) result_state",
    "  FROM system.lakeflow.job_run_timeline GROUP BY job_id, run_id)",
    "SELECT jn.name AS job_name, r.run_id, r.run_start, r.result_state,",
    "  CASE WHEN r.result_state='SUCCEEDED' THEN 'Succeeded'",
    "       WHEN r.result_state IN ('ERROR','FAILED','TIMEDOUT') THEN 'Failed'",
    "       ELSE 'Other' END AS status,",
    "  round((unix_timestamp(r.run_end)-unix_timestamp(r.run_start))/60.0, 2) AS duration_min",
    "FROM runs r JOIN jn ON r.job_id=jn.job_id AND jn.rn=1",
    "WHERE jn.name LIKE '%princeton_poc%' AND r.result_state IS NOT NULL",
    "  AND r.run_start >= date_sub(current_date(), 30)",
    "ORDER BY r.run_start DESC",
]

KPI = [
    "WITH jn AS (",
    "  SELECT job_id, name, ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY change_time DESC) rn",
    "  FROM system.lakeflow.jobs WHERE delete_time IS NULL),",
    "runs AS (",
    "  SELECT job_id, run_id, MIN(period_start_time) run_start,",
    "         MAX(CASE WHEN result_state IS NOT NULL THEN result_state END) result_state",
    "  FROM system.lakeflow.job_run_timeline GROUP BY job_id, run_id)",
    "SELECT count(*) AS total_runs,",
    "  sum(CASE WHEN result_state='SUCCEEDED' THEN 1 ELSE 0 END) AS succeeded,",
    "  sum(CASE WHEN result_state IN ('ERROR','FAILED','TIMEDOUT') THEN 1 ELSE 0 END) AS failed,",
    "  round(100.0*sum(CASE WHEN result_state='SUCCEEDED' THEN 1 ELSE 0 END)/count(*), 1) AS success_pct",
    "FROM runs r JOIN jn ON r.job_id=jn.job_id AND jn.rn=1",
    "WHERE jn.name LIKE '%princeton_poc%' AND result_state IS NOT NULL",
    "  AND run_start >= date_sub(current_date(), 30)",
]

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


def counter(name, dataset, field, title, x):
    return {
        "widget": {
            "name": name,
            "queries": [{"name": "main_query", "query": {
                "datasetName": dataset,
                "fields": [{"name": field, "expression": f"`{field}`"}],
                "disaggregated": True}}],
            "spec": {"version": 2, "widgetType": "counter",
                     "encodings": {"value": {"fieldName": field, "displayName": title}},
                     "frame": {"title": title, "showTitle": True}},
        },
        "position": {"x": x, "y": 2, "width": 2, "height": 3},
    }


def text(name, line, y):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": [line]}},
            "position": {"x": 0, "y": y, "width": 6, "height": 1}}


dashboard = {
    "datasets": [
        {"name": "kpi", "displayName": "KPI summary (30d)", "queryLines": [l + "\n" for l in KPI]},
        {"name": "runs", "displayName": "Job run history (30d)", "queryLines": [l + "\n" for l in RUNS]},
        {"name": "tasks", "displayName": "Task run detail (30d)", "queryLines": [l + "\n" for l in TASKS]},
    ],
    "pages": [{
        "name": "monitoring",
        "displayName": "Job Monitoring",
        "pageType": "PAGE_TYPE_CANVAS",
        "layout": [
            text("title", "## Princeton POC — Job Monitoring (SE-34)", 0),
            text("subtitle",
                 "Run history, success rate, durations & retries — sourced live from "
                 "`system.lakeflow` (no custom ingestion). Scoped to `%princeton_poc%` jobs, last 30 days.",
                 1),
            counter("kpi-total", "kpi", "total_runs", "Total runs (30d)", 0),
            counter("kpi-succeeded", "kpi", "succeeded", "Succeeded", 2),
            counter("kpi-success-pct", "kpi", "success_pct", "Success %", 4),
            # Runs over time (colored by status) — cardinality 3 (Succeeded/Failed/Other)
            {"widget": {
                "name": "runs-over-time",
                "queries": [{"name": "main_query", "query": {
                    "datasetName": "runs",
                    "fields": [
                        {"name": "daily(run_start)", "expression": "DATE_TRUNC(\"DAY\", `run_start`)"},
                        {"name": "count(run_id)", "expression": "COUNT(`run_id`)"},
                        {"name": "status", "expression": "`status`"}],
                    "disaggregated": False}}],
                "spec": {"version": 3, "widgetType": "bar",
                         "encodings": {
                             "x": {"fieldName": "daily(run_start)", "scale": {"type": "temporal"}, "displayName": "Day"},
                             "y": {"fieldName": "count(run_id)", "scale": {"type": "quantitative"}, "displayName": "Runs"},
                             "color": {"fieldName": "status", "scale": {"type": "categorical"}, "displayName": "Status"}},
                         "frame": {"title": "Runs per day by status", "showTitle": True}}},
             "position": {"x": 0, "y": 5, "width": 3, "height": 5}},
            # Avg task duration by task_key (E8 DAG) — bar
            {"widget": {
                "name": "task-durations",
                "queries": [{"name": "main_query", "query": {
                    "datasetName": "tasks",
                    "fields": [
                        {"name": "task_key", "expression": "`task_key`"},
                        {"name": "avg(duration_min)", "expression": "AVG(`duration_min`)"}],
                    "disaggregated": False}}],
                "spec": {"version": 3, "widgetType": "bar",
                         "encodings": {
                             "x": {"fieldName": "task_key", "scale": {"type": "categorical"}, "displayName": "Task"},
                             "y": {"fieldName": "avg(duration_min)", "scale": {"type": "quantitative"}, "displayName": "Avg min"}},
                         "frame": {"title": "Avg task duration (min)", "showTitle": True}}},
             "position": {"x": 3, "y": 5, "width": 3, "height": 5}},
            text("runs-header", "### Recent job runs", 10),
            # Run history table
            {"widget": {
                "name": "runs-table",
                "queries": [{"name": "main_query", "query": {
                    "datasetName": "runs",
                    "fields": [
                        {"name": "job_name", "expression": "`job_name`"},
                        {"name": "run_start", "expression": "`run_start`"},
                        {"name": "status", "expression": "`status`"},
                        {"name": "result_state", "expression": "`result_state`"},
                        {"name": "duration_min", "expression": "`duration_min`"}],
                    "disaggregated": True}}],
                "spec": {"version": 2, "widgetType": "table",
                         "encodings": {"columns": [
                             {"fieldName": "job_name", "displayName": "Job"},
                             {"fieldName": "run_start", "displayName": "Started"},
                             {"fieldName": "status", "displayName": "Status"},
                             {"fieldName": "result_state", "displayName": "Result state"},
                             {"fieldName": "duration_min", "displayName": "Duration (min)"}]},
                         "frame": {"title": "Run history (last 30 days)", "showTitle": True}}},
             "position": {"x": 0, "y": 11, "width": 6, "height": 6}},
        ],
    }],
}

out = pathlib.Path(__file__).parent / "e9_monitoring.lvdash.json"
out.write_text(json.dumps(dashboard, indent=2))
print(f"wrote {out} ({len(json.dumps(dashboard))} bytes)")
