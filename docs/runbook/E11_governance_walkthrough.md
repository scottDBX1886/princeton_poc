# E11 — Governance Walkthrough (SE-40, SE-41, SE-42, SE-43)

Proves Databricks' native data-governance surface across the POC data: **lineage** (automatic),
**schema-drift detection** (Auto Loader, source-driven), **data-drift monitoring** (UC data profiling, formerly Lakehouse Monitoring), and
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

**The idea:** E1 ingests student CSVs with Auto Loader. Drop a new file that has an **extra column**
the pipeline has never seen, re-run E1, and Auto Loader **detects** the change and **stops the run
with a clear message** naming the new column — real source-driven drift detection, not a schema
change you made yourself.

**Prerequisite:** you've already run **E1** (SE-04) in this session, so `e1_students_raw` exists in
your schema. (Substitute your schema for `<you>` — e.g. `wksp_scott_johnson`.)

**Step 1 — get the drift file (no CLI needed).** In Catalog Explorer, open the Volume
`princeton_poc_dev.landing_dev.files` → folder **`e11_drift_demo`** → **download**
`drifted_students.csv` (the real 8 student columns **plus** an unexpected `citizenship` column;
`student_id`s from 900001 so it never collides with real data).

**Step 2 — upload it into E1's landing folder + re-run.** In Catalog Explorer, open the same Volume
→ the **`students_csv`** folder → **Upload to this volume** → drop `drifted_students.csv` in. Then open
your E1 pipeline and click **Run**.

**Step 3 — observe the detection.** With Auto Loader's default (`addNewColumns`), the run **stops
with `UnknownFieldException`**, and the pipeline's **error / event log names the new column**
(`citizenship`). That is the RFP's "detected and surfaced; pipeline halts with a clear message."
Auto Loader has also recorded the new column in its schema, so simply **clicking Run again** resumes
with the widened schema (the new column now flows through) — "handles the change gracefully" once
you've acknowledged it.

**Step 4 — reset when done:** in Catalog Explorer, open the `students_csv` folder and delete the
uploaded `drifted_students.csv`.

> **The behaviour is configurable** via `cloudFiles.schemaEvolutionMode` on the stream — this is the
> "or handles the change gracefully per configuration" half of the RFP ask. You do not need to change
> anything for the demo above (the default already detects + halts), but the three modes are:
> - **`addNewColumns` (default)** — halts with `UnknownFieldException`, adds the column, resumes on re-run.
> - **`rescue`** — never fails; unexpected fields land in the built-in `_rescued_data` column (query it to see what drifted).
> - **`failOnNewColumns`** — halts and will **not** resume until you update the schema or remove the file (strict contract).

> **Why Auto Loader, not `ALTER TABLE` + `DESCRIBE HISTORY`:** the RFP asks the platform to *detect*
> a structural change in a **source**. `DESCRIBE HISTORY` only records a change *you* made — it's an
> audit log, not detection. Auto Loader noticing an unexpected column in an arriving file is genuine
> source-driven detection, which is the production reality for ingestion.

## SE-42 — Data-drift detection (UC data profiling)

> **Naming:** what was "Lakehouse Monitoring" is now **Data profiling**, under Unity Catalog
> **data quality monitoring**. You **create a profile** on a table (Catalog Explorer → the table →
> **Quality** tab); older docs/UI may still say "monitor." Same feature.

**The idea:** a data profile snapshots a table's distribution each time it refreshes. Take a
baseline, change the data, refresh again — the profile **flags the drift and names the column/metric
that moved.** Drift is measured **between successive refreshes of the same profile**, so you apply
the change *between* two refreshes (not by comparing two tables).

You'll profile the **`e5_student_enriched` table you already built in E5** — it lives in your own
`wksp_<you>` schema, so nothing shared is touched. Substitute your schema for `<you>` throughout
(e.g. `wksp_scott_johnson`).

**Step 1 — create the profile (UI).** Catalog Explorer → open
`princeton_poc_dev.wksp_<you>.e5_student_enriched` → **Quality** tab → **Create data profile**
(older UI: "Create monitor"):
- **Profile type:** *Snapshot*
- **Metrics for these columns:** `cumulative_gpa` (numeric) and `standing` (categorical)
- Leave the **output/metrics schema** as your own schema (`wksp_<you>`)
- **Create**, then click **Refresh metrics**. This first refresh is the **baseline**.

**Step 2 — introduce drift, then refresh again:**
```sql
-- shift a numeric and a categorical column on a third of the rows so drift is obvious
UPDATE princeton_poc_dev.wksp_<you>.e5_student_enriched
SET standing = 'Alumnus', cumulative_gpa = 4.0
WHERE student_id % 3 = 0;
```
Back on the **Quality** tab → **Refresh metrics** a **second** time. There are now two refresh
windows for the profile to compare.

**Step 3 — see the drift flagged.** On the **Quality** tab, open the profile's **dashboard**, or
query its **drift metrics table** (its name is shown on the Quality tab, in your schema). Between the
two windows, `standing` and `cumulative_gpa` shift — the drift metrics row **names those columns and
the metric that moved**, which is exactly SE-42's "anomaly flagged with the metric that triggered it,"
with the two windows as the historical trend.

**Reset when done:** re-run your **E5 pipeline** — it rebuilds `e5_student_enriched` back to its
baseline values. (Or just leave it; it's your own sandbox copy.)

> **Confirmed on this workspace:** a profile writes its own **profile-metrics** and **drift-metrics**
> Delta tables into the schema you choose — there is **no** global `system.lakehouse_monitoring`
> schema. Drift needs the change applied **between two refreshes of one profile**; a single snapshot,
> or two separate profiles, will not populate drift metrics.

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
