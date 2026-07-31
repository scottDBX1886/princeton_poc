# Princeton POC — Phase 0: Shared Data Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic shared higher-ed data foundation (core model, raw source files, multi-million-row fact, day-2 change script) in Unity Catalog `princeton_poc`, packaged in a DAB skeleton, so all later persona phases build on one common dataset.

**Architecture:** A single seeded Spark/Faker generator produces the normalized higher-ed model as Delta tables (Bronze→Silver→Gold) and as raw source files (CSV/pipe/Excel/JSON/XML) on a UC Volume. A `row_count` parameter scales the `enrollment_history` fact. A day-2 change script drives CDC/SCD/drift downstream. Everything is a DAB resource for one-command deploy to any workspace. The two apps (mock REST API, SFTP server) are a separate plan (Plan 2).

**Tech Stack:** Databricks (Unity Catalog, Volumes, serverless notebooks/jobs), PySpark, Faker, Databricks Asset Bundles (DAB), Databricks CLI, Git.

## Global Constraints

- **Simpler is better** — POC proves capability, not production. Fewest honest artifacts.
- **Deterministic** — every generator uses a fixed seed so internal and POC workspaces produce identical data.
- **Catalog:** per-target (shared metastore) — dev=`princeton_poc_dev`, qa=`princeton_poc_test`, prod=`princeton_poc`. Value flows target → `var.catalog` → job parameter → notebook `catalog` widget → every `saveAsTable`. Notebooks must NOT hardcode the catalog; they read `dbutils.widgets.get("catalog")`.
- **Schemas:** `bronze`, `silver`, `gold`, `landing` (volume schema).
- **Volume:** `<catalog>.landing.files` at `/Volumes/<catalog>/landing/files/`.
- **Profile:** NEVER auto-select. All CLI commands take `--profile <PROFILE>`; the operator chooses at execution. Placeholder `<PROFILE>` throughout.
- **Serverless** compute for all notebooks/jobs unless a task states otherwise.
- **Production-mode targets** (qa/prod) must set `workspace.root_path` (DAB requirement) — use `/Workspace/Shared/.bundle/${bundle.name}/${bundle.target}`, plus a bundle-level `permissions` grant (`CAN_MANAGE` for group `users`) to acknowledge the shared path. Dev (development mode) auto-isolates under the user's path.
- **Per-target catalog** flows via a job `parameters:` entry + each notebook task's `base_parameters: {catalog: ${var.catalog}}` + a `catalog` widget in every notebook.
- **Everything is a DAB resource** — no click-ops for anything that must reproduce in the POC workspace.
- **Verification model** (Databricks-appropriate, replaces pytest-TDD): each task ends with build → run → **assert** (row counts / schema / files land) → commit. Assertions are explicit SQL or CLI checks with expected output.
- **Row-count parameter:** `row_count` (default 5_000_000 internal; override to ~50_000_000 in POC).

---

### Task 0: Repo + DAB skeleton + workspace preflight

**Files:**
- Create: `databricks.yml` (bundle root)
- Create: `resources/foundation.job.yml`
- Create: `src/foundation/__init__.py`
- Create: `README.md`
- Create: `.gitignore`
- Create: `docs/CONFIG.md`

**Interfaces:**
- Produces: a deployable bundle named `princeton_poc` with `dev`/`qa`/`prod` targets; a job resource key `foundation_build` (populated in later tasks).

- [ ] **Step 1: Confirm CLI + auth (operator picks profile)**

Run: `databricks --version` (expect v0.294.0+) and `databricks current-user me --profile <PROFILE>`
Expected: version prints; user JSON returns (confirms auth to the chosen workspace).

- [ ] **Step 2: Initialize git repo**

```bash
cd /Users/scott.johnson/customers/Princeton/it_rfp
git init
```

- [ ] **Step 3: Write `.gitignore`**

```
.databricks/
__pycache__/
*.pyc
.env
/tmp/
```

- [ ] **Step 4: Write `databricks.yml`**

```yaml
bundle:
  name: princeton_poc

variables:
  catalog:
    description: Target UC catalog
    default: princeton_poc
  storage_root:
    description: Managed storage location URL for the catalog (external location or metastore-managed path). Operator sets per target.
    default: ""   # MUST be overridden per target with a real storage URL
  warehouse_id:
    description: SQL warehouse ID for SQL-backed tasks (added in later phases). Set per target when needed.
    default: ""   # plain (lazy) var — no Phase 0 resource uses a warehouse. A `lookup:` here fails validate if the named warehouse is absent, so use a plain default and supply an ID when SQL tasks land.
  row_count:
    description: Rows in enrollment_history fact
    default: 5000000

targets:
  dev:
    mode: development
    default: true
    workspace:
      host: ${workspace.host}
    variables:
      storage_root: "<DEV_STORAGE_URL>"   # e.g. s3://.../princeton_poc or abfss://...
  qa:
    mode: production
    workspace:
      host: ${workspace.host}
    variables:
      storage_root: "<QA_STORAGE_URL>"
  prod:
    mode: production
    workspace:
      host: ${workspace.host}
    variables:
      storage_root: "<PROD_STORAGE_URL>"

include:
  - resources/*.yml
```

> **Note (storage_root):** the catalog needs a managed storage location. Operator supplies a real external-location / object-store URL per target. If the target metastore already has a default managed location and you prefer to inherit it, drop `storage_root` from the catalog resource in Task 1 — but the explicit path is the portable default for fresh POC workspaces.

- [ ] **Step 5: Write placeholder `resources/foundation.job.yml`**

```yaml
resources:
  jobs:
    foundation_build:
      name: "[princeton_poc] Foundation build"
      tasks: []
```

- [ ] **Step 6: Validate the bundle**

Run: `databricks bundle validate -t dev --profile <PROFILE>`
Expected: "Validation OK" with bundle name `princeton_poc`.

- [ ] **Step 7: Write `docs/CONFIG.md` (the "what to fill in before deploy" reference)**

```markdown
# Princeton POC — Deployment Configuration

All values are DAB variables declared in `databricks.yml`. Edit the per-target
`variables:` block, OR override at deploy with `--var name=value` (no file edit).
Precedence: databricks.yml default → per-target → `--var` → `BUNDLE_VAR_<name>` env var.

## Variables to set

| Variable | Purpose | Default | You must set it? |
|----------|---------|---------|------------------|
| `catalog` | Target UC catalog name | `princeton_poc` | No — override only to avoid a name clash |
| `storage_root` | Catalog managed storage location (external-location / object-store URL) | *(empty placeholder)* | **YES — before first deploy.** Set `<DEV/QA/PROD_STORAGE_URL>` per target. Drop the line to inherit metastore default. |
| `warehouse_id` | SQL warehouse for SQL tasks (by name lookup) | `"Serverless Starter Warehouse"` | **YES if that warehouse name doesn't exist** in the target workspace — change the lookup name. |
| `row_count` | Rows in `enrollment_history` fact | `5000000` | No — override to ~`50000000` for the POC: `--var row_count=50000000` |

## Per-workspace values (fill in)

| Target | `--profile` | `storage_root` | `warehouse_id` (name) |
|--------|-------------|----------------|-----------------------|
| dev (internal) | _____ | _____ | _____ |
| qa | _____ | _____ | _____ |
| prod (Princeton POC) | _____ | _____ | _____ |

## Secrets (NOT bundle variables — never commit)
Credentials (SFTP password, OAuth client secret for the mock API) live in a UC secret
scope and are referenced by name. Set up in Plan 2 (apps), not here.

## Deploy
```bash
databricks bundle validate --strict -t <target> --profile <PROFILE>
databricks bundle deploy -t <target> --profile <PROFILE>
databricks bundle run foundation_build -t <target> --profile <PROFILE>
```
```

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "chore: DAB skeleton + repo init + CONFIG.md for Princeton POC foundation"
```

---

### Task 1: Unity Catalog namespace as DAB resources (catalog, schemas, volume)

**Why declarative, not SQL:** DABs natively supports `catalogs`, `schemas`, and
`volumes` as resource types (verified via `databricks bundle schema`). The namespace is
therefore created at **`bundle deploy`** — before any job runs — so nothing that
references the catalog can race ahead of its creation. No `CREATE CATALOG` SQL script.

**Files:**
- Create: `resources/uc_namespace.yml`

**Interfaces:**
- Produces (at deploy): catalog `princeton_poc` (with `storage_root`); schemas
  `bronze`, `silver`, `gold`, `landing`; volume `princeton_poc.landing.files`. All later
  tasks assume these exist.

- [ ] **Step 1: Write `resources/uc_namespace.yml`**

```yaml
resources:
  catalogs:
    princeton_poc:
      name: ${var.catalog}
      comment: "Princeton POC shared data foundation"
      storage_root: ${var.storage_root}   # omit this line to inherit metastore default
  schemas:
    bronze:
      catalog_name: ${var.catalog}
      name: bronze
    silver:
      catalog_name: ${var.catalog}
      name: silver
    gold:
      catalog_name: ${var.catalog}
      name: gold
    landing:
      catalog_name: ${var.catalog}
      name: landing
  volumes:
    landing_files:
      catalog_name: ${var.catalog}
      schema_name: landing
      name: files
      volume_type: MANAGED
```

- [ ] **Step 2: Validate**

Run: `databricks bundle validate --strict -t dev --profile <PROFILE>`
Expected: "Validation OK"; the four resource types resolve.
(Catalog creation requires the `CREATE CATALOG` metastore privilege for the deploying
principal — if absent, operator requests it; see spec §8.)

- [ ] **Step 3: Deploy to create the namespace**

Run: `databricks bundle deploy -t dev --profile <PROFILE>`
Expected: catalog, schemas, and volume created in the workspace.

- [ ] **Step 4: Assert namespace exists**

Run:
```sql
SHOW SCHEMAS IN princeton_poc;
```
Expected rows include: `bronze`, `silver`, `gold`, `landing`.

Run:
```sql
DESCRIBE VOLUME princeton_poc.landing.files;
```
Expected: volume path `/Volumes/princeton_poc/landing/files`.

- [ ] **Step 5: Commit**

```bash
git add resources/uc_namespace.yml && git commit -m "feat: UC namespace (catalog+schemas+volume) as DAB resources"
```

---

### Task 2: Core entity generator (deterministic) → Silver dims/facts

**Files:**
- Create: `src/foundation/10_generate_core.py` (notebook-style, `# COMMAND ----------` cells)

**Interfaces:**
- Consumes: catalog/schemas from Task 1; `row_count` widget (default 5_000_000).
- Produces Silver tables: `department`(~40), `term`(~24), `faculty`(~2000), `course`(~5000), `student`(~30000), `enrollment`, `financial_aid`(~50000). `student` has `ssn`,`dob`,`dept_id`,`status`. `financial_aid` has `amount`. `dept_id` present on student/faculty/course.

- [ ] **Step 1: Write the generator (fixed seed)**

Use the **databricks-synthetic-data-gen** skill patterns. Key requirements to encode:
```python
# COMMAND ----------
dbutils.widgets.text("row_count", "5000000")
SEED = 42
import random; from faker import Faker
fake = Faker(); Faker.seed(SEED); random.seed(SEED)
CATALOG = "princeton_poc"
# COMMAND ----------
# department (~40): dept_id, name, division, building
# term (~24): term_id, year, season, start_date, end_date
# faculty (~2000): faculty_id, first/last, ssn, dept_id (FK), rank, hire_date
# course (~5000): course_id, dept_id (FK), faculty_id (FK), title, credits
# student (~30000): student_id, first/last, ssn, dob, dept_id (FK major), status, email
# financial_aid (~50000): aid_id, student_id (FK), amount, aid_type, term_id
# enrollment (core, modest): enrollment_id, student_id, course_id, term_id, grade, gpa_points
# Write each as Delta: spark.createDataFrame(...).write.mode("overwrite")
#   .saveAsTable(f"{CATALOG}.silver.<name>")
```
`status` domain: `["active","leave","graduated","withdrawn"]` (SCD-Type-2 attribute).

- [ ] **Step 2: Run the notebook** (serverless) with `row_count=100000` for a fast build-check.

- [ ] **Step 3: Assert row counts and schema**

Run:
```sql
SELECT 'department' t, count(*) c FROM princeton_poc.silver.department
UNION ALL SELECT 'student', count(*) FROM princeton_poc.silver.student
UNION ALL SELECT 'financial_aid', count(*) FROM princeton_poc.silver.financial_aid;
```
Expected: department ≈ 40; student ≈ 30000; financial_aid ≈ 50000.

Run:
```sql
DESCRIBE princeton_poc.silver.student;
```
Expected columns include `ssn`, `dob`, `dept_id`, `status`.

- [ ] **Step 4: Assert determinism**

Re-run the notebook; confirm the same first student row (same seed → identical data):
```sql
SELECT student_id, first_name, ssn FROM princeton_poc.silver.student ORDER BY student_id LIMIT 1;
```
Expected: identical values across runs.

- [ ] **Step 5: Commit**

```bash
git add src/foundation/10_generate_core.py && git commit -m "feat: deterministic core higher-ed entity generator"
```

---

### Task 3: Multi-million-row fact `enrollment_history` (Gold, scalable)

**Files:**
- Create: `src/foundation/11_generate_fact.py`

**Interfaces:**
- Consumes: Silver `student`, `course`, `term` (Task 2); `row_count` widget.
- Produces: `princeton_poc.gold.enrollment_history` (grain: student×course×term), liquid-clustered on `term_id`, `dept_id`. Plus a companion heavy query file.

- [ ] **Step 1: Write the fact generator (Spark-scale, seeded)**

```python
# COMMAND ----------
dbutils.widgets.text("row_count", "5000000")
n = int(dbutils.widgets.get("row_count"))
from pyspark.sql import functions as F
# Build n rows by cross-sampling student/course/term with a seeded rand()
# columns: enrollment_id (monotonically_increasing_id), student_id, course_id,
#          term_id, dept_id, grade, gpa_points, load_ts
df = (spark.range(n)
      .withColumn("student_id", (F.rand(42)* /* student count */ 30000).cast("int")+1)
      # ... course_id, term_id via F.rand(seed) joins; dept_id carried from student
     )
(df.write.mode("overwrite")
   .clusterBy("term_id","dept_id")
   .saveAsTable("princeton_poc.gold.enrollment_history"))
```

- [ ] **Step 2: Write companion heavy query** `src/foundation/heavy_query.sql`

```sql
-- Reusable "load" for compute scenarios (PA-13..18) and DS-05.
SELECT dept_id, term_id,
       count(*) enrollments,
       avg(gpa_points) avg_gpa,
       rank() OVER (PARTITION BY term_id ORDER BY count(*) DESC) dept_rank
FROM princeton_poc.gold.enrollment_history
GROUP BY dept_id, term_id;
```

- [ ] **Step 3: Run with `row_count=1000000`** (build-check volume).

- [ ] **Step 4: Assert count and clustering**

Run:
```sql
SELECT count(*) FROM princeton_poc.gold.enrollment_history;
```
Expected: 1000000.

Run:
```sql
DESCRIBE DETAIL princeton_poc.gold.enrollment_history;
```
Expected: `clusteringColumns` = `["term_id","dept_id"]`.

- [ ] **Step 5: Assert heavy query runs and returns**

Run `heavy_query.sql`. Expected: returns rows; note execution time for later PA baseline.

- [ ] **Step 6: Commit**

```bash
git add src/foundation/11_generate_fact.py src/foundation/heavy_query.sql && git commit -m "feat: scalable enrollment_history fact + heavy query"
```

---

### Task 4: Raw source files with deliberate gotchas → landing Volume

**Files:**
- Create: `src/foundation/20_write_source_files.py`

**Interfaces:**
- Consumes: Silver tables (Task 2).
- Produces on `/Volumes/princeton_poc/landing/files/`: `students.csv`, `enrollments.pipe.txt`, `financial_aid.xlsx` (multi-sheet), `course_catalog.json` (nested), `faculty.xml` (repeating + optional nodes).

- [ ] **Step 1: Write the file exporter with gotchas**

```python
# COMMAND ----------
import pandas as pd
base = "/Volumes/princeton_poc/landing/files"
sp = spark.table("princeton_poc.silver.student").limit(2000).toPandas()
# students.csv — inject a quoted field with embedded comma: "Doe, John"
sp.loc[sp.index[0], "last_name"] = "Doe, John"   # embedded delimiter test (SE-04)
sp.to_csv(f"{base}/students.csv", index=False, quoting=1)  # QUOTE_ALL
# enrollments.pipe.txt — pipe-delimited, one field containing a pipe
en = spark.table("princeton_poc.silver.enrollment").limit(2000).toPandas()
en.to_csv(f"{base}/enrollments.pipe.txt", sep="|", index=False)
# financial_aid.xlsx — 3 sheets: Summary, AidDetail (target), Decoy
fa = spark.table("princeton_poc.silver.financial_aid").limit(1000).toPandas()
with pd.ExcelWriter(f"{base}/financial_aid.xlsx") as w:
    fa.head(5).to_excel(w, sheet_name="Summary", index=False)
    fa.to_excel(w, sheet_name="AidDetail", index=False)   # named-sheet target (SE-05)
    fa.head(1).to_excel(w, sheet_name="Decoy", index=False)
# course_catalog.json — nested dept -> [courses] with some optional keys omitted
# faculty.xml — <department><faculty>... with optional <tenure> on some only (SE-07)
```

- [ ] **Step 2: Run the notebook.**

- [ ] **Step 3: Assert files landed**

Run: `databricks fs ls dbfs:/Volumes/princeton_poc/landing/files --profile <PROFILE>`
Expected: all five filenames present.

- [ ] **Step 4: Assert gotchas present**

Run: `databricks fs cat dbfs:/Volumes/princeton_poc/landing/files/students.csv --profile <PROFILE> | head -2`
Expected: first data row contains quoted `"Doe, John"` — not split across columns.

- [ ] **Step 5: Commit**

```bash
git add src/foundation/20_write_source_files.py && git commit -m "feat: raw source files (CSV/pipe/Excel/JSON/XML) with deliberate gotchas"
```

---

### Task 5: Bronze landing + Silver conform (medallion wiring)

**Files:**
- Create: `src/foundation/30_bronze_silver.py`

**Interfaces:**
- Consumes: raw files (Task 4), core Silver (Task 2).
- Produces: Bronze raw-landed tables from files; confirms Silver conformed layer. Establishes the Bronze→Silver→Gold flow diagram scenarios reference (SE-40 lineage).

- [ ] **Step 1: Write Auto Loader / read of the CSV into Bronze**

```python
# COMMAND ----------
(spark.read.option("header", True).option("multiLine", True).option("quote", '"')
 .csv("/Volumes/princeton_poc/landing/files/students.csv")
 .write.mode("overwrite").saveAsTable("princeton_poc.bronze.students_raw"))
```

- [ ] **Step 2: Run and assert embedded delimiter handled**

Run:
```sql
SELECT count(*) FROM princeton_poc.bronze.students_raw;
```
Expected: 2000 (no row-split from the embedded comma).

- [ ] **Step 3: Commit**

```bash
git add src/foundation/30_bronze_silver.py && git commit -m "feat: bronze landing + silver conform wiring"
```

---

### Task 6: Day-2 change script (CDC/SCD/drift engine)

**Files:**
- Create: `src/foundation/40_day2_changes.sql`

**Interfaces:**
- Consumes: Silver `student`, `enrollment` (Task 2).
- Produces: a self-documenting, known-answer set of changes for SE-03/21/22/23/41. Enables Delta CDF downstream.

- [ ] **Step 1: Enable Change Data Feed on the SCD target**

```sql
ALTER TABLE princeton_poc.silver.student SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
```

- [ ] **Step 2: Write the day-2 change script (known counts)**

```sql
-- INSERTS: 10 net-new students
INSERT INTO princeton_poc.silver.student
  SELECT student_id + 100000, first_name, last_name, ssn, dob, dept_id, 'active', email
  FROM princeton_poc.silver.student ORDER BY student_id LIMIT 10;
-- UPDATES: 20 status changes active -> graduated (SCD Type 1/2 trigger)
UPDATE princeton_poc.silver.student
  SET status = 'graduated'
  WHERE student_id IN (SELECT student_id FROM princeton_poc.silver.student
                       WHERE status='active' ORDER BY student_id LIMIT 20);
-- DELETES: 5 students removed at source (hard-delete detection SE-03)
DELETE FROM princeton_poc.silver.student
  WHERE student_id IN (SELECT student_id FROM princeton_poc.silver.student
                       ORDER BY student_id DESC LIMIT 5);
-- SCHEMA DRIFT: add a column (SE-41)
ALTER TABLE princeton_poc.silver.student ADD COLUMN citizenship STRING;
```

- [ ] **Step 3: Capture the pre-change table version** (before running Step 2 in a real demo)

Run:
```sql
DESCRIBE HISTORY princeton_poc.silver.student LIMIT 1;
```
Note the version number as the CDF read floor.

- [ ] **Step 4: Assert changes are captured via CDF**

After applying, run:
```sql
SELECT _change_type, count(*)
FROM table_changes('princeton_poc.silver.student', <pre_change_version>)
GROUP BY _change_type;
```
Expected: `insert`=10 (+ update_postimage), `update_preimage`/`update_postimage`=20 each, `delete`=5.

- [ ] **Step 5: Commit**

```bash
git add src/foundation/40_day2_changes.sql && git commit -m "feat: day-2 change script driving CDC/SCD/drift with known counts"
```

---

### Task 7: Wire everything into the DAB `foundation_build` job + full-scale run

**Files:**
- Modify: `resources/foundation.job.yml`

**Interfaces:**
- Consumes: all notebooks/SQL from Tasks 1–6.
- Produces: a single ordered `foundation_build` job that rebuilds the entire foundation in any workspace with one command.

- [ ] **Step 1: Define the ordered job tasks**

```yaml
resources:
  jobs:
    foundation_build:
      name: "[princeton_poc] Foundation build"
      # Note: the UC namespace (catalog/schemas/volume) is created at `bundle deploy`
      # via resources/uc_namespace.yml — NOT as a job task. So generate_core is the
      # first task and has no uc_setup dependency.
      tasks:
        - task_key: generate_core
          notebook_task: {notebook_path: ../src/foundation/10_generate_core.py}
        - task_key: generate_fact
          depends_on: [{task_key: generate_core}]
          notebook_task:
            notebook_path: ../src/foundation/11_generate_fact.py
            base_parameters: {row_count: "${var.row_count}"}
        - task_key: write_files
          depends_on: [{task_key: generate_core}]
          notebook_task: {notebook_path: ../src/foundation/20_write_source_files.py}
        - task_key: bronze_silver
          depends_on: [{task_key: write_files}]
          notebook_task: {notebook_path: ../src/foundation/30_bronze_silver.py}
```

- [ ] **Step 2: Validate + deploy to dev**

Run: `databricks bundle validate --strict -t dev --profile <PROFILE>` then `databricks bundle deploy -t dev --profile <PROFILE>`
Expected: deploy succeeds; the UC namespace (from Task 1, if not already deployed) and the
job `[princeton_poc] Foundation build` both appear in the workspace.

- [ ] **Step 3: Run the full foundation build**

Run: `databricks bundle run foundation_build -t dev --profile <PROFILE>`
Expected: all tasks succeed.

- [ ] **Step 4: End-to-end assert**

Run:
```sql
SELECT
 (SELECT count(*) FROM princeton_poc.silver.student) students,
 (SELECT count(*) FROM princeton_poc.gold.enrollment_history) fact_rows;
```
Expected: students ≈ 30000; fact_rows = configured `row_count`.

- [ ] **Step 5: Commit**

```bash
git add resources/foundation.job.yml && git commit -m "feat: DAB foundation_build job — one-command foundation rebuild"
```

---

## Deliverable: runbook stub

- [ ] **Final step: seed the POC runbook**

Create `docs/runbook/README.md` with a Phase-0 section stating: to stand up the shared
dataset in any workspace, run `databricks bundle run foundation_build -t <target> --profile <PROFILE>`,
then the assert query from Task 7 Step 4. Later persona plans append one runbook entry per
scenario/combination (Designer prompt / Assistant prompt / pre-built fallback / expected outcome).

The runbook MUST include a **demo-time step for `src/foundation/40_day2_changes.sql`**
(kept standalone, not auto-run): "To demonstrate CDC/SCD/drift (SE-03/21/22/23/41), run this
script during the session, then run the CDF assert (Task 6 Step 4) to show the platform
detected exactly 10 inserts / 20 updates / 5 deletes + the added column."
Commit.

---

## Self-Review

**Spec coverage (Phase 0 scope only):**
- §4.1 core model → Task 2 ✓
- §4.2 raw source files + gotchas → Task 4 ✓
- §4.4 multi-M fact + heavy query → Task 3 ✓
- §4.6 day-2 change script → Task 6 ✓
- Packaging (DAB, dev/qa/prod, one-command) → Tasks 0, 7 ✓
- UC namespace as declarative resources (catalog+schemas+volume, `storage_root`) → Task 1 ✓
- §4.3 REST API app, §4.5 SFTP app → **deferred to Plan 2** (separate subsystem) — intentional.
- BYO-DB (§4 element 3) → parked per spec §8 — no Phase 0 task, correct.
- Runbook deliverable → seeded here, extended per phase ✓

**Placeholder scan:** `<PROFILE>`, `<pre_change_version>`, `<DEV/QA/PROD_STORAGE_URL>` are
intentional operator-supplied values, documented in Global Constraints / task steps — not
plan placeholders. The fact generator (Task 3 Step 1) has inline `/* ... */` sketch comments;
flagged for fill-in at execution using the databricks-synthetic-data-gen skill. `warehouse_id`
and `storage_root` vars are declared in `databricks.yml` at Task 0 (no longer a Task 7 gap).

**Type consistency:** table names (`princeton_poc.silver.student`, `.gold.enrollment_history`)
consistent across Tasks 2–7. `row_count` widget/var name consistent. `student.status` domain
consistent between Task 2 and Task 6.
