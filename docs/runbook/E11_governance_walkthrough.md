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

## SE-41 — Schema-drift detection (Auto Loader, source-driven)

Auto Loader **detects structural changes in source files** (new/renamed/retyped columns) when they
land, and either evolves the schema, routes unexpected data to `_rescued_data`, or halts the
pipeline — all configurable via `cloudFiles.schemaEvolutionMode`.

**Context:** E1's Auto Loader pipeline (`e1_students_raw` stream) monitors
`/Volumes/princeton_poc_dev/landing_dev/files/students_csv/` for incoming student CSV files with
the schema: `student_id, first_name, last_name, ssn, dob, dept_id, status, email`.

**Isolation-safe live demo** (your per-person schema, no foundation mutation):

### Step 1: Set up your pipeline baseline
Deploy + run **E1** in your `wksp_<you>` schema if not already done. This ingests students.csv
into your `e1_students_raw` streaming table. Verify it succeeded:
```sql
SELECT COUNT(*) FROM princeton_poc_dev.wksp_<you>.e1_students_raw;
-- Expected: 2000
```

### Step 2: Drop the drifted students file (extra column)
A ready-made drift file lives at **`engineer/src/e11/drifted_students.csv`** — the real 8 columns
plus an unexpected `citizenship` column. Upload it into the landing directory the E1 stream watches:
```bash
databricks fs cp engineer/src/e11/drifted_students.csv \
  "dbfs:/Volumes/princeton_poc_dev/landing_dev/files/students_csv/" --profile princeton_poc
```
(Its `student_id`s start at 900001 so it never collides with the real data; delete it from the
landing dir after the demo to reset.)

### Step 3: Trigger the pipeline and observe the outcome (depends on schemaEvolutionMode)

Re-run the E1 pipeline in your schema. The outcome depends on the configured `cloudFiles.schemaEvolutionMode`:

**Outcome 1 — `addNewColumns` (current E1 default):**
- Auto Loader detects the new `citizenship` column and adds it to the schema.
- The pipeline **fails with an exception** (stream halts with "UnknownFieldException").
- **Why?** The exception forces you to acknowledge the schema change; restart the pipeline to proceed
  with the widened schema.
- **Surfacing:** The error appears in the pipeline's **Execution Details** (UI) with the column name.
- This is the **safe-by-default** mode — drift is detected and surfaced before silent data corruption.

**Outcome 2 — `rescue` (route to `_rescued_data`):**
Edit your pipeline's `e1_file_ingestion_sdp.py` to add `.option("cloudFiles.schemaEvolutionMode", "rescue")`
to the `e1_students_raw` definition:
```python
return (spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        # ... header, quote, escape ...
        .option("cloudFiles.schemaEvolutionMode", "rescue")  # ADD THIS
        .load(f"{LANDING}/students_csv"))
```
- Re-run the pipeline with `rescue` mode.
- The stream **does not fail**. Rows with the extra column are captured in the schema's built-in
  `_rescued_data` column (a JSON string of unexpected fields).
- **Surfacing:** Query the `_rescued_data` column to see which rows had unexpected data and what was rescued.
- This mode is used when you want **resilience over strictness** (e.g., third-party feeds evolving independently).

**Outcome 3 — `failOnNewColumns` (halt and require manual resolution):**
Edit your pipeline to use `"failOnNewColumns"`:
```python
.option("cloudFiles.schemaEvolutionMode", "failOnNewColumns")
```
- Re-run the pipeline with this mode.
- The stream **fails immediately** and does not restart without manual intervention.
- The schema is NOT automatically updated. You must either:
  - Remove the drifted file from the landing directory, or
  - Update the provided schema definition (the SDP's table definition) to include the new column.
- **Surfacing:** The pipeline halts with a clear error message naming the unexpected column(s).
- This mode is used when you want **strict schema contracts** (e.g., production pipelines with formal data agreements).

### Step 4: Verify the detection + surface
Whichever mode you test, the **platform detects the drift**:
- The pipeline error or `_rescued_data` JSON surface what columns changed.
- Catalog Explorer → `e1_students_raw` → **History** tab shows the moment the schema changed (if evolved).
- The data engineer is notified immediately — no silent corruption.

> **Why this demo uses E1's Auto Loader, not SQL mutations:** the RFP asks for "detection of
> structural changes to a source" — that's file-level drift, not schema changes the operator makes
> themselves. Auto Loader detects file changes automatically as data lands. This is source-driven drift
> detection, which is the production reality for ingestion pipelines.

## SE-42 — Data-drift detection (Lakehouse Monitoring)

Lakehouse Monitoring profiles a table's data distribution over time and flags anomalies (changes in
mean / stddev / null rate / distinct counts / category proportions). **Drift is temporal within one
monitor** — it is computed between *successive refreshes* of the same monitored table — so to show
drift you apply a change **between** two refreshes, not by comparing two separate monitors.

Each monitor writes **its own** output tables — a profile-metrics table and a drift-metrics table —
as Delta tables in the **output schema you choose when you create the monitor**. There is **no**
global `system.lakehouse_monitoring` schema; find the exact output-table names on the monitor's own
page (Catalog Explorer → the table → Quality tab → the monitor links to them).

**Isolation-safe demo** (mutate a copy you own, never the shared fact):

```sql
-- 1. Make a copy you can mutate, in your own schema
CREATE TABLE princeton_poc_dev.wksp_<you>.enrollment_drift_demo AS
SELECT * FROM princeton_poc_dev.gold_dev.enrollment_history;
```

**2. Create a monitor on that copy (UI):** Catalog Explorer →
`princeton_poc_dev.wksp_<you>.enrollment_drift_demo` → **Quality** / **Monitoring** →
**Create monitor**:
- **Profile type:** Snapshot.
- **Measure columns:** `gpa_points` (DOUBLE) and `grade` (STRING).
- Pick an **output schema** (your `wksp_<you>` is fine).
- Click **Refresh metrics** — this is the **baseline** window.

**3. Introduce drift, then refresh again:**
```sql
-- shift the grade distribution: originally ~10 grades, now 100% 'A'
UPDATE princeton_poc_dev.wksp_<you>.enrollment_drift_demo
SET grade = 'A' WHERE grade IS NOT NULL;
```
Back on the monitor → **Refresh metrics** a **second** time. Now there are two windows to compare.

**4. See the drift flagged:** open the monitor's **Quality dashboard**, or query its **drift-metrics
output table** (the name is shown on the monitor page — typically the monitored table name plus a
`_drift_metrics` suffix, in the output schema you chose). The row for `grade` between the two windows
shows the distribution shift — a categorical drift metric (e.g. a large chi-squared / JS-distance)
identifying `grade` as the column that moved.

**Verified capability:** the baseline refresh establishes the expected distribution; the post-skew
refresh is flagged as drift, naming the column (`grade`) and the metric that moved — which is exactly
SE-42's "anomaly flagged with the metric that triggered it," with the two windows as the historical
trend.

> **Two things confirmed on this workspace:** there is no pre-provisioned `system.lakehouse_monitoring`
> schema (a monitor's metrics live in the output schema you pick), and drift needs the change applied
> **between two refreshes of one monitor** — a single snapshot, or two separate monitors, will not
> populate drift metrics.

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

| Scenario | Evidence | Automatic/On-Demand |
|----------|----------|-----------|
| SE-40 lineage | `system.access.table_lineage` + Lineage tab — full medallion + wksp chains | ✅ automatic (no setup) |
| SE-41 schema drift | Auto Loader detects source column adds/changes: evolve schema, rescue unexpected columns, or fail-with-message per `schemaEvolutionMode` | ✅ automatic (as files land) |
| SE-42 data drift | Lakehouse Monitor baseline profile → drifted copy → drift metrics flag anomaly (metric name + direction); `system.lakehouse_monitoring` tables queryable | on-demand (create + refresh monitor) |
| SE-43 discovery + AI docs | Catalog Explorer search + **AI suggest** comments / `COMMENT ON` | on-demand (AI action) |

**Expected outcome:** All four governance capabilities are native platform features. Lineage is
automatic; schema drift is detected as files land (Auto Loader); data drift requires creating a
monitor and comparing snapshots; discovery + AI docs are one-click actions. No custom code was
built — this is the standard Databricks governance surface.
