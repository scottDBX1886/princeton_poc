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

> Note on the two already-built items:
> - **SE-09 (SFTP ingestion)** is a fully-built scenario end-to-end; its pre-built job
>   currently writes a shared `bronze_dev.sftp_financial_aid` table + shared Volume
>   subfolder, so it needs the per-person `wksp_<user>` retrofit before a group session.
> - **SE-08** is only the **data source** so far — the mock REST API *app* that serves
>   paginated OAuth data is deployed (read-only, safe for concurrency), but the
>   *ingestion pipeline* that pulls from it into a table is scenario **E3**, still to be
>   built. The isolation pattern applies to E3 when built, not to the shared app.
> Both work as-is for a solo walkthrough.

## Persona scenario entries

_Appended as Phases 1–4 are built. Each entry:_
- **Scenario ID(s) + title**
- **What it proves**
- **No-code path** (Lakeflow Designer / Genie prompt to paste)
- **Code path** (Databricks Assistant prompt to paste)
- **Pre-built fallback** (object to run if a prompt drifts)
- **Expected outcome** (from the RFP) + how to verify

_(Phase 2 Data Scientist, Phase 3 Business Analyst, Phase 4 Admin — TBD as built.)_

## Phase 1 — Software / Data Engineer

### E1 — Multi-format file ingestion (SE-04, SE-05, SE-06, SE-07)

**What it proves:** the platform natively ingests five file formats with real-world
"gotchas": CSV with quoted/embedded delimiters, pipe-delimited text, multi-sheet Excel
(targeting a *named* sheet), nested JSON, and XML with optional nodes.

**Setup (SA, done):** foundation source files staged on the landing Volume; pre-built
notebook deployed to `/Workspace/Shared/Princeton POC/1 - Engineer/E1 - Multi-format file ingestion`.

**No-code / low-code path (Lakeflow Designer):** *"Create a pipeline that reads the five
files under `/Volumes/princeton_poc_dev/landing_dev/files/` — students_csv (CSV, keep
quoted embedded commas), enrollments_pipe (pipe-delimited), financial_aid.xlsx (sheet
AidDetail), course_catalog_json (nested), faculty_xml (rowTag faculty) — and writes each
to a bronze table."*

**Code path (Databricks Assistant):** *"Write a PySpark notebook that reads each of the
five formats from the landing Volume with native readers (csv, excel with
dataAddress='AidDetail', json, xml rowTag=faculty), writing each to my own schema. Show
row counts and verify the embedded-comma value stays in one field."*

**Pre-built fallback:** run the deployed notebook **E1 - Multi-format file ingestion**
(or `src/engineer/e1_file_ingestion.py`).

**Expected outcome:** five tables in your per-person `wksp_<you>` schema —
`e1_students_raw` (2000), `e1_enrollments_raw` (2000), `e1_financial_aid_raw` (1000, from
the AidDetail sheet only), `e1_course_catalog_raw` (10 depts), `e1_faculty_raw` (200).
The row `"Doe, John"` proves the embedded comma didn't split (SE-04); ~66/134
tenure-present/null split proves the optional XML node became null, not a dropped row (SE-07).

**Notes:** (1) Native Excel **read** works (DBR 17.1+) via `.option("dataAddress", "AidDetail")`
— a bare sheet name, not the `'Sheet'!A1` quoting from the old spark-excel library.
(2) Outputs go to a **per-person schema** (`wksp_<current_user>`) so ~20 people run it
concurrently without colliding; the foundation stays read-only.

---

### SE-08 — REST API ingestion (authenticated + paginated)

**What it proves:** the platform ingests from a paginated REST API using OAuth 2.0
client-credentials, with token refresh handled automatically.

**Setup (SA, done):** `princeton-mock-api` app deployed to dev; SP granted SELECT on
`princeton_poc_dev.silver_dev.enrollment` via `src/apps/grant_app_sp.sh`.
App URL: `https://princeton-mock-api-3438839487639471.11.azure.databricksapps.com`

**The API (what the pipeline calls):**
- `POST /oauth/token` — form: `grant_type=client_credentials`, `client_id=princeton_poc_client`,
  `client_secret=poc_secret_change_me` → `{access_token, expires_in: 300}`
- `GET /enrollments?page=N&page_size=100` — bearer in `X-API-Token` header →
  `{page, page_size, total, next, data:[...]}`. `next` is null on the last page.

**Code path (Assistant prompt for the DMIA team):** *"Write a Spark/Python ingestion that
POSTs client_credentials to {url}/oauth/token, then pages through {url}/enrollments using
the returned bearer in the X-API-Token header, following the `next` field until null,
re-fetching a new token when a call returns 401 (token expiry), and writes all rows to a
Delta table princeton_poc_dev.bronze_dev.api_enrollments."*

**Expected outcome:** all 60,000 enrollment rows retrieved across pages; a token refresh
occurs mid-run (300s TTL) with no manual intervention; row count matches
`SELECT count(*) FROM princeton_poc_dev.silver_dev.enrollment`.

**Pre-built fallback:** the app itself + `src/apps/mock_api/verify.py` (token → paginate → assert).

**Note:** the mock bearer is carried in `X-API-Token` (not `Authorization`) because the
Databricks Apps platform proxy uses `Authorization` for its own SSO. The client-credentials
flow is otherwise a standard OAuth 2.0 demonstration.

---

### SE-09 — SFTP file retrieval & ingestion (native, no shell script)

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
