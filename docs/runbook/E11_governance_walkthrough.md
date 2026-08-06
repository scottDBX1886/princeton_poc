# E11 — Governance Walkthrough (SE-40, SE-41, SE-42, SE-43)

Proves Databricks' native data-governance surface across the POC data: **lineage** (automatic),
**schema-drift history** (automatic, Delta), **data-drift monitoring** (Lakehouse Monitoring), and
**catalog discovery + AI-generated documentation**. Two of the four are captured by the platform
with zero setup; the other two are one-click/one-command actions shown here.

All queries below were verified against the live `princeton_poc_dev` workspace.

---

## SE-40 — Data lineage (end-to-end, automatic)

Unity Catalog captures lineage automatically as pipelines/notebooks run — no instrumentation.

**UI:** Catalog Explorer → `princeton_poc_dev` → `silver_dev` → `student` → **Lineage** tab →
see upstream (Bronze) and downstream (Gold, per-person `wksp_*`) dependencies as a graph.

**SQL (the same lineage, queryable):**
```sql
SELECT source_table_full_name, target_table_full_name
FROM system.access.table_lineage
WHERE target_table_full_name LIKE 'princeton_poc_dev.%'
  AND source_table_full_name IS NOT NULL
ORDER BY target_table_full_name;
```
**Verified output** includes real chains built by the POC, e.g.:
```
silver_dev.student           → gold_dev.enrollment_history
silver_dev.student           → admin_demo.student            (PA masking copies)
silver_dev.department        → wksp_<user>.ds_01_dept_enrollment_rank   (downstream analyst work)
```
The point: lineage spans the whole medallion flow **and** everyone's per-person derived tables,
with no extra work — it's a property of running on the platform.

## SE-41 — Schema-drift detection (automatic, Delta history)

Every schema change (add/rename/retype a column) is recorded in the table's Delta history.

**Isolation-safe live demo** (writes only to your `wksp_<you>`, never the shared foundation):
```sql
-- 1. stage a small table you own
CREATE TABLE princeton_poc_dev.wksp_<you>.e11_drift_demo AS
SELECT student_id, dept_id, status FROM princeton_poc_dev.silver_dev.student LIMIT 100;

-- 2. drift it — add a column
ALTER TABLE princeton_poc_dev.wksp_<you>.e11_drift_demo ADD COLUMN citizenship STRING;

-- 3. the change is captured, with who/when:
DESCRIBE HISTORY princeton_poc_dev.wksp_<you>.e11_drift_demo;
```
**Verified output** — the history shows `version 1 = ADD COLUMNS` above `version 0 = CREATE TABLE AS SELECT`.
Catalog Explorer → the table → **History** tab shows the same, with `userName` and `timestamp`.

> **Why the demo drifts a wksp table, not the shared `silver_dev.student`:** the foundation is
> read-only for the group (the multi-user isolation model — we replaced the in-place
> `40_day2_changes.sql` mutation with E6's snapshot approach). Each participant drifts their own
> copy, so ~20 people can run SE-41 concurrently. The mechanism (Delta history captures the ALTER)
> is identical to what you'd see on a production table.

## SE-42 — Data-drift detection (Lakehouse Monitoring)

Lakehouse Monitoring profiles a table over time and flags distribution drift / quality anomalies.
This is an on-demand feature (create a monitor), not a pre-populated system table.

**Create a monitor (UI):** Catalog Explorer → `princeton_poc_dev.gold_dev.enrollment_history`
(the 5,000,000-row fact) → **Quality**/**Monitoring** → **Create monitor**:
- **Profile type:** Snapshot.
- **Measure columns:** `gpa_points` (numeric — verified DOUBLE) and `grade` (categorical — verified STRING).
- **Schedule:** on-demand for the demo (or daily).

Click **Refresh metrics** to snapshot the current distribution (mean/stddev/null%/distinct counts).
Monitoring writes `_profile_metrics` and `_drift_metrics` tables you can query or dashboard.

**Simulate + detect drift (optional):** in your own `wksp` copy, skew some grades, point a monitor
at it, refresh, and compare profiles — the drift metrics move. On the shared fact, the baseline
snapshot alone is enough to show the capability.

> **Note:** this workspace has no `system.lakehouse_monitoring` schema pre-provisioned — monitors
> are created per-table via the UI/API, which is the intended workflow. The measure columns above
> are confirmed to exist on the fact table.

## SE-43 — Catalog discovery + AI-generated documentation

Unity Catalog is the searchable data catalog; Databricks AI can auto-generate table/column
descriptions.

**Discovery (UI):** Catalog Explorer → search `student` → see it in `silver_dev`, with schema,
sample data, lineage, and permissions in one place. The search bar spans catalogs/schemas/tables/columns.

**AI-generated comments (the headline):** open `princeton_poc_dev.silver_dev.student` → in the
**Comment**/description field click **AI suggest** → Databricks proposes a table description and
per-column comments (e.g. *"Dimension table of enrolled students; `dob` is a mixed-format birth
date string, `status` tracks enrollment standing"*). Accept to persist them.

**Seed/verify comments via SQL (so discovery shows something concrete now):**
```sql
COMMENT ON TABLE princeton_poc_dev.silver_dev.student IS
  'Student dimension — one row per student. PII: ssn, dob. dept_id = declared major.';
ALTER TABLE princeton_poc_dev.silver_dev.student ALTER COLUMN status
  COMMENT 'Enrollment standing (Active / Leave / Graduated / Withdrawn) — an SCD-tracked attribute.';

-- confirm:
SELECT column_name, comment FROM system.information_schema.columns
WHERE table_catalog='princeton_poc_dev' AND table_schema='silver_dev' AND table_name='student';
```
> POC tables ship without comments (verified — all `NULL`), so this is where you either run the
> **AI suggest** action live (the marquee SE-43 answer) or seed a few comments as above. Either way,
> `system.information_schema` and Catalog Explorer then surface them for discovery.

---

## SE-40…43 coverage

| Scenario | Evidence | Automatic? |
|----------|----------|-----------|
| SE-40 lineage | `system.access.table_lineage` + Lineage tab — full medallion + wksp chains | ✅ automatic |
| SE-41 schema drift | `DESCRIBE HISTORY` shows `ADD COLUMNS` (isolation-safe wksp demo) | ✅ automatic |
| SE-42 data drift | Lakehouse Monitoring on the 5M-row fact (`gpa_points`, `grade`) | on-demand (create monitor) |
| SE-43 discovery + AI docs | Catalog Explorer search + **AI suggest** comments / `COMMENT ON` | on-demand (AI action) |

**Expected outcome:** lineage and Delta history are already populated by the POC's own runs (no
setup); Lakehouse Monitoring and AI comments are one-click actions demonstrated live. All four
governance capabilities are native — nothing custom was built.
