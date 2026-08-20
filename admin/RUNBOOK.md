# Princeton POC — Platform Administrator Runbook

Scenario entries for the Platform Administrator persona (PA-01…PA-25). Security scenarios run
on the `admin_demo` schema (copies of the sensitive tables) so masking/RLS demos never mutate
the shared foundation. Index: [`docs/runbook/README.md`](../docs/runbook/README.md).

Status: [`docs/SCENARIO_TRACKER.md`](../docs/SCENARIO_TRACKER.md).

---

# PA-A — Identity & Access Management (PA-01 … PA-06)

**What this group proves:** an administrator provisions people by role, grants access to groups
rather than individuals, scopes permissions down to a single object, and can answer "who could read
this" *and* "who actually did" in SQL.

**Build status:** one build object — `admin/src/pa_a_identity_access.py`, deployed as job
`[<catalog>] PA-A — Identity & access (PA-01…06)`. Strategy and the two procedures that are policy
rather than code (onboarding, credential rotation) are in
[`PA_A_IDENTITY_STRATEGY.md`](PA_A_IDENTITY_STRATEGY.md).

**Prereq:** `admin_demo` must exist — run `pa_admin_demo_setup` first (PA Task 0).

## ⚠️ Two environment constraints that shape this scenario

Both were hit while building, and both fail in ways that look like something else:

1. **Unity Catalog will not grant to a workspace-local group.** Groups created in this workspace
   are SCIM `type=WorkspaceGroup`, and `GRANT … TO <group>` returns `PRINCIPAL_DOES_NOT_EXIST`.
   Only **account-level** groups (`type=Group`) can hold UC privileges. With no account-admin
   rights here, PA-A maps each RFP role onto an account group that already exists.
2. **Grants need MANAGE on the securable.** `princeton_poc_dev` is owned by another user, so
   catalog-scoped grants return `PERMISSION_DENIED`. PA-A therefore grants at **`admin_demo`
   scope**, which the PA admin owns — and which is where spec §3.1 requires PA security scenarios
   to operate anyway. The constraint and the design agree.

**Policy checks use `is_member()`, not `is_account_group_member()`.** The account-level function
cannot see workspace groups, so a mask written against it redacts for *everyone including the
admin* while appearing to work. `is_member()` resolves both group types.

## Role → group mapping

| RFP role | Account group used | PA admin a member? |
|---|---|---|
| admin | `dbx_demo_shared_admins` | **yes** |
| faculty | `data_engineers_demo_group` | no |
| student | `dbx_demo_shared_dev_group` | no |

**Say this mapping out loud in the demo.** The group names are inherited from the shared workspace,
not chosen. In Princeton's own tenancy these would be `princeton_admins` / `_faculty` / `_students`,
provisioned by SCIM from their IdP — the pattern is identical, only the names and the group-check
function change.

The membership column is what makes PA-B's masking demo real: the admin sees unmasked `ssn`, the
other two roles demonstrably do not. Nothing is staged.

## PA-01 / PA-02 / PA-04 — provisioning, group-based access, object-level permissions

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the grants notebook)

<details>
<summary><strong>Assistant prompt (generate the identity & access notebook)</strong> — click to expand</summary>

```text
Write a PySpark notebook that sets up role-based access control in Unity Catalog and proves it works.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix value ALREADY includes its leading underscore, so concatenate with no separator —
f"{catalog}.silver{suffix}", never f"silver_{suffix}". The bundle passes _dev / _test / "" (empty,
for prod), so an underscore in the f-string breaks qa and prod while passing on dev.

Two hard constraints — get these wrong and it fails at runtime in ways that look like other things:

1. Unity Catalog will NOT grant to a workspace-local group. Groups created in a workspace are SCIM
   type=WorkspaceGroup and GRANT returns PRINCIPAL_DOES_NOT_EXIST. Only ACCOUNT-level groups
   (type=Group) can hold UC privileges. So do NOT create groups — discover the existing
   account-level ones with the SDK (w.groups.list(), keep those where meta.resource_type == "Group")
   and map the three RFP roles onto them.
2. GRANT needs MANAGE on the securable. Grant at <catalog>.admin_demo scope, NOT catalog scope —
   the admin owns admin_demo but not the catalog, and catalog-scoped grants return
   PERMISSION_DENIED.

Steps:
1. Map three roles — admin, faculty, student — onto account-level groups. For each, print whether
   it is UC-grantable and whether is_member('<group>') is true for the caller. Use is_member(), NOT
   is_account_group_member(): the account-level function cannot see workspace groups and would make
   every downstream mask redact for everyone including the admin.
2. Grant on <catalog>.admin_demo: ALL PRIVILEGES to admin; USE SCHEMA + SELECT to faculty; and for
   student, USE SCHEMA on the schema plus SELECT on ONLY the admin_demo.student table — no
   schema-wide SELECT. That narrower grant IS the object-level-permissions scenario.
3. Read the effective grants back from information_schema. Note the column names differ:
   schema_privileges uses schema_name, table_privileges uses table_schema. Mixing them gives
   UNRESOLVED_COLUMN.
4. Assert: every role maps to a UC-grantable group; is_member() is true for the admin role (else the
   masking demo has no authorised reader); is_member() is FALSE for at least one other role (else
   there is no contrast to demonstrate); each role holds a privilege on admin_demo; and the student
   role does NOT hold schema-wide SELECT.
```

</details>

### PA-01 — provisioning

**How to test:** run the job, or the notebook interactively. It reports, per role, whether the group
is UC-grantable and whether `is_member()` resolves for the caller.

Provisioning a person is then a **membership change only** — no grants are edited:
**Settings → Identity and access → Groups** → add the user. Verify as them:
`SELECT is_member('data_engineers_demo_group')` → `true`.

**⚠️ Membership is cached.** After a group change, `is_member()` kept returning the old answer for
30+ seconds. Make membership changes a few minutes before you need them on screen — do not remove
someone from a group live and expect the next query to redact.

## PA-02 — Group-based access control

> **Built:** ✅ · **Prompt:** — n/a

**What it proves:** every grant targets a group. Onboarding is a membership change; offboarding
revokes everything at once, because nothing was ever granted to an individual.

**Expected outcome:** `admin_demo` shows `ALL PRIVILEGES` for the admin group, `USE_SCHEMA` +
`SELECT` for faculty, and `USE_SCHEMA` only for the student group.

## PA-03 — Environment-level access segregation

> **Built:** 🟡 model demonstrated, not applied · **Prompt:** — n/a

Environments are separate **catalogs** — `princeton_poc_dev`, `_test`, `_qa`, `princeton_poc` — in
one workspace. `USE CATALOG` gates everything beneath it, so withholding it is absolute: there is
no schema-level way around a missing catalog grant.

**Why 🟡:** applying catalog-scoped grants needs MANAGE on the catalog, which the PA admin does not
hold here. The notebook demonstrates the model by reading the live catalog grant state; applying it
per environment is a one-line `GRANT` for the catalog owner.

## PA-04 — Object-level permissions

> **Built:** ✅ · **Prompt:** — n/a

**The demonstration is the student role.** It gets `USE_SCHEMA` on `admin_demo` but **no
schema-wide `SELECT`** — just `SELECT` on `admin_demo.student`. No grant on `faculty` or
`financial_aid` means no access to them at all. An assertion fails if schema-wide SELECT ever leaks
in, because that would silently widen access and still look like a pass.

**Expected outcome:** `information_schema.table_privileges` shows the student group with exactly one
table grant.

> Column name gotcha: `schema_privileges` uses **`schema_name`**; `table_privileges` uses
> **`table_schema`**. Mixing them up gives `UNRESOLVED_COLUMN`.

## PA-05 — Permission audit trail

> **Built:** ✅ · **Prompt:** 🟢 tested (`princeton_poc_dev`: Genie space over the audit + lineage tables — both NL prompts generated correct SQL against real data)

### No-code path — audit access in natural language

Genie space **`[<catalog>] Access Audit (PA-05)`**, grounded on `system.access.audit` and
`system.access.table_lineage`, created by the `genie_setup` task of `foundation_build`.

| Prompt | Verified result |
|---|---|
| `Who changed permissions in the last 7 days, and on what object?` | correct SQL — `service_name='unityCatalog'`, `action_name='updatePermissions'`, actor + securable, `event_date` filtered |
| `Who has read the student, faculty or financial_aid tables recently?` | queried `table_lineage`, returned 7 reader/table pairs |
| `Which principals were granted access this week, and by whom?` | — |
| `Show all access denials in the last 7 days` | — |

Both tested prompts produced an **`event_date` partition filter**, which the space's instructions
require — the two tables hold tens of millions of rows a week (21,214 permission changes in the last
day alone here), so an unfiltered query looks broken.

> **Why a PA-specific space rather than reusing DS-08's.** The DS-08 space is grounded on the same
> `system.access.audit` table but instructed toward *notebook* activity. Asked the PA question it
> generated correct SQL and answered *"no permission changes in the last 7 days"* — because it
> filtered `service_name='notebook'`. The data was there: 21,214 rows. Same table, wrong lens.
> Grounding instructions matter as much as table selection, and a plausible wrong answer is worse
> than an error.

Two questions, two tables:

- **Who changed a permission?** `system.access.audit`, `action_name = 'updatePermissions'` — actor,
  securable, and the change itself.
- **Who actually read the sensitive tables?** `system.access.table_lineage`. A grants list says who
  *could*; lineage says who *did*. That distinction is usually the one an auditor cares about.

**⚠️ Always filter on `event_date`** — it is the partition column on both, and they hold tens of
millions of rows per week (53M over 7 days in this workspace). An unfiltered query is slow enough to
look broken.

## PA-06 — Service principals & credential rotation

> **Built:** ✅ · **Prompt:** — n/a

The POC already ships a working example: `engineer/src/apps/grant_app_sp.sh` grants the mock REST
API app's service principal `SELECT` on one table — least privilege for a workload identity, no
human credential involved.

**The rotation argument in one line:** grants attach to the **principal**, not the credential. So
rotating an SP secret is invisible to permissions — exactly what an embedded personal token cannot
offer. Full 5-step procedure, plus the audit query to confirm it, in
[`PA_A_IDENTITY_STRATEGY.md`](PA_A_IDENTITY_STRATEGY.md).

**Expected outcome:** the notebook lists the workspace's service principals and any UC grants held
by a UUID grantee (SP application IDs are UUIDs, so they stand out from user and group grantees).


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

---

---

# PA-F — Cost Tracking & Chargeback (PA-19 … PA-25)

**What this group proves:** the platform gives an administrator financial accountability — total
spend, attribution by user/team/pipeline, forecasting, budget alerts, pre-run estimation, and
optimization guidance — all from native cost surfaces (`system.billing.*`, `system.compute.*`).

**Build status:** PA-19/20/21/23 are covered by the stock **Workspace Usage Dashboard V2**
(AI/BI, ships with UC-enabled workspaces). PA-22 is an admin-console **budget** walkthrough.
PA-25 is a built **Genie space** (cost-optimization assistant). PA-24 is an honest **partial**
(native pre-run estimation is limited — EXPLAIN COST + post-run actuals).

> **Attribution depends on tagging.** PA-20/21 slice cost by `custom_tags` / `usage_metadata`.
> The dashboard is fully capable, but the *quality* of user/dept/pipeline attribution depends on
> Princeton applying tags to clusters, warehouses, and jobs. State this plainly — it's a customer
> process input, not a platform gap.

---

## PA-19 / PA-20 / PA-21 / PA-23 — Spend, attribution, forecasting (Usage Dashboard)

**RFP asks:** PA-19 overall spend by cost driver (compute/storage/transfer) over time, exportable ·
PA-20 cost by user/department · PA-21 cost by pipeline/workload · PA-23 spend forecasting (≥30-day horizon).

**Platform capability:** the stock **Workspace Usage Dashboard V2** (AI/BI, over
`system.billing.usage` + `system.billing.list_prices`) covers all four:
- **PA-19** — Usage Overview page: spend over time by product/SKU; compute vs storage vs egress are
  distinct SKUs; export via the dashboard ⋯ menu (CSV/PDF).
- **PA-20** — Tag Matching page: explodes `custom_tags` to attribute cost by department/cost-center.
- **PA-21** — group by `usage_metadata` keys (job/pipeline id) or a `project`/`pipeline` tag.
- **PA-23** — Forecast: uses `AI_FORECAST()` with a configurable horizon (≥30 days) + 90% confidence band.

**Steps to test:**
1. Open **Workspace Usage Dashboard V2** (Dashboards → search "Usage").
2. PA-19: on Usage Overview, show total spend over time and the product/SKU breakdown; export.
3. PA-20: Tag Matching page → pick a tag key (e.g. `department`) → show cost per value.
4. PA-21: group by a pipeline/job tag or `usage_metadata` key.
5. PA-23: show the forecast line + confidence band projecting ≥30 days out.

**Expected outcome:** spend trend + cost-driver breakdown (PA-19), per-tag attribution (PA-20/21),
and a 30-day+ forecast (PA-23) — all from native billing system tables.

**Notes:** PA-20/21 attribution is only as complete as the tags applied to compute/jobs. Verify
compute/storage/transfer appear as separate SKUs when demoing PA-19.

---

## PA-22 — Budget alerts & spending limits

**RFP asks:** *"configure a budget threshold so an alert fires when projected or actual spend
approaches or exceeds a defined limit. Alert fires before the limit is breached; notification
includes current spend, projected spend, and threshold value."*

**Platform capability:** native **Budgets** in the account/usage console — set a spend threshold
with a period + optional filters (workspace, tag, SKU) and email recipients; Databricks alerts on
actual/forecasted spend against the budget.

**Steps to test (walkthrough):**
1. Account console → **Usage → Budgets → Create budget**.
2. Set a period (e.g. monthly), an amount, optional filters (workspace/tag), and alert email(s).
3. Save — show the budget tracking actual vs. threshold; alerts fire as spend approaches the limit.

**Expected outcome:** a budget with an alert threshold; notification includes current + projected
spend vs. the limit. No build — admin-console configuration.

---

## PA-24 — Query & job cost estimation (PARTIAL)

**RFP asks:** *"before executing a large query or pipeline run, show whether the platform can
provide an estimated cost or resource consumption preview. Estimate reasonably aligned with actual
post-run cost."*

**Honest coverage — PARTIAL.** Databricks is primarily a *post-run actuals* platform; there is no
native per-query "this will cost $X" preview. The demonstrable answer:
- **`EXPLAIN COST <query>`** — returns the optimizer's plan **with cost/statistics estimates**
  (estimated row counts + sizes per plan node) *before* execution — the native pre-run resource-shape signal.
- **Query Profile** (post-run) — actual time/rows/memory, which align with the EXPLAIN COST plan.
- **`system.billing.usage`** (post-run) — actual $ cost, closing the estimate-vs-actual loop.

**Steps to test:**
1. Run `EXPLAIN COST <a heavy query>` in the SQL editor → show the estimated statistics per plan node.
2. Execute the query → open **Query Profile** → show actual rows/time/memory align with the estimate.
3. Look the query up in `system.query.history` / `system.billing.usage` → show actual cost.

**Expected outcome:** EXPLAIN COST gives a pre-run resource/statistics estimate; Query Profile +
billing confirm actuals align. Frame PA-24 as **Partial** in the vendor response.

**Note:** for *forward workload* cost planning (size a hypothetical pipeline before writing SQL),
**Lakemeter OSS** (`github.com/databrickslabs/lakemeter-oss`, a Databricks Labs app) provides
pre-run workload estimates with SKU breakdowns. Mentioned as an option; not deployed in this POC.

---

## PA-25 — Cost optimization recommendations (Genie space)  ⭐ BUILD ITEM

**RFP asks:** *"show whether the platform provides automated recommendations for reducing spend —
identifying unused resources, oversized compute, or redundant storage. At least one actionable
recommendation surfaced with an estimated savings value."*

**Build:** a **Genie space** — *[princeton_poc] PA-25 Cost Optimization Assistant*
(`admin/src/pa_f_cost_genie.json`) — grounded on `system.billing.usage`, `system.billing.list_prices`,
and `system.compute.warehouse_events`. Admins ask cost questions in natural language; Genie
generates the SQL, returns spend/attribution, and flags idle/oversized warehouses with savings.
Verified on princeton_poc: "total spend by product last 30 days" → SQL $8.18, JOBS $1.04, DLT
$0.25, APPS $0.10, PredictiveOpt $0.07 (correct USD via the list_prices join).

**Steps to test / demo:**
1. Open the Genie space **[princeton_poc] PA-25 Cost Optimization Assistant**.
2. Ask a starter question: *"What is our total spend in the last 30 days broken down by product?"*
3. Ask an optimization question: *"Which warehouses look idle or underutilized, and what could we save?"* — Genie queries `system.compute.warehouse_events` and surfaces oversized/idle warehouses.
4. Ask an attribution question: *"Break spend down by custom tag."*

**Expected outcome:** Genie answers each in natural language with correct SQL over the billing/compute
system tables, and surfaces at least one actionable optimization with an estimated $ figure.

**Notes:** (1) Also mention **Predictive Optimization** (GA) — automated OPTIMIZE/VACUUM on UC
managed tables — for the RFP's "redundant storage" angle. (2) Honest framing: the Genie space makes
cost analysis *conversational*, but the recommendations are analyst-initiated (AI-mediated query),
not a fully-automated recommendation engine — note as such in the vendor response.
