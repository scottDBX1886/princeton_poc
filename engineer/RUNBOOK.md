# Princeton POC — Software / Data Engineer Runbook

Scenario entries for the Engineer persona (SE-01…SE-43). Prerequisite: the shared foundation is
built — see [`foundation/RUNBOOK.md`](../foundation/RUNBOOK.md). Index + coverage map + group-session
rules: [`docs/runbook/README.md`](../docs/runbook/README.md).

_Engineer scenarios use **Genie code** to generate the SDP pipeline (parameterized to the
engineer's own schema); **Lakeflow Designer** is the Business Analyst path. Each entry: what it
proves · setup · code path (paste-in prompt, collapsed) · pre-built fallback · expected outcome._


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
- Run order into your wksp: **E1 → E3 → E4 → E5 → E6-setup → E6 → E7.** (E4 reads E1+E3;
  E7 reads E5; E6 needs its snapshot-setup notebook first.) SE-09, E8, E9 are independent of
  this order (SA-deployed jobs/dashboard).
- You have `CREATE SCHEMA` on `princeton_poc_dev` (the SDP auto-creates your wksp on first run).

**Prompt test checklist** (all 9 built objects):

| Entry | How to run | Pass signal (from Expected outcome) |
|-------|-----------|-------------------------------------|
| E1 | prompt → Assistant → SDP | 5 bronze tables (2000/2000/1000/10/200); `"Doe, John"` stays one field |
| E3 | prompt → Assistant → notebook | 60,000 rows; a token refresh occurs mid-run |
| E4 | prompt → Assistant → SDP | `e4_enrollment_reconciled`; ~3,939 file+db+api |
| E5 | prompt → Assistant → SDP | 8 MVs; `e5_gpa_valid`=59988 / `e5_gpa_rejects`=12 |
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

> **Built:** ✅ · **Prompt:** 🟢 tested (E1 Genie → SDP)

**What it proves:** the platform natively ingests five file formats with real-world
"gotchas": CSV with quoted/embedded delimiters, pipe-delimited text, multi-sheet Excel
(targeting a *named* sheet), nested JSON, and XML with optional nodes.

**Setup (SA, done):** foundation source files staged on the landing Volume; pre-built
notebook deployed to `/Workspace/Shared/Princeton POC/1 - Engineer/E1 - Multi-format file ingestion`.

<details>
<summary><strong>Code path (Genie — generate the SDP pipeline)</strong> — click to expand the copy-paste prompt</summary>

```text
I'm building a Lakeflow Spark Declarative Pipeline (Python) that ingests five higher-ed source
files into bronze streaming tables using Auto Loader. Write the pipeline for me.

Important: each source is staged in its OWN directory under
/Volumes/princeton_poc_dev/landing_dev/files/ — Auto Loader reads a directory, not a single
file — so point each streaming table at the directory. Create one @dp.table streaming table per
source, reading with spark.readStream.format("cloudFiles"), and let Auto Loader manage its own
schema location and checkpoints (don't set them). Enable cloudFiles.inferColumnTypes on each.

Create these five tables in catalog princeton_poc_dev, schema wksp_<my_user>:

1. e1_students_raw — dir students_csv/ — cloudFiles.format csv, header true, quote '"',
   escape '"' (a name field contains an embedded comma inside quotes; it must stay one field).
2. e1_enrollments_raw — dir enrollments_pipe/ — cloudFiles.format csv, header true, sep "|".
3. e1_financial_aid_raw — dir financial_aid_xlsx/ — cloudFiles.format excel, dataAddress
   "AidDetail" (read only that named sheet, not the first), headerRows 1. Excel via Auto Loader
   does NOT support schema evolution, so set cloudFiles.schemaEvolutionMode "none".
4. e1_course_catalog_raw — dir course_catalog_json/ — cloudFiles.format json, multiLine true
   (nested objects/arrays).
5. e1_faculty_raw — dir faculty_xml/ — cloudFiles.format xml, rowTag "faculty" (optional
   <tenure> node should come through as null, not drop the row).

The pipeline's target catalog + schema are set in the pipeline settings, so reference each
table by its short name; don't hard-code the catalog inside the code.
```

</details>

<details>
<summary><strong>Notebook alternative (for the imperative-code angle — batch reads, not Auto Loader)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a PySpark notebook that batch-reads five higher-ed sources under
/Volumes/princeton_poc_dev/landing_dev/files/ with native readers and writes each to catalog
princeton_poc_dev, schema wksp_<my_user>:
  - students_csv/ (csv, header, quote '"', escape '"')
  - enrollments_pipe/ (csv, header, sep "|")
  - financial_aid_xlsx/financial_aid.xlsx (spark.read.format("excel"), dataAddress "AidDetail",
    headerRows 1 — a single-file path is fine for a batch read)
  - course_catalog_json/ (json, multiLine)
  - faculty_xml/ (xml, rowTag "faculty")
Print each row count and verify the embedded-comma value "Doe, John" stays in one field.
```

</details>

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

> **Built:** ✅ · **Prompt:** 🟢 tested (output identical to pre-built)

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
2. **The API's own OAuth (SE-08 proper)** — `POST /oauth/token` client-credentials using the
   app's OWN demo creds (`princeton_poc_client` / `poc_secret_change_me`, distinct from the SP)
   → returned token goes in `X-API-Token` **as the raw token, not `Bearer …`** → page
   `GET /enrollments` by **page number** (`next` = next page number) until `next` is null → re-issue on 401.

<details>
<summary><strong>Code path (Databricks Assistant — notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a notebook that ingests a paginated REST API served by the Databricks App named
"princeton-mock-api", which sits behind the Databricks Apps SSO proxy. Get the app's base URL
from `databricks apps get princeton-mock-api` (the "url" field), e.g.
https://princeton-mock-api-<id>.<region>.databricksapps.com.

There are TWO SEPARATE sets of credentials — do not mix them up:
  • Layer-1 (Apps SSO proxy): a SERVICE PRINCIPAL's client_id/client_secret, read from secret
    scope princeton_poc_e3. Used only to get a workspace OAuth token.
  • Layer-2 (the app's own OAuth): the app's OWN demo credentials, which are literally
    client_id="princeton_poc_client" and client_secret="poc_secret_change_me" (these are the
    app's fixed demo creds, NOT the service principal's — pass them as literals).

Steps:
  1. POST https://<workspace-host>/oidc/v1/token with grant_type=client_credentials,
     scope=all-apis, using the SP client_id/client_secret from scope princeton_poc_e3.
     Take the returned access_token — call it PLATFORM_TOKEN.
  2. POST {base_url}/oauth/token with grant_type=client_credentials and the APP's demo
     client_id/client_secret ("princeton_poc_client" / "poc_secret_change_me"), AND send
     header Authorization: Bearer PLATFORM_TOKEN (so the call clears the SSO proxy). Take the
     returned access_token — call it API_TOKEN.
  3. GET {base_url}/enrollments with BOTH headers on every request:
       Authorization: Bearer PLATFORM_TOKEN
       X-API-Token: API_TOKEN            <-- the RAW token, NOT "Bearer <token>"
     Pagination is PAGE-NUMBER based: send params page (start at 1) and page_size=1000. The
     JSON response has fields total, data (the rows), and next (the next page NUMBER, or null
     when done). Loop until next is null. On HTTP 401, re-run step 2 to refresh API_TOKEN and
     retry the same page. Use page_size=1000 (the API's max) so it's ~60 pages, not 600.
Write all rows to catalog princeton_poc_dev, schema wksp_<my_user>, table
e3_enrollments_from_api. Add a request timeout on every call. Assert the final row count
equals the API's reported total. Never hardcode the SP secret (only the app's demo creds are literals).
```

</details>

> **Before running:** confirm the app is up — `databricks apps get princeton-mock-api` should
> show `RUNNING`. If it's `UNAVAILABLE`/`STOPPED`, start it (`databricks apps start princeton-mock-api`,
> ~1–2 min) or the SA re-deploys it; E3 can't ingest until the app is running.

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

## E4 — Multi-source merge (SE-10)

> **Built:** ✅ · **Prompt:** 🟡 written — not yet regenerated & verified

**What it proves:** one pipeline reconciles three different source *types* on a common key —
file-sourced students (E1), API-sourced enrollments (E3), and a DB-sourced table (Silver).

**Setup (SA, done):** requires E1 + E3 to have run into the same wksp schema (their Bronze
outputs are the inputs — the correct medallion pattern; ingestion auth stays in E3).

<details>
<summary><strong>Code path (Genie — generate the SDP)</strong> — click to expand the copy-paste prompt</summary>

```text
Generate a Lakeflow SDP materialized view named e4_enrollment_reconciled in catalog
princeton_poc_dev, schema wksp_<my_user>, that reconciles three source types on student_id:
  - wksp_<my_user>.e1_students_raw            (file-sourced)
  - wksp_<my_user>.e3_enrollments_from_api    (API-sourced)
  - princeton_poc_dev.silver_dev.student      (DB-sourced)
Tag each output row with a source_system column showing which sources it matched
(e.g. "file+db+api" vs "api"), so matched vs unmatched reconciliation is visible.
```

</details>

**Pre-built fallback:** `engineer/resources/e4_pipeline.pipeline.yml` (`engineer/src/sdp/e4_multisource_merge_sdp.py`).

**Expected outcome:** `e4_enrollment_reconciled` — rows tagged `file+db+api` where the
student is in the file sample, `api` otherwise (matched vs unmatched reconciliation is
visible via `source_system`, which is the point of SE-10). ~3,939 fully-reconciled on the SA data.

## E5 — "Kitchen-sink" transformation pipeline (SE-11 … SE-20)

> **Built:** ✅ · **Prompt:** 🟢 tested (all 10 patterns covered)

**What it proves:** ten transformation capabilities in one pipeline — the platform's
breadth for real ETL work. One notebook section per scenario.

**Setup (SA, done):** pre-built notebook `/Workspace/Shared/Princeton POC/1 - Engineer/E5 - Transformation kitchen-sink`.

**Scenario map (each a labeled section):** SE-11 lookup enrichment (matched/unmatched) ·
SE-12 inner/left/full joins · SE-13 string ops (substring/concat/split/case) · SE-14
null + conditional (coalesce/if-then-else) · SE-15 mixed-format date parsing · SE-16 cast
validation with reject path · SE-17 running totals with control-break · SE-18 pivot +
unpivot · SE-19 last-record-in-group · SE-20 grouped iteration → one summary row.

<details>
<summary><strong>Code path (Genie — generate the SDP pipeline)</strong> — click to expand the copy-paste prompt</summary>

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
Name the lookup-enriched, one-row-per-student materialized view exactly `e5_student_enriched`,
and give it a `standing` column derived from the student status
(e.g. CASE WHEN status = 'graduated' THEN 'Alumnus' ELSE 'Active' END). Downstream steps
(E7 target loading) read `e5_student_enriched` and filter on `standing`, so this name and
column are a fixed contract even though the other MV names are free.
```

</details>

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

> **Expect variation from the prompt (this is fine, not a discrepancy):** the prompt is
> deliberately **language-agnostic**, so Genie may generate the pipeline in **SQL or Python** —
> both are first-class SDP — and may split the work into a **different number of MVs** than the
> pre-built's 8 (a verified run produced a SQL pipeline with 14 MVs). What matters is that all
> ten patterns (SE-11…20) are covered and the reject-path split + pivot behave. Exact row counts
> on the reject MVs can also differ if the generation validates a different column (e.g. casting
> `gpa_points` to INT drops all fractional GPAs) — still a valid demonstration of the reject path.
> The platform choosing the language from a plain-English ask is itself part of the story.

## E6 — CDC + SCD (SE-03, SE-21, SE-22, SE-23)

> **Built:** ✅ · **Prompt:** 🟢 tested (SCD1/SCD2 match pre-built)

**What it proves:** change-data-capture (new/changed/deleted) and both slowly-changing-
dimension types, inferred automatically by diffing two snapshots — no hand-written CDC logic.

**Setup (SA, done):** run **E6 - snapshot setup** notebook first — it builds `student_snapshot_v1`
(baseline) and `student_snapshot_v2` (baseline + planted **10 inserts / 20 updates / 5 deletes**)
in your wksp schema. Then run the E6 pipeline.

<details>
<summary><strong>Code path (Genie — generate the SDP)</strong> — click to expand the copy-paste prompt</summary>

```text
Generate a Lakeflow SDP (Python) that uses apply_changes_from_snapshot to compare two
student snapshots and infer inserts/updates/deletes. Feed the snapshots via a callable that
returns wksp_<my_user>.student_snapshot_v1 as version 1, then wksp_<my_user>.student_snapshot_v2
as version 2, then None. keys = student_id. Build both:
  - e6_student_scd1 : SCD Type 1 (latest state / overwrite)
  - e6_student_scd2 : SCD Type 2 (full history with __START_AT / __END_AT)
Write to catalog princeton_poc_dev, schema wksp_<my_user>.
```

</details>

**Pre-built fallback:** `engineer/resources/e6_pipeline.pipeline.yml` (`engineer/src/sdp/e6_cdc_scd_sdp.py`)
+ the snapshot-setup notebook.

**Expected outcome:** `e6_student_scd1` = 1005 (1000 − 5 deletes + 10 inserts), 10 inserted
ids; `e6_student_scd2` = 1005 current + ~21 end-dated history rows (`__START_AT`/`__END_AT`).
The known counts are the proof (SE-03/23 = the detected changes; SE-21 = overwrite; SE-22 = history).

**Notes:** the snapshot-diff is **isolation-safe** — it writes to your wksp and never mutates
the shared `silver_dev` foundation (the standalone `40_day2_changes.sql` mutated it in place,
which would break a concurrent group session; this SDP form is the recommended one).

## E7 — Target loading (SE-24, SE-25, SE-26, SE-27)

> **Built:** ✅ · **Prompt:** 🟢 tested (princeton_poc: 23999 target, 0 alumni, 4 export formats — matches baseline)

**What it proves:** loading a database target with UPSERT + hard-delete, and exporting to
CSV / pipe / Excel / JSON.

**Setup (SA, done):** requires E5's `e5_student_enriched` MV in your wksp schema. Pre-built
notebook `/Workspace/Shared/Princeton POC/1 - Engineer/E7 - Target loading`.

<details>
<summary><strong>Code path (Databricks Assistant — notebook)</strong> — click to expand the copy-paste prompt</summary>

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

</details>

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

> **Built:** ✅ · **Prompt:** — n/a (SA-deployed job, no generation prompt)

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

> **Built:** ✅ · **Prompt:** 🟡 written — not yet regenerated & verified

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

> **Built:** ✅ · **Prompt:** 🟡 written — not yet regenerated & verified

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
[`docs/runbook/E9_monitoring_walkthrough.md`](../docs/runbook/E9_monitoring_walkthrough.md) (Jobs/Pipelines UI
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

> **Built:** ✅ · **Prompt:** — n/a (git/CLI walkthrough, no generation prompt)

**What it proves:** the POC is engineered the way a production data platform is — versioned in
Git, promoted across environments from one codebase, deployed by CI, and rollback-able. **The
repo + bundle + workflow *are* the deliverable; there's no notebook to run.**

**Setup (SA, done):** the repo (`https://github.com/scottDBX1886/princeton_poc`), the three
bundle targets (`dev`/`qa`/`prod`, **all validating**), the CI workflow
(`.github/workflows/deploy.yml`), and a known-good release tag. Full guide:
[`docs/runbook/E10_devops_walkthrough.md`](../docs/runbook/E10_devops_walkthrough.md).

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

> **Built:** ✅ · **Prompt:** — n/a (UI/SQL walkthrough, no generation prompt)

**What it proves:** Databricks' native governance surface over the POC data — **lineage** and
**schema-drift history** are captured automatically (zero setup), while **data-drift monitoring**
and **AI-generated documentation** are one-click actions. Nothing custom is built.

**Setup (SA, done):** no build needed — lineage and Delta history are already populated by the
POC's own pipeline/job runs. Full guide:
[`docs/runbook/E11_governance_walkthrough.md`](../docs/runbook/E11_governance_walkthrough.md).

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