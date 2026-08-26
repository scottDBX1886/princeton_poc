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

### Step 2: Create a drifted students file (extra column)
Drop a new CSV into the landing directory with an **extra column** (`citizenship`) that the schema
doesn't expect. The file should have the same first 8 columns + the new one:
```bash
# On your local machine, create drifted_students.csv:
"student_id","first_name","last_name","ssn","dob","dept_id","status","email","citizenship"
"5001","Alice","Chen","999-12-3456","01/15/1998","10","active","alice@example.com","US"
"5002","Bob","Kumar","999-87-6543","03/20/1999","20","active","bob@example.com","IN"
```

Then upload it to the landing directory:
```bash
databricks fs cp drifted_students.csv \
  "dbfs:/Volumes/princeton_poc_dev/landing_dev/files/students_csv/" --profile princeton_poc
```

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

Lakehouse Monitoring profiles a table's data distribution and detects anomalies (changes in
mean/stddev/null rates/distinct counts) between snapshots or over time. Drift is flagged with the
specific metric that moved.

**Create a baseline monitor (UI):** Catalog Explorer → `princeton_poc_dev.gold_dev.enrollment_history`
(the 5,000,000-row fact) → **Quality**/**Monitoring** → **Create monitor**:
- **Profile type:** Snapshot (for a full-table profile across all rows).
- **Measure columns:** `gpa_points` (numeric — verified DOUBLE) and `grade` (categorical — verified STRING).
- **Schedule:** on-demand for the demo.

Click **Refresh metrics** to capture the baseline profile. Monitoring creates two Delta tables in
`system.lakehouse_monitoring`:
- `_profile_metrics` — row count, mean, stddev, null%, distinct counts per column, per refresh.
- `_drift_metrics` — detected anomalies (metric + direction + severity) when a measure drifts
  beyond configured thresholds from the baseline.

Query the baseline:
```sql
SELECT table_name, col_name, metric_name, value
FROM system.lakehouse_monitoring.profile_metrics
WHERE table_name LIKE '%enrollment_history%'
ORDER BY metric_timestamp DESC, col_name, metric_name
LIMIT 20;
```
This shows the baseline mean GPA, grade distribution, null counts, etc.

**Simulate + detect drift:** In your own `wksp_<you>` schema, create a copy of the fact and skew it:
```sql
-- 1. Create a copy of enrollment_history in your schema
CREATE TABLE princeton_poc_dev.wksp_<you>.enrollment_history_v2 AS
SELECT * FROM princeton_poc_dev.gold_dev.enrollment_history;

-- 2. Skew the data: set all grades to 'A' (originally ~15% A, now 100%)
UPDATE princeton_poc_dev.wksp_<you>.enrollment_history_v2
SET grade = 'A' WHERE grade IS NOT NULL;

-- 3. Create a Lakehouse Monitor on your skewed copy (same UI steps as above):
-- Catalog Explorer → your schema → enrollment_history_v2 → Quality → Create monitor
-- Profile type: Snapshot, measure columns: gpa_points, grade, refresh now.

-- 4. Query the drifted profile and compare to the baseline:
SELECT col_name, metric_name, value
FROM system.lakehouse_monitoring.profile_metrics
WHERE table_name LIKE '%enrollment_history_v2%'
ORDER BY metric_timestamp DESC, col_name, metric_name
LIMIT 20;

-- The grade column's distinct_values and proportions will show 100% 'A' (vs baseline ~15%).
-- This is the DRIFT DETECTED.

-- 5. View drift anomalies flagged by the monitor:
SELECT col_name, metric_name, direction, severity
FROM system.lakehouse_monitoring.drift_metrics
WHERE table_name LIKE '%enrollment_history_v2%'
ORDER BY metric_timestamp DESC;

-- Example: anomaly on grade's distinct_values with severity="medium" (far from baseline).
```

**Verified capability:** baseline profile establishes the expected distribution; the drifted copy
shows the metric move (grade diversity from ~5 categories to 1). The drift metrics table surfaces
the anomaly with the column and metric name, allowing the operator to investigate "what changed?"

> **Note:** monitors are created per-table via the UI/API. The `system.lakehouse_monitoring` schema
> is automatically provisioned when you create the first monitor. Profile metrics update on each
> refresh; drift anomalies are computed relative to the baseline profile.

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
