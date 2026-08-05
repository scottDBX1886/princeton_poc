# E9 — Monitoring & Operations Walkthrough (SE-34)

Companion to the pre-built **Workload Monitoring dashboard** (`engineer/resources/e9_monitoring.dashboard.yml`).
SE-34 asks the platform to monitor runs, view logs, and set alerts. This shows all the
surfaces: the **AI/BI dashboard** (fleet view across all workload types), the **Jobs/Pipelines UI**
(per-run drill-down), and **system tables** (SQL access to the same telemetry) — plus how to
wire failure alerts.

The key point for the customer: **all of this is native, across every workload type.** Databricks
captures telemetry automatically — jobs and pipelines into `system.lakeflow.*`, and notebook/query
activity into `system.query.history` — so there is no monitoring pipeline to build.

**Three workload types, three system-table sources:**

| Workload | System table | POC scope |
|----------|--------------|-----------|
| **Jobs** | `system.lakeflow.job_run_timeline` (+ `job_task_run_timeline`, `jobs`) | job name `LIKE '%princeton_poc%'` |
| **Pipelines** | `system.lakeflow.pipeline_update_timeline` (+ `pipelines`) | pipeline name `LIKE '%princeton_poc%'` (E1/E4/E5/E6 SDP) |
| **Notebook runs** | `system.query.history` (`query_source.notebook_id` set) | POC SQL warehouse id (notebook statements aren't catalog-tagged) |

---

## 1. The pre-built dashboard (fleet view — all workload types)

Deployed by the bundle. Open it from the summary URL:
```bash
databricks bundle summary -t dev --profile dbx_shared_demo | grep -A2 e9_monitoring
```
It shows, over the last 30 days: total runs / failed / success-% across **jobs, pipelines, and
notebooks combined**; a "runs by workload type & status" bar chart; average duration per job-task
(the E8 DAG tasks show up here); and a unified run-history table tagging each row with its
`workload_type`. It reads the system tables live, so it reflects every run the group makes during
the session — a job kicked off, an SDP pipeline refreshed, or a notebook query fired.

## 2. Jobs UI — per-run drill-down

1. Workspace → **Jobs & Pipelines** → open **`[princeton_poc_dev] Orchestration Demo (E8)`**.
2. **Tasks** tab → the visual DAG (`stage → leg_a/leg_b → merge → external_call → retry_demo → notify`).
3. **Runs** tab → click a run to see start/end, duration, and per-task status.
4. Click the **`retry_demo`** task on the latest run → you'll see **two attempts**: attempt 1
   FAILED, attempt 2 SUCCEEDED. Expand **Logs** to see the simulated-transient-failure message
   on attempt 1 and the success on the retry. *(This is the SE-30 retry made visible.)*

For **pipelines**, open a `%princeton_poc%` SDP pipeline (e.g. `[princeton_poc_dev] E6 CDC + SCD (SDP)`)
→ its **Updates** history shows each refresh with state and duration; click an update for the
per-dataset graph and event log. For **notebook runs**, open a notebook → the SQL cells' history
is in the cell output and in the SQL warehouse **Query History** (also queryable below).

## 3. System tables — SQL access to the same telemetry

The dashboard's queries are reusable in any SQL editor / Genie. All verified against live data.
The dashboard's main dataset UNIONs the three sources below into one normalized run history;
here they are split out per workload type so you can run each independently.

**Run history (last 30 days, POC jobs):**
```sql
WITH jn AS (
  SELECT job_id, name, ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY change_time DESC) rn
  FROM system.lakeflow.jobs WHERE delete_time IS NULL),
runs AS (
  SELECT job_id, run_id, MIN(period_start_time) run_start, MAX(period_end_time) run_end,
         MAX(CASE WHEN result_state IS NOT NULL THEN result_state END) result_state
  FROM system.lakeflow.job_run_timeline GROUP BY job_id, run_id)
SELECT jn.name AS job_name, r.run_id, r.run_start, r.result_state,
       round((unix_timestamp(r.run_end)-unix_timestamp(r.run_start))/60.0, 2) AS duration_min
FROM runs r JOIN jn ON r.job_id=jn.job_id AND jn.rn=1
WHERE jn.name LIKE '%princeton_poc%' AND r.result_state IS NOT NULL
ORDER BY r.run_start DESC;
```

**Per-task detail (durations + which tasks failed):**
```sql
WITH jn AS (
  SELECT job_id, name, ROW_NUMBER() OVER (PARTITION BY job_id ORDER BY change_time DESC) rn
  FROM system.lakeflow.jobs WHERE delete_time IS NULL),
tasks AS (
  SELECT job_id, job_run_id, task_key, MIN(period_start_time) task_start,
         MAX(period_end_time) task_end,
         MAX(CASE WHEN result_state IS NOT NULL THEN result_state END) result_state
  FROM system.lakeflow.job_task_run_timeline GROUP BY job_id, job_run_id, task_key)
SELECT jn.name AS job_name, t.task_key, t.result_state,
       round((unix_timestamp(t.task_end)-unix_timestamp(t.task_start))/60.0, 2) AS duration_min
FROM tasks t JOIN jn ON t.job_id=jn.job_id AND jn.rn=1
WHERE jn.name LIKE '%Orchestration Demo%'
ORDER BY t.task_start DESC;
```

**Pipeline updates (the E1/E4/E5/E6 SDP pipelines):**
```sql
WITH pn AS (
  SELECT pipeline_id, name, ROW_NUMBER() OVER (PARTITION BY pipeline_id ORDER BY change_time DESC) rn
  FROM system.lakeflow.pipelines WHERE delete_time IS NULL)
SELECT pn.name AS pipeline_name, u.update_id,
       MIN(u.period_start_time) AS update_start,
       MAX(CASE WHEN u.result_state IS NOT NULL THEN u.result_state END) AS result_state,
       round((unix_timestamp(MAX(u.period_end_time))-unix_timestamp(MIN(u.period_start_time)))/60.0, 2) AS duration_min
FROM system.lakeflow.pipeline_update_timeline u JOIN pn ON u.pipeline_id=pn.pipeline_id AND pn.rn=1
WHERE pn.name LIKE '%princeton_poc%'
GROUP BY pn.name, u.update_id
HAVING result_state IS NOT NULL
ORDER BY update_start DESC;
```

**Notebook runs (scoped to the POC SQL warehouse):**
```sql
-- Substitute your POC warehouse id (the one in databricks.yml var.warehouse_id).
SELECT statement_id, executed_by, execution_status, start_time,
       round((unix_timestamp(end_time)-unix_timestamp(start_time))/60.0, 2) AS duration_min,
       substr(regexp_replace(statement_text, '\s+', ' '), 1, 60) AS statement_preview
FROM system.query.history
WHERE query_source.notebook_id IS NOT NULL
  AND compute.warehouse_id = 'a94a22f8652d85c1'
  AND start_time >= date_sub(current_date(), 30)
ORDER BY start_time DESC
LIMIT 100;
```

> **Gotchas worth explaining to the customer** (they're real platform behavior, not quirks):
> - `system.lakeflow.job_run_timeline` and `pipeline_update_timeline` are **timeline** tables —
>   one row per state-period, with `result_state` set only on the terminal row. Hence
>   `GROUP BY run_id`/`update_id` + `MAX(CASE WHEN result_state IS NOT NULL …)`.
> - `system.lakeflow.jobs` and `pipelines` are **SCD** (`change_time`/`delete_time`), so a
>   renamed object has multiple rows — `ROW_NUMBER() … ORDER BY change_time DESC` picks the current name.
> - On serverless, the `*_duration_seconds` columns can read 0; compute duration from the
>   period timestamps instead (as above).
> - **Notebook statements aren't tagged with a catalog**, so they can't be scoped by
>   `%princeton_poc%` like jobs/pipelines — scope them by the POC **SQL warehouse id** instead
>   (`compute.warehouse_id`). Notebook Spark work that doesn't hit a SQL warehouse isn't in
>   `query.history`; only warehouse-routed SQL is (which is what the dashboard shows).

## 4. Alerts (failure notification)

Two native mechanisms, both already demonstrated or one-click:
- **Job-level notifications (built in E8):** `e8_orchestration.job.yml` has an
  `email_notifications` block firing `on_failure` / `on_success`. Extend recipients, or add a
  `webhook_notifications` block for Slack/Teams (a UC-secret-backed webhook is stubbed in
  `engineer/src/e8/e8_notify.py`).
- **SQL alert on the system tables:** create a Databricks SQL **Alert** on the run-history
  query above with a condition like `count of failed runs in last 1h > 0` → notify a
  destination. This alerts across *all* jobs, not just one.

---

## SE-34 coverage

| Requirement | Surface shown |
|-------------|---------------|
| View runs & history (jobs, pipelines, notebooks) | Dashboard unified run-history table · Jobs & Pipelines UI Runs/Updates tabs |
| Inspect task/update logs | Jobs UI task drill-down (incl. the retry_demo two-attempt view) · pipeline update event log |
| Metrics (durations, success rate) across workload types | Dashboard KPIs + "runs by workload type" chart · system-table SQL |
| Set alerts | E8 job-level email/webhook · SQL Alert on system tables |

**Expected outcome:** the dashboard is deployed and ACTIVE, populated from live system-table
data across **jobs, pipelines, and notebook runs** (it already shows the E8 job run with its
retry, the E1/E4/E5/E6 pipeline updates, and POC-warehouse notebook statements). No custom
monitoring build was required.
