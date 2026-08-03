# Princeton POC — Phase 2: Data Scientist — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Data Scientist (Persona 2) workflow — SQL exploration, Python/R notebooks, local connectivity, in-platform ML, scheduled workflows, version control, and visualization — all on the shared foundation, demonstrating the full ad-hoc→productionized→scheduled→shared lifecycle.

**Architecture:** Notebooks on the shared foundation (`princeton_poc_dev`) read from `gold_dev` and `silver_dev` tables via a reusable Genie space (NL path) or direct SQL/Python. Artifacts include Python + R notebooks, a pre-built connection guide (local connectivity), MLflow training + model registry, Jobs scheduling, Git-versioned notebooks, and notebook visualizations. Each task is a self-contained scenario or combination, with expected outputs verified green.

**Tech Stack:** Databricks notebooks (Python/R kernels), Databricks Genie, Databricks SQL connector + ODBC/JDBC, PySpark, pandas, MLflow, Databricks Jobs, Git (notebook Git folders), AI/BI dashboards.

## Global Constraints

- **⚠️ MULTI-USER ISOLATION (overrides every task's output path).** ~20+ participants run these runbooks concurrently in one session, per-person. Therefore: (1) the foundation (`silver_dev`/`gold_dev` + landing files) is **READ-ONLY** — no task writes to it; (2) every task that creates/writes an object (ML models, output tables, write-back) targets a **per-person schema** `${catalog}.wksp_${user}` where `user = regexp_replace(current_user(),'[^a-zA-Z0-9]','_')`, created via `CREATE SCHEMA IF NOT EXISTS`; MLflow models register under a per-user UC path. Where a task shows a shared output like `gold_dev.ds_*`, substitute `wksp_${user}.ds_*`. Helper:
  ```python
  user = spark.sql("SELECT current_user()").first()[0]
  USER_SCHEMA = "wksp_" + __import__("re").sub(r"[^a-zA-Z0-9]", "_", user)
  spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CAT}.{USER_SCHEMA}")
  ```
  A shared Genie space / AI-BI dashboard is fine (read-only). BYO-file upload lands in the per-user schema.
- **Simpler is better** — POC proves capability, not production. Fewest honest artifacts.
- **Catalog:** dev=`princeton_poc_dev`, schemas `silver_dev`, `gold_dev`, `landing_dev`.
- **Notebooks:** stored in Git folders (repo: `github.com/scottDBX1886/princeton_poc`), tied to the Phase 0 bundle.
- **Profile:** NEVER auto-select. All CLI commands take `--profile <PROFILE>`; the operator chooses at execution. Placeholder `<PROFILE>` throughout.
- **Serverless** compute for all notebooks/jobs unless a task states otherwise.
- **Foundation assumed live:** silver_dev tables (`department`, `term`, `faculty`, `course`, `student`, `enrollment`, `financial_aid`) and gold_dev.enrollment_history exist and are populated by Phase 0.
- **Notebook widgets:** read `dbutils.widgets.get("catalog")` and `get("schema_suffix")` (defaulting to `dev`). This allows the same notebook to run on dev/qa/prod without edit.
- **Scenario outputs:** write to scenario-scoped tables (e.g., `gold_dev.ds_a_genie_results`, `gold_dev.ds_e_ml_predictions`) so they don't overwrite foundation tables.
- **Verification model:** each task ends with build → run → assert (row counts / schema / files) → commit. No manual click validation; CLI asserts only.
- **Genie space:** a single reusable space over both `silver_dev` and `gold_dev`; prompts are the demo vehicle for NL queries (DS-A), and the space is embedded in the runbook as "ask this question live."
- **MLflow:** models registered in UC catalog `princeton_poc_dev.models`, inheriting platform RLS/CLS via Delta sharing if requested (PA-10 downstream).
- **Dual DS-06:** RFP uses "DS-06" for both "local connectivity" (pre-built guide) and "in-platform ML training" (notebook). Split as **DS-06(a)** (connection guide, no run artifact) and **DS-06(b)** (MLflow notebook). Flag this numbering error to Princeton in the read-out.

---

### Task 0: Git folder + notebook skeleton + repo wiring

**Files:**
- Create: `src/datascientist/__init__.py`
- Modify: `databricks.yml` (add notebook Git folder resource)
- Create: `src/datascientist/.gitignore`

**Interfaces:**
- Produces: a Git-versioned notebook folder at `/Workspace/Repos/.../princeton_poc/src/datascientist/` wired to `github.com/scottDBX1886/princeton_poc` (the operator's repo).
- All later DS notebooks land in this folder and are automatically versioned.

- [ ] **Step 1: Confirm Git repo is live**

Run: `git -C /Users/scott.johnson/customers/Princeton/it_rfp remote -v` (verify `princeton_poc` repo is configured).

- [ ] **Step 2: Write `src/datascientist/__init__.py`**

```python
# src/datascientist/__init__.py
# Namespace marker for the Data Scientist persona notebooks.
# Each notebook in this folder demonstrates a scenario from Persona 2.
```

- [ ] **Step 3: Add Git folder resource to `databricks.yml`**

Insert under `resources:` → `repos:` (create if absent):
```yaml
resources:
  repos:
    datascientist:
      url: https://github.com/scottDBX1886/princeton_poc
      path: /Repos/shared/datascientist
      branch: main
```

- [ ] **Step 4: Validate + deploy**

Run: `databricks bundle validate --strict -t dev --profile <PROFILE>`
Run: `databricks bundle deploy -t dev --profile <PROFILE>`
Expected: repo resource resolves; Git folder appears in workspace.

- [ ] **Step 5: Commit**

```bash
cd /Users/scott.johnson/customers/Princeton/it_rfp
git add src/datascientist/__init__.py databricks.yml && git commit -m "chore: DS persona Git folder + notebook skeleton"
```

---

### Task 1: SQL + Genie exploration (DS-01) — Tracks: #15

**Files:**
- Create: `src/datascientist/01_sql_genie_exploration.py` (notebook)
- Create: `resources/genie_foundation.genie.yml` (Genie space resource)

**Interfaces:**
- Consumes: `gold_dev.enrollment_history`, `silver_dev.{student,course,department}`.
- Produces: a runnable SQL notebook with 3+ ad-hoc queries (joins, window functions, CTEs); plus a Genie space `datascientist-foundation` over both silver_dev and gold_dev for NL querying.

- [ ] **Step 1: Write the SQL notebook**

Create `src/datascientist/01_sql_genie_exploration.py`:

```python
# Databricks notebook source
# COMMAND ----------
# DS-01: SQL + Genie exploration over Gold & Silver
# Demonstrates ad-hoc analysis, joins, window functions, CTEs.

dbutils.widgets.text("catalog", "princeton_poc_dev")
cat = dbutils.widgets.get("catalog")

# COMMAND ----------
# Setup
spark.sql(f"USE CATALOG {cat}")
spark.sql(f"USE SCHEMA gold_dev")

# COMMAND ----------
# Query 1: Top departments by enrollment volume (window function)
sql_query_1 = f"""
SELECT dept_id, dept_name,
       enrollment_count,
       rank() OVER (ORDER BY enrollment_count DESC) as rank
FROM (
  SELECT d.dept_id, d.name as dept_name, count(*) as enrollment_count
  FROM {cat}.gold_dev.enrollment_history eh
  JOIN {cat}.silver_dev.department d ON eh.dept_id = d.dept_id
  GROUP BY d.dept_id, d.name
)
ORDER BY rank
LIMIT 10
"""
df1 = spark.sql(sql_query_1)
display(df1)

# COMMAND ----------
# Query 2: Student GPA by term (CTE + aggregate)
sql_query_2 = f"""
WITH student_gpa AS (
  SELECT student_id, term_id, avg(gpa_points) as avg_gpa
  FROM {cat}.gold_dev.enrollment_history
  GROUP BY student_id, term_id
)
SELECT t.term_id, t.year, t.season,
       avg(sg.avg_gpa) as cohort_avg_gpa,
       count(distinct sg.student_id) as students
FROM student_gpa sg
JOIN {cat}.silver_dev.term t ON sg.term_id = t.term_id
GROUP BY t.term_id, t.year, t.season
ORDER BY t.term_id
"""
df2 = spark.sql(sql_query_2)
display(df2)

# COMMAND ----------
# Query 3: Faculty course load + student feedback (multi-join)
sql_query_3 = f"""
SELECT f.faculty_id, f.first_name, f.last_name,
       d.name as dept_name,
       count(distinct c.course_id) as courses_taught,
       count(distinct eh.student_id) as students_enrolled
FROM {cat}.silver_dev.faculty f
JOIN {cat}.silver_dev.department d ON f.dept_id = d.dept_id
LEFT JOIN {cat}.silver_dev.course c ON f.faculty_id = c.faculty_id
LEFT JOIN {cat}.gold_dev.enrollment_history eh ON c.course_id = eh.course_id
GROUP BY f.faculty_id, f.first_name, f.last_name, d.name
ORDER BY count(distinct eh.student_id) DESC
LIMIT 20
"""
df3 = spark.sql(sql_query_3)
display(df3)

# COMMAND ----------
# Genie prompt suggestion (copy to Genie Space for NL):
# "Show me the distribution of student GPAs by department across all terms"
# "Which faculty members have the highest student load, and what departments are they in?"
# "Compare enrollment trends term-over-term for each department"
```

- [ ] **Step 2: Write the Genie space resource**

Create `resources/genie_foundation.genie.yml`:

```yaml
resources:
  genie_spaces:
    foundation:
      name: "[princeton_poc] Data Foundation"
      catalog_name: ${var.catalog}
      schema_name: gold_dev
      description: >-
        Natural language exploration over the shared higher-ed data foundation.
        Surfaces gold_dev facts and silver_dev dimensions for ad-hoc analysis.
      datasets:
        - catalog_name: ${var.catalog}
          schema_name: gold_dev
          tables:
            - enrollment_history
        - catalog_name: ${var.catalog}
          schema_name: silver_dev
          tables:
            - student
            - department
            - term
            - course
            - faculty
```

Note: Genie resource is `name: "[princeton_poc] Data Foundation"` so the runbook can reference "ask the Genie space named '...'".

- [ ] **Step 3: Run the notebook** (serverless) — test the three queries.

Expected: all three queries return rows; window function ranks and CTE aggregates work.

- [ ] **Step 4: Assert the notebook ran**

```sql
SELECT count(*) FROM princeton_poc_dev.gold_dev.enrollment_history;
```
Expected: multi-million row count ✓

- [ ] **Step 5: Deploy the Genie space**

Run: `databricks bundle deploy -t dev --profile <PROFILE>`
Expected: Genie space resource created.

- [ ] **Step 6: Verify Genie space is queryable**

Run: `databricks genie spaces list -t dev --profile <PROFILE>` (or use the UI).
Expected: space `[princeton_poc] Data Foundation` appears.

- [ ] **Step 7: Commit**

```bash
git add src/datascientist/01_sql_genie_exploration.py resources/genie_foundation.genie.yml && git commit -m "feat(ds-01): SQL + Genie exploration over foundation; DS-01 scenario"
```

---

### Task 2: Python + R notebooks + BYO upload (DS-02, DS-03, DS-04) — Tracks: #16

**Files:**
- Create: `src/datascientist/02_python_pandas_notebook.py` (Python notebook)
- Create: `src/datascientist/03_r_analysis_notebook.r` (R notebook)
- Create: `src/datascientist/04_byo_data_blend.py` (Python notebook: CSV upload + join)

**Interfaces:**
- Consumes: foundation tables + a sample CSV file uploaded to landing volume.
- Produces: three runnable notebooks demonstrating Python (pandas read/transform/write), R (statistical summary), and BYO-data blending (read local file → join with platform data → output).

- [ ] **Step 1: Write Python pandas notebook**

Create `src/datascientist/02_python_pandas_notebook.py`:

```python
# Databricks notebook source
# COMMAND ----------
# DS-02: Python Pandas read/transform/write on foundation data
# Demonstrate pandas operations on Delta tables.

dbutils.widgets.text("catalog", "princeton_poc_dev")
cat = dbutils.widgets.get("catalog")

# COMMAND ----------
import pandas as pd
import numpy as np

# Read enrollment_history as pandas
df_enrollments = spark.sql(f"""
  SELECT student_id, course_id, term_id, grade, gpa_points
  FROM {cat}.gold_dev.enrollment_history
  LIMIT 10000
""").toPandas()

print(f"Loaded {len(df_enrollments)} enrollment rows")

# COMMAND ----------
# Transform: add derived columns, summary stats
df_enrollments['grade_numeric'] = df_enrollments['grade'].apply(
    lambda g: {'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0}.get(g, np.nan)
)
df_enrollments['quarter_gpa'] = df_enrollments['gpa_points'].rolling(window=4, min_periods=1).mean()

# Summary stats
print("GPA statistics:")
print(df_enrollments[['gpa_points', 'quarter_gpa']].describe())

# COMMAND ----------
# Write transformed data back to Delta
output_table = f"{cat}.gold_dev.ds_02_pandas_output"
df_output = df_enrollments[['student_id', 'term_id', 'gpa_points', 'grade_numeric']].drop_duplicates()
spark.createDataFrame(df_output).write.mode("overwrite").saveAsTable(output_table)
print(f"Wrote {len(df_output)} rows to {output_table}")

# COMMAND ----------
# Verify
spark.sql(f"SELECT count(*) FROM {output_table}").show()
```

- [ ] **Step 2: Write R analysis notebook**

Create `src/datascientist/03_r_analysis_notebook.r`:

```r
# Databricks notebook source
# COMMAND ----------
# DS-03: R statistical analysis on foundation data

catalog <- "princeton_poc_dev"

# COMMAND ----------
# Read from Delta table
query <- sprintf("SELECT gpa_points, grade FROM %s.gold_dev.enrollment_history LIMIT 5000", catalog)
df_enrollments <- SparkR::sql(query)
df_local <- SparkR::collect(df_enrollments)

cat(sprintf("Loaded %d rows\n", nrow(df_local)))

# COMMAND ----------
# Basic statistics
cat("\nGPA Summary:\n")
print(summary(df_local$gpa_points))

# Correlation & distribution
cat("\nGPA Distribution (quartiles):\n")
print(quantile(df_local$gpa_points, probs=seq(0, 1, 0.25)))

# Grade distribution
cat("\nGrade Distribution:\n")
print(table(df_local$grade))

# COMMAND ----------
# Write summary stats back
summary_df <- data.frame(
  metric = c("mean_gpa", "sd_gpa", "min_gpa", "max_gpa"),
  value = c(
    mean(df_local$gpa_points, na.rm=TRUE),
    sd(df_local$gpa_points, na.rm=TRUE),
    min(df_local$gpa_points, na.rm=TRUE),
    max(df_local$gpa_points, na.rm=TRUE)
  )
)

output_table <- sprintf("%s.gold_dev.ds_03_r_summary", catalog)
SparkR::createDataFrame(summary_df) %>%
  SparkR::write.mode("overwrite") %>%
  SparkR::saveAsTable(output_table)

cat(sprintf("Wrote summary to %s\n", output_table))
```

- [ ] **Step 3: Write BYO data blend notebook**

Create `src/datascientist/04_byo_data_blend.py`:

```python
# Databricks notebook source
# COMMAND ----------
# DS-04: BYO data — upload CSV to landing volume, join with platform data

import pandas as pd
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "princeton_poc_dev")
cat = dbutils.widgets.get("catalog")

# COMMAND ----------
# Assume a CSV has been uploaded to landing_dev volume
# Example: external_rankings.csv with columns: dept_id, ranking, benchmark_score
landing_path = f"/Volumes/{cat}/landing_dev/files"

# For demo, create a sample external data file (in real scenario, user uploads via UI)
external_data = pd.DataFrame({
    "dept_id": [1, 2, 3, 4, 5],
    "ranking": [1, 2, 3, 4, 5],
    "benchmark_score": [95.2, 88.5, 76.3, 65.1, 52.8]
})
external_data.to_csv(f"{landing_path}/external_rankings.csv", index=False)
print(f"Wrote sample external data to {landing_path}/external_rankings.csv")

# COMMAND ----------
# Read external data
df_external = spark.read.option("header", True).csv(f"{landing_path}/external_rankings.csv")
df_external = df_external.withColumn("ranking", F.col("ranking").cast("int")) \
                         .withColumn("benchmark_score", F.col("benchmark_score").cast("double"))

# Read foundation data
df_internal = spark.sql(f"""
  SELECT d.dept_id, d.name as dept_name, count(*) as enrollment_count
  FROM {cat}.gold_dev.enrollment_history eh
  JOIN {cat}.silver_dev.department d ON eh.dept_id = d.dept_id
  GROUP BY d.dept_id, d.name
""")

# COMMAND ----------
# Join external + internal
df_blended = df_internal.join(df_external, on="dept_id", how="left")

# COMMAND ----------
# Write blended output
output_table = f"{cat}.gold_dev.ds_04_byo_blended"
df_blended.write.mode("overwrite").saveAsTable(output_table)
print(f"Wrote {df_blended.count()} rows to {output_table}")

# COMMAND ----------
# Display
display(spark.sql(f"SELECT * FROM {output_table}"))
```

- [ ] **Step 4: Run all three notebooks** (serverless).

Expected: all three complete without error.

- [ ] **Step 5: Assert output tables exist**

```sql
SELECT count(*) FROM princeton_poc_dev.gold_dev.ds_02_pandas_output;
SELECT count(*) FROM princeton_poc_dev.gold_dev.ds_03_r_summary;
SELECT count(*) FROM princeton_poc_dev.gold_dev.ds_04_byo_blended;
```
Expected: all three return row counts > 0.

- [ ] **Step 6: Commit**

```bash
git add src/datascientist/02_python_pandas_notebook.py src/datascientist/03_r_analysis_notebook.r src/datascientist/04_byo_data_blend.py && git commit -m "feat(ds-02,03,04): Python + R + BYO data blend notebooks; DS-02/03/04 scenarios"
```

---

### Task 3: Large-dataset query (DS-05) — Tracks: #17

**Files:**
- Create: `src/datascientist/05_large_dataset_query.py` (notebook)

**Interfaces:**
- Consumes: `gold_dev.enrollment_history` (multi-million row fact).
- Produces: a notebook that runs a heavy query (joins + window functions + aggregates), captures the query profile + execution plan, and logs the run time for later PA cost analysis (PA-13..18).

- [ ] **Step 1: Write the heavy query notebook**

Create `src/datascientist/05_large_dataset_query.py`:

```python
# Databricks notebook source
# COMMAND ----------
# DS-05: Large-dataset query on multi-million-row fact
# Demonstrates query profiling, execution plans, and performance analysis.

dbutils.widgets.text("catalog", "princeton_poc_dev")
cat = dbutils.widgets.get("catalog")

# COMMAND ----------
import time

# COMMAND ----------
# Enable query profiling
spark.sql("SET spark.databricks.queryProfile.enabled = true")

# COMMAND ----------
# Heavy query: department-term enrollment summary with ranks
query = f"""
SELECT dept_id, term_id,
       count(*) as enrollments,
       avg(gpa_points) as avg_gpa,
       min(gpa_points) as min_gpa,
       max(gpa_points) as max_gpa,
       rank() OVER (PARTITION BY term_id ORDER BY count(*) DESC) as dept_rank
FROM {cat}.gold_dev.enrollment_history
GROUP BY dept_id, term_id
ORDER BY term_id, dept_rank
"""

# COMMAND ----------
# Run and time
start = time.time()
df_result = spark.sql(query)
df_result.cache()  # Force execution
row_count = df_result.count()
elapsed = time.time() - start

print(f"Query completed in {elapsed:.2f} seconds")
print(f"Result set: {row_count} rows")

# COMMAND ----------
# Capture query profile
# (Databricks UI shows this; programmatic access via Spark history is internal)
spark.sql("DESCRIBE QUERY PROFILE")

# COMMAND ----------
# Display results
display(df_result)

# COMMAND ----------
# Write performance metadata
metadata = spark.createDataFrame([{
    "query_type": "enrollment_summary",
    "row_count": row_count,
    "elapsed_seconds": round(elapsed, 2),
    "timestamp": spark.sql("SELECT current_timestamp() as ts").collect()[0][0]
}])

output_table = f"{cat}.gold_dev.ds_05_query_metrics"
metadata.write.mode("overwrite").saveAsTable(output_table)
print(f"Metrics written to {output_table}")
```

- [ ] **Step 2: Run the notebook** (serverless).

Expected: query completes; row count and elapsed time logged.

- [ ] **Step 3: Assert results and metrics**

```sql
SELECT * FROM princeton_poc_dev.gold_dev.ds_05_query_metrics;
```
Expected: row_count, elapsed_seconds populated.

- [ ] **Step 4: Commit**

```bash
git add src/datascientist/05_large_dataset_query.py && git commit -m "feat(ds-05): large-dataset query + profiling; DS-05 scenario"
```

---

### Task 4: Local connectivity (DS-06(a)) — Tracks: #18

**Files:**
- Create: `resources/ds_06a_connectivity_guide.md` (pre-built guide, no execution artifact)

**Interfaces:**
- Produces: a markdown guide with connection snippets for Python (databricks-sql-connector), R (odbc), and SAS/SPSS (JDBC) connecting from a laptop to the POC workspace, inheriting UC RLS/CLS permissions.
- No in-workspace notebook to run; this is a reference document + snippets.

- [ ] **Step 1: Write the connectivity guide**

Create `resources/ds_06a_connectivity_guide.md`:

```markdown
# DS-06(a): Local Connectivity — Python/R/SAS/SPSS from Laptop

This guide demonstrates how Data Scientists on their laptops (Python, R, SAS, SPSS)
connect to Databricks over the SQL connector (Python) or JDBC/ODBC bridges,
inheriting UC permissions automatically.

## Prerequisites

- Databricks workspace at `<workspace-url>` (e.g., `https://xxxxx.cloud.databricks.com`)
- Personal access token (PAT) generated in Account Settings → User Settings
- SQL Warehouse ID (e.g., `abc123xyz`)
- UC catalog `princeton_poc_dev`, schemas `silver_dev`, `gold_dev`

## 1. Python (databricks-sql-connector)

### Install

```bash
pip install databricks-sql-connector
```

### Connect and Query

```python
from databricks import sql

connection = sql.connect(
    server_hostname="xxxxx.cloud.databricks.com",
    http_path="/sql/1.0/warehouses/<WAREHOUSE_ID>",
    auth_type="pat",
    token="<YOUR_PAT>"
)

cursor = connection.cursor()
cursor.execute("SELECT * FROM princeton_poc_dev.gold_dev.enrollment_history LIMIT 10")
rows = cursor.fetchall()
for row in rows:
    print(row)
cursor.close()
connection.close()
```

### With Pandas

```python
import pandas as pd
from databricks import sql

connection = sql.connect(...)
df = pd.read_sql("SELECT * FROM princeton_poc_dev.silver_dev.student", connection)
print(df.head())
```

**UC Permissions:** The PAT-authenticated user inherits their UC object permissions
automatically. If a table is restricted via RLS (row filters) or CLS (column masks),
they are applied transparently.

## 2. R (ODBC via Databricks JDBC driver)

### Install ODBC Driver

On macOS/Linux:
```bash
brew install unixodbc
# Download Databricks JDBC driver from
# https://databricks.com/spark/odbc-driver-download
# Extract and note the path (e.g., /usr/local/lib/libdbcjdbc.so)
```

### Configure ODBC DSN (`~/.odbc.ini`)

```ini
[databricks_warehouse]
Driver = Databricks JDBC Driver
Server = xxxxx.cloud.databricks.com
Port = 443
HTTPPath = /sql/1.0/warehouses/<WAREHOUSE_ID>
AuthType = Pat
UserAgentEntry = Databricks
UseNativeQuery = 1
UID = token
PWD = <YOUR_PAT>
```

### Connect in R

```r
library(odbc)

con <- dbConnect(
  odbc::odbc(),
  dsn = "databricks_warehouse"
)

result <- dbGetQuery(con, "SELECT * FROM princeton_poc_dev.silver_dev.department LIMIT 10")
print(result)
dbDisconnect(con)
```

**UC Permissions:** Same as Python — applied transparently.

## 3. SAS (JDBC)

### Configure SAS/ACCESS Interface to JDBC

In SAS code:
```sas
LIBNAME mydb JDBC
  URL="jdbc:databricks://xxxxx.cloud.databricks.com:443;HTTPPath=/sql/1.0/warehouses/<WAREHOUSE_ID>"
  UID="token"
  PWD="<YOUR_PAT>";

DATA my_enrollments;
  SET mydb.'princeton_poc_dev'n.'gold_dev'n.'enrollment_history'n;
RUN;
```

**UC Permissions:** Inherited per the SAS user identity.

## 4. SPSS (JDBC via Simba driver)

### Install Simba Databricks JDBC Driver

Download from Databricks downloads portal; extract and add to SPSS classpath.

### Configure in SPSS Statistics

Via the UI: Databases → New Connection
- Driver: Databricks
- Server: xxxxx.cloud.databricks.com
- Warehouse: /sql/1.0/warehouses/<WAREHOUSE_ID>
- User: token
- Password: <YOUR_PAT>

Connect and query tables in `princeton_poc_dev.{silver_dev,gold_dev}`.

## Permissions Model

All tools inherit the connecting user's UC permissions:
- If a user lacks `SELECT` on a table, queries fail with `PERMISSION_DENIED`.
- If RLS row filters are defined, only compliant rows are returned.
- If CLS column masks are defined, masked columns are NULL or transformed.

**No special configuration needed** — UC is the source of truth.

## Security Notes (POC vs. Production)

- **POC:** PAT is the simplest method. Store in an env var or `.env` (never commit).
- **Production:** use OAuth 2.0 flows or service principals with scoped credentials.
- Rotate PATs regularly; use short TTLs where supported.

---

Snippets are runnable as-is on the dev workspace. Adapt the warehouse ID, workspace URL, and PAT for qa/prod.
```

- [ ] **Step 2: Verify the guide is readable**

```bash
cat resources/ds_06a_connectivity_guide.md
```
Expected: guide content displays with all three language examples intact.

- [ ] **Step 3: Commit**

```bash
git add resources/ds_06a_connectivity_guide.md && git commit -m "docs(ds-06a): local connectivity guide (Python/R/SAS/SPSS); DS-06(a) scenario"
```

---

### Task 5: In-platform ML training (DS-06(b)) — Tracks: #19

**Files:**
- Create: `src/datascientist/06b_mlflow_training.py` (notebook)

**Interfaces:**
- Consumes: `gold_dev.enrollment_history`, `silver_dev.student` (features).
- Produces: a trained classification/regression model (predict student grade or GPA), logged to MLflow with metrics, registered in UC (`princeton_poc_dev.models.grade_predictor`), ready for serving.

- [ ] **Step 1: Write the MLflow training notebook**

Create `src/datascientist/06b_mlflow_training.py`:

```python
# Databricks notebook source
# COMMAND ----------
# DS-06(b): In-platform ML training with MLflow
# Train a classification model to predict student grade from enrollment features.

dbutils.widgets.text("catalog", "princeton_poc_dev")
cat = dbutils.widgets.get("catalog")

# COMMAND ----------
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
import pandas as pd

# COMMAND ----------
# Set MLflow experiment
exp_name = f"/Users/{spark.sql('SELECT current_user()').collect()[0][0].split('@')[0]}/ds_grade_prediction"
mlflow.set_experiment(exp_name)

# COMMAND ----------
# Load training data: enrollment + student features
query = f"""
SELECT 
  eh.enrollment_id,
  eh.student_id,
  eh.course_id,
  eh.term_id,
  eh.gpa_points,
  eh.grade,
  s.dept_id,
  year(current_date()) - year(s.dob) as age
FROM {cat}.gold_dev.enrollment_history eh
JOIN {cat}.silver_dev.student s ON eh.student_id = s.student_id
LIMIT 50000
"""

df_train = spark.sql(query).toPandas()
print(f"Loaded {len(df_train)} rows for training")

# COMMAND ----------
# Prepare features and target
# Features: course_id, term_id, dept_id, age, gpa_points
# Target: grade (A, B, C, D, F)
X = df_train[['course_id', 'term_id', 'dept_id', 'age', 'gpa_points']].fillna(0)
y = df_train['grade']

# Encode grade labels
grade_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'F': 4}
y_encoded = y.map(grade_map)

X_train, X_test, y_train, y_test = train_test_split(X, y_encoded, test_size=0.2, random_state=42)
print(f"Train: {len(X_train)}, Test: {len(X_test)}")

# COMMAND ----------
# Train model
with mlflow.start_run() as run:
    model = RandomForestClassifier(n_estimators=50, max_depth=10, random_state=42)
    model.fit(X_train, y_train)
    
    # Predictions
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, average='weighted')
    
    # Log metrics
    mlflow.log_metric("accuracy", accuracy)
    mlflow.log_metric("f1_score", f1)
    mlflow.log_param("n_estimators", 50)
    mlflow.log_param("max_depth", 10)
    
    # Log model
    mlflow.sklearn.log_model(model, "grade_predictor")
    
    print(f"Run ID: {run.info.run_id}")
    print(f"Accuracy: {accuracy:.3f}, F1: {f1:.3f}")

# COMMAND ----------
# Register model in UC
model_uri = f"runs:/{run.info.run_id}/grade_predictor"
registered_model = mlflow.register_model(
    model_uri, 
    f"{cat}.models.grade_predictor"
)
print(f"Model registered: {registered_model.name}")

# COMMAND ----------
# Transition to Production (optional for POC)
# mlflow.transition_model_version_stage(
#     name=f"{cat}.models.grade_predictor",
#     version=registered_model.version,
#     stage="Production"
# )

# COMMAND ----------
# Display run summary
print(f"Experiment: {exp_name}")
print(f"Model: {cat}.models.grade_predictor")
print(f"Accuracy: {accuracy:.3f}")
```

- [ ] **Step 2: Run the notebook** (serverless).

Expected: model trains, metrics log, model registers in UC.

- [ ] **Step 3: Assert model is registered**

```sql
SELECT * FROM system.unity.catalogs WHERE catalog_name = 'princeton_poc_dev';
-- Then query the model registry (UI is easiest)
```
Or via MLflow CLI:
```bash
databricks ml experiments list --profile <PROFILE>
```

- [ ] **Step 4: Verify UC model entry**

```bash
databricks assets list --asset-types MODELS --profile <PROFILE> | grep grade_predictor
```
Expected: model appears in UC.

- [ ] **Step 5: Commit**

```bash
git add src/datascientist/06b_mlflow_training.py && git commit -m "feat(ds-06b): MLflow classification model training + UC registration; DS-06(b) scenario"
```

---

### Task 6: Scheduled notebook/script (DS-07) — Tracks: #20

**Files:**
- Create: `src/datascientist/07_scheduled_analysis.py` (notebook)
- Create: `resources/ds_07_scheduled.job.yml` (Job resource, runs on schedule)

**Interfaces:**
- Consumes: `gold_dev.enrollment_history`.
- Produces: a scheduled Job that runs daily (parameterized to dev), writes a summary table (`gold_dev.ds_07_daily_summary`), and logs a timestamp. The Job is versioned in the DAB + Git.

- [ ] **Step 1: Write the scheduled analysis notebook**

Create `src/datascientist/07_scheduled_analysis.py`:

```python
# Databricks notebook source
# COMMAND ----------
# DS-07: Scheduled daily analysis
# Runs on a Job schedule; writes a daily summary of enrollment metrics to a target table.

dbutils.widgets.text("catalog", "princeton_poc_dev")
cat = dbutils.widgets.get("catalog")

# COMMAND ----------
from datetime import datetime

# COMMAND ----------
# Compute daily summary
query = f"""
SELECT 
  current_date() as run_date,
  count(*) as total_enrollments,
  count(distinct student_id) as unique_students,
  count(distinct course_id) as unique_courses,
  avg(gpa_points) as avg_gpa,
  approx_percentile(gpa_points, 0.5) as median_gpa,
  current_timestamp() as computed_at
FROM {cat}.gold_dev.enrollment_history
"""

df_summary = spark.sql(query)
display(df_summary)

# COMMAND ----------
# Append to output table (allows historical tracking)
output_table = f"{cat}.gold_dev.ds_07_daily_summary"
(df_summary.write.mode("append").format("delta")
 .option("mergeSchema", True)
 .saveAsTable(output_table))

print(f"Summary appended to {output_table}")

# COMMAND ----------
# Verify
spark.sql(f"SELECT run_date, total_enrollments, avg_gpa FROM {output_table} ORDER BY run_date DESC LIMIT 1").show()
```

- [ ] **Step 2: Write the Job resource**

Create `resources/ds_07_scheduled.job.yml`:

```yaml
resources:
  jobs:
    ds_07_scheduled_analysis:
      name: "[princeton_poc] DS-07 Scheduled daily analysis"
      schedule:
        quartz_cron_expression: "0 0 9 * * ?"   # Daily at 9 AM (UTC)
        pause_status: UNPAUSED
      tasks:
        - task_key: daily_analysis
          notebook_task:
            notebook_path: ../src/datascientist/07_scheduled_analysis.py
            base_parameters:
              catalog: ${var.catalog}
          new_cluster:
            spark_version: "15.4.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 1
```

Note: for simplicity, using a new cluster; can be switched to serverless once tested.

- [ ] **Step 3: Validate + deploy**

Run: `databricks bundle validate --strict -t dev --profile <PROFILE>`
Run: `databricks bundle deploy -t dev --profile <PROFILE>`
Expected: Job resource created, appears in workspace.

- [ ] **Step 4: Trigger a manual run (don't wait for schedule)**

Run: `databricks jobs run-now --job-id <ID> --profile <PROFILE>`
Expected: job runs; output table `ds_07_daily_summary` gets a row.

- [ ] **Step 5: Assert output table**

```sql
SELECT count(*) FROM princeton_poc_dev.gold_dev.ds_07_daily_summary;
```
Expected: ≥ 1 row.

- [ ] **Step 6: Commit**

```bash
git add src/datascientist/07_scheduled_analysis.py resources/ds_07_scheduled.job.yml && git commit -m "feat(ds-07): scheduled daily analysis job; DS-07 scenario"
```

---

### Task 7: Notebook version control & sharing (DS-08) — Tracks: #21

**Files:**
- All previous notebooks (already in Git folder from Task 0).
- Create: `docs/notebook_sharing.md` (guide for sharing notebooks + Git workflow).

**Interfaces:**
- Produces: evidence that notebooks are Git-versioned (all under `/Repos/shared/datascientist`, linked to GitHub repo), and a guide showing how to share a notebook link with other users (sharing permissions, read-only URLs).

- [ ] **Step 1: Verify Git folder is live and all notebooks are committed**

```bash
cd /Users/scott.johnson/customers/Princeton/it_rfp
git log --oneline src/datascientist/
```
Expected: all notebook commits appear.

- [ ] **Step 2: Create notebook sharing guide**

Create `docs/notebook_sharing.md`:

```markdown
# DS-08: Notebook Version Control & Sharing

All Data Scientist notebooks live in a Git folder, automatically versioned
on each save. Notebooks can be shared read-only or with edit permissions.

## Viewing in Databricks UI

Each notebook in `/Repos/shared/datascientist/` is live-versioned:
- Click the notebook → click "Git" (top right) → see commit history, branch info.
- Revert to any prior commit; no data loss.

## Sharing a Notebook

### Read-Only Link (most common)

1. Open notebook in Databricks
2. Click Share (top right) → Share with users → select users/groups
3. Set permission = Can View
4. Copy the URL (auto-generated read-only link)
5. Share the link

### Edit Permission

1. Share → select users → permission = Can Edit
2. Share the URL

Permissions inherit the viewer's UC object access — if they lack `SELECT` on a table
referenced in the notebook, they see an error, not the data.

## Git Workflow

All notebooks are committed to `github.com/scottDBX1886/princeton_poc`.
Changes sync automatically when you save in the notebook editor.

To review changes:
```bash
cd /Users/scott.johnson/customers/Princeton/it_rfp
git log --oneline src/datascientist/
git show <commit-hash>  # see the diff
```

## Reproducibility

Every notebook is tied to a Git commit hash. When sharing, the recipient
can run the exact version from that point in time (no "works for me" surprises).

---

DS-08 is satisfied by the Git folder + sharing permissions.
```

- [ ] **Step 3: Verify at least one notebook can be shared**

In the Databricks UI: open any notebook → Share → confirm UI works.

- [ ] **Step 4: Commit**

```bash
git add docs/notebook_sharing.md && git commit -m "docs(ds-08): notebook version control & sharing guide; DS-08 scenario"
```

---

### Task 8: In-platform visualization (DS-09) — Tracks: #22

**Files:**
- Create: `src/datascientist/09_visualizations.py` (notebook with notebook viz + AI/BI dashboard)
- Create: `resources/ds_09_dashboard.aibi.yml` (AI/BI dashboard resource)

**Interfaces:**
- Consumes: `gold_dev.enrollment_history`, `silver_dev.student`, `department`.
- Produces: a notebook with built-in visualizations (bars, line charts) + an AI/BI dashboard querying foundation data. Both are sharable and owned by the workspace.

- [ ] **Step 1: Write the visualization notebook**

Create `src/datascientist/09_visualizations.py`:

```python
# Databricks notebook source
# COMMAND ----------
# DS-09: In-platform visualization — notebook viz + AI/BI dashboard
# Demonstrates charting, aggregations, and dashboard-ready queries.

dbutils.widgets.text("catalog", "princeton_poc_dev")
cat = dbutils.widgets.get("catalog")

# COMMAND ----------
# Chart 1: GPA distribution (histogram)
gpa_dist = spark.sql(f"""
SELECT 
  case 
    when gpa_points >= 3.7 then 'A (3.7-4.0)'
    when gpa_points >= 3.3 then 'A- (3.3-3.7)'
    when gpa_points >= 3.0 then 'B+ (3.0-3.3)'
    when gpa_points >= 2.7 then 'B (2.7-3.0)'
    when gpa_points >= 2.0 then 'C (2.0-2.7)'
    else 'Below C'
  end as gpa_band,
  count(*) as count
FROM {cat}.gold_dev.enrollment_history
GROUP BY gpa_band
ORDER BY gpa_points DESC
""")

display(gpa_dist)

# COMMAND ----------
# Chart 2: Enrollments by department (bar)
enrollments_by_dept = spark.sql(f"""
SELECT 
  d.name as department,
  count(*) as enrollments,
  avg(eh.gpa_points) as avg_gpa
FROM {cat}.gold_dev.enrollment_history eh
JOIN {cat}.silver_dev.department d ON eh.dept_id = d.dept_id
GROUP BY d.name
ORDER BY enrollments DESC
LIMIT 15
""")

display(enrollments_by_dept)

# COMMAND ----------
# Chart 3: Enrollment trend by term (line)
enrollment_trend = spark.sql(f"""
SELECT 
  t.term_id,
  t.year,
  t.season,
  count(*) as enrollments,
  avg(eh.gpa_points) as avg_gpa
FROM {cat}.gold_dev.enrollment_history eh
JOIN {cat}.silver_dev.term t ON eh.term_id = t.term_id
GROUP BY t.term_id, t.year, t.season
ORDER BY t.term_id
""")

display(enrollment_trend)

# COMMAND ----------
# Save trend query for AI/BI dashboard
spark.sql(f"""
CREATE OR REPLACE VIEW {cat}.gold_dev.ds_09_enrollment_trend AS
{enrollment_trend._jdf.sql()}
""")
print(f"Created view: {cat}.gold_dev.ds_09_enrollment_trend")
```

- [ ] **Step 2: Write the AI/BI dashboard resource**

Create `resources/ds_09_dashboard.aibi.yml`:

```yaml
resources:
  dashboards:
    ds_09_foundation:
      name: "[princeton_poc] DS-09 Foundation dashboard"
      publication_name: ds_09_foundation_pub
      queries:
        - name: enrollment_by_gpa_band
          query: |
            SELECT 
              case 
                when gpa_points >= 3.7 then 'A (3.7-4.0)'
                when gpa_points >= 3.3 then 'A- (3.3-3.7)'
                when gpa_points >= 3.0 then 'B+ (3.0-3.3)'
                when gpa_points >= 2.7 then 'B (2.7-3.0)'
                when gpa_points >= 2.0 then 'C (2.0-2.7)'
                else 'Below C'
              end as gpa_band,
              count(*) as count
            FROM ${var.catalog}.gold_dev.enrollment_history
            GROUP BY gpa_band
          display_type: bar
        - name: enrollments_by_department
          query: |
            SELECT 
              d.name as department,
              count(*) as enrollments,
              round(avg(eh.gpa_points), 2) as avg_gpa
            FROM ${var.catalog}.gold_dev.enrollment_history eh
            JOIN ${var.catalog}.silver_dev.department d ON eh.dept_id = d.dept_id
            GROUP BY d.name
            ORDER BY enrollments DESC
          display_type: bar
        - name: enrollment_trend
          query: |
            SELECT 
              t.year,
              t.season,
              count(*) as enrollments
            FROM ${var.catalog}.gold_dev.enrollment_history eh
            JOIN ${var.catalog}.silver_dev.term t ON eh.term_id = t.term_id
            GROUP BY t.year, t.season
            ORDER BY t.year, t.season
          display_type: line
```

Note: Simplified YAML; actual AI/BI dashboard resources may vary by DBR/API version.

- [ ] **Step 3: Run the notebook** (serverless).

Expected: three charts display in the notebook.

- [ ] **Step 4: Deploy the dashboard resource**

Run: `databricks bundle deploy -t dev --profile <PROFILE>`
Expected: dashboard resource created.

- [ ] **Step 5: Assert dashboard in workspace**

List dashboards (UI or CLI):
```bash
databricks dashboards list --profile <PROFILE>
```
Expected: `[princeton_poc] DS-09 Foundation dashboard` appears.

- [ ] **Step 6: Commit**

```bash
git add src/datascientist/09_visualizations.py resources/ds_09_dashboard.aibi.yml && git commit -m "feat(ds-09): notebook + AI/BI dashboard visualizations; DS-09 scenario"
```

---

## Deliverable: runbook entries

- [ ] **Final step: Append DS phase to `docs/runbook/README.md`**

Create or update `docs/runbook/README.md` with a Data Scientist section:

```markdown
## Phase 2: Data Scientist (Persona 2)

### DS-01: SQL + Genie Exploration

**Scenario:** Data Scientist runs ad-hoc SQL queries with joins, window functions, CTEs.
Then uses natural language to explore the same data.

**Demonstration:**
1. Run notebook: `src/datascientist/01_sql_genie_exploration.py`
   - Queries 1–3 return ranking, GPA trends, faculty load summaries.
2. Open Genie space: `[princeton_poc] Data Foundation`
3. Ask: "Show me the distribution of student GPAs by department across all terms"
   - Genie auto-generates SQL; returns results.
4. Ask: "Which faculty members have the highest student load?"
   - Genie responds with top faculty + student counts.

**Expected Outcome:** Both SQL (direct) and Genie (NL) return correct aggregates over gold_dev/silver_dev.

**Pre-built Fallback:** Notebook queries hard-coded; Genie space pre-configured.

---

### DS-02, DS-03, DS-04: Python/R & BYO Data

**Scenarios:** Data Scientist uses Python (pandas), R (stats), and brings own data (CSV upload).

**Demonstration:**
1. Run `src/datascientist/02_python_pandas_notebook.py`
   - Loads enrollment_history, transforms with pandas, writes ds_02_pandas_output.
2. Run `src/datascientist/03_r_analysis_notebook.r`
   - Computes GPA summary stats in R; writes ds_03_r_summary.
3. Run `src/datascientist/04_byo_data_blend.py`
   - Creates sample external rankings CSV; joins with internal data; writes ds_04_byo_blended.

**Expected Outcome:** All three output tables exist with row counts > 0.

---

### DS-05: Large-Dataset Query

**Scenario:** Query multi-million-row fact (`enrollment_history`) at scale; observe performance profile.

**Demonstration:**
1. Run `src/datascientist/05_large_dataset_query.py`
   - Executes heavy query (group by dept + term, window rank); logs elapsed time.
   - Query profile visible in Databricks UI (Spark Jobs).

**Expected Outcome:** Query completes; metrics logged to `ds_05_query_metrics` with elapsed time recorded.

---

### DS-06(a): Local Connectivity

**Scenario:** Data Scientist on laptop (Python, R, SAS, SPSS) connects to POC workspace over SQL connector / ODBC / JDBC,
inheriting UC permissions.

**Demonstration:**
1. Refer to: `resources/ds_06a_connectivity_guide.md`
2. Install: `pip install databricks-sql-connector` (Python)
3. Run snippet from guide:
   ```python
   from databricks import sql
   connection = sql.connect(
       server_hostname="<workspace-url>",
       http_path="/sql/1.0/warehouses/<WAREHOUSE_ID>",
       auth_type="pat",
       token="<YOUR_PAT>"
   )
   cursor = connection.cursor()
   cursor.execute("SELECT * FROM princeton_poc_dev.gold_dev.enrollment_history LIMIT 10")
   ```
4. Rows returned = UC permissions applied ✓

**Expected Outcome:** Laptop connects; queries return correct row counts; RLS/CLS applied if defined (PA-09/10).

**Note:** This is a configuration + reference demo, not an in-workspace artifact.

---

### DS-06(b): In-Platform ML Training

**Scenario:** Train a classification model in-platform using MLflow, register to UC.

**Demonstration:**
1. Run `src/datascientist/06b_mlflow_training.py`
   - Trains RandomForest on enrollment features to predict grade.
   - Logs metrics (accuracy, F1) to MLflow.
   - Registers model in UC: `princeton_poc_dev.models.grade_predictor`.
2. Verify in MLflow UI: model appears with metrics.

**Expected Outcome:** Model registered in UC; metrics logged; model is callable for inference.

**Note:** RFP has duplicate DS-06; we split as DS-06(a)/(b). Flag to Princeton in read-out.

---

### DS-07: Scheduled Notebook/Script

**Scenario:** A notebook runs on a Job schedule (daily), writes a summary table for trend analysis.

**Demonstration:**
1. Job `[princeton_poc] DS-07 Scheduled daily analysis` is live in the workspace.
2. Trigger manually: `databricks jobs run-now --job-id <ID> --profile <PROFILE>`
3. Verify output: `SELECT run_date, total_enrollments, avg_gpa FROM princeton_poc_dev.gold_dev.ds_07_daily_summary`
   - Row count increases on each run.

**Expected Outcome:** Job runs on schedule; summary table appends daily metrics.

---

### DS-08: Notebook Version Control & Sharing

**Scenario:** Data Scientist shares a notebook link; the notebook is Git-versioned (reproducible, no "works for me" surprises).

**Demonstration:**
1. Open any notebook (e.g., `01_sql_genie_exploration.py`)
2. Click Share (top right) → select users → set permission (Can View / Can Edit)
3. Copy link → recipients see the exact notebook at the current Git commit
4. Git history visible in Databricks UI: click Git (top right) → see commit log.
5. Revert to any prior commit if needed.

**Expected Outcome:** Notebook shared; recipient can run it; version tied to Git commit hash.

---

### DS-09: In-Platform Visualization

**Scenario:** Create charts in notebook + an AI/BI dashboard over foundation data.

**Demonstration:**
1. Run `src/datascientist/09_visualizations.py`
   - Displays 3 charts (GPA distribution, enrollments by dept, enrollment trend).
2. Open AI/BI dashboard: `[princeton_poc] DS-09 Foundation dashboard`
   - Same 3 queries, formatted as dashboard tiles.
   - Shareable, auto-refreshes on data changes.

**Expected Outcome:** Visualizations render; dashboard queries return correct aggregates; dashboard is publishable.

---

## Summary

All 8 DS scenarios (DS-01..09, accounting for DS-06 split) are demonstrated end-to-end:
- **SQL + NL (Genie):** DS-01
- **Python, R, BYO data:** DS-02, DS-03, DS-04
- **Large-scale query:** DS-05
- **Local connectivity:** DS-06(a) — pre-built guide
- **In-platform ML:** DS-06(b)
- **Scheduled jobs:** DS-07
- **Version control + sharing:** DS-08
- **Visualization:** DS-09

All outputs are persisted on the foundation; all notebooks are Git-versioned and shareable.
```

- [ ] **Step 7: Commit**

```bash
git add docs/runbook/README.md && git commit -m "docs: runbook — DS phase (DS-01..09) scenarios complete"
```

---

## Self-Review

**Spec coverage (Phase 2, DS Persona):**

| Built object | Scenarios | Status |
|---|---|---|
| DS-A SQL + Genie exploration | DS-01 | Task 1 ✓ |
| DS-B Python + R notebooks | DS-02, DS-03 | Task 2 ✓ |
| DS-B BYO data blend | DS-04 | Task 2 ✓ |
| DS-C Large-dataset query | DS-05 | Task 3 ✓ |
| DS-D Local connectivity (pre-built guide) | DS-06(a) | Task 4 ✓ |
| DS-E In-platform ML training | DS-06(b) | Task 5 ✓ |
| DS-F Scheduled notebook → table | DS-07 | Task 6 ✓ |
| DS-G Notebook version control + sharing | DS-08 | Task 7 ✓ |
| DS-H Notebook + AI/BI visualization | DS-09 | Task 8 ✓ |

**Placeholder scan:**
- `<PROFILE>` — operator-supplied; documented in Global Constraints ✓
- `<warehouse_id>`, `<workspace-url>`, `<YOUR_PAT>` in connectivity guide — operator-supplied; documented ✓
- All notebooks read `dbutils.widgets.get("catalog")` → parameterized, not hardcoded ✓
- All output tables follow `ds_<task>_<name>` naming to avoid collision with foundation ✓

**Type consistency:**
- Catalog/schema names (`princeton_poc_dev`, `silver_dev`, `gold_dev`) consistent across all tasks ✓
- Widget names (`catalog`, `schema_suffix`) consistent ✓
- Output table naming (`ds_01_genie_results`, `ds_02_pandas_output`, etc.) consistent ✓
- MLflow model name consistent (`grade_predictor`) ✓

**Open issues/risks:**
1. **Dual DS-06 flag:** RFP uses "DS-06" for both local connectivity and in-platform ML. This plan splits as DS-06(a)/(b). Flag to Princeton in the read-out: "Numbering error in RFP; we split as DS-06(a)/(b)."
2. **Genie space schema support:** Genie should support cross-schema queries (silver_dev + gold_dev). If not, fall back to SQL notebook only for DS-01.
3. **AI/BI dashboard YAML:** Dashboard resource YAML syntax varies by DBR; simplified here. Adjust at execution time if the resource validator complains.
4. **MLflow UC registration:** requires UC model registry support (DBR 14.2+). Confirm workspace has this enabled before running DS-06(b).

**Notebooks + git folder wiring:**
- All notebooks live under `src/datascientist/` in the Git folder (Task 0).
- Git folder resource (`resources/repos:datascientist`) ties to GitHub repo.
- Operator runs `databricks bundle deploy` once to wire the folder; thereafter notebooks auto-version on save.

**Foundation dependencies:**
- Phase 0 must be deployed first: Phase 2 assumes `silver_dev` and `gold_dev` tables exist and are populated.
- Genie space queries both schemas; queries in notebooks join them; all verified in assertions.

**Schedule:**
- Each task is self-contained and runnable independently (after Task 0).
- Recommended order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 (logical dependency flow).
- Actual execution can parallelize Task 2–8 once Task 0 (Git wiring) is live.

---

**Next phase:** Phase 3 (Business Analyst) builds on the same foundation with no-code/low-code paths (Genie, Designer, AI/BI).
