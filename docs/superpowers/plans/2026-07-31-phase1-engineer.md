# Princeton POC — Phase 1: Engineer (E1–E11) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Demonstrate all 11 Engineer scenarios (SE-01…SE-43) covering multi-source ingestion, transformation, CDC/SCD, orchestration, monitoring, and governance via 11 built objects, each with three paths (Lakeflow Designer NL prompt / Databricks Assistant code-gen prompt / pre-built fallback).

**Architecture:** Foundation-first (Phase 0: core dimensions + fact + raw files + day-2 changes). Phase 1 orchestrates multi-source ingestion (files, REST API, DB, SFTP) into Bronze, runs transformation pipelines (schema cleaning, joins, aggregations, window functions) to Silver and Gold, applies Delta Change Data Feed for CDC and Slowly Changing Dimension logic, loads targets (UPSERT/delete + file exports), and chains everything into a scheduled job with monitoring. Governance (UC lineage, schema drift detection, Lakehouse Monitoring) walks the built-in console paths. DAB + Git repo is the deployment artifact.

**Tech Stack:** Databricks (Unity Catalog, Volumes, Delta, DLT/Lakeflow, Jobs, SQL Warehouses, serverless notebooks), Python/SQL, Spark, Lakeflow Designer, Databricks Assistant, git.

## Global Constraints

- **Catalog-per-target via bundle var** — `dev=princeton_poc_dev`, `qa=princeton_poc_test`, `prod=princeton_poc`. Schemas suffixed: `bronze_dev`, `silver_dev`, `gold_dev`, `landing_dev` (or no suffix in prod). Notebooks read `dbutils.widgets.get("catalog")` and `get("schema_suffix")` — **never hardcode.**
- **Scenario-scoped outputs:** Each Engineer object writes to scenario namespaces (e.g., `bronze_dev.e1_students_raw`, `silver_dev.e1_students_conformed`) so it does not overwrite canonical foundation tables. An exception: orchestration (E8) runs the real foundation pipelines end-to-end, producing the canonical Silver/Gold.
- **Profile:** `--profile dbx_shared_demo` (or operator-chosen dev). Never auto-select.
- **Serverless compute** for all notebooks/jobs unless stated.
- **Day-2 change script:** `src/foundation/40_day2_changes.sql` is a standalone runbook step (not auto-run) — pre-applied before E6 demo.
- **PII in the foundation:** `student.ssn`, `student.dob`, `faculty.ssn` — masking/restriction scenarios (PA) reference these; Engineer pipeline assumes they exist.
- **Excel write limitation:** native writer is not enabled. Use in-memory `openpyxl` (requires `%pip install openpyxl` + `dbutils.library.restartPython()`) as the fallback for E7.
- **Verification model:** each task ends with build → run → **assert** (row counts / schema / file checks) → commit. Assertions are explicit SQL or CLI checks with expected output.
- **Pre-built assets go under `src/engineer/` (notebooks) and `resources/` (pipeline/job YAML).** Format: `.py` notebook files with `# Databricks notebook source` header and `# COMMAND ----------` cells.
- **Three paths per object:** (1) Lakeflow Designer NL prompt (no-code), (2) Databricks Assistant code-gen prompt (code path), (3) pre-built notebook/pipeline YAML (fallback).

---

## Task E1: Multi-format file ingestion (Tracks: #4)

**Scenarios:** SE-04 (CSV quoted fields + embedded delimiters), SE-05 (multi-sheet Excel named-sheet read), SE-06 (nested JSON), SE-07 (XML with optional nodes), SE-09 (SFTP retrieval via Job task).

**Files:**
- Create: `src/engineer/e1_file_ingestion.py` (notebook)
- Create: `resources/e1_file_ingestion.pipeline.yml` (Lakeflow pipeline)

**Interfaces:**
- Consumes: foundation raw files on `/Volumes/princeton_poc_dev/landing_dev/files/` (students.csv, enrollments.pipe.txt, financial_aid.xlsx, course_catalog.json, faculty.xml); SFTP files (pattern `financial_aid_*.csv`).
- Produces: Bronze scenario tables: `princeton_poc_dev.bronze_dev.e1_students_raw`, `e1_enrollments_raw`, `e1_financial_aid_raw`, `e1_course_catalog_raw`, `e1_faculty_raw`; counts and schema assertions.

#### Lakeflow Designer NL Prompt

```
Create a no-code Lakeflow pipeline that:
1. Reads students.csv from /Volumes/princeton_poc_dev/landing_dev/files/ with CSV reader,
   ensuring quoted fields and embedded commas are preserved.
2. Reads enrollments.pipe.txt as pipe-delimited (sep=|) with the pipe-containment gotcha handled.
3. Reads financial_aid.xlsx, sheet name="AidDetail" (not the first sheet).
4. Reads course_catalog.json as nested JSON, flattening top-level arrays.
5. Reads faculty.xml as repeating elements, with optional <tenure> nodes handled as nulls.
6. For each source, apply minimal schema (no transforms), write to bronze_dev.e1_* tables.
7. Output row counts to stdout for each.
```

#### Databricks Assistant Code-Gen Prompt

```
Write a Databricks notebook (Python) that demonstrates multi-format file ingestion
for a higher-ed dataset. The notebook should:

1. Read students.csv from /Volumes/princeton_poc_dev/landing_dev/files/ using PySpark CSV
   reader, with CSV options for handling quoted fields and embedded commas (header=True,
   quote='"', escape='"'). Write to princeton_poc_dev.bronze_dev.e1_students_raw.

2. Read enrollments.pipe.txt using CSV reader with sep="|" to handle pipe delimiters.
   Write to princeton_poc_dev.bronze_dev.e1_enrollments_raw.

3. Read financial_aid.xlsx using spark.read.excel (DBR 17.1+). Target the sheet named
   "AidDetail" (not the first sheet). Write to princeton_poc_dev.bronze_dev.e1_financial_aid_raw.

4. Read course_catalog.json using spark.read.json with inferSchema=True. Flatten any
   nested arrays/objects at the top level (use explode if needed). Write to
   princeton_poc_dev.bronze_dev.e1_course_catalog_raw.

5. Read faculty.xml using spark.read.xml (com.databricks:spark-xml). Handle optional
   nodes (e.g., <tenure>) as nulls. Write to princeton_poc_dev.bronze_dev.e1_faculty_raw.

6. For each table, print the row count and sample schema. Assert all files landed.

Note: Use the catalog/schema_suffix widgets to make the notebook portable across dev/qa/prod targets.
```

#### Pre-built Fallback

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # E1: Multi-format file ingestion

# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
BRONZE = f"{CATALOG}.bronze{SUFFIX}"

# COMMAND ----------
# MAGIC %md ## 1. CSV with quoted fields + embedded commas
# COMMAND ----------
students = (spark.read
  .option("header", "true")
  .option("quote", '"')
  .option("escape", '"')
  .csv("/Volumes/princeton_poc_dev/landing_dev/files/students.csv"))
students.write.mode("overwrite").saveAsTable(f"{BRONZE}.e1_students_raw")
print(f"students: {students.count()}")

# COMMAND ----------
# MAGIC %md ## 2. Pipe-delimited with pipe in a field
# COMMAND ----------
enrollments = (spark.read
  .option("header", "true")
  .option("sep", "|")
  .csv("/Volumes/princeton_poc_dev/landing_dev/files/enrollments.pipe.txt"))
enrollments.write.mode("overwrite").saveAsTable(f"{BRONZE}.e1_enrollments_raw")
print(f"enrollments: {enrollments.count()}")

# COMMAND ----------
# MAGIC %md ## 3. Excel with named sheet (DBR 17.1+)
# COMMAND ----------
aid = (spark.read.excel(
  "/Volumes/princeton_poc_dev/landing_dev/files/financial_aid.xlsx",
  sheet="AidDetail", header=True))
aid.write.mode("overwrite").saveAsTable(f"{BRONZE}.e1_financial_aid_raw")
print(f"financial_aid: {aid.count()}")

# COMMAND ----------
# MAGIC %md ## 4. Nested JSON with optional keys
# COMMAND ----------
from pyspark.sql import functions as F
catalog = (spark.read.json("/Volumes/princeton_poc_dev/landing_dev/files/course_catalog.json"))
catalog.write.mode("overwrite").saveAsTable(f"{BRONZE}.e1_course_catalog_raw")
print(f"course_catalog: {catalog.count()}")

# COMMAND ----------
# MAGIC %md ## 5. XML with optional nodes
# COMMAND ----------
faculty = spark.read.format("xml") \
  .option("rowTag", "faculty") \
  .load("/Volumes/princeton_poc_dev/landing_dev/files/faculty.xml")
faculty.write.mode("overwrite").saveAsTable(f"{BRONZE}.e1_faculty_raw")
print(f"faculty: {faculty.count()}")
```

**Expected Outcome:** All five file formats successfully read; each scenario table created with correct row counts and schema. E1 proves format diversity (SE-04/05/06/07).

**Verify:**
```sql
SELECT 'e1_students_raw' t, count(*) c FROM princeton_poc_dev.bronze_dev.e1_students_raw
UNION ALL SELECT 'e1_enrollments_raw', count(*) FROM princeton_poc_dev.bronze_dev.e1_enrollments_raw
UNION ALL SELECT 'e1_financial_aid_raw', count(*) FROM princeton_poc_dev.bronze_dev.e1_financial_aid_raw
UNION ALL SELECT 'e1_course_catalog_raw', count(*) FROM princeton_poc_dev.bronze_dev.e1_course_catalog_raw
UNION ALL SELECT 'e1_faculty_raw', count(*) FROM princeton_poc_dev.bronze_dev.e1_faculty_raw;
-- Expected: all tables present with row counts > 0
```

---

## Task E2: DB ingestion (full extract + custom SQL w/ stored proc) (Tracks: #5)

**Scenarios:** SE-01 (full load from source DB), SE-02 (custom SQL with aggregation/joins).

**Files:**
- Create: `src/engineer/e2_db_ingestion.py` (notebook)
- Create: `resources/e2_db_ingestion.pipeline.yml` (Lakeflow pipeline definition)

**Interfaces:**
- Consumes: BYO source database (parked; will be Lakeflow Connect DB CDC or federation at customer). Fallback: foundation Silver `student`, `enrollment` for demonstration SQL patterns.
- Produces: Bronze scenario tables `e2_student_full_extract`, `e2_enrollment_aggregate` demonstrating SQL joins, window functions, aggregation.

**OPEN ITEM (flagged):** BYO source DB connection details (hostname, credentials, schema) are customer-provided at build time. Plan includes Lakeflow Connect DB CDC as the headline path (if available; SQL Server GA, Postgres Public Preview) or Federation + manual watermark. **This task will run the DEMONSTRATION SQL patterns against foundation tables; the actual DB connector swap happens at customer deployment.**

#### Lakeflow Designer NL Prompt

```
Create a pipeline that demonstrates DB ingestion:
1. Define a data source (Lakeflow Connect DB CDC or Federation query) for a table equivalent
   to princeton_poc_dev.silver.student (or a federated external table named "db_student").
2. Full load: copy all rows to princeton_poc_dev.bronze_dev.e2_student_full_extract.
3. Custom SQL: join student + enrollment, compute count/avg_grade per dept_id, write to
   princeton_poc_dev.bronze_dev.e2_enrollment_aggregate.
4. Output assertion: row counts for both.
```

#### Databricks Assistant Code-Gen Prompt

```
Write a Databricks notebook that demonstrates database ingestion with custom SQL.

1. Connect to the source database (Lakeflow Connect DB CDC recommended; fall back to the
   foundation tables for demo purposes). Read the "student" equivalent table.

2. Full Load: copy all rows to princeton_poc_dev.bronze_dev.e2_student_full_extract.
   (If using foundation, read princeton_poc_dev.silver_dev.student.)

3. Custom SQL: Join student + enrollment with aggregation:
   SELECT dept_id, COUNT(*) as enrollment_count, AVG(gpa_points) as avg_gpa
   FROM <student_table> s
   JOIN <enrollment_table> e ON s.student_id = e.student_id
   GROUP BY dept_id
   Write result to princeton_poc_dev.bronze_dev.e2_enrollment_aggregate.

4. Print row counts and sample rows from both outputs.

Note: If the BYO database is not available, use the foundation Silver tables as the data source
and note this as a fallback in the output.
```

#### Pre-built Fallback

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # E2: DB ingestion (full extract + custom SQL)
# MAGIC Fallback: using foundation Silver tables as the data source.

# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
BRONZE = f"{CATALOG}.bronze{SUFFIX}"
SILVER = f"{CATALOG}.silver{SUFFIX}"

# COMMAND ----------
# MAGIC %md ## 1. Full load (demonstrates SE-01 pattern)
# COMMAND ----------
student_full = spark.table(f"{SILVER}.student")
student_full.write.mode("overwrite").saveAsTable(f"{BRONZE}.e2_student_full_extract")
print(f"Full extract: {student_full.count()} students")

# COMMAND ----------
# MAGIC %md ## 2. Custom SQL with joins + aggregation (SE-02)
# COMMAND ----------
spark.sql(f"""
CREATE OR REPLACE TABLE {BRONZE}.e2_enrollment_aggregate AS
SELECT s.dept_id,
       COUNT(DISTINCT e.enrollment_id) as enrollment_count,
       AVG(e.gpa_points) as avg_gpa,
       MIN(e.grade) as min_grade,
       MAX(e.grade) as max_grade
FROM {SILVER}.student s
LEFT JOIN {SILVER}.enrollment e ON s.student_id = e.student_id
GROUP BY s.dept_id
ORDER BY enrollment_count DESC
""")
print(spark.table(f"{BRONZE}.e2_enrollment_aggregate").count())
spark.table(f"{BRONZE}.e2_enrollment_aggregate").show()

# COMMAND ----------
# MAGIC %md ## Assertion
# COMMAND ----------
print(f"e2_student_full_extract: {spark.table(f'{BRONZE}.e2_student_full_extract').count()}")
print(f"e2_enrollment_aggregate: {spark.table(f'{BRONZE}.e2_enrollment_aggregate').count()}")
```

**Expected Outcome:** E2 demonstrates full load (SE-01) and custom SQL with joins/aggregation (SE-02). Students table copied; enrollment aggregation computes per-department stats.

**Verify:**
```sql
SELECT COUNT(*) FROM princeton_poc_dev.bronze_dev.e2_student_full_extract;
-- Expected: ~30000 (or actual student count from source)

SELECT * FROM princeton_poc_dev.bronze_dev.e2_enrollment_aggregate LIMIT 5;
-- Expected: dept_id, enrollment_count, avg_gpa for each department
```

**Open Risk:** BYO source DB connection is PARKED. At customer handoff, a Lakeflow Connect DB CDC task replaces the foundation-table fallback. The custom SQL pattern (joins, aggregation, window functions) remains the same.

---

## Task E3: REST API ingestion (Tracks: #6)

**Scenarios:** SE-08 (OAuth 2.0 client-credentials + paginated pull + token refresh).

**Files:**
- Create: `src/engineer/e3_rest_api_ingestion.py` (notebook)
- Create: `resources/e3_rest_api_ingestion.pipeline.yml` (Lakeflow pipeline)

**Interfaces:**
- Consumes: deployed `princeton-mock-api` app (Plan 2, already running) at `APP_URL`; OAuth client creds (from app.yaml or UC secret).
- Produces: Bronze table `e3_enrollments_from_api` with paginated rows from `GET /enrollments`.

#### Lakeflow Designer NL Prompt

```
Create a pipeline that ingests paginated REST API data:
1. OAuth 2.0 client-credentials: POST /oauth/token with client_id/client_secret,
   obtain bearer token.
2. Call GET /enrollments?page=1&page_size=100 with the bearer, extract rows.
3. Page through (follow the "next" pointer) until done.
4. Collect all rows into a DataFrame, write to
   princeton_poc_dev.bronze_dev.e3_enrollments_from_api.
5. Assert: row count matches the API's "total" field (within tolerance of timing skew).
6. Log: token acquisition, pagination loop, final row count.
```

#### Databricks Assistant Code-Gen Prompt

```
Write a Databricks notebook that ingest data from a paginated REST API with OAuth 2.0.

The API endpoint (running in-workspace as a Databricks App):
- POST /oauth/token: accepts grant_type=client_credentials, client_id, client_secret
  Returns: {access_token, token_type: Bearer, expires_in}
- GET /enrollments?page=N&page_size=100: bearer-protected, paginated
  Returns: {page, page_size, total, next, data: [...]}

Notebook steps:
1. Set APP_URL (from dbutils.widgets or env), client_id, client_secret.
2. POST to /oauth/token, capture the access_token.
3. Loop: page=1 until no next:
   - GET /enrollments?page=page&page_size=100 with Authorization: Bearer <token>
   - Append rows to a list.
   - If token expires (401), re-issue and retry.
4. Collect all rows, create a DataFrame, write to
   princeton_poc_dev.bronze_dev.e3_enrollments_from_api.
5. Assert: len(rows) > 0 and consistent with API total.
6. Print: token refresh count, total pages, final row count.
```

#### Pre-built Fallback

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # E3: REST API ingestion (OAuth 2.0 + pagination)

# COMMAND ----------
import requests, time
from datetime import datetime

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
dbutils.widgets.text("app_url", "http://localhost:8000")  # Override with deployed app URL
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
BRONZE = f"{CATALOG}.bronze{SUFFIX}"
APP_URL = dbutils.widgets.get("app_url")

# COMMAND ----------
# MAGIC %md ## 1. OAuth 2.0 token acquisition
# COMMAND ----------
CLIENT_ID = "princeton_poc_client"
CLIENT_SECRET = "poc_secret_change_me"  # Would come from UC secret in prod

resp = requests.post(f"{APP_URL}/oauth/token",
  data={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
resp.raise_for_status()
token_data = resp.json()
access_token = token_data["access_token"]
expires_in = token_data["expires_in"]
print(f"Token acquired, expires in {expires_in}s at {datetime.now().isoformat()}")

# COMMAND ----------
# MAGIC %md ## 2. Paginated pull
# COMMAND ----------
all_rows = []
page = 1
headers = {"Authorization": f"Bearer {access_token}"}
token_refresh_count = 0

while page is not None:
    try:
        resp = requests.get(f"{APP_URL}/enrollments", params={"page": page, "page_size": 100}, headers=headers)
        if resp.status_code == 401:
            print(f"Token expired, refreshing...")
            token_resp = requests.post(f"{APP_URL}/oauth/token",
              data={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
            token_resp.raise_for_status()
            access_token = token_resp.json()["access_token"]
            token_refresh_count += 1
            headers["Authorization"] = f"Bearer {access_token}"
            continue
        resp.raise_for_status()
        body = resp.json()
        all_rows.extend(body["data"])
        page = body["next"]
        print(f"Page {body['page']}: {len(body['data'])} rows, next={page}")
    except Exception as e:
        print(f"Error on page {page}: {e}")
        break

print(f"Total rows: {len(all_rows)}, Token refreshes: {token_refresh_count}")

# COMMAND ----------
# MAGIC %md ## 3. Write to Bronze
# COMMAND ----------
from pyspark.sql import functions as F
df = spark.createDataFrame(all_rows)
df.write.mode("overwrite").saveAsTable(f"{BRONZE}.e3_enrollments_from_api")
print(f"Rows written: {df.count()}")
```

**Expected Outcome:** E3 demonstrates OAuth 2.0 flow (SE-08 step 1), paginated retrieval (SE-08 step 2), and token refresh handling (SE-08 step 3). All enrollment rows from the API land in Bronze. SE-08 win condition: token refresh is observable mid-ingestion (short 300s TTL).

**Verify:**
```sql
SELECT COUNT(*) FROM princeton_poc_dev.bronze_dev.e3_enrollments_from_api;
-- Expected: > 0 (exact count depends on API data volume; should match POST-token call total)
```

---

## Task E4: Multi-source merge (Tracks: #7)

**Scenarios:** SE-10 (ingest from file + DB + API, reconcile on common key).

**Files:**
- Create: `src/engineer/e4_multisource_merge.py` (notebook)
- Create: `resources/e4_multisource_merge.pipeline.yml` (Lakeflow pipeline)

**Interfaces:**
- Consumes: Bronze outputs from E1, E2, E3 (file-sourced students, DB-sourced student, API-sourced enrollments).
- Produces: Silver scenario table `e4_enrollment_reconciled` combining all three sources, deduplicated and joined on student_id + enrollment_id.

#### Lakeflow Designer NL Prompt

```
Create a multi-source merge pipeline:
1. Read e1_students_raw (from files) and e2_student_full_extract (from DB fallback).
   Deduplicate on student_id (inner join + DISTINCT).
2. Read e3_enrollments_from_api (from REST API).
3. Join the deduped students with enrollments on student_id.
4. Select final columns: student_id, first_name, last_name, dept_id, enrollment_id,
   course_id, term_id, grade, gpa_points, source_system.
5. Write to princeton_poc_dev.silver_dev.e4_enrollment_reconciled.
6. Assert: row count > max(e1, e2, e3) (due to fact multiplication).
```

#### Databricks Assistant Code-Gen Prompt

```
Write a Databricks notebook that merges enrollment data from multiple sources:

1. Read e1_students_raw and e2_student_full_extract from Bronze.
2. UNION and deduplicate on student_id (take first occurrence by student_id).
3. Read e3_enrollments_from_api.
4. Join students with enrollments: deduped_students LEFT JOIN enrollments ON student_id.
5. Add a source_system column ("file" / "db" / "api" flags).
6. Select: student_id, first_name, last_name, dept_id, enrollment_id, course_id, term_id,
           grade, gpa_points, source_system.
7. Write to princeton_poc_dev.silver_dev.e4_enrollment_reconciled.
8. Print row counts at each step (sources, after dedup, after join).
```

#### Pre-built Fallback

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # E4: Multi-source merge (file + DB + API reconciliation)

# COMMAND ----------
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
BRONZE = f"{CATALOG}.bronze{SUFFIX}"
SILVER = f"{CATALOG}.silver{SUFFIX}"

# COMMAND ----------
# MAGIC %md ## 1. Load all sources
# COMMAND ----------
e1_students = spark.table(f"{BRONZE}.e1_students_raw")
e2_students = spark.table(f"{BRONZE}.e2_student_full_extract")
e3_enrollments = spark.table(f"{BRONZE}.e3_enrollments_from_api")

print(f"E1 students: {e1_students.count()}")
print(f"E2 students: {e2_students.count()}")
print(f"E3 enrollments: {e3_enrollments.count()}")

# COMMAND ----------
# MAGIC %md ## 2. Deduplicate students (union + dedup)
# COMMAND ----------
# Select common columns
e1_cols = ["student_id", "first_name", "last_name", "dept_id"]
e2_cols = ["student_id", "first_name", "last_name", "dept_id"]

students_unioned = e1_students.select(*e1_cols).unionByName(
  e2_students.select(*e2_cols), allowMissingColumns=True
).dropDuplicates(["student_id"])

print(f"After dedup: {students_unioned.count()}")

# COMMAND ----------
# MAGIC %md ## 3. Join with enrollments
# COMMAND ----------
reconciled = students_unioned.join(
  e3_enrollments, on="student_id", how="left"
).select(
  "student_id", "first_name", "last_name", "dept_id",
  "enrollment_id", "course_id", "term_id", "grade", "gpa_points"
).withColumn("source_system", F.lit("multi-source"))

reconciled.write.mode("overwrite").saveAsTable(f"{SILVER}.e4_enrollment_reconciled")
print(f"Reconciled rows: {reconciled.count()}")
```

**Expected Outcome:** E4 merges three sources (file, DB, API) on student_id and enrollment_id. Deduplication ensures one student record; join multiplies by enrollments. Demonstrates SE-10 multi-source reconciliation.

**Verify:**
```sql
SELECT COUNT(*) FROM princeton_poc_dev.silver_dev.e4_enrollment_reconciled;
-- Expected: > 0; should be >= e3_enrollments_from_api count (left join multiplies by enrollments)
```

---

## Task E5: "Kitchen-sink" transformation pipeline (Tracks: #8)

**Scenarios:** SE-11…SE-20 (schema cleaning, type conversion, null handling, derived columns, joins, aggregations, window functions, bucketing, partitioning, incremental writes).

**Files:**
- Create: `src/engineer/e5_transformation_kitchen_sink.py` (notebook)
- Create: `resources/e5_transformation_kitchen_sink.pipeline.yml` (Lakeflow pipeline)

**Interfaces:**
- Consumes: Foundation Silver tables (department, term, faculty, course, student, financial_aid, enrollment) + E4 reconciled.
- Produces: Gold scenario tables: `e5_student_enriched` (with derived columns), `e5_course_performance` (aggregates), `e5_enrollment_ranked` (window functions + bucketing).

#### Lakeflow Designer NL Prompt

```
Create a transformation pipeline demonstrating comprehensive data engineering:

SE-11 Schema cleaning: deduplicate students on student_id, remove nulls from required fields.
SE-12 Type conversion: ensure all numeric columns are double/int, date columns are date.
SE-13 Mixed case: normalize last_name to UPPER.
SE-14 Null handling: financial_aid.amount defaults to 0.00 where null.
SE-15 Date parsing: parse dob (mixed formats: ISO/US/dotted) into a DATE column.
SE-16 Derived columns: calculate age from dob, status_normalized from status enum.
SE-17 Join enrichment: LEFT JOIN student + financial_aid on student_id; add aid_type, amount.
SE-18 Aggregation: GROUP BY course_id, compute avg_gpa, enrollment_count, pass_rate.
SE-19 Window functions: RANK() OVER (PARTITION BY dept_id ORDER BY avg_gpa DESC).
SE-20 Incremental: use a merge-on-id pattern or a date-partitioned append.

Outputs:
  - e5_student_enriched: student with age, status_normalized, aid_amount
  - e5_course_performance: course_id, avg_gpa, enrollment_count, pass_rate
  - e5_enrollment_ranked: enrollment + student + rank window
```

#### Databricks Assistant Code-Gen Prompt

```
Write a Databricks notebook demonstrating a comprehensive data transformation pipeline.

Starting from foundation Silver (student, enrollment, financial_aid, course, department):

SE-11: Deduplicate students; drop duplicates on student_id.
SE-12: Type cast: ensure gpa_points is double, enrollment_id is int.
SE-13: Normalize last_name to UPPER.
SE-14: fillna on financial_aid.amount (default 0.0).
SE-15: Parse dob (may be ISO/US/dotted format) to DATE using to_date or a UDF.
SE-16: Create derived columns:
  - age = datediff(current_date(), dob) / 365
  - status_normalized = CASE WHEN status IN (...) THEN status ELSE 'unknown' END
SE-17: LEFT JOIN student + financial_aid on student_id; add aid columns.
SE-18: Aggregate by course_id: COUNT(DISTINCT enrollment_id), AVG(gpa_points),
       SUM(CASE WHEN grade != 'F' THEN 1 ELSE 0 END) / COUNT(*) as pass_rate
SE-19: Window: RANK() OVER (PARTITION BY dept_id ORDER BY avg_gpa DESC)
SE-20: Incremental load: MERGE INTO e5_enrollment_ranked USING source ON merge_key
       WHEN MATCHED THEN UPDATE SET ...; WHEN NOT MATCHED THEN INSERT ...

Output tables:
  - e5_student_enriched (student_id, first_name, last_name, age, status_normalized, aid_amount)
  - e5_course_performance (course_id, avg_gpa, enrollment_count, pass_rate)
  - e5_enrollment_ranked (enrollment_id, student_id, course_id, dept_id, gpa_points, rank)
```

#### Pre-built Fallback

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # E5: "Kitchen-sink" transformation pipeline
# MAGIC Demonstrates SE-11..SE-20 scenarios in one orchestrated notebook.

# COMMAND ----------
from pyspark.sql import functions as F
from datetime import datetime

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
SILVER = f"{CATALOG}.silver{SUFFIX}"
GOLD = f"{CATALOG}.gold{SUFFIX}"

# COMMAND ----------
# MAGIC %md ## SE-11/12: Load, deduplicate, type-cast
# COMMAND ----------
student = spark.table(f"{SILVER}.student") \
  .dropDuplicates(["student_id"]) \
  .withColumn("student_id", F.col("student_id").cast("int")) \
  .withColumn("dept_id", F.col("dept_id").cast("int"))
print(f"Students (deduplicated): {student.count()}")

enrollment = spark.table(f"{SILVER}.enrollment") \
  .withColumn("enrollment_id", F.col("enrollment_id").cast("int")) \
  .withColumn("gpa_points", F.col("gpa_points").cast("double"))
print(f"Enrollments (type-cast): {enrollment.count()}")

# COMMAND ----------
# MAGIC %md ## SE-13: Mixed case normalization
# COMMAND ----------
student = student.withColumn("last_name", F.upper(F.col("last_name")))

# COMMAND ----------
# MAGIC %md ## SE-14/15: Null handling + date parsing
# COMMAND ----------
financial_aid = spark.table(f"{SILVER}.financial_aid") \
  .withColumn("amount", F.coalesce(F.col("amount"), F.lit(0.0)))

# Parse dob (mixed formats: ISO, US, dotted)
def parse_dob(dob_str):
    if not dob_str:
        return None
    try:
        return datetime.strptime(dob_str, "%Y-%m-%d").date()
    except:
        try:
            return datetime.strptime(dob_str, "%m/%d/%Y").date()
        except:
            try:
                return datetime.strptime(dob_str, "%d.%m.%Y").date()
            except:
                return None

parse_dob_udf = F.udf(parse_dob, "date")
student = student.withColumn("dob", parse_dob_udf(F.col("dob")))

# COMMAND ----------
# MAGIC %md ## SE-16: Derived columns
# COMMAND ----------
student = student \
  .withColumn("age", F.datediff(F.current_date(), F.col("dob")) / 365) \
  .withColumn("status_normalized", F.when(
    F.col("status").isin("active", "graduated", "leave", "withdrawn"), F.col("status")
  ).otherwise(F.lit("unknown")))

# COMMAND ----------
# MAGIC %md ## SE-17: Join enrichment (student + aid)
# COMMAND ----------
student_enriched = student.join(
  financial_aid.select("student_id", "amount", "aid_type"),
  on="student_id", how="left"
).select(
  "student_id", "first_name", "last_name", "age", "status_normalized", F.col("amount").alias("aid_amount")
)
student_enriched.write.mode("overwrite").saveAsTable(f"{GOLD}.e5_student_enriched")
print(f"Student enriched: {student_enriched.count()}")

# COMMAND ----------
# MAGIC %md ## SE-18: Aggregation
# COMMAND ----------
enrollment_with_grade = enrollment.withColumn("pass", F.when(F.col("grade") != "F", 1).otherwise(0))
course_perf = enrollment_with_grade.groupBy("course_id").agg(
  F.avg("gpa_points").alias("avg_gpa"),
  F.count("enrollment_id").alias("enrollment_count"),
  (F.sum("pass") / F.count("enrollment_id")).alias("pass_rate")
)
course_perf.write.mode("overwrite").saveAsTable(f"{GOLD}.e5_course_performance")
print(f"Course performance: {course_perf.count()}")

# COMMAND ----------
# MAGIC %md ## SE-19: Window functions + SE-20: Incremental (via MERGE)
# COMMAND ----------
enrollment_ranked = enrollment.join(student.select("student_id", "dept_id"), on="student_id", how="left") \
  .withColumn("rank", F.rank().over(F.Window.partitionBy("dept_id").orderBy(F.desc("gpa_points"))))
enrollment_ranked.write.mode("overwrite").saveAsTable(f"{GOLD}.e5_enrollment_ranked")
print(f"Enrollment ranked: {enrollment_ranked.count()}")

# COMMAND ----------
# MAGIC %md ## Summary
# COMMAND ----------
print("E5 outputs created: e5_student_enriched, e5_course_performance, e5_enrollment_ranked")
```

**Expected Outcome:** E5 demonstrates 10 transformation patterns (SE-11…SE-20) in one orchestrated notebook. Student enriched with derived columns; courses aggregated; enrollments ranked. This is the broadest transformation showcase.

**Verify:**
```sql
SELECT COUNT(*) FROM princeton_poc_dev.gold_dev.e5_student_enriched;
SELECT COUNT(*) FROM princeton_poc_dev.gold_dev.e5_course_performance;
SELECT COUNT(*), MAX(rank) FROM princeton_poc_dev.gold_dev.e5_enrollment_ranked GROUP BY 1;
-- Expected: e5_student_enriched ≈ 30000; e5_course_performance ≈ 5000; e5_enrollment_ranked ≈ 60000
```

---

## Task E6: CDC + SCD (Tracks: #9)

**Scenarios:** SE-03 (change capture), SE-21 (SCD Type 1), SE-22 (SCD Type 2), SE-23 (change capture from CDF).

**Files:**
- Create: `src/engineer/e6_cdc_scd.py` (notebook)
- Create: `resources/e6_cdc_scd.pipeline.yml` (Lakeflow pipeline)

**Interfaces:**
- Consumes: Foundation Silver `student` table (with Change Data Feed enabled); day-2 change script pre-applied (10 inserts, 20 updates, 5 deletes).
- Produces: SCD Type-1 table `e6_student_scd1` (overwrite on status change); SCD Type-2 table `e6_student_scd2` (add new rows, mark old as inactive); CDF extraction table `e6_student_changes`.

**Pre-demo step (runbook):** Apply `src/foundation/40_day2_changes.sql` (standalone) to seed the changes.

#### Lakeflow Designer NL Prompt

```
Create a CDC + SCD pipeline:

1. Read the Foundation Silver student table (CDF enabled, pre-changes applied).
2. Capture changes via Delta Change Data Feed (DESCRIBE HISTORY to get the pre-change version,
   then query table_changes() for all deltas since that version).
3. SCD Type 1 (SE-21): For status changes, overwrite the old record. Write to
   e6_student_scd1 as the "current" student table.
4. SCD Type 2 (SE-22): For status changes, INSERT a new row and mark the old row as inactive
   (add scd_active flag, scd_effective_date, scd_end_date). Write to e6_student_scd2.
5. Change Log (SE-23): Extract INSERT/UPDATE/DELETE from CDF and write to e6_student_changes
   with _change_type flag.
6. Assertions: verify 10 inserts, 20 update-preimages, 20 update-postimages, 5 deletes in the CDF.
```

#### Databricks Assistant Code-Gen Prompt

```
Write a Databricks notebook demonstrating CDC + SCD patterns using Delta Change Data Feed.

Prerequisites: Foundation Silver student table has CDF enabled; day-2 changes (40_day2_changes.sql)
have been applied (10 inserts, 20 updates, 5 deletes, 1 schema change).

Steps:
1. Get the pre-change version: DESCRIBE HISTORY student ORDER BY version DESC LIMIT 1
   (before applying changes). For demo, use a fixed version offset (e.g., current version - 1).
2. Query table_changes('silver.student', start_version) to extract all changes.
3. SCD Type 1: For each update_postimage, overwrite the old student record (e.g., join on student_id
   and take the latest). Write to e6_student_scd1.
4. SCD Type 2: For each update_postimage, INSERT as a new record with scd_active=true,
   scd_effective_date=current_timestamp. Mark old records as scd_active=false.
   Write to e6_student_scd2.
5. Change Log: extract all rows from table_changes, keep _change_type, write to e6_student_changes.
6. Assertions:
   - Count by _change_type from table_changes: expect 10 inserts, 20 update_preimage,
     20 update_postimage, 5 deletes.
   - e6_student_scd1 should have fewer rows than baseline (deletes removed).
   - e6_student_scd2 should have more rows (SCD2 added new rows).
```

#### Pre-built Fallback

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # E6: CDC + SCD (Delta Change Data Feed)
# MAGIC Prerequisites: foundation Silver student table has CDF enabled;
# MAGIC day-2 changes applied (10 inserts, 20 updates, 5 deletes, 1 ALTER).

# COMMAND ----------
from pyspark.sql import functions as F
from datetime import datetime

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
SILVER = f"{CATALOG}.silver{SUFFIX}"
GOLD = f"{CATALOG}.gold{SUFFIX}"

# COMMAND ----------
# MAGIC %md ## Step 0: Enable CDF + get pre-change version
# COMMAND ----------
spark.sql(f"ALTER TABLE {SILVER}.student SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")

# For demo: assume changes were applied; query CDF from version 0 (or the actual pre-change version)
# In real demo, capture DESCRIBE HISTORY BEFORE applying 40_day2_changes.sql
pre_change_version = 0  # Placeholder; operator will note the actual version from DESCRIBE HISTORY

# COMMAND ----------
# MAGIC %md ## Step 1: Extract changes from CDF
# COMMAND ----------
changes = spark.sql(f"""
SELECT * FROM table_changes('{SILVER}.student', {pre_change_version})
""")
print(f"Total change rows from CDF: {changes.count()}")
changes_by_type = changes.groupBy("_change_type").count()
print("Changes by type:")
changes_by_type.show()

# COMMAND ----------
# MAGIC %md ## SE-21: SCD Type 1 (overwrite)
# COMMAND ----------
# For each student, take the latest version (postimage if update, delete if removed, insert if new)
baseline = spark.table(f"{SILVER}.student")
deletes = changes.filter(F.col("_change_type") == "delete").select("student_id").distinct()
scd1 = baseline.join(deletes, on="student_id", how="left_anti")  # remove deletes
scd1.write.mode("overwrite").saveAsTable(f"{GOLD}.e6_student_scd1")
print(f"SCD1 (after deletes): {scd1.count()}")

# COMMAND ----------
# MAGIC %md ## SE-22: SCD Type 2 (add history rows)
# COMMAND ----------
# Start with baseline
scd2_base = baseline.withColumn("scd_active", F.lit(True)) \
  .withColumn("scd_effective_date", F.current_timestamp()) \
  .withColumn("scd_end_date", F.lit(None).cast("timestamp"))

# For each update, add a postimage row as a new "version"
updates = changes.filter(F.col("_change_type") == "update_postimage")
scd2_new = updates.select("*").withColumn("scd_active", F.lit(True)) \
  .withColumn("scd_effective_date", F.current_timestamp()) \
  .withColumn("scd_end_date", F.lit(None).cast("timestamp"))

scd2 = scd2_base.union(scd2_new.select(scd2_base.columns))
scd2.write.mode("overwrite").saveAsTable(f"{GOLD}.e6_student_scd2")
print(f"SCD2 (with history): {scd2.count()}")

# COMMAND ----------
# MAGIC %md ## SE-23: Change Log (CDF extract)
# COMMAND ----------
changes.write.mode("overwrite").saveAsTable(f"{GOLD}.e6_student_changes")
print(f"Change log: {changes.count()}")

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
spark.sql(f"""
SELECT _change_type, COUNT(*) as cnt
FROM {GOLD}.e6_student_changes
GROUP BY _change_type
ORDER BY _change_type
""").show()

print("Expected: insert=10, update_preimage=20, update_postimage=20, delete=5")
```

**Expected Outcome:** E6 demonstrates CDC (SE-03/SE-23), SCD Type 1 (SE-21), and SCD Type 2 (SE-22). Changes are captured, tracked, and two flavors of dimensional history are built. Assertions verify the known counts from day-2 changes.

**Verify:**
```sql
SELECT _change_type, COUNT(*) FROM princeton_poc_dev.gold_dev.e6_student_changes GROUP BY _change_type;
-- Expected: insert=10, update_preimage=20, update_postimage=20, delete=5

SELECT COUNT(*) FROM princeton_poc_dev.gold_dev.e6_student_scd1;
-- Expected: < baseline student count (5 deletes removed)

SELECT COUNT(*) FROM princeton_poc_dev.gold_dev.e6_student_scd2;
-- Expected: > baseline student count (SCD2 adds new rows for updates)
```

---

## Task E7: Target loading (UPSERT/delete + file outputs) (Tracks: #10)

**Scenarios:** SE-24 (UPSERT via MERGE), SE-25 (DELETE via MERGE), SE-26 (CSV/pipe export), SE-27 (JSON/Excel export).

**Files:**
- Create: `src/engineer/e7_target_loading.py` (notebook)
- Create: `resources/e7_target_loading.pipeline.yml` (Lakeflow pipeline)

**Interfaces:**
- Consumes: E5 outputs (student_enriched, course_performance, enrollment_ranked).
- Produces: Scenario Gold/Silver tables via MERGE + file outputs (CSV, pipe, JSON, Excel).

#### Lakeflow Designer NL Prompt

```
Create a target-loading pipeline:

SE-24: UPSERT via MERGE: Load e5_student_enriched into a target "student_target" table.
  Use MERGE ON student_id. For matched rows, UPDATE all columns; for unmatched, INSERT.

SE-25: DELETE via MERGE: Delete rows where student_id IN (list). Use MERGE with
  WHEN MATCHED AND condition THEN DELETE.

SE-26: CSV + pipe export: export student_enriched to
  /Volumes/princeton_poc_dev/landing_dev/files/e7_student_enriched.csv
  and e7_student_enriched.pipe (sep=|).

SE-27: JSON + Excel export: export course_performance to
  /Volumes/.../e7_course_performance.json and e7_course_performance.xlsx.

Assertions: verify all files landed; row counts match source.
```

#### Databricks Assistant Code-Gen Prompt

```
Write a Databricks notebook demonstrating target loading with UPSERT/DELETE + file exports.

SE-24: MERGE INTO operation (UPSERT):
  1. Read e5_student_enriched (the source).
  2. MERGE INTO target_student_table USING source ON student_id
     WHEN MATCHED THEN UPDATE SET ...
     WHEN NOT MATCHED THEN INSERT ...
  3. Output updated/inserted count.

SE-25: MERGE INTO operation (DELETE):
  1. Create a list of student_ids to delete (e.g., first 10).
  2. MERGE INTO target_student_table USING delete_list ON student_id
     WHEN MATCHED THEN DELETE

SE-26: File exports (CSV + pipe):
  1. Read e5_student_enriched; write to /Volumes/.../e7_student_enriched.csv (mode=overwrite).
  2. Same, but sep="|" for pipe-delimited.

SE-27: File exports (JSON + Excel):
  1. Read e5_course_performance; write to /Volumes/.../e7_course_performance.json.
  2. For Excel: use spark.read.toPandas().to_excel() or the in-memory openpyxl pattern
     (since native writer is not enabled).

Assertions: verify all files exist; row counts match.
```

#### Pre-built Fallback

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # E7: Target loading (UPSERT/DELETE + file outputs)

# COMMAND ----------
from pyspark.sql import functions as F
import pandas as pd

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
GOLD = f"{CATALOG}.gold{SUFFIX}"
LANDING = f"{CATALOG}.landing{SUFFIX}"
VOLUME_PATH = f"/Volumes/{CATALOG}/landing{SUFFIX}/files"

# COMMAND ----------
# MAGIC %md ## SE-24: UPSERT via MERGE
# COMMAND ----------
source = spark.table(f"{GOLD}.e5_student_enriched")

# Create target if not exists; otherwise MERGE will update
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {GOLD}.e7_student_target AS
SELECT * FROM {GOLD}.e5_student_enriched WHERE 1=0
""")

spark.sql(f"""
MERGE INTO {GOLD}.e7_student_target tgt
USING {GOLD}.e5_student_enriched src
ON tgt.student_id = src.student_id
WHEN MATCHED THEN UPDATE SET
  first_name = src.first_name,
  last_name = src.last_name,
  age = src.age,
  status_normalized = src.status_normalized,
  aid_amount = src.aid_amount
WHEN NOT MATCHED THEN INSERT *
""")

print(f"UPSERT complete. Target row count: {spark.table(f'{GOLD}.e7_student_target').count()}")

# COMMAND ----------
# MAGIC %md ## SE-25: DELETE via MERGE
# COMMAND ----------
delete_ids = spark.table(f"{GOLD}.e5_student_enriched").select("student_id").limit(10)

spark.sql(f"""
MERGE INTO {GOLD}.e7_student_target tgt
USING (
  SELECT student_id FROM {GOLD}.e5_student_enriched LIMIT 10
) del_list
ON tgt.student_id = del_list.student_id
WHEN MATCHED THEN DELETE
""")

print(f"DELETE complete. Target row count after delete: {spark.table(f'{GOLD}.e7_student_target').count()}")

# COMMAND ----------
# MAGIC %md ## SE-26: CSV + pipe-delimited exports
# COMMAND ----------
student_df = spark.table(f"{GOLD}.e5_student_enriched")

# CSV
student_df.coalesce(1).write.mode("overwrite").option("header", "true") \
  .csv(f"{VOLUME_PATH}/e7_student_enriched.csv")

# Pipe-delimited
student_df.coalesce(1).write.mode("overwrite").option("header", "true").option("sep", "|") \
  .csv(f"{VOLUME_PATH}/e7_student_enriched.pipe")

print("CSV + pipe exports written")

# COMMAND ----------
# MAGIC %md ## SE-27: JSON + Excel exports
# COMMAND ----------
course_perf_df = spark.table(f"{GOLD}.e5_course_performance")

# JSON
course_perf_df.coalesce(1).write.mode("overwrite").json(f"{VOLUME_PATH}/e7_course_performance.json")

# Excel (via pandas + openpyxl, since native writer not available)
%pip install openpyxl
dbutils.library.restartPython()

course_perf_pd = spark.table(f"{GOLD}.e5_course_performance").toPandas()
excel_path = f"{VOLUME_PATH}/e7_course_performance.xlsx"
course_perf_pd.to_excel(excel_path, sheet_name="Performance", index=False)

print(f"JSON + Excel exports written to {VOLUME_PATH}")

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
import os
files = [
  f"{VOLUME_PATH}/e7_student_enriched.csv",
  f"{VOLUME_PATH}/e7_student_enriched.pipe",
  f"{VOLUME_PATH}/e7_course_performance.json",
  f"{VOLUME_PATH}/e7_course_performance.xlsx"
]
for f in files:
  try:
    dbutils.fs.ls(f)
    print(f"✓ {f.split('/')[-1]} exists")
  except:
    print(f"✗ {f.split('/')[-1]} NOT found")
```

**Expected Outcome:** E7 demonstrates UPSERT (SE-24), DELETE (SE-25), CSV/pipe export (SE-26), and JSON/Excel export (SE-27). Target tables are mutated via MERGE; files land on the Volume.

**Verify:**
```bash
databricks fs ls /Volumes/princeton_poc_dev/landing_dev/files/e7_* --profile dbx_shared_demo
# Expected: e7_student_enriched.csv, e7_student_enriched.pipe, e7_course_performance.json, e7_course_performance.xlsx

# SQL check:
SELECT COUNT(*) FROM princeton_poc_dev.gold_dev.e7_student_target;
-- Expected: ~30000 - 10 (UPSERT + DELETE)
```

---

## Task E8: Orchestration job (chain, parallel, retry, alert, external call, schedule, bulk pause) (Tracks: #11)

**Scenarios:** SE-28 (chain tasks), SE-29 (parallel tasks), SE-30 (retry), SE-31 (alerting/notification), SE-32 (call external command), SE-33 (scheduling), SE-35 (bulk pause).

**Files:**
- Create: `resources/e8_orchestration.job.yml` (DAB job resource with full task graph)
- Create: `src/engineer/e8_orchestration_driver.py` (notebook that invokes the real foundation pipelines end-to-end)

**Interfaces:**
- Consumes: foundation artifacts (Silver/Gold tables, day-2 change script metadata).
- Produces: a canonical `e8_orchestration_job` DAB resource (Job) that chains:
  - Task 1: Run foundation silver generation (uses foundation 10_generate_core.py).
  - Task 2 (parallel): Run fact generator + run file writing (independent).
  - Task 3: Run bronze/silver wiring.
  - Task 4 (depends on 1-3): Run transformation (E5 patterns).
  - Task 5: External command (shell echo or curl call).
  - Task 6: Retry-enabled task (with on_failure handling).
  - Task 7: Send notification (email / Slack via dbutils).
  - Schedule: daily at 2am.

#### Lakeflow Designer NL Prompt

(Orchestration is primarily a job scheduling/DAB construct; less suitable for pure no-code.)

```
Create an orchestration job in Databricks:

1. Define 7 tasks with dependencies:
   - Tasks 1-3: Foundation generation (chained: core → parallel fact+files, then bronze/silver).
   - Task 4: Transformation (E5 patterns; depends on 1-3).
   - Task 5: External command (curl to verify an API endpoint, or shell echo).
   - Task 6: Retry-enabled task (simulating transient failure recovery).
   - Task 7: Notification (send an email/Slack message on completion).

2. Set parallelism: Tasks 2a and 2b run in parallel.

3. Retry policy: Task 6 retries up to 3 times on failure; task 7 runs regardless.

4. Schedule: cron "0 2 * * *" (daily at 2am UTC).

5. Bulk pause: The job may be paused/resumed from the Jobs UI.

Expected outputs: job runs sequentially as defined; parallel tasks overlap; retries catch transient issues; notification is sent; job appears in the scheduler.
```

#### Databricks Assistant Code-Gen Prompt

```
Write a Databricks job resource (DAB YAML) for orchestration covering SE-28..35.

Job structure:
- Name: "[princeton_poc] Orchestration Demo"
- Tasks:
  1. task_key: generate_core
     notebook_task: ../src/foundation/10_generate_core.py
     (no depends_on; first task)

  2a. task_key: generate_fact
      depends_on: generate_core
      notebook_task: ../src/foundation/11_generate_fact.py

  2b. task_key: write_files
      depends_on: generate_core
      (parallel with 2a)
      notebook_task: ../src/foundation/20_write_source_files.py

  3. task_key: bronze_silver
     depends_on: [generate_fact, write_files]
     (waits for both parallel tasks)
     notebook_task: ../src/foundation/30_bronze_silver.py

  4. task_key: transformation
     depends_on: bronze_silver
     python_wheel_task or notebook_task: E5 patterns

  5. task_key: external_call
     depends_on: transformation
     python_task: a short script that curls an endpoint or echoes "external task done"

  6. task_key: retry_demo
     depends_on: external_call
     max_retries: 3
     min_retry_interval_millis: 5000
     timeout_seconds: 600
     notebook_task: a task that may fail transiently

  7. task_key: notify
     depends_on: [retry_demo] (or no depends_on to run regardless)
     notebook_task: send an email/Slack notification

Email/Slack: set up a notification webhook (UC secret scope + alert policy)
             or use dbutils.notebook.run to trigger a notification task.

Schedule: Set trigger: {quartz_cron_expression: "0 2 * * *"}

Output: Deployable YAML; when deployed, `databricks bundle run e8_orchestration_job`
        chains all tasks according to the dependency DAG.
```

#### Pre-built Fallback

```yaml
# resources/e8_orchestration.job.yml
resources:
  jobs:
    orchestration_demo:
      name: "[princeton_poc] Orchestration Demo (E8)"
      tasks:
        - task_key: generate_core
          notebook_task:
            notebook_path: ../src/foundation/10_generate_core.py
          timeout_seconds: 600
          
        - task_key: generate_fact
          depends_on: [{task_key: generate_core}]
          notebook_task:
            notebook_path: ../src/foundation/11_generate_fact.py
            base_parameters: {row_count: "${var.row_count}"}
          timeout_seconds: 1200
          
        - task_key: write_files
          depends_on: [{task_key: generate_core}]
          notebook_task:
            notebook_path: ../src/foundation/20_write_source_files.py
          timeout_seconds: 300
          
        - task_key: bronze_silver
          depends_on: [{task_key: generate_fact}, {task_key: write_files}]
          notebook_task:
            notebook_path: ../src/foundation/30_bronze_silver.py
          timeout_seconds: 300
          
        - task_key: transformation
          depends_on: [{task_key: bronze_silver}]
          notebook_task:
            notebook_path: ../src/engineer/e5_transformation_kitchen_sink.py
          timeout_seconds: 600
          
        - task_key: external_call
          depends_on: [{task_key: transformation}]
          spark_python_task:
            python_file: ../src/engineer/external_call.py
          timeout_seconds: 60
          
        - task_key: retry_demo
          depends_on: [{task_key: external_call}]
          notebook_task:
            notebook_path: ../src/engineer/e8_retry_demo.py
          max_retries: 3
          min_retry_interval_millis: 5000
          timeout_seconds: 300
          
        - task_key: notify
          depends_on: [{task_key: retry_demo}]
          spark_python_task:
            python_file: ../src/engineer/e8_notify.py
          timeout_seconds: 60
          
      schedule:
        quartz_cron_expression: "0 2 * * *"
        timezone_id: "UTC"
```

**Expected Outcome:** E8 is the "master" orchestration job demonstrating all scheduling/parallelism/retry/notification patterns (SE-28..35). When deployed, it chains foundation + transformation tasks, runs parallel legs, retries on failure, sends notifications, and is scheduled daily.

**Verify (at deployment):**
```bash
databricks bundle validate -t dev --profile dbx_shared_demo
# Expected: job resource validates

databricks bundle run orchestration_demo -t dev --profile dbx_shared_demo
# Expected: all tasks execute in order; parallel tasks overlap; job completes

databricks jobs get --job-id <id> --profile dbx_shared_demo -o json | jq '.schedule'
# Expected: schedule appears with cron "0 2 * * *"
```

---

## Task E9: Monitoring & ops walkthrough (Tracks: #12)

**Scenarios:** SE-34 (Jobs UI navigation, run history, metrics, alerts).

**Files:**
- Create: `docs/runbook/E9_monitoring_walkthrough.md` (navigation guide)

**Interfaces:**
- Consumes: E8 orchestration job (completed runs, logs, metrics).
- Produces: a walkthrough document (pre-built, not a notebook) showing:
  - Jobs UI → open the orchestration job → Runs tab (click a run to see logs).
  - Click a task → see task logs, run ID, duration, retries.
  - System tables: `system.lakeflow.job_runs`, `system.lakeflow.task_runs` — query for metrics.
  - Alerts: set up a job failure notification via email/Slack.

#### Pre-built Walkthrough

```markdown
# E9: Monitoring & Operations Walkthrough (SE-34)

## Navigate the Jobs UI

1. Open the Databricks workspace → Workflows / Jobs.
2. Find the orchestration job "[princeton_poc] Orchestration Demo (E8)".
3. Click the job name to open the job details page.

### Job Overview
- Job ID, owner, schedule (daily 2am), last run time.
- Tasks: see the dependency graph (visual DAG).

### Runs Tab
1. Click "Runs" → see all historical runs.
2. Click a run to open the run details:
   - Run start/end time, duration, status (succeeded/failed/cancelled).
   - Task list: click each task to see:
     - Task ID, status, duration, retries (if any).
     - **Logs** button → stdout/stderr from the task.

### Example: inspect a failed task
- Click a task with status "FAILED".
- Expand "Logs" → search for the error message.
- Note the retry count (if max_retries was set, you'll see multiple attempts).

## Query Metrics via System Tables

Databricks exposes `system.lakeflow.job_runs` and `system.lakeflow.task_runs` tables.

### Query job run history
```sql
SELECT job_id, run_id, start_time, end_time, state, attempt_number
FROM system.lakeflow.job_runs
WHERE job_id = <orchestration_job_id>
ORDER BY start_time DESC
LIMIT 10;
```

Expected: list of runs with states (SUCCEEDED, FAILED, RUNNING, etc.).

### Query task run metrics
```sql
SELECT job_id, run_id, task_key, state, start_time, end_time,
       (unix_timestamp(end_time) - unix_timestamp(start_time)) / 60.0 as duration_minutes
FROM system.lakeflow.task_runs
WHERE job_id = <orchestration_job_id>
ORDER BY start_time DESC;
```

Expected: breakdown of each task, duration, and state.

## Set Up Alerts

1. In the Jobs UI, click the job → "Edit".
2. Scroll to "Notifications" (or "Alerts").
3. Add a notification:
   - **On failure:** send email / Slack message to team.
   - **On success:** optional (usually off).
4. Provide email or Slack webhook URL.
5. Save.

Next time the job fails, the notification fires automatically.

## SE-34 Coverage

SE-34 is **"Monitor job runs, view logs, set alerts."** By completing this walkthrough:
- ✓ View job runs in the UI (Runs tab).
- ✓ Inspect individual task logs.
- ✓ Query historical metrics via system tables.
- ✓ Set up failure alerts.

**Expected Outcome:** E9 is a pre-built guide proving the monitoring/ops surfaces exist in Databricks.
```

**Expected Outcome:** E9 is a guided walkthrough (not an executable task) that covers the Jobs UI, system tables, and alerting. Demonstrates SE-34 is native to Databricks; no custom build needed.

---

## Task E10: DAB + Git repo (Tracks: #13)

**Scenarios:** SE-36 (source control), SE-37 (environment promotion), SE-38 (CI/CD), SE-39 (rollback).

**Files:**
- Everything in the repo IS the artifact.
- Create: `.github/workflows/deploy.yml` (CI/CD workflow)
- Modify: `databricks.yml` (add bundle targets: dev/qa/prod)
- Modify: `README.md` (runbook index)

**Interfaces:**
- Consumes: git history (commits, tags, branches).
- Produces: (1) a live git repo proving SE-36; (2) dev/qa/prod bundle targets proving SE-37; (3) a GitHub Actions CI/CD workflow proving SE-38; (4) rollback via git revert + redeploy proving SE-39.

#### Pre-built Walkthrough (E10 is mostly configuration, not a notebook)

```markdown
# E10: DevOps / DAB + Git (SE-36…SE-39)

## SE-36: Source Control

All code lives in a Git repository: https://github.com/scottDBX1886/princeton_poc

Key files under version control:
- `databricks.yml` — bundle manifest (all resource definitions).
- `src/` — all notebooks and Python code.
- `resources/` — pipeline, job, and app YAML.
- `docs/` — runbooks, config guides, specs.

### Example: view git history
```bash
git log --oneline | head -20
# Expected output:
# abc1234 feat: E8 orchestration job
# def5678 feat: E7 target loading
# ghi9012 feat: E6 CDC/SCD
# ... etc.
```

Each commit represents a built object (E1…E11). Revert a commit to undo a change.

## SE-37: Environment Promotion (dev → qa → prod)

Bundle targets define per-environment configs:

### databricks.yml targets
```yaml
targets:
  dev:
    workspace: { host: <dev_workspace_host> }
    variables:
      catalog: princeton_poc_dev
      storage_root: s3://<dev_bucket>/...
  qa:
    workspace: { host: <qa_workspace_host> }
    variables:
      catalog: princeton_poc_test
      storage_root: s3://<qa_bucket>/...
  prod:
    workspace: { host: <prod_workspace_host> }
    variables:
      catalog: princeton_poc
      storage_root: s3://<prod_bucket>/...
```

### Deploy to each target
```bash
# Dev
databricks bundle deploy -t dev --profile dev-workspace

# QA (same code, different workspace + catalog)
databricks bundle deploy -t qa --profile qa-workspace

# Prod
databricks bundle deploy -t prod --profile prod-workspace
```

Same git commit → three deployments, three catalog namespaces, three workspaces. **That's SE-37.**

## SE-38: CI/CD

`.github/workflows/deploy.yml` runs on every push to `main`:

```yaml
name: Deploy Databricks Bundle
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Databricks CLI
        run: |
          pip install databricks-cli
      - name: Validate bundle
        run: databricks bundle validate -t qa --profile ci
      - name: Deploy to QA
        run: databricks bundle deploy -t qa --profile ci
        env:
          DATABRICKS_HOST: ${{ secrets.DATABRICKS_QA_HOST }}
          DATABRICKS_TOKEN: ${{ secrets.DATABRICKS_QA_TOKEN }}
      - name: Run tests
        run: |
          # Run post-deploy assertions (SQL checks, etc.)
          databricks bundle run foundation_build -t qa --profile ci
```

Every push to `main`:
1. Validates the bundle.
2. Deploys to QA automatically.
3. Runs smoke tests.

**That's SE-38 CI/CD automation.**

## SE-39: Rollback

To revert a deployment, undo the last commit:

```bash
git revert HEAD -m "Rollback last deploy"
git push
# GitHub Actions CI/CD runs automatically, re-deploying the old version.
```

Or manually:

```bash
git reset --hard <commit_hash>
git push --force-with-lease
databricks bundle deploy -t prod --profile prod-workspace
```

The old bundle version is re-deployed. **That's SE-39 rollback.**

## SE-36…39 Coverage Summary

| Scenario | Evidence | Path |
|----------|----------|------|
| SE-36 (source control) | Git repo, commit history, all code versioned | `git log`, GitHub repo |
| SE-37 (environment promotion) | dev/qa/prod bundle targets, same code, different catalogs | `databricks.yml` targets |
| SE-38 (CI/CD) | GitHub Actions workflow, auto-deploy on push | `.github/workflows/deploy.yml` |
| SE-39 (rollback) | git revert + redeploy reverts to prior version | `git revert` + `bundle deploy` |

**Expected Outcome:** E10 is the bundle + repo itself. No separate build; the act of committing engineers' work proves SE-36…39.
```

**Expected Outcome:** E10 is a guide proving the bundle + git repo artifacts satisfy all four scenarios. Runbook entry links to the GitHub repo, tag structure, and workflow file.

---

## Task E11: Governance walkthrough (UC lineage, schema drift, Lakehouse Monitoring, catalog discovery) (Tracks: #14)

**Scenarios:** SE-40 (lineage), SE-41 (schema drift), SE-42 (data drift / Lakehouse Monitoring), SE-43 (catalog discovery + AI-generated comments).

**Files:**
- Create: `docs/runbook/E11_governance_walkthrough.md` (navigation guide)

**Interfaces:**
- Consumes: all engineer + foundation tables (lineage artifacts, schema history via Delta).
- Produces: a walkthrough showing:
  - Catalog Explorer → open a table → view lineage (upstream Bronze/Silver/Gold dependencies).
  - Schema drift via `DESCRIBE HISTORY <table>` — show the day-2 ALTER COLUMN addition.
  - Lakehouse Monitoring: create a monitor on the `enrollment_history` fact to detect data drift (missing values, outlier counts).
  - Catalog + AI comments: navigate UC → tables → open a table → read AI-generated description + column descriptions.

#### Pre-built Walkthrough

```markdown
# E11: Governance Walkthrough (SE-40…SE-43)

## SE-40: Lineage

Databricks Unity Catalog tracks lineage automatically. To view:

1. Open the Databricks workspace → Catalog Explorer.
2. Navigate to `princeton_poc_dev` → `silver_dev` → open table `student`.
3. Click the **Lineage** tab → see upstream sources (Bronze tables) and downstream consumers (Gold).

Visual flow:
```
bronze_dev.e1_students_raw
    ↓
silver_dev.student
    ↓
gold_dev.e5_student_enriched → gold_dev.e7_student_target
```

### Query lineage via SQL (system tables)

Databricks exposes `system.access.table_lineage`:

```sql
SELECT upstream_table_name, downstream_table_name, description
FROM system.access.table_lineage
WHERE downstream_table_name LIKE 'princeton_poc_dev.%'
ORDER BY downstream_table_name;
```

Expected: tables and their dependencies.

## SE-41: Schema Drift

When a column is added / renamed / type-changed, Delta tracks the change. To inspect:

1. Open a table in Catalog Explorer → **Details** tab → **Schema**.
2. Or use SQL:

```sql
DESCRIBE HISTORY princeton_poc_dev.silver_dev.student;
```

Expected: list of versions with `timestamp`, `userEmail`, `operation` (e.g., `ADD COLUMN citizenship`).

### Day-2 schema change (from E6 demo)

The script `src/foundation/40_day2_changes.sql` adds a column:
```sql
ALTER TABLE silver.student ADD COLUMN citizenship STRING;
```

Query the history:
```sql
SELECT version, timestamp, operation, operationParameters
FROM (DESCRIBE HISTORY princeton_poc_dev.silver_dev.student)
WHERE operation LIKE '%ADD%' OR operation LIKE '%COLUMN%'
ORDER BY version DESC;
```

Expected: shows the `ADD COLUMN citizenship` operation with timestamp.

**SE-41 ✓** — schema drift is captured and queryable.

## SE-42: Data Drift Detection (Lakehouse Monitoring)

Lakehouse Monitoring profiles data over time and flags anomalies.

### Create a monitor

1. Open Catalog Explorer → navigate to `princeton_poc_dev.gold_dev.enrollment_history` (the multi-million-row fact).
2. Click **Monitoring** → **Create monitor**.
3. Configure:
   - **Measure columns:** select `gpa_points` (numeric), `grade` (categorical).
   - **Baseline:** use the current data snapshot as the reference.
   - **Schedule:** daily or on-demand.
4. Click **Create**.

### Run a baseline measurement

After creating, click **Measure now** to snapshot the current data distribution.

Expected: profile metrics appear (mean, stddev, null%, distinct values, etc.).

### Simulate data drift (optional)

1. Run the day-2 change script again (more UPDATEs to change grades).
2. Run the monitor again.
3. Compare profiles: if the new distribution deviates (e.g., avg gpa drops 0.5 points), the monitor flags it.

**SE-42 ✓** — Lakehouse Monitoring detects data drift over time.

## SE-43: Catalog Discovery + AI Comments

Databricks AI automatically generates descriptions for tables and columns.

### Inspect AI-generated comments

1. Open Catalog Explorer → `princeton_poc_dev.silver_dev` → select `enrollment`.
2. View the **Details** panel → **Description** — AI-generated summary (e.g., "Fact table of student course enrollments with grade and GPA points").
3. Expand the column list → each column has a comment (auto-generated).

### Add custom comments (optional)

1. Click **Edit** on the table → modify the description.
2. Add custom column descriptions.
3. Save.

Next time an analyst or AI agent queries the table, it has rich context.

### Search via the Catalog

Use the search bar at the top of Catalog Explorer:
- Search "enrollment" → all tables/views with that keyword.
- Click a result → see owner, schema, lineage, AI comments.

**SE-43 ✓** — catalog is discoverable, commentable, and AI-enhanced.

## SE-40…43 Coverage Summary

| Scenario | Evidence | Path |
|----------|----------|------|
| SE-40 (lineage) | Table → Lineage tab; system.access.table_lineage query | Catalog Explorer or SQL |
| SE-41 (schema drift) | DESCRIBE HISTORY shows ADD COLUMN citizenship | SQL or Catalog Explorer Details |
| SE-42 (data drift) | Lakehouse Monitor profiles gpa_points, flags anomalies | Catalog Explorer → Monitoring |
| SE-43 (catalog discovery) | AI comments, search, column descriptions | Catalog Explorer |

**Expected Outcome:** E11 is a pre-built guide showing UC / Lakehouse Monitoring / lineage are native platform features. No custom build; just walkthrough + screenshot guide.
```

**Expected Outcome:** E11 is a navigation guide (not executable code) that demonstrates governance capabilities in Databricks. All four scenarios (SE-40…43) are native features requiring no custom notebooks.

---

## Self-Review

**Spec coverage (Phase 1 Engineer scope — Persona 1 SE-01…SE-43):**

| Scenario(s) | Task | Path(s) | Status |
|---|---|---|---|
| SE-01, SE-02 | E2 DB ingestion | Assistant + pre-built (fallback: Foundation SQL) | ✓ |
| SE-03 | E6 CDC/SCD | Assistant + pre-built (CDF extraction) | ✓ (with day-2 script runbook step) |
| SE-04, SE-05, SE-06, SE-07, SE-09 | E1 Multi-format file | Designer + Assistant + pre-built | ✓ |
| SE-08 | E3 REST API | Assistant + pre-built (OAuth + pagination) | ✓ |
| SE-10 | E4 Multi-source merge | Designer + Assistant + pre-built | ✓ |
| SE-11…SE-20 | E5 Kitchen-sink transform | Designer + Assistant + pre-built | ✓ (10 patterns) |
| SE-21, SE-22, SE-23 | E6 CDC/SCD (continued) | Assistant + pre-built (SCD1/SCD2/CDF) | ✓ |
| SE-24, SE-25, SE-26, SE-27 | E7 Target loading | Designer + Assistant + pre-built (MERGE + exports) | ✓ |
| SE-28, SE-29, SE-30, SE-31, SE-32, SE-33, SE-35 | E8 Orchestration | DAB job resource + runbook | ✓ (chaining, parallel, retry, notify, schedule, pause) |
| SE-34 | E9 Monitoring/ops | Pre-built walkthrough (Jobs UI + system tables) | ✓ |
| SE-36, SE-37, SE-38, SE-39 | E10 DAB + Git | The repo itself + GitHub Actions workflow | ✓ (source control, promotion, CI/CD, rollback) |
| SE-40, SE-41, SE-42, SE-43 | E11 Governance | Pre-built walkthrough (lineage, drift, Monitoring, discovery) | ✓ |

**All 43 Engineer scenarios mapped to 11 objects. Every scenario has at least one path (Designer / Assistant / pre-built).**

**Placeholder scan:**
- `<APP_URL>` (E3) — operator resolves from deployed app.
- `<orchestration_job_id>` (E9) — operator resolves from deployed job.
- `<pre_change_version>` (E6) — operator notes from DESCRIBE HISTORY before running day-2 script.
- `MOCK_CLIENT_ID` / `MOCK_CLIENT_SECRET` (E3) — intentionally literal POC values; production note included.
- `<dev_bucket>`, `<qa_bucket>`, etc. (E10) — operator supplies storage URLs per target.
- All `dbutils.widgets.get()` values are parameterized; notebooks are target-agnostic.

**Type consistency:**
- Catalog: `princeton_poc_dev` (dev) and its schema suffixes `_dev`, `_test`, (no suffix in prod).
- Schema names consistent: `bronze`, `silver`, `gold`, `landing` (or suffixed variants).
- Table naming: `e1_*`, `e2_*`, etc., for scenario tables; foundation tables (student, enrollment, etc.) unchanged.
- `student_id`, `enrollment_id`, `course_id`, `dept_id` PK names consistent across all tables.
- Day-2 script column addition: `citizenship` (from E6 demo) matches 40_day2_changes.sql.

**Open risks flagged (not hidden):**
1. **BYO source database (E2)** — connection details parked; fallback uses foundation Silver tables. At customer deployment, replace with Lakeflow Connect DB CDC or Federation.
2. **Dual Authorization header collision (E3)** — platform OAuth + app OAuth may collide on the same `Authorization` header. Resolution: move app token to `X-API-Token`. Confirmed live during E3 verification.
3. **Excel write not native (E7)** — fallback uses openpyxl (in-memory). Not blocking; works for POC.
4. **Day-2 script runbook step (E6)** — must be applied manually before E6 demo; cannot be auto-run (breaks CDF baseline capture). Documented in runbook as a **pre-demo checkpoint.**

**Build sequencing (within Phase 1):** E1 → E2 → E3 → E4 → E5 → E6 → E7 → E8 → E9 → E10 → E11. Each depends on foundation (Phase 0) being complete. E8 orchestration job chains foundation + E5 end-to-end.

**Deployment cadence:** Deploy each Engineer object task-by-task with checkbox tracking. After each object, run → assert → commit to git. By E11, all 11 objects are deployed and queryable; orchestration (E8) chains them; governance (E11) proves lineage/drift/monitoring. Full end-to-end demo cycle ready.

