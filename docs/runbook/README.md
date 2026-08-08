# Princeton POC — Demonstration Runbook

Hand-to-the-DMIA-team playbook for running each RFP scenario live. Grows one entry per
scenario/combination as each build phase completes. Each entry gives the no-code path
(Lakeflow Designer / Genie prompt), the code path (Databricks Assistant prompt), the
pre-built fallback object, and the expected outcome.

---

## Build-item → scenario coverage map

Each runbook entry (build object) covers several RFP scenario IDs. This is the bridge from
"what you run" to "what Princeton grades" (RFP §7). The authoritative per-ID checklist lives
in [`docs/SCENARIO_TRACKER.md`](../SCENARIO_TRACKER.md); this table is the runbook-facing
summary. **Status:** ✅ built & verified · 🟡 partial/prereq only · ⬜ planned.

| Build item | RFP scenario IDs | Capability | Status |
|-----------|------------------|-----------|--------|
| **Foundation** | — (shared dataset) | Higher-ed data across bronze/silver/gold + 5 source files | ✅ |
| **E1** — Multi-format file ingestion | SE-04, SE-05, SE-06, SE-07 | CSV/delimited, Excel (named sheet), nested JSON, XML | ✅ |
| **E3** — REST API ingestion | SE-08 | OAuth 2.0 + pagination + token refresh | ✅ |
| **E4** — Multi-source merge | SE-10 | Reconcile file + API + DB on one key | ✅ |
| **E5** — Transformation kitchen-sink | SE-11 … SE-20 | Lookup, joins, strings, nulls, dates, cast/reject, running totals, pivot, last-in-group, iteration | ✅ |
| **E6** — CDC + SCD | SE-03, SE-21, SE-22, SE-23 | Change capture + SCD Type 1 & Type 2 (snapshot diff) | ✅ |
| **E7** — Target loading | SE-24, SE-25, SE-26, SE-27 | UPSERT + hard-delete; CSV/pipe/JSON/Excel export | ✅ |
| **SE-09** — SFTP retrieval & ingestion | SE-09 | Pattern-matched SFTP pull → Volume → Auto Loader (no shell script) | ✅ |
| **E2** — Relational DB ingestion | SE-01, SE-02 | Full extract + custom SQL (BYO-DB) | ⬜ parked |
| **E8** — Orchestration | SE-28, SE-29, SE-30, SE-31, SE-32, SE-33, SE-35 | Sequential/parallel/scheduled jobs, retry, alerting, external calls | ✅ |
| **E9** — Workload monitoring | SE-34 | AI/BI dashboard over jobs + pipelines + notebook runs (system tables) | ✅ |
| **E10** — DevOps / CI-CD | SE-36, SE-37, SE-38, SE-39 | Source control, env promotion, CI/CD, rollback | ✅ |
| **E11** — Observability & governance | SE-40, SE-41, SE-42, SE-43 | Lineage, schema drift, data drift, auto-docs | ✅ |
| **DS-A … DS-H** — Data Scientist | DS-01 … DS-09 | SQL/NL exploration, notebooks (Py/R), BYO-data, large data, local connect, ML, scheduling, version control, viz | ⬜ |
| **BA-A … BA-E** — Business Analyst | BA-01 … BA-08 | No-code browse (Genie), subscriptions (AI/BI), Designer + Genie-agent flows for extract/upload+join/transform, saved workflow | ✅ |
| **PA-A … PA-F** — Platform Admin | PA-01 … PA-25 | Access mgmt, column/row security, compute/capacity, cost/chargeback | ⬜ |

**Coverage so far: 49 of 85 RFP scenario IDs ✅ built & verified** — the **entire Engineer
persona except the parked E2 (BYO-DB, SE-01/02)** (ingestion, transformation, CDC/SCD,
target-loading, orchestration, monitoring, DevOps, governance) **plus the entire Business
Analyst persona (BA-01…08)** (no-code browse, subscriptions, extracts, upload+join+transform,
saved workflow). Remaining work is E2 (parked) plus the Data Scientist and Admin personas.

---

## Phase 0 — Stand up the shared data foundation

Every scenario runs against this one dataset. Build it once per workspace.

**Prerequisites:** a **serverless** workspace (UC default storage requires serverless), a SQL
warehouse id, and a CLI `--profile` for that workspace. **No external storage location or
credential is needed** — the catalog uses UC **default storage** (see the "new workspace" note below).

**Catalog / schema names are per-target:** `dev` → `princeton_poc_dev` + `*_dev` schemas,
`qa` → `princeton_poc_test` + `*_test`, `prod` → `princeton_poc` + no suffix. Names flow from
the target vars into every task, so the verify queries use `<catalog>`/`<sfx>` — substitute the
target you built (dev = `princeton_poc_dev` / `_dev`).

**Build (order matters — the catalog must exist on default storage before the rest):**
```bash
# 1. Deploy the bundle (uploads code; creates jobs/pipelines/app; dashboards+Genie need step 2+3 first,
#    so on a brand-new workspace expect the Genie spaces to fail here — that's fine, step 4 fixes it).
databricks bundle validate -t dev --profile datamarket
databricks bundle deploy   -t dev --profile datamarket

# 2. Generate the data. The foundation job's FIRST task (uc_setup) runs SQL `CREATE CATALOG/SCHEMA/
#    VOLUME` on serverless → provisions UC default storage → then generates all tables + source files.
databricks bundle run foundation_build -t dev --profile datamarket

# 3. Re-deploy so the Genie spaces create now that silver_<sfx> tables exist (they ground on live tables).
databricks bundle deploy -t dev --profile datamarket
```

**Verify (assert query — substitute `<catalog>` + `<sfx>`, e.g. `princeton_poc_dev` / `_dev`):**
```sql
SELECT
  (SELECT count(*) FROM <catalog>.silver<sfx>.student)          AS students,   -- 30000
  (SELECT count(*) FROM <catalog>.gold<sfx>.enrollment_history) AS fact_rows,  -- = row_count (5,000,000)
  (SELECT count(*) FROM <catalog>.silver<sfx>.enrollment)       AS enrollments;-- 60000
```
And confirm the five source files landed:
```bash
databricks fs ls dbfs:/Volumes/<catalog>/landing<sfx>/files --profile datamarket
# expect: students.csv, enrollments.pipe.txt, financial_aid.xlsx, course_catalog.json, faculty.xml
```

### Deploying to a new / customer POC workspace

The **`dev` target is the reusable POC template.** To stand the POC up in a fresh workspace, you
do **not** add a new target — you point `dev` at that workspace and reuse everything:

1. In `databricks.yml`, set the `dev` target's `workspace.profile` (and host) to the POC workspace,
   and `warehouse_id` to its serverless SQL warehouse. Leave catalog/schema names as-is.
2. Clear any stale local state for the target so old resource IDs don't leak across workspaces:
   `rm -rf .databricks/bundle/dev`.
3. Run the **Build** sequence above (deploy → `foundation_build` → deploy).

**Why no storage config:** the catalog is created by SQL `CREATE CATALOG` (in the `uc_setup`
task) on a serverless warehouse, which provisions **UC default storage** automatically — so a
serverless workspace needs **no external location, storage credential, or `storage_root`**. (The
DAB `catalogs` *resource* was intentionally removed: the REST API path creates a storage-less
catalog and every table/volume then fails `403 credentialName=None`. SQL-on-serverless is the
only path that provisions default storage.)

**Gotchas (all learned the hard way, captured here so the POC deploy is smooth):**
- **Genie spaces need their tables to already exist** — deploy them *after* `foundation_build`
  (hence the deploy → run → deploy order). On the first deploy they'll error "table does not exist"; that's expected.
- **App name is workspace-global** — if a prior partial deploy left `princeton-mock-api`, a
  redeploy hits `ALREADY_EXISTS`; `databricks bundle destroy -t dev --profile datamarket` clears it.
- **Stale deploy lock** after an interrupted run → add `--force-lock` (safe when it's your own lock).
- **Genie `.geniespace.json` tables must be sorted by identifier**, else create fails `INVALID_PARAMETER_VALUE`.

---

## Demo-time: CDC / SCD / schema-drift (SE-03, SE-21, SE-22, SE-23, SE-41)

These are triggered by the **standalone day-2 change script** — run it live during the
session, then show the platform detecting exactly the planted changes.

**Step 1 — note the current table version (the CDF floor):**
```sql
DESCRIBE HISTORY <catalog>.silver_dev.student LIMIT 1;   -- note the version number
```

**Step 2 — apply the day-2 changes** (`foundation/src/40_day2_changes.sql`): run the
script. It plants **10 inserts, 20 updates, 5 deletes, and adds one column.**

**Step 3 — show the platform detected them (CDF):**
```sql
SELECT _change_type, count(*)
FROM table_changes('<catalog>.silver_dev.student', <version_from_step_1>)
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

## SA pre-flight — how to test these prompts

Run each engineer prompt yourself once before handing this to the DMIA team, to confirm it
produces the expected object. The loop is the same for every entry:

1. **Open the surface named in the entry.** For a *Genie-generated SDP* prompt: create a new
   Lakeflow pipeline, open its editor, and use the **Assistant** (sparkle) panel — or use the
   Databricks Assistant in a notebook attached to the pipeline. For a *Databricks Assistant —
   notebook* prompt (E3, E7): open a new notebook and use the Assistant panel. E8, E9 and SE-09
   are **SA-deployed** (a `bundle run` / a deployed dashboard) — no prompt to paste; see below.
2. **Paste the prompt** from the entry's fenced code-path block. Each is self-contained —
   catalog, schema, and paths are spelled out.
3. **Substitute your schema.** Replace every `wksp_<my_user>` with your own per-person schema:
   `wksp_` + your login email with each non-alphanumeric char turned into `_`.
   - Testing as Scott → `wksp_scott_johnson_databricks_com`.
   - For E3, also replace `<workspace-host>` with your workspace URL (e.g. `https://<...>.azuredatabricks.net`).
4. **For SDP prompts:** put the generated code in the pipeline source, set the pipeline's
   **default catalog = `princeton_poc_dev`** and **default schema = your `wksp_<you>`**, then
   run the pipeline. **For notebook prompts:** just run the notebook.
5. **Check against the entry's "Expected outcome."** That's the pass signal.

**Prereqs for a clean run** (build order matters — several prompts read prior outputs):
- Foundation job has run (Phase 0) — provides `silver_dev` + the landing files.
- `princeton-mock-api` app is **running** and the `princeton_poc_e3` secret scope exists (E3).
- Run order into your wksp: **E1 → E3 → E5 → E4 → E6-setup → E6 → E7.** (E4 reads E1+E3;
  E7 reads E5; E6 needs its snapshot-setup notebook first.) SE-09, E8, E9 are independent of
  this order (SA-deployed jobs/dashboard).
- You have `CREATE SCHEMA` on `princeton_poc_dev` (the SDP auto-creates your wksp on first run).

**Prompt test checklist** (all 9 built objects):

| Entry | How to run | Pass signal (from Expected outcome) |
|-------|-----------|-------------------------------------|
| E1 | prompt → Assistant → SDP | 5 bronze tables (2000/2000/1000/10/200); `"Doe, John"` stays one field |
| E3 | prompt → Assistant → notebook | 60,000 rows; a token refresh occurs mid-run |
| E5 | prompt → Assistant → SDP | 8 MVs; `e5_gpa_valid`=59988 / `e5_gpa_rejects`=12 |
| E4 | prompt → Assistant → SDP | `e4_enrollment_reconciled`; ~3,939 file+db+api |
| E6 | prompt → Assistant → SDP | scd1=1005; scd2=1005 current + ~21 end-dated |
| E7 | prompt → Assistant → notebook | target has 0 alumni; 4 export artifacts |
| SE-09 | `databricks bundle run sftp_ingest -t dev` | 3 files on Volume; Bronze table = 600 rows |
| E8 | `databricks bundle run orchestration_demo -t dev` | job SUCCESS; `retry_demo` fails attempt 0, succeeds attempt 1 |
| E9 | open the deployed **Workload Monitoring** dashboard | ACTIVE; shows jobs + pipelines + notebook runs, last 30d |
| E10 | `git log` · `bundle validate -t dev/qa/prod` · `git tag` | versioned history; all 3 targets `Validation OK!`; release tag listed |
| E11 | lineage/DESCRIBE-HISTORY SQL · Catalog Explorer monitor + AI-suggest | lineage chains returned; `ADD COLUMNS` in history; monitor metrics; AI comments |
| BA-01 | open Genie "Enrollment Explorer" · Catalog Explorer preview | NL questions return grouped results; schema + sample rows |
| BA-02 | open the **Enrollment by Department (BA-02)** dashboard · Subscribe/Export | ACTIVE; KPIs + charts render; subscription/download works |
| BA-03/06/07 | Designer: add `silver_dev.enrollment` → paste Genie-agent prompt → Download (fallback: `enrollment_export.sql`) | filtered extract; CSV/Excel/pipe download |
| BA-04 | Designer: upload budget CSV → paste Genie-agent prompt → Run (fallback: `bundle run ba_budget_enrollment_join`) | `wksp_<you>.ba_dept_budget_enrollment_summary` ≈ 35,937 rows |
| BA-05/08 | Designer: add `silver_dev.student` → paste Genie-agent prompt → Run → Save as workflow (fallback: same job) | transformed table in `wksp_<you>`; saved reusable workflow |

> If a prompt's generated code drifts from the expected outcome, the committed pre-built
> object in each entry is the source of truth — diff against it, then tighten the prompt.

## E1 — Multi-format file ingestion (SE-04, SE-05, SE-06, SE-07)

**What it proves:** the platform natively ingests five file formats with real-world
"gotchas": CSV with quoted/embedded delimiters, pipe-delimited text, multi-sheet Excel
(targeting a *named* sheet), nested JSON, and XML with optional nodes.

**Setup (SA, done):** foundation source files staged on the landing Volume; pre-built
notebook deployed to `/Workspace/Shared/Princeton POC/1 - Engineer/E1 - Multi-format file ingestion`.

**Code path (Genie — generate the SDP pipeline):**
```text
Generate a Lakeflow Spark Declarative Pipeline that reads the five files under
/Volumes/princeton_poc_dev/landing_dev/files/ and creates one bronze streaming table each,
using Auto Loader:
  - students.csv           -> CSV, keep quoted embedded commas as one field
  - enrollments.pipe.txt   -> pipe-delimited
  - financial_aid.xlsx     -> Excel, read only the sheet named AidDetail
  - course_catalog.json    -> nested JSON
  - faculty.xml            -> XML, rowTag faculty
Target catalog princeton_poc_dev, schema wksp_<my_user>. Note that streaming Excel via
Auto Loader requires cloudFiles.schemaEvolutionMode=none.
```

**Notebook alternative (for the imperative-code angle):**
```text
Write a PySpark notebook that reads each of the five files under
/Volumes/princeton_poc_dev/landing_dev/files/ with native readers (csv; excel with
dataAddress='AidDetail'; json; xml rowTag=faculty), writing each to catalog
princeton_poc_dev, schema wksp_<my_user>. Show row counts and verify the embedded-comma
value "Doe, John" stays in one field.
```

**Pre-built fallback:** deploy + run the committed **SDP pipeline**
`engineer/resources/e1_pipeline.pipeline.yml` (`engineer/src/sdp/e1_file_ingestion_sdp.py`) — 5 bronze
streaming tables via Auto Loader. The notebook `engineer/src/e1_file_ingestion.py` remains
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

**Code path (Databricks Assistant — notebook):**
```text
Write a notebook that ingests a paginated REST API behind the Databricks Apps SSO proxy:
  1. Get a service-principal OAuth M2M token from <workspace-host>/oidc/v1/token with
     scope=all-apis (client_id/client_secret from secret scope princeton_poc_e3); put it in
     the Authorization header to clear the Apps proxy.
  2. Then do the app's own client-credentials OAuth (POST /oauth/token) and put that bearer
     in the X-API-Token header.
  3. Page through GET /enrollments following the "next" cursor until it is null, refreshing
     the X-API-Token on any 401.
Write all rows to catalog princeton_poc_dev, schema wksp_<my_user>, table
e3_enrollments_from_api. Never hardcode credentials.
```

**Pre-built fallback:** run the deployed notebook **E3 - REST API ingestion**
(local reference client: `engineer/src/apps/mock_api/verify.py`).

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

**Code path (Genie — generate the SDP pipeline):**
```text
Generate a Lakeflow Spark Declarative Pipeline reading from princeton_poc_dev.silver_dev,
writing materialized views to catalog princeton_poc_dev, schema wksp_<my_user>, that
demonstrates:
  - reference lookup enrichment with matched/unmatched handling
  - inner, left, and full outer joins
  - string manipulation (substring, concat, split, case)
  - null + conditional logic (coalesce, if/then/else)
  - parsing mixed-format date strings (use try_to_date / try_cast so bad values don't throw)
  - casting with a reject path: use an expectation (expect_or_drop) to drop bad casts into
    the valid MV, and a separate MV that captures the rejected rows
  - running totals per group (control-break)
  - a pivot
  - last-record-per-group
  - a one-row-per-student summary
```

**Pre-built fallback:** deploy + run the committed **SDP pipeline**
`engineer/resources/e5_pipeline.pipeline.yml` (`engineer/src/sdp/e5_transformations_sdp.py`) — 8
materialized views. (The imperative notebook `engineer/src/e5_transformation_kitchen_sink.py`
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

## E4 — Multi-source merge (SE-10)

**What it proves:** one pipeline reconciles three different source *types* on a common key —
file-sourced students (E1), API-sourced enrollments (E3), and a DB-sourced table (Silver).

**Setup (SA, done):** requires E1 + E3 to have run into the same wksp schema (their Bronze
outputs are the inputs — the correct medallion pattern; ingestion auth stays in E3).

**Code path (Genie — generate the SDP):**
```text
Generate a Lakeflow SDP materialized view named e4_enrollment_reconciled in catalog
princeton_poc_dev, schema wksp_<my_user>, that reconciles three source types on student_id:
  - wksp_<my_user>.e1_students_raw            (file-sourced)
  - wksp_<my_user>.e3_enrollments_from_api    (API-sourced)
  - princeton_poc_dev.silver_dev.student      (DB-sourced)
Tag each output row with a source_system column showing which sources it matched
(e.g. "file+db+api" vs "api"), so matched vs unmatched reconciliation is visible.
```

**Pre-built fallback:** `engineer/resources/e4_pipeline.pipeline.yml` (`engineer/src/sdp/e4_multisource_merge_sdp.py`).

**Expected outcome:** `e4_enrollment_reconciled` — rows tagged `file+db+api` where the
student is in the file sample, `api` otherwise (matched vs unmatched reconciliation is
visible via `source_system`, which is the point of SE-10). ~3,939 fully-reconciled on the SA data.

## E6 — CDC + SCD (SE-03, SE-21, SE-22, SE-23)

**What it proves:** change-data-capture (new/changed/deleted) and both slowly-changing-
dimension types, inferred automatically by diffing two snapshots — no hand-written CDC logic.

**Setup (SA, done):** run **E6 - snapshot setup** notebook first — it builds `student_snapshot_v1`
(baseline) and `student_snapshot_v2` (baseline + planted **10 inserts / 20 updates / 5 deletes**)
in your wksp schema. Then run the E6 pipeline.

**Code path (Genie — generate the SDP):**
```text
Generate a Lakeflow SDP (Python) that uses apply_changes_from_snapshot to compare two
student snapshots and infer inserts/updates/deletes. Feed the snapshots via a callable that
returns wksp_<my_user>.student_snapshot_v1 as version 1, then wksp_<my_user>.student_snapshot_v2
as version 2, then None. keys = student_id. Build both:
  - e6_student_scd1 : SCD Type 1 (latest state / overwrite)
  - e6_student_scd2 : SCD Type 2 (full history with __START_AT / __END_AT)
Write to catalog princeton_poc_dev, schema wksp_<my_user>.
```

**Pre-built fallback:** `engineer/resources/e6_pipeline.pipeline.yml` (`engineer/src/sdp/e6_cdc_scd_sdp.py`)
+ the snapshot-setup notebook.

**Expected outcome:** `e6_student_scd1` = 1005 (1000 − 5 deletes + 10 inserts), 10 inserted
ids; `e6_student_scd2` = 1005 current + ~21 end-dated history rows (`__START_AT`/`__END_AT`).
The known counts are the proof (SE-03/23 = the detected changes; SE-21 = overwrite; SE-22 = history).

**Notes:** the snapshot-diff is **isolation-safe** — it writes to your wksp and never mutates
the shared `silver_dev` foundation (the standalone `40_day2_changes.sql` mutated it in place,
which would break a concurrent group session; this SDP form is the recommended one).

## E7 — Target loading (SE-24, SE-25, SE-26, SE-27)

**What it proves:** loading a database target with UPSERT + hard-delete, and exporting to
CSV / pipe / Excel / JSON.

**Setup (SA, done):** requires E5's `e5_student_enriched` MV in your wksp schema. Pre-built
notebook `/Workspace/Shared/Princeton POC/1 - Engineer/E7 - Target loading`.

**Code path (Databricks Assistant — notebook):**
```text
Write a notebook that, using catalog princeton_poc_dev and schema wksp_<my_user>:
  1. Seeds a target table e7_student_target from a 500-row subset of e5_student_enriched.
  2. MERGEs the full e5_student_enriched into e7_student_target on student_id
     (update matched, insert unmatched) — an UPSERT.
  3. Hard-deletes alumni rows (standing = 'Alumnus') from the target.
  4. Exports the target to CSV, pipe-delimited, JSON, and Excel under
     /Volumes/princeton_poc_dev/landing_dev/files/e7_exports/wksp_<my_user>/.
Use native writers for CSV/pipe/JSON; write Excel with openpyxl in-memory.
```

**Pre-built fallback:** run the deployed notebook **E7 - Target loading**
(`engineer/src/e7_target_loading.py`).

**Expected outcome:** `e7_student_target` after UPSERT+delete (0 alumni remain); four export
artifacts under `…/files/e7_exports/wksp_<you>/` (student_target_csv, _pipe, _json, .xlsx);
JSON reads back at 1000 rows.

**Why a notebook (not SDP / not a pipeline sink):** we evaluated both LDP **sinks** and a
**custom Python data source** as sinks. Neither fits E7, for one load-bearing reason:
pipeline sinks are fed by a **streaming, append-only** flow, so they can't do SE-24's
**UPSERT + hard-delete** — that needs a batch `MERGE` + `DELETE` (E6 already covers the
*declarative* CDC/SCD upsert). Built-in sink formats (`delta`/`kafka`/Event Hubs) also have
**no CSV/JSON/Excel** option. A custom Python data source *can* write flat files from its
`streamWriter.commit(...)`, so it technically answers the file-format gap — but it's still
append-only/streaming and is ~60–80 lines of `DataSource`/`DataSourceStreamWriter`
boilerplate (+ checkpoint, + openpyxl on every executor) to replace a three-line native
`df.write.format("csv")`. More moving parts and a worse demo than the notebook. So the
imperative notebook is the honest fit; Excel write uses openpyxl in-memory (native Excel
*writer* not enabled; reader is). _(Where a custom data source **does** earn a place in this
RFP: the **reader** side — the clean answer to E2's bring-your-own-DB and a platform-openness
showcase. And `dp.create_sink` is the answer if a future need is "stream pipeline output to an
external Delta/Kafka target" — not E7's file-export + MERGE requirements.)_

## SE-09 — SFTP file retrieval & ingestion (native, no shell script)

**What it proves:** the platform retrieves pattern-matched files from an SFTP server,
stages them in a UC Volume, and ingests them via Auto Loader — all as orchestrated,
git-versioned Lakeflow tasks, with NO standalone shell/bash script.

**Setup (SA, done):** job `[princeton_poc_dev] SFTP ingest (SE-09)` deployed to dev.

**Run:**
```bash
databricks bundle run sftp_ingest -t dev --profile datamarket
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

## E8 — Orchestration (SE-28, SE-29, SE-30, SE-31, SE-32, SE-33, SE-35)

**What it proves:** the platform's job orchestration surface — task chaining, parallel
execution, automated retry on failure, scheduling, external-command calls, and
notifications — all in one **Lakeflow Job** (the tool for orchestration, distinct from SDP
pipelines and standalone notebooks).

**Setup (SA, done):** job `[princeton_poc_dev] Orchestration Demo (E8)` deployed to dev. It is
**isolation-safe** — reads the shared foundation read-only and stages/writes only to your
per-person `wksp_<user>` schema, so ~20 people can run it concurrently.

**Task DAG (7 tasks):**
```
stage ──┬── leg_a ──┐
        └── leg_b ──┴── merge ── external_call ── retry_demo ── notify
```

**Run:**
```bash
databricks bundle run orchestration_demo -t dev --profile datamarket
```

**Code path (Databricks Assistant — the job is a DAB resource):** *"Generate a Databricks
Asset Bundle job with 7 tasks: a stage task, two parallel legs that both depend only on
stage, a merge that depends on both legs, an external-command task, a retry-enabled task
(max_retries) that simulates a transient failure, and a notification task — plus a paused
daily cron schedule and job-level email notifications."*

**Pre-built fallback:** the `orchestration_demo` job itself
(`engineer/resources/e8_orchestration.job.yml` + the 7 driver notebooks under
`engineer/src/e8/`).

**Expected outcome (verified 2026-08-05):** job **TERMINATED SUCCESS**. Per-task proof of
each scenario:
- **SE-28 chaining** — tasks run in dependency order (`stage → legs → merge → external → retry → notify`).
- **SE-29 parallel** — `leg_a` and `leg_b` start and finish in the *same* window (genuine overlap, not serialized).
- **SE-30 retry** — `retry_demo` **attempt 0 FAILED, attempt 1 SUCCESS** (a run-scoped marker on the
  Volume makes it fail once then recover, so the retry policy is exercised and the job still ends green).
- **SE-31 notification** — job-level `email_notifications` fire on success/failure; the `notify` task emits a completion payload.
- **SE-32 external command** — `external_call` runs a subprocess and branches on its output.
- **SE-33 schedule / SE-35 bulk pause** — a daily cron (`0 0 2 * * ?`) is attached but **PAUSED**;
  unpause/pause from the Jobs UI (kept paused so concurrent POC users don't get surprise 2am runs).

Outputs in `wksp_<you>`: `e8_students_stage`, `e8_by_dept`, `e8_by_status`, `e8_summary`.

**Notes:** (1) The retry demo is an **honest** transient-failure simulation — it really fails
and really recovers on retry, rather than a task hard-coded to pass; the marker is keyed to
`{{job.run_id}}` so every fresh run repeats the fail-once-then-succeed cycle. (2) On serverless
there's no shell task type, so SE-32's "external command" runs via a Python `subprocess` — the
same call-an-external-process-and-act-on-its-output pattern, minus a dedicated shell task.
(3) A Slack/Teams webhook post is stubbed (commented) in `e8_notify.py`; wire a UC secret scope
to enable it for the customer POC.

## E9 — Workload monitoring dashboard (SE-34)

**What it proves:** the platform's native observability surface across **all three workload
types — jobs, pipelines, and notebook runs** — run history, success rate, durations, and retry
visibility, with **no custom monitoring build**. Databricks captures the telemetry into system
tables automatically; the dashboard just reads it.

**Data sources (no ingestion — the platform populates these):**
- **Jobs** → `system.lakeflow.job_run_timeline` (scoped by job name `LIKE '%princeton_poc%'`)
- **Pipelines** → `system.lakeflow.pipeline_update_timeline` (the E1/E4/E5/E6 SDP pipelines)
- **Notebook runs** → `system.query.history` where `query_source.notebook_id` is set, scoped to
  the POC SQL warehouse (notebook statements aren't catalog-tagged, so the warehouse is the scope)

**Setup (SA, done):** AI/BI dashboard `[princeton_poc_dev] Workload Monitoring (E9 · SE-34)`
deployed to dev as a **DAB resource** (`engineer/resources/e9_monitoring.dashboard.yml` +
`engineer/src/e9/e9_monitoring.lvdash.json`, generated by `engineer/src/e9/build_dashboard.py`),
so it versions/promotes across dev/qa/prod like every other object. Open it:
```bash
databricks bundle summary -t dev --profile datamarket | grep -A2 e9_monitoring
```

**Code path (Databricks Assistant / Genie):** *"Build an AI/BI dashboard over
system.lakeflow.job_run_timeline, system.lakeflow.pipeline_update_timeline, and
system.query.history (notebook-origin) showing run history, success rate, and durations across
jobs, pipelines, and notebooks for my POC over the last 30 days."* (Genie can also answer these
ad-hoc — the walkthrough has the SQL.)

**Pre-built fallback:** the deployed dashboard itself + the guided walkthrough
[`docs/runbook/E9_monitoring_walkthrough.md`](E9_monitoring_walkthrough.md) (Jobs/Pipelines UI
drill-down, the reusable system-table SQL, and how to wire failure alerts).

**Expected outcome (verified 2026-08-05):** dashboard is **ACTIVE** with 4 datasets (kpi,
by_type, runs, tasks) populated from live data — the unified run table shows **Jobs** (14 runs
incl. E8), **Pipelines** (E1/E4/E5/E6 SDP updates), and **Notebooks** (POC-warehouse statements)
side by side. The "runs by workload type & status" chart and success-% KPI render; drilling into
the `retry_demo` task in the Jobs UI shows the two attempts (FAILED → SUCCEEDED) from SE-30.

**Notes:** (1) The unified run-history dataset UNIONs the three sources into one normalized shape
(`workload_type` / `name` / `status` / `duration_min`); statuses are normalized across systems
(`FINISHED`/`SUCCEEDED`/`COMPLETED` → *Succeeded*, `ERROR`/`FAILED`/`TIMEDOUT` → *Failed*).
(2) Notebook scoping uses the POC SQL warehouse id, **baked into the `.lvdash.json`** (dashboards
have no runtime vars) — regenerate per target with `python engineer/src/e9/build_dashboard.py
--warehouse <id>`. (3) Real system-table gotchas (documented in the walkthrough): timeline tables
need `GROUP BY run_id` + `MAX(CASE WHEN result_state IS NOT NULL…)`; the `jobs`/`pipelines` tables
are SCD so pick the current name via `ROW_NUMBER`; compute duration from timestamps since
serverless leaves `*_duration_seconds` at 0. (4) SE-34 alerts: E8's job-level
`email_notifications` + a Databricks SQL Alert on the run-history query.

## E10 — DevOps: source control, promotion, CI/CD, rollback (SE-36, SE-37, SE-38, SE-39)

**What it proves:** the POC is engineered the way a production data platform is — versioned in
Git, promoted across environments from one codebase, deployed by CI, and rollback-able. **The
repo + bundle + workflow *are* the deliverable; there's no notebook to run.**

**Setup (SA, done):** the repo (`https://github.com/scottDBX1886/princeton_poc`), the three
bundle targets (`dev`/`qa`/`prod`, **all validating**), the CI workflow
(`.github/workflows/deploy.yml`), and a known-good release tag. Full guide:
[`docs/runbook/E10_devops_walkthrough.md`](E10_devops_walkthrough.md).

**How to test (commands, not a prompt):**
```bash
git log --oneline | head                       # SE-36: versioned history, one commit per object
databricks bundle validate -t dev  --profile datamarket   # SE-37: all three targets validate…
databricks bundle validate -t qa   --profile datamarket   #   …same code, three catalogs
databricks bundle validate -t prod --profile datamarket
git tag                                         # SE-39: known-good tag to roll back to
```
The CI workflow (SE-38) is visible under the repo's **Actions** tab — the `validate` job runs on
every push/PR; `deploy` is a manual dispatch that promotes to a chosen target.

**Expected outcome:** `git log` shows the versioned build history; **all three** `bundle validate`
calls return `Validation OK!` (same code, `princeton_poc_dev` / `_test` / `princeton_poc`);
`git tag` lists the release tag; the Actions tab shows the CI runs. SE-39 rollback = `git revert`
or deploy a prior tag, then `bundle deploy`.

**Notes:** (1) `qa`/`prod` carry a **placeholder** `warehouse_id` (fill with the real workspace's
SQL warehouse before deploying there) — but they *validate*, which is what makes the "one commit →
three environments" promotion claim honest. Catalogs use UC **default storage**, so no
`storage_root`/external location is needed per target (serverless workspaces only). (2) The
`deploy` job is manual + secret-gated
on purpose: no auto-deploy to unprovisioned hosts. Flip it to `push: [main]` once qa secrets exist.
(3) The `validate` CI job would have caught the E9 `warehouse_id` regression — a live argument for
the CI gate.

## E11 — Governance: lineage, schema drift, data drift, AI docs (SE-40, SE-41, SE-42, SE-43)

**What it proves:** Databricks' native governance surface over the POC data — **lineage** and
**schema-drift history** are captured automatically (zero setup), while **data-drift monitoring**
and **AI-generated documentation** are one-click actions. Nothing custom is built.

**Setup (SA, done):** no build needed — lineage and Delta history are already populated by the
POC's own pipeline/job runs. Full guide:
[`docs/runbook/E11_governance_walkthrough.md`](E11_governance_walkthrough.md).

**How to test (verified queries + UI actions):**
```sql
-- SE-40 lineage (automatic): full medallion + downstream wksp chains
SELECT source_table_full_name, target_table_full_name
FROM system.access.table_lineage
WHERE target_table_full_name LIKE 'princeton_poc_dev.%' AND source_table_full_name IS NOT NULL
ORDER BY target_table_full_name;

-- SE-41 schema drift (automatic, isolation-safe — writes only your wksp)
CREATE TABLE princeton_poc_dev.wksp_<you>.e11_drift_demo AS
  SELECT student_id, dept_id, status FROM princeton_poc_dev.silver_dev.student LIMIT 100;
ALTER TABLE princeton_poc_dev.wksp_<you>.e11_drift_demo ADD COLUMN citizenship STRING;
DESCRIBE HISTORY princeton_poc_dev.wksp_<you>.e11_drift_demo;   -- shows version 1 = ADD COLUMNS
```
- **SE-42 (data drift):** Catalog Explorer → `gold_dev.enrollment_history` (5M rows) →
  **Monitoring** → create a Snapshot monitor on `gpa_points` + `grade` → **Refresh metrics**.
- **SE-43 (discovery + AI docs):** Catalog Explorer → open `silver_dev.student` → **AI suggest**
  a description + column comments (or seed via `COMMENT ON`), then search to discover them.

**Expected outcome:** the lineage query returns real Bronze→Silver→Gold→wksp chains; the drift
demo's `DESCRIBE HISTORY` shows `ADD COLUMNS` at version 1; a monitor produces profile/drift
metrics on the fact; AI-suggested comments appear on the table and in `information_schema`.

**Notes:** (1) SE-41 drifts a **wksp copy**, not the shared `silver_dev` (isolation model — the
foundation is read-only for the group; ~20 people run it concurrently). (2) POC tables ship
without comments (verified all `NULL`), so SE-43 is demonstrated by the live **AI suggest** action
or a `COMMENT ON` seed. (3) Lakehouse Monitoring is created per-table via UI/API (no pre-populated
system schema here) — the measure columns are confirmed present on the fact table.

---

# Persona 2 — Data Scientist

_TBD as built (DS-A…DS-H). Genie natural-language exploration (DS-01) and notebook/ML
scenarios land here._

# Persona 3 — Business Analyst

_No-code / low-code only — the analyst never writes SQL. Five pre-built objects (a Genie space,
an AI/BI dashboard, a saved SQL export query, a sample upload + Designer canvas, and a saved
workflow job) cover BA-01…08. All read the shared foundation; the one object that writes
(BA-04/05/08) writes to the analyst's own `wksp_<user>` schema. Full walkthroughs in
`businessanalyst/src/walkthroughs/`._

## BA-01 — No-code browse, filter, preview (Genie + Catalog Explorer)

**What it proves:** an analyst discovers and filters the enrollment data with natural language
(Genie) and by browsing (Catalog Explorer) — zero SQL.

**Setup (SA, done):** shared, read-only Genie space **"Enrollment Explorer (BA-01)"** deployed as
a **DAB `genie_spaces` resource** (`businessanalyst/resources/ba_genie.genie_space.yml` +
serialized body `src/genie/enrollment_explorer.geniespace.json`) — **deployed & verified** (accepts
questions). Open it: `databricks bundle summary -t dev --profile datamarket | grep -A2 ba_enrollment_explorer`.

**How to test:** open the Genie space → click a starter question (*"Show me enrollment counts by
department"*) → refine in English (*"…for Fall 2024"*). Then Catalog Explorer →
`silver_dev.enrollment` → Sample Data. Walkthrough: `README_BA01.md`.

**Expected outcome:** Genie returns grouped enrollment summaries (all sample questions verified to
return live data); Catalog Explorer shows schema + sample rows. **Join gotcha** baked into the
space instructions: enrollment has no `dept_id` — a course's department is `course.dept_id`.

## BA-02 — Scheduled report & subscription (AI/BI dashboard)

**What it proves:** an analyst subscribes to a pre-built dashboard for recurring delivery, or
exports it on demand — no SQL.

**Setup (SA, done):** AI/BI dashboard **"Enrollment by Department (BA-02)"** deployed as a DAB
resource (`businessanalyst/resources/ba_dashboard.dashboard.yml` +
`src/dashboards/enrollment_by_department.lvdash.json`), **verified ACTIVE**. KPIs, top-15
department bar, enrollment-by-year trend, dept×term detail table.

**How to test:** `databricks bundle summary -t dev --profile datamarket | grep -A2 ba_enrollment`
→ open the URL → **Schedule/Subscribe** (email/Slack, weekly), or **⋯ → Download** (CSV/Excel/PDF).
Walkthrough: `README_BA02.md`.

**Expected outcome:** a per-user subscription registers, or a file downloads. Queries pre-tested
on `silver_dev` (40 depts, 960 dept×term groups, avg GPA ≈ 3.1). Read-only → concurrent-safe.

> **Demo flow for BA-03/04/05 (Lakeflow Designer + its Genie agent).** The analyst starts from
> data — either an **existing platform object** (BA-03, BA-05) or a **file they upload** (BA-04) —
> then **describes what they want in plain English to the Designer's Genie agent**, which builds
> the flow. The runbook gives the exact prompt to paste. No SQL, no manual node-wiring. If the
> live NL build stalls, each entry's **pre-built fallback** (a verified job / saved query) produces
> the same result.

## BA-03 / BA-06 / BA-07 — Ad-hoc extract to CSV / Excel / pipe (Designer, from existing data)

**What it proves:** starting from an **existing** platform object, an analyst describes an extract
in natural language, Designer builds it, and they download the result in three formats — no SQL.

**Demo flow:**
1. **Start point — existing data:** in Lakeflow Designer, **Add data** → pick
   `princeton_poc_dev.silver_dev.enrollment` (the foundation fact — already there, nothing to upload).
2. **Prompt the Designer Genie agent** (paste, then edit the filter in plain English):
   ```text
   From the enrollment table, join to student, course, term, and department so each row shows
   student name, course title, term year and season, grade, gpa_points, and department name.
   Filter to the Johnson Department. Sort by year descending. This is for an ad-hoc extract I'll
   download as CSV/Excel.
   ```
3. Designer builds the join+filter flow. **Run**, then **Download** the result → CSV (BA-03) /
   Excel (BA-06) / pipe-delimited (BA-07).

**Pre-built fallback:** saved query `businessanalyst/src/queries/enrollment_export.sql` (same
join, editable filter lines, 10k `LIMIT`) — run it in the SQL editor and **Download Results**.
Walkthrough: `README_BA03.md`.

**Expected outcome:** a filtered, human-readable extract (student name, course title, term, grade,
GPA, department); the Johnson-Department filter returns a smaller set (verified). All three formats download cleanly.

## BA-04 — Upload + join + transform (Designer, from your own file)

**What it proves:** an analyst **uploads their own spreadsheet**, then has the Designer Genie agent
join it to platform data and transform it — no SQL.

**Demo flow:**
1. **Start point — upload:** in Lakeflow Designer → **Add data** → **Upload file** →
   `departments_budget_fy2025.csv` (columns: `dept_id, dept_name, budget_amount, approved_date`).
   *(A pre-staged copy also lives at `/Volumes/princeton_poc_dev/landing_dev/files/uploads/` if a
   live upload isn't convenient.)*
2. **Prompt the Designer Genie agent:**
   ```text
   Join my uploaded budget file to the enrollment data: my file has dept_id and budget_amount;
   join it through the course table (course.dept_id) to the enrollment fact, and join student to
   get status. Keep only active students. Rename budget_amount to total_budget and dept_name to
   department. Add a column budget_per_student = total_budget divided by the number of distinct
   students in that department. Save the result to my own schema.
   ```
3. Designer builds upload→join→filter→rename→derive→write. **Run.**

**Pre-built fallback:** job **"BA Workflow — Budget-Enriched Enrollment"**
(`businessanalyst/resources/ba_workflow.job.yml`) — **verified green (35,937 rows)**:
```bash
databricks bundle run ba_budget_enrollment_join -t dev --profile datamarket
```

**Expected outcome:** `wksp_<you>.ba_dept_budget_enrollment_summary` — enrollments enriched with
department budget + derived `budget_per_student` (e.g. Leblanc Dept 1,169,659 → 1,094.16/student).

## BA-05 / BA-08 — Light transform (Designer, from existing data) + save & reuse

**What it proves:** starting from an **existing** object, an analyst applies light transforms
(rename / filter / derived field) via a Designer Genie-agent prompt, then **saves the flow as a
reusable workflow** (BA-08).

**Demo flow:**
1. **Start point — existing data:** Designer → **Add data** → `princeton_poc_dev.silver_dev.student`
   (join `department` for the major name).
2. **Prompt the Designer Genie agent:**
   ```text
   From the student table joined to department, keep only active students. Rename the department
   name column to major, derive a full_name column by concatenating first_name and last_name, and
   add an email_domain column extracted from the part of the email after the @. Save the result to
   my own schema.
   ```
3. Designer builds the rename/filter/derive flow. **Run.**
4. **BA-08 — save & reuse:** **Save as** a workflow/job. Re-run any time (or schedule it); change
   the filter/params to reuse on new data without rebuilding the canvas.

**Pre-built fallback:** the same `ba_budget_enrollment_join` job demonstrates the save-and-reuse
pattern (parameters `upload_file`, `status_filter`, `catalog`, `schema_suffix`); re-run it or
schedule it. Walkthrough: `README_BA04_BA08.md`.

**Expected outcome:** a transformed table in `wksp_<you>` (renamed + derived columns, active-only),
and a saved workflow that re-runs on demand.

**Notes:** (1) **Isolation** — Designer/fallback both write to the analyst's own `wksp_<user>`,
not shared `silver_dev`, so ~20 analysts run concurrently. (2) **Join gotcha the Genie agent
handles:** `enrollment` has no `dept_id` — a course's department is `course.dept_id`; the prompts
state this so the agent joins correctly. (3) `countDistinct` in a Spark window is unsupported —
the fallback job aggregates distinct students per dept separately and joins back.

# Persona 4 — Platform Administrator

_TBD as built (PA-A…PA-F). Runs once, by one designated admin, on the `admin_demo` schema
for masking/RLS scenarios._
