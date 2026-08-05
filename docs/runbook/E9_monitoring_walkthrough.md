# E9 — Monitoring & Operations Walkthrough (SE-34)

Companion to the pre-built **Job Monitoring dashboard** (`engineer/resources/e9_monitoring.dashboard.yml`).
SE-34 asks the platform to monitor job runs, view logs, and set alerts. This shows all three
surfaces: the **Jobs UI** (per-run drill-down), the **AI/BI dashboard** (fleet view), and
**system tables** (SQL access to the same telemetry) — plus how to wire failure alerts.

The key point for the customer: **all of this is native.** Databricks captures job/task run
telemetry into `system.lakeflow.*` automatically — there is no monitoring pipeline to build.

---

## 1. The pre-built dashboard (fleet view)

Deployed by the bundle. Open it from the summary URL:
```bash
databricks bundle summary -t dev --profile dbx_shared_demo | grep -A2 e9_monitoring
```
It shows, for all `%princeton_poc%` jobs over the last 30 days: total runs / succeeded /
success-%, runs-per-day colored by status, average duration per task (the E8 DAG tasks show
up here), and a run-history table. It reads `system.lakeflow` live, so it reflects every run
the group makes during the session.

## 2. Jobs UI — per-run drill-down

1. Workspace → **Jobs & Pipelines** → open **`[princeton_poc_dev] Orchestration Demo (E8)`**.
2. **Tasks** tab → the visual DAG (`stage → leg_a/leg_b → merge → external_call → retry_demo → notify`).
3. **Runs** tab → click a run to see start/end, duration, and per-task status.
4. Click the **`retry_demo`** task on the latest run → you'll see **two attempts**: attempt 1
   FAILED, attempt 2 SUCCEEDED. Expand **Logs** to see the simulated-transient-failure message
   on attempt 1 and the success on the retry. *(This is the SE-30 retry made visible.)*

## 3. System tables — SQL access to the same telemetry

The dashboard's queries are reusable in any SQL editor / Genie. The three that back the
dashboard (all verified):

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

> **Gotchas worth explaining to the customer** (they're real platform behavior, not quirks):
> - `system.lakeflow.job_run_timeline` is a **timeline** table — one row per state-period, with
>   `result_state` set only on the terminal row. Hence `GROUP BY run_id` +
>   `MAX(CASE WHEN result_state IS NOT NULL …)`.
> - `system.lakeflow.jobs` is **SCD** (`change_time`/`delete_time`), so a renamed job has
>   multiple rows — `ROW_NUMBER() … ORDER BY change_time DESC` selects the current name.
> - On serverless, the `*_duration_seconds` columns can read 0; compute duration from the
>   period timestamps instead (as above).

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
| View job runs & history | Jobs UI Runs tab · dashboard run-history table |
| Inspect task logs | Jobs UI task drill-down (incl. the retry_demo two-attempt view) |
| Metrics (durations, success rate) | Dashboard KPIs + charts · system-table SQL |
| Set alerts | E8 job-level email/webhook · SQL Alert on system tables |

**Expected outcome:** the dashboard is deployed and ACTIVE, populated from live `system.lakeflow`
data (it already shows the E8 run with its retry). No custom monitoring build was required.
