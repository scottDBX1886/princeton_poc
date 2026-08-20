# Princeton POC — Platform Administrator Runbook

Scenario entries for the Platform Administrator persona (PA-01…PA-25). Security scenarios run
on the `admin_demo` schema (copies of the sensitive tables) so masking/RLS demos never mutate
the shared foundation. Index: [`docs/runbook/README.md`](../docs/runbook/README.md).

Status: [`docs/SCENARIO_TRACKER.md`](../docs/SCENARIO_TRACKER.md).

---

# PA-E — Compute & Capacity Management (PA-13 … PA-18)

**What this group proves:** an administrator can size, isolate, pause, monitor, and prioritize
compute — the operational controls a platform team needs for performance, cost, and availability.

**Build status:** only **PA-17 (capacity dashboard)** is a build object; PA-13/14/15/16/18 are
**admin walkthroughs** (UI / CLI actions, no generated artifact). This runbook gives the RFP ask
+ context for each; the SA fills in the exact click/CLI steps against the target workspace.


**Prereq for PA-17 dashboard:** some query history must exist. Running the E-persona pre-builts
(or any queries) on the workspace populates `system.query.history`, which the dashboard reads.

---

## PA-13 — Scaling compute up/down (manual)


**RFP asks:** *"an administrator manually increases compute capacity to handle a heavy workload,
then scales it back down afterward. Scale operation completes without interrupting active
workloads; new capacity reflected in monitoring; scale-down reclaims resources."*

**Demo flow: - Databricks Demo**
1.  Execute ***SQL Timed Loop Demo*** notebook.  This will execute a 60 sec loop for our testing
2.  Resize the actively running compute to increase cluster capacity while the notebook is running to show no interruption.
3.  View the total running clusters/nodes in the UI
4.  REsize the cluster to reduce the number of clusters/nodes and view the reduction real time in the UI 


**Reference Links:**
***https://docs.databricks.com/api/warehouses/v1/warehouse***
***https://docs.databricks.com/api/clusters/v2/cluster***

**Expected outcome:** warehouse resizes live; the capacity dashboard (PA-17)
reflects the new size / higher throughput; scaling back down reclaims the clusters.



---

## PA-14 — Auto-scaling configuration

**RFP asks:** *"configure the platform to automatically scale compute up when demand exceeds a
threshold and down during idle. Auto-scale triggers under load; scale-down after idle; scaling
events logged with timestamps and trigger reasons."*


**Steps to test:**
1. Open the SQL warehouse ***Serverless Starter Warehouse*** in a tab
2. Open notebook ***PA_14_AUTO_SCALE_UP_DOWN***
3. Execute the notebook
4. Monitor the SQL Warehouse to show clusters scale from 1 to 3 while notebook is running
5. Monitor the SQL Warehouse to show the clusters scale down after about 2-3 mins

**Expected outcome:** under concurrent load the cluster count rises toward max;
after the idle window it drops back toward min; the scaling is visible in the warehouse monitoring
tab.

---

## PA-15 — Compute isolation — workload separation

**RFP asks:** *"different workloads (production pipelines, ad-hoc analyst queries, data science
notebooks) assigned to separate compute pools to prevent contention. Analyst query consuming heavy
resources does not degrade production throughput; assignments visible in admin console."*

**Steps to test:**
1.  This will just be a conversation around how compute works.  

**Expected outcome:** two workloads on two warehouses run without interfering;
warehouse assignment is visible per job/query.


---

## PA-16 — Pause & resume compute resources

**RFP asks:** *"pause a compute resource during a known idle window and resume automatically or on
demand before workloads begin. Paused and resumed without data loss or reconfiguration;
pause/resume events visible in logs."*



**Steps to test:**
1.  Stop warehouse if running
2.  Execute asny query to show that the cluster/warehouse will start automatically.
3.  Highlight the idle timeout on the warehouses and talk about serverless idle time.

**Expected outcome:** warehouse stops and starts cleanly; a query after resume
runs without reconfiguration. 

---

## PA-17 — Capacity dashboard & utilization monitoring  ⭐ BUILD ITEM

**RFP asks:** *"navigate a dashboard showing current compute utilization, historical usage trends,
queue depth, and any throttling events. Displays real-time and historical metrics; admin can
identify peak usage and underutilized windows."*

**Build:** an AI/BI dashboard over **`system.query.history`** (verified table + columns on the POC
workspace). It shows query volume/latency trends, per-user workload, a performance-tier
distribution, and — importantly for the RFP's "queue depth / throttling" ask — the
**`waiting_at_capacity_duration_ms`** and **`waiting_for_compute_duration_ms`** columns, which are
the platform's native queuing/throttling signals.

**Verified dashboard SQL (runs today on princeton_poc — `system.query.history`):**
```sql
-- Daily throughput + latency + queuing by warehouse (last 7 days)
SELECT
  DATE(start_time)                                    AS query_date,
  compute.warehouse_id                                AS warehouse_id,
  COUNT(*)                                            AS query_count,
  ROUND(AVG(total_duration_ms))                       AS avg_total_ms,
  ROUND(percentile(total_duration_ms, 0.95))          AS p95_total_ms,
  ROUND(AVG(waiting_at_capacity_duration_ms))         AS avg_queue_ms,   -- throttling/queue depth
  SUM(CASE WHEN waiting_at_capacity_duration_ms > 0 THEN 1 ELSE 0 END) AS throttled_queries
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 7 DAYS
  AND compute.warehouse_id IS NOT NULL
GROUP BY DATE(start_time), compute.warehouse_id
ORDER BY query_date DESC;

-- Per-user workload (who's driving load)
SELECT executed_by AS user, COUNT(*) query_count,
       ROUND(AVG(total_duration_ms)) avg_ms, SUM(read_rows) total_rows_read
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 7 DAYS
GROUP BY executed_by ORDER BY query_count DESC;

-- Performance-tier distribution (fast / medium / slow)
SELECT CASE WHEN total_duration_ms < 1000 THEN '1 Fast (<1s)'
            WHEN total_duration_ms < 5000 THEN '2 Medium (1-5s)'
            ELSE '3 Slow (>5s)' END AS perf_tier,
       COUNT(*) AS queries
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 7 DAYS
GROUP BY 1 ORDER BY 1;
```

**Build status:** ✅ **BUILT & deployed** — `admin/src/pa_e_capacity_dashboard.json` +
`admin/resources/pa_e_capacity_dashboard.dashboard.yml` (deploys with the bundle). Verified live
on princeton_poc: dashboard **[princeton_poc] PA-17 Capacity & Utilization**, ACTIVE, all dataset
queries tested against `system.query.history` before deploy.

**Build path:** deploys as an AI/BI dashboard resource with `bundle deploy`, or regenerate via
Genie/Assistant with the prompt below.

<details>
<summary><strong>Genie / Assistant prompt (regenerate the dashboard)</strong></summary>

```text
Build an AI/BI dashboard over system.query.history for the last 30 days showing compute
utilization and capacity: total query count, average + p95 total_duration_ms; hourly query
volume as a line (peaks vs idle windows); a count of throttled queries
(where waiting_at_capacity_duration_ms > 0) as the queue-depth/throttling signal; query count and
avg duration per executed_by user in a table; and a performance-tier bar bucketing total_duration_ms
into Fast (<1s), Medium (1-5s), Slow (>5s).
```
</details>

**Steps to test / demo:**
1. Open the dashboard **[princeton_poc] PA-17 Capacity & Utilization** (Dashboards → search PA-17).
2. Read the four KPIs (total queries, avg + p95 duration, throttled count) and the hourly volume
   line — point out a peak hour vs. an idle window (utilization + historical trend).
3. Show the **Throttled Queries** KPI + per-user table's Throttled column — that's the RFP's
   "queue depth / throttling events." (To make it non-zero, run the PA-14 concurrent-load notebook
   first, then refresh — queued queries appear as throttled.)

**Expected outcome:** dashboard ACTIVE; shows query volume + latency trend, per-user load,
perf-tier split, and the queue/throttle metric; admin can spot peak vs idle windows.

**Notes:** the RFP's "queue depth / throttling events" maps to `waiting_at_capacity_duration_ms`
(time a query waited because the warehouse was at capacity) — a real native signal, no custom
instrumentation.

---

## PA-18 — Workload prioritization & queuing

**RFP asks:** *"configure priority levels for job types or user groups so high-priority workloads
aren't delayed by lower-priority activity during contention. High-priority job runs ahead of
queued lower-priority jobs in a simulated contention scenario; no code change required."*

**Platform capability:** Databricks SQL warehouses queue FIFO per warehouse; prioritization is
achieved by **warehouse separation** (a dedicated higher-capacity warehouse for priority/SLA
workloads) rather than per-query priority hints. Job-level: pin priority jobs to the reserved
warehouse via `warehouse_id`.

**[SA TO FILL] — steps to test:**
1.
2.
3.

**Expected outcome (SA to confirm):** priority workload completes ahead of lower-priority load
during contention; queuing visible via `waiting_at_capacity_duration_ms` in the PA-17 dashboard.

**Notes:** _(Honest framing — Databricks doesn't expose per-query priority in standard SQL;
prioritization is warehouse-level. SA: confirm this is acceptable to Princeton or note as a
partial/workaround in the vendor response.)_

---

_PA-A/B/C/D and PA-F entries: to be added as those objects land._
