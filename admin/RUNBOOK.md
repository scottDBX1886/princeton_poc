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

> ⚠️ **Compute-type note (read first — it shapes several scenarios).** The POC workspace today
> has a **serverless SQL warehouse** (`Serverless Starter Warehouse`, Small, 10-min auto-stop).
> Serverless behaves differently from classic/pro SQL warehouses for several PA-E scenarios:
> - **Manual cluster-size scaling (PA-13)** and **pause/resume (PA-16)** are classic/pro-warehouse
>   operations. On serverless, compute is auto-managed (spins up on demand, scales to zero when
>   idle) — so the "manual scale" and "pause" stories are demonstrated on a **classic/pro SQL
>   warehouse** (create one for the demo) OR reframed as "serverless auto-manages this for you."
> - **[SA decide]** which framing to use per scenario, and whether to stand up a classic warehouse
>   for the PA-13/16 demos. Both are legitimate; the honest answer depends on what Princeton runs.

**Prereq for PA-17 dashboard:** some query history must exist. Running the E-persona pre-builts
(or any queries) on the workspace populates `system.query.history`, which the dashboard reads.

---

## PA-13 — Scaling compute up/down (manual)

**RFP asks:** *"an administrator manually increases compute capacity to handle a heavy workload,
then scales it back down afterward. Scale operation completes without interrupting active
workloads; new capacity reflected in monitoring; scale-down reclaims resources."*

**Platform capability:** classic/pro SQL warehouse **cluster size** (XS→S→M→L→XL) and
**min/max clusters** are changed live from the SQL Warehouses UI or CLI; resize applies without
dropping running queries.

**Reference commands (classic/pro warehouse):**
```bash
databricks warehouses list --profile princeton_poc
databricks warehouses update --id <WAREHOUSE_ID> --cluster-size L --profile princeton_poc   # scale up
databricks warehouses update --id <WAREHOUSE_ID> --cluster-size S --profile princeton_poc   # scale down
databricks warehouses get --id <WAREHOUSE_ID> --profile princeton_poc                       # confirm new size
```

**[SA TO FILL] — steps to test:**
1.
2.
3.

**Expected outcome (SA to confirm):** warehouse resizes live; the capacity dashboard (PA-17)
reflects the new size / higher throughput; scaling back down reclaims the clusters.

**Notes:** _(SA — note whether you demoed on a classic warehouse or reframed for serverless.)_

---

## PA-14 — Auto-scaling configuration

**RFP asks:** *"configure the platform to automatically scale compute up when demand exceeds a
threshold and down during idle. Auto-scale triggers under load; scale-down after idle; scaling
events logged with timestamps and trigger reasons."*

**Platform capability:** a classic/pro SQL warehouse takes **min/max cluster** bounds — Databricks
adds clusters as query concurrency/queuing rises and removes them when idle (transparent, no
per-query config). Serverless does this automatically with no configuration.

**Reference command:**
```bash
databricks warehouses update --id <WAREHOUSE_ID> --min-num-clusters 2 --max-num-clusters 8 --profile princeton_poc
```

**[SA TO FILL] — steps to test:**
1.
2.
3.

**Expected outcome (SA to confirm):** under concurrent load the cluster count rises toward max;
after the idle window it drops back toward min; the scaling is visible in the warehouse monitoring
tab. _(On serverless: show that autoscaling + scale-to-zero is automatic.)_

**Notes:**

---

## PA-15 — Compute isolation — workload separation

**RFP asks:** *"different workloads (production pipelines, ad-hoc analyst queries, data science
notebooks) assigned to separate compute pools to prevent contention. Analyst query consuming heavy
resources does not degrade production throughput; assignments visible in admin console."*

**Platform capability:** separate **SQL warehouses** (and/or serverless job compute) per workload
class; jobs/dashboards/queries are pinned to a specific `warehouse_id`. A heavy analyst query on
warehouse A cannot starve a pipeline on warehouse B.

**[SA TO FILL] — steps to test:**
1.
2.
3.

**Expected outcome (SA to confirm):** two workloads on two warehouses run without interfering;
warehouse assignment is visible per job/query.

**Notes:** _(The POC already models this — foundation jobs run on serverless, the SQL warehouse
serves analytics. SA: decide whether to add a second warehouse to make isolation explicit.)_

---

## PA-16 — Pause & resume compute resources

**RFP asks:** *"pause a compute resource during a known idle window and resume automatically or on
demand before workloads begin. Paused and resumed without data loss or reconfiguration;
pause/resume events visible in logs."*

**Platform capability:** classic/pro SQL warehouses **stop/start** on command and **auto-stop**
after an idle timeout; serverless scales to zero automatically (its form of "pause").

**Reference commands (classic/pro warehouse):**
```bash
databricks warehouses stop  --id <WAREHOUSE_ID> --profile princeton_poc   # pause
databricks warehouses start --id <WAREHOUSE_ID> --profile princeton_poc   # resume
```

**[SA TO FILL] — steps to test:**
1.
2.
3.

**Expected outcome (SA to confirm):** warehouse stops and starts cleanly; a query after resume
runs without reconfiguration. _(Serverless: show the 10-min auto-stop + on-demand cold start.)_

**Notes:**

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

**Build path:** deploy as an AI/BI dashboard resource (`admin/resources/pa_e_capacity_dashboard.*`)
or generate via Genie/Assistant with the prompt below.

<details>
<summary><strong>Genie / Assistant prompt (generate the dashboard)</strong></summary>

```text
Build an AI/BI dashboard over system.query.history for the last 7 days showing compute
utilization and capacity: daily query count and average + p95 total_duration_ms by
compute.warehouse_id; average waiting_at_capacity_duration_ms and a count of throttled queries
(where waiting_at_capacity_duration_ms > 0) as the queue-depth/throttling signal; query count and
avg duration per executed_by user; and a performance-tier distribution bucketing total_duration_ms
into Fast (<1s), Medium (1-5s), Slow (>5s).
```
</details>

**[SA TO FILL] — steps to test / demo the dashboard:**
1.
2.
3.

**Expected outcome (SA to confirm):** dashboard ACTIVE; shows query volume + latency trend,
per-user load, perf-tier split, and the queue/throttle metric; admin can spot peak vs idle windows.

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
