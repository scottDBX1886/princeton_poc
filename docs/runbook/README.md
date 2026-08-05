# Princeton POC — Demonstration Runbook

Hand-to-the-DMIA-team playbook for running each RFP scenario live. Grows one entry per
scenario/combination as each build phase completes. Each entry gives the no-code path
(Lakeflow Designer / Genie prompt), the code path (Databricks Assistant prompt), the
pre-built fallback object, and the expected outcome.

---

## Phase 0 — Stand up the shared data foundation

Every scenario runs against this one dataset. Build it once per workspace.

**Prerequisites:** `docs/CONFIG.md` values filled in (`storage_root`, `warehouse_id`);
`--profile` chosen.

**Catalog name is per-target** (shared-metastore naming): `dev` → `princeton_poc_dev`,
`qa` → `princeton_poc_test`, `prod` → `princeton_poc`. The value flows automatically from
the target into every job task, so the verify queries below use `<catalog>` — substitute
the one for the target you built.

**Build:**
```bash
databricks bundle validate --strict -t dev --profile <PROFILE>
databricks bundle deploy  -t dev --profile <PROFILE>   # creates catalog/schemas/volume + the job
databricks bundle run foundation_build -t dev --profile <PROFILE>   # generates all data + files
```

**Verify (assert query — substitute `<catalog>` for the target):**
```sql
SELECT
  (SELECT count(*) FROM <catalog>.silver.student)            AS students,       -- ~30000
  (SELECT count(*) FROM <catalog>.gold.enrollment_history)   AS fact_rows,      -- = row_count
  (SELECT count(*) FROM <catalog>.silver.financial_aid)      AS aid_rows;       -- ~50000
```
And confirm the five source files landed:
```bash
databricks fs ls dbfs:/Volumes/<catalog>/landing/files --profile <PROFILE>
# expect: students.csv, enrollments.pipe.txt, financial_aid.xlsx, course_catalog.json, faculty.xml
```

---

## Demo-time: CDC / SCD / schema-drift (SE-03, SE-21, SE-22, SE-23, SE-41)

These are triggered by the **standalone day-2 change script** — run it live during the
session, then show the platform detecting exactly the planted changes.

**Step 1 — note the current table version (the CDF floor):**
```sql
DESCRIBE HISTORY <catalog>.silver.student LIMIT 1;   -- note the version number
```

**Step 2 — apply the day-2 changes** (`src/foundation/40_day2_changes.sql`): run the
script. It plants **10 inserts, 20 updates, 5 deletes, and adds one column.**

**Step 3 — show the platform detected them (CDF):**
```sql
SELECT _change_type, count(*)
FROM table_changes('<catalog>.silver.student', <version_from_step_1>)
GROUP BY _change_type;
-- Expect: insert=10, update_preimage=20, update_postimage=20, delete=5
```
The known counts ARE the proof: "the platform detected exactly the changes we planted."

**Schema drift (SE-41):** the `ALTER TABLE ... ADD COLUMN citizenship` in the same script
is the drift event — show it surfaced in Catalog Explorer / the pipeline's schema view.

---

## ⚠️ Running this with a group (multi-user sessions)

These runbooks are run by **~20+ participants concurrently, per-person**. To avoid
collisions:
- The **foundation is read-only** — nobody writes to `silver_dev` / `gold_dev` or the
  landing source files. Browse/query/Genie/AI-BI/REST are all safe to run concurrently.
- **Scenarios that create objects write to your own per-person schema**
  `princeton_poc_dev.wksp_<your_user>` (notebooks derive it automatically from
  `current_user()`), so your outputs never clash with anyone else's.
- **Admin (PA) scenarios are performed by one designated person for the whole group**,
  against a dedicated `admin_demo` schema (copies of the sensitive tables) — so masking/
  RLS demos don't change what everyone else sees.
- **Compute:** the session uses an autoscaling SQL warehouse (or serverless) sized for
  concurrency; heavy scenarios (DS-05, PA-13…18) route through it.

> **Status of already-built items** (safe for a group session unless noted): E1, E3, E5,
> and SE-09 are all built and write to per-person `wksp_<user>` schemas — except the SE-09
> job, which currently writes a shared `bronze_dev.sftp_financial_aid` table and will get
> the `wksp_<user>` retrofit before a concurrent group session (fine as-is for a solo/paired
> walkthrough).

---

# Persona 1 — Software / Data Engineer

_Scenario entries below. Each gives: what it proves · code path (Genie-generated SDP
pipeline) · pre-built fallback · expected outcome. **Engineer scenarios use Genie code** to
generate the SDP pipeline code (parameterized to the engineer's own schema). **Lakeflow
Designer** (visual no-code) is the Business Analyst / Data Scientist path, built later._

## E1 — Multi-format file ingestion (SE-04, SE-05, SE-06, SE-07)

**What it proves:** the platform natively ingests five file formats with real-world
"gotchas": CSV with quoted/embedded delimiters, pipe-delimited text, multi-sheet Excel
(targeting a *named* sheet), nested JSON, and XML with optional nodes.

**Setup (SA, done):** foundation source files staged on the landing Volume; pre-built
notebook deployed to `/Workspace/Shared/Princeton POC/1 - Engineer/E1 - Multi-format file ingestion`.

**Code path (Genie — generate the SDP pipeline):** *"Generate a Lakeflow Spark Declarative
Pipeline that reads the five files under `/Volumes/princeton_poc_dev/landing_dev/files/` —
students_csv (CSV, keep quoted embedded commas), enrollments_pipe (pipe-delimited),
financial_aid.xlsx (sheet AidDetail), course_catalog_json (nested), faculty_xml (rowTag
faculty) — creating one bronze streaming table each. Target catalog `princeton_poc_dev`,
schema `wksp_<my_user>`."* (Fill in your own schema, then deploy + run the generated pipeline.)

**Notebook alternative (for the imperative-code angle):** *"Write a PySpark notebook that
reads each of the five formats from the landing Volume with native readers (csv, excel with
dataAddress='AidDetail', json, xml rowTag=faculty), writing each to my own schema. Show
row counts and verify the embedded-comma value stays in one field."*

**Pre-built fallback:** deploy + run the committed **SDP pipeline**
`resources/e1_pipeline.pipeline.yml` (`src/engineer/sdp/e1_file_ingestion_sdp.py`) — 5 bronze
streaming tables via Auto Loader. The notebook `src/engineer/e1_file_ingestion.py` remains
as an imperative alternative.

> **SDP note:** streaming Excel via Auto Loader requires `cloudFiles.schemaEvolutionMode=none`.
> The pipeline's target schema (its per-person `wksp_<user>`) is set in the pipeline config
> and is **auto-created on run** — verified by dropping the schema and re-running.

**Expected outcome:** five tables in your per-person `wksp_<you>` schema —
`e1_students_raw` (2000), `e1_enrollments_raw` (2000), `e1_financial_aid_raw` (1000, from
the AidDetail sheet only), `e1_course_catalog_raw` (10 depts), `e1_faculty_raw` (200).
The row `"Doe, John"` proves the embedded comma didn't split (SE-04); ~66/134
tenure-present/null split proves the optional XML node became null, not a dropped row (SE-07).

**Notes:** (1) Native Excel **read** works (DBR 17.1+) via `.option("dataAddress", "AidDetail")`
— a bare sheet name, not the `'Sheet'!A1` quoting from the old spark-excel library.
(2) Outputs go to a **per-person schema** (`wksp_<current_user>`) so ~20 people run it
concurrently without colliding; the foundation stays read-only.

## E3 — REST API ingestion (SE-08): OAuth 2.0 + pagination + token refresh

**What it proves:** the platform ingests from a paginated REST API using OAuth 2.0
client-credentials, following pagination automatically and refreshing the token on expiry
— with no manual intervention.

**Setup (SA, done):** mock API app `princeton-mock-api` deployed + running; a service
principal `princeton-poc-e3-ingest` (client_id `aa5bc098-…`) with **CAN_USE** on the app;
its OAuth secret stored in UC secret scope `princeton_poc_e3` (keys `client_id`,
`client_secret`). Pre-built notebook: `/Workspace/Shared/Princeton POC/1 - Engineer/E3 - REST API ingestion`.

**Two auth layers (the faithful "internal API behind a gateway" pattern):**
1. **Apps SSO proxy** — the notebook authenticates as the service principal via OAuth
   **M2M**: client-credentials grant at `{host}/oidc/v1/token` (`scope=all-apis`), token
   in `Authorization`. This is what lets an *unattended* notebook reach the app.
2. **The API's own OAuth (SE-08 proper)** — `POST /oauth/token` client-credentials →
   bearer in `X-API-Token` → page `GET /enrollments` until `next` is null → re-issue on 401.

**Code path (Databricks Assistant):** *"Write a notebook that gets an SP OAuth M2M token
from {host}/oidc/v1/token (creds from secret scope princeton_poc_e3), uses it to reach the
app, then does the app's own client-credentials OAuth and pages through /enrollments,
refreshing on 401, writing all rows to my schema."*

**Pre-built fallback:** run the deployed notebook **E3 - REST API ingestion**
(local reference client: `src/apps/mock_api/verify.py`).

**Expected outcome:** 60,000 rows in `wksp_<you>.e3_enrollments_from_api`; ~600 pages;
a token refresh occurs mid-run (300s TTL) with no manual step; final count == API `total`.

**Notes:** (1) The SP + `CAN_USE` + secret-scope setup is a **workspace-admin** one-time
task — this is also the answer to *"how does an in-workspace pipeline call a
gateway-protected internal API,"* and doubles as PA-06 (service account + credential
management) evidence. (2) SE-08's actual requirement (the API's OAuth + pagination) is
independent of the proxy; the SP layer is Databricks-Apps plumbing to reach the app
unattended. (3) SP credentials live only in the UC secret scope, never in notebook code.

## E5 — "Kitchen-sink" transformation pipeline (SE-11 … SE-20)

**What it proves:** ten transformation capabilities in one pipeline — the platform's
breadth for real ETL work. One notebook section per scenario.

**Setup (SA, done):** pre-built notebook `/Workspace/Shared/Princeton POC/1 - Engineer/E5 - Transformation kitchen-sink`.

**Scenario map (each a labeled section):** SE-11 lookup enrichment (matched/unmatched) ·
SE-12 inner/left/full joins · SE-13 string ops (substring/concat/split/case) · SE-14
null + conditional (coalesce/if-then-else) · SE-15 mixed-format date parsing · SE-16 cast
validation with reject path · SE-17 running totals with control-break · SE-18 pivot +
unpivot · SE-19 last-record-in-group · SE-20 grouped iteration → one summary row.

**Code path (Genie — generate the SDP pipeline):** *"Generate a Lakeflow Spark Declarative
Pipeline over `princeton_poc_dev.silver_dev` demonstrating: reference lookup with unmatched
handling, the three join types, string manipulation, null/conditional logic, parsing
mixed-format dates, casting with a reject path (use an expectation to drop bad casts and a
separate view to capture them), running totals per group, a pivot, last-record-per-group,
and a one-row-per-student summary — as materialized views in my schema `wksp_<my_user>`."*

**Pre-built fallback:** deploy + run the committed **SDP pipeline**
`resources/e5_pipeline.pipeline.yml` (`src/engineer/sdp/e5_transformations_sdp.py`) — 8
materialized views. (The imperative notebook `src/engineer/e5_transformation_kitchen_sink.py`
remains as an alternative.)

**Expected outcome (materialized views in `wksp_<you>`):** `e5_student_enriched` (30000),
`e5_student_dates` (30000), `e5_gpa_valid` (**59988** — bad casts dropped by the expectation),
`e5_gpa_rejects` (**12** — the same bad rows captured, proving SE-16's reject path),
`e5_running_totals` (960 = 40 depts × 24 terms), `e5_grade_pivot` (40),
`e5_last_enrollment` / `e5_student_summary` (~26k students with enrollments).

**Notes (real platform behaviors worth showing the customer):** (1) SE-16's reject path is a
declarative **Expectation** (`@dp.expect_or_drop`) — valid rows flow to `e5_gpa_valid` with
drop-metrics tracked automatically; a sibling MV captures the rejects. Cleaner than a manual
staging split. (2) **`try_to_date` / `try_cast`** (not `to_date`/`cast`, which throw in ANSI
mode) parse the mixed-format dates and tolerate bad casts. (3) All 8 MVs run in one managed
update with automatic dependency resolution + lineage — no orchestration code.

## SE-09 — SFTP file retrieval & ingestion (native, no shell script)

**What it proves:** the platform retrieves pattern-matched files from an SFTP server,
stages them in a UC Volume, and ingests them via Auto Loader — all as orchestrated,
git-versioned Lakeflow tasks, with NO standalone shell/bash script.

**Setup (SA, done):** job `[princeton_poc_dev] SFTP ingest (SE-09)` deployed to dev.

**Run:**
```bash
databricks bundle run sftp_ingest -t dev --profile dbx_shared_demo
```

**What happens:** task `retrieve` (`50_sftp_retrieve.py`) runs an in-process paramiko SFTP
server, connects a paramiko client over it, pattern-matches `financial_aid_*.csv`, and pulls
3 dated files to `/Volumes/princeton_poc_dev/landing_dev/files/sftp/`. Task `ingest`
(`51_sftp_ingest.py`) runs Auto Loader → `princeton_poc_dev.bronze_dev.sftp_financial_aid`.

**Expected outcome:** 3 files land on the Volume (`financial_aid_20260728/29/30.csv`);
Bronze table = 600 rows (3 × 200). No shell script anywhere — retrieval is Python paramiko
in a governed, scheduled Lakeflow task.

**Pre-built fallback:** the `sftp_ingest` job itself (both notebooks).

**Notes:** (1) The SFTP server + client run over an in-process `socket.socketpair()` because
the serverless sandbox blocks TCP loopback listeners — still a real SFTP protocol exchange.
Production points the client at a real SFTP host with credentials from a UC secret scope;
the pull logic is identical. (2) **Parked upgrade path:** if the customer obtains the
Lakeflow Connect SFTP connector (Public Preview), it replaces the paramiko retrieval task
with a fully managed connector — the marquee no-code answer.

---

# Persona 2 — Data Scientist

_TBD as built (DS-A…DS-H). Genie natural-language exploration (DS-01) and notebook/ML
scenarios land here._

# Persona 3 — Business Analyst

_TBD as built (BA-A…BA-E). No-code Genie + AI/BI + Lakeflow Designer scenarios land here._

# Persona 4 — Platform Administrator

_TBD as built (PA-A…PA-F). Runs once, by one designated admin, on the `admin_demo` schema
for masking/RLS scenarios._
