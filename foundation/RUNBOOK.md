# Princeton POC — Foundation Runbook (shared setup)

The shared data foundation every persona runs against. Build it once per workspace, then the
Engineer / BA / DS / PA runbooks all read from it. Index: [`docs/runbook/README.md`](../docs/runbook/README.md).

## Phase 0 — Stand up the shared data foundation

Every scenario runs against this one dataset. Build it once per workspace.

**Prerequisites:** a **serverless** workspace (UC default storage requires serverless), a SQL
warehouse id, and a CLI `--profile` for that workspace. **No external storage location or
credential is needed** — the catalog uses UC **default storage** (see the "new workspace" note below).

**Catalog / schema names are per-target:** `dev` → `princeton_poc_dev` + `*_dev` schemas,
`qa` → `princeton_poc_test` + `*_test`, `prod` → `princeton_poc` + no suffix. Names flow from
the target vars into every task, so the verify queries use `<catalog>`/`<sfx>` — substitute the
target you built (dev = `princeton_poc_dev` / `_dev`).

**Build (two steps — deploy, then run; no re-deploy needed):**
```bash
# 1. Deploy the bundle. Creates jobs/pipelines/dashboards/app only — it does NOT touch live tables,
#    so this is always clean/green even on a brand-new workspace.
databricks bundle validate -t dev --profile datamarket
databricks bundle deploy   -t dev --profile datamarket

# 2. Run the foundation job — one run does everything, in order:
#    uc_setup      -> SQL CREATE CATALOG/SCHEMA/VOLUME on serverless (provisions UC default storage)
#    generate_*/bronze_silver -> all tables + source files
#    genie_setup   -> creates the Genie spaces from the now-existing tables (Genie API needs them to exist)
databricks bundle run foundation_build -t dev --profile datamarket
```

> **Why Genie is a job task, not a deploy-time resource:** the Genie API validates its grounding
> tables at create time, and they don't exist until the data loads. Making Genie creation the
> foundation job's final task decouples `bundle deploy` from the data load — one deploy + one run,
> no re-deploy, no mid-deploy "table does not exist" failure.

**Verify (assert query — substitute `<catalog>` + `<sfx>`, e.g. `princeton_poc_dev` / `_dev`):**
```sql
SELECT
  (SELECT count(*) FROM <catalog>.silver<sfx>.student)          AS students,   -- 30000
  (SELECT count(*) FROM <catalog>.gold<sfx>.enrollment_history) AS fact_rows,  -- = row_count (5,000,000)
  (SELECT count(*) FROM <catalog>.silver<sfx>.enrollment)       AS enrollments;-- 60000
```
And confirm the five source **directories** landed (each format is a directory so Auto Loader
can monitor it; the .xlsx lives inside `financial_aid_xlsx/`):
```bash
databricks fs ls dbfs:/Volumes/<catalog>/landing<sfx>/files --profile datamarket
# expect dirs: students_csv, enrollments_pipe, financial_aid_xlsx, course_catalog_json, faculty_xml
```

### Deploying to a new / customer POC workspace

The **`dev` target is the reusable POC template.** You do **not** add a new target — you point
`dev` at the new workspace and reuse everything. Requires a **serverless** workspace (for UC
default storage). Work top-to-bottom:

**A. Repoint the bundle (3 edits + clear state)**
- [ ] 1. Create a CLI profile for the workspace: `databricks auth login --host https://<poc-url> --profile poc`
- [ ] 2. Get its warehouse id: `databricks warehouses list --profile poc`
- [ ] 3. In `databricks.yml`, on the `dev` target, set `workspace.profile: poc` and
      `variables.warehouse_id: <poc-warehouse-id>`. **Leave `catalog`/`schema_suffix` as-is**
      (`princeton_poc_dev` / `_dev`) — several notebooks hardcode those names.
- [ ] 4. Clear stale local state so old workspace resource IDs don't leak:
      `rm -rf .databricks/bundle/dev`

**B. Build the foundation (2 commands — the whole data + Genie layer)**
- [ ] 5. `databricks bundle deploy -t dev --profile poc`  (clean/green; no live-table dependency)
- [ ] 6. `databricks bundle run foundation_build -t dev --profile poc`
      (uc_setup → default-storage catalog+schemas+volume, generators, genie_setup)
- [ ] 7. Verify with the assert query above (students 30000 / fact 5,000,000 / enrollments 60000).

**C. Per-workspace prereqs that do NOT auto-deploy** (needed for E3 — the REST-API scenario; skip
if you're not demoing E3). These are manual because they involve a service principal + a secret:
- [ ] 8. **Mock API app** — start it: `databricks bundle run mock_api -t dev --profile poc`
      (deploy uploads the code but doesn't start it serving; app is workspace-global).
- [ ] 9. **Secret scope** — `databricks secrets create-scope princeton_poc_e3 --profile poc`, then
      store the ingest SP's creds: `put-secret princeton_poc_e3 client_id` and `client_secret`
      (paste values in your own terminal — never in chat/history).
- [ ] 10. **Grants** — the ingest SP needs `CAN_USE` on the `princeton-mock-api` app; the *app's own*
      SP needs `USE CATALOG` + `USE SCHEMA` + `SELECT` on `princeton_poc_dev.silver_dev` (else
      `/enrollments` 500s with `INSUFFICIENT_PRIVILEGES`). Get the app SP via
      `databricks apps get princeton-mock-api`.
- [ ] 11. Confirm E3 end to end: run the pre-built E3 notebook → 60,000 rows in `e3_enrollments_from_api`.

**D. Per-persona / prompt-test prereqs** (only if testing those prompts on the new workspace)
- [ ] 12. **E4** reads E1 + E3 outputs from the *same* schema — run E1 and E3 into your test schema first.
- [ ] 13. **E6** needs its snapshot-setup notebook run first (creates `student_snapshot_v1`/`v2` in your schema).

**Why no storage config:** the catalog is created by SQL `CREATE CATALOG` (in the `uc_setup`
task) on a serverless warehouse, which provisions **UC default storage** automatically — so a
serverless workspace needs **no external location, storage credential, or `storage_root`**. (The
DAB `catalogs` *resource* was intentionally removed: the REST API path creates a storage-less
catalog and every table/volume then fails `403 credentialName=None`. SQL-on-serverless is the
only path that provisions default storage.)

**Gotchas (all learned the hard way, captured here so the POC deploy is smooth):**
- **Genie spaces are created by the foundation job's `genie_setup` task** (not at deploy time),
  so they're built after the tables exist automatically — no special ordering, no re-deploy.
  (They're job-created artifacts, so they won't appear in `bundle summary`/`destroy`; the task is
  idempotent and rebuilds them on each `foundation_build` run.)
- **App name is workspace-global** — if a prior partial deploy left `princeton-mock-api`, a
  redeploy hits `ALREADY_EXISTS`; `databricks bundle destroy -t dev --profile <profile>` clears it.
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
