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
| **E9** — Job monitoring | SE-34 | Job monitoring dashboard | ⬜ |
| **E10** — DevOps / CI-CD | SE-36, SE-37, SE-38, SE-39 | Source control, env promotion, CI/CD, rollback | 🟡 repo/bundle exists |
| **E11** — Observability & governance | SE-40, SE-41, SE-42, SE-43 | Lineage, schema drift, data drift, auto-docs | ⬜ |
| **DS-A … DS-H** — Data Scientist | DS-01 … DS-09 | SQL/NL exploration, notebooks (Py/R), BYO-data, large data, local connect, ML, scheduling, version control, viz | ⬜ |
| **BA-A … BA-E** — Business Analyst | BA-01 … BA-08 | No-code browse, subscriptions, extracts, spreadsheet join, light transforms, saved workflows | ⬜ |
| **PA-A … PA-F** — Platform Admin | PA-01 … PA-25 | Access mgmt, column/row security, compute/capacity, cost/chargeback | ⬜ |

**Coverage so far: 32 of 85 RFP scenario IDs ✅ built & verified** (all Engineer ingestion,
transformation, CDC/SCD, target-loading, and orchestration scenarios). Remaining work is
Engineer monitoring/DevOps/governance (E9–E11) plus the Data Scientist, Business Analyst,
and Admin personas.

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

**Step 2 — apply the day-2 changes** (`foundation/src/40_day2_changes.sql`): run the
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

## SA pre-flight — how to test these prompts

Run each engineer prompt yourself once before handing this to the DMIA team, to confirm it
produces the expected object. The loop is the same for every entry:

1. **Open the surface named in the entry.** For a *Genie-generated SDP* prompt: create a new
   Lakeflow pipeline, open its editor, and use the **Assistant** (sparkle) panel — or use the
   Databricks Assistant in a notebook attached to the pipeline. For a *Databricks Assistant —
   notebook* prompt (E3, E7): open a new notebook and use the Assistant panel.
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
  E7 reads E5; E6 needs its snapshot-setup notebook first.)
- You have `CREATE SCHEMA` on `princeton_poc_dev` (the SDP auto-creates your wksp on first run).

**Prompt test checklist:**

| Entry | Surface | Pass signal (from Expected outcome) |
|-------|---------|-------------------------------------|
| E1 | Assistant → SDP | 5 bronze tables (2000/2000/1000/10/200); `"Doe, John"` stays one field |
| E3 | Assistant → notebook | 60,000 rows; a token refresh occurs mid-run |
| E5 | Assistant → SDP | 8 MVs; `e5_gpa_valid`=59988 / `e5_gpa_rejects`=12 |
| E4 | Assistant → SDP | `e4_enrollment_reconciled`; ~3,939 file+db+api |
| E6 | Assistant → SDP | scd1=1005; scd2=1005 current + ~21 end-dated |
| E7 | Assistant → notebook | target has 0 alumni; 4 export artifacts |

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
databricks bundle run orchestration_demo -t dev --profile dbx_shared_demo
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

---

# Persona 2 — Data Scientist

_TBD as built (DS-A…DS-H). Genie natural-language exploration (DS-01) and notebook/ML
scenarios land here._

# Persona 3 — Business Analyst

_TBD as built (BA-A…BA-E). No-code Genie + AI/BI + Lakeflow Designer scenarios land here._

# Persona 4 — Platform Administrator

_TBD as built (PA-A…PA-F). Runs once, by one designated admin, on the `admin_demo` schema
for masking/RLS scenarios._
