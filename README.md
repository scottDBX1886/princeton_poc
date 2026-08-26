# Princeton University — Data Platform Modernization POC

Databricks POC demonstrating the RFP's 85 test scenarios across four personas
(Software/Data Engineer, Data Scientist, Business Analyst, Platform Administrator)
on one shared higher-ed data foundation.

## Documents
- **Scenario tracker:** `docs/SCENARIO_TRACKER.md` — all 85 RFP scenario IDs + status (coverage source of truth)
- **Project board:** https://github.com/users/scottDBX1886/projects/2 — the ~34 build objects (work-item tracking)
- **Runbook:** split per persona — `docs/runbook/README.md` is the index (coverage map + links) →
  `foundation/RUNBOOK.md` (build first), then `engineer/`, `businessanalyst/`, `datascientist/`, `admin/RUNBOOK.md`
- **Interactive runbook app:** a Databricks App presents every scenario with follow-along steps + copy-paste prompts (deployed by the standup script below)

## Quick start — one-command standup

Stand up the **entire POC** on a fresh serverless workspace with a single script:

```bash
databricks auth login --host https://<workspace-host> --profile <profile>
./scripts/setup_new_workspace.sh <profile>
```

That script is the deploy — it runs the whole checklist, idempotently and fail-fast:
1. **Preflight** — auth check + auto-discovers the serverless SQL warehouse
2. **Regenerates the E9 dashboard** for that warehouse (dashboards bake in the warehouse id)
3. **Pre-creates** the catalog + schemas + landing volume via SQL on default storage
   (serverless provisions UC default storage — no `storage_root` / external location needed)
4. **Deploys** the bundle (`bundle deploy`) and **runs `foundation_build`** (30k students / 5M-row fact + Genie spaces)
5. **Starts** the mock REST API app and the interactive runbook app
6. **Creates** the E3 ingest service principal, mints its OAuth secret, and populates the secret scope
7. **Wires** the UC grants
8. **Runs & asserts** every pre-built object (E1/E3/E4/E5/E6/E7/SE-09/E8/BA)
9. **Verifies** the key row counts

Verified end-to-end on a fresh customer workspace (foundation 30k/5M · E3 60k · E4 60k · E5 59,988 · E6 1,005 · E7 23,999).

> **Prompt-testing** (generating each object from its natural-language prompt) is the manual UI
> follow-up — a script can't drive Genie/Designer. The script validates the **build**; the runbook
> app carries the prompts to test in the UI.

### Manual / reference deploy
The two steps at the heart of the script, if you want to run them by hand:
```bash
databricks bundle validate -t dev --profile <profile>
databricks bundle deploy   -t dev --profile <profile>
databricks bundle run foundation_build -t dev --profile <profile>
```
Notes: the `dev` target is the reusable POC template (repoint its `profile` + `warehouse_id`).
Apps must be *started* (`bundle run <app>`), not just deployed. E9's dashboard bakes the
warehouse id, so regenerate it per workspace with `engineer/src/e9/build_dashboard.py --warehouse <id>`.

## Structure
One DAB bundle, organized by **persona** so multiple contributors work without collisions.
Each persona folder owns its own `resources/` (DAB definitions) + `src/` (code); the
`databricks.yml` include glob (`*/resources/*.yml`) auto-discovers new persona folders, so
adding a persona needs **no edit to `databricks.yml`**.
- `databricks.yml` — bundle root + dev/qa/prod targets + shared variables (catalog, schema_suffix, warehouse_id, per-target app names)
- `scripts/setup_new_workspace.sh` — the one-command standup (above)
- `foundation/` — **shared** dataset all personas depend on: `resources/` (UC namespace + build job), `src/` (data generators, source-file writer, day-2 change script)
- `engineer/` — Software/Data Engineer scenarios: SDP pipelines, SFTP job, mock-API app, notebooks
- `businessanalyst/` (BA-01…08), `datascientist/` (DS-01…09), `admin/` (PA-01…25) — each with the same `resources/` + `src/` shape and a per-persona RUNBOOK
- `runbook_app/` — the interactive runbook Databricks App (data-driven from `src/static/data.json`)
- `docs/` — runbook index + walkthroughs, scenario tracker

> **Note:** E2 (relational-DB ingestion, SE-01/02) is pre-built directly in the customer
> workspace as Lakeflow Connect connectors and is intentionally not version-controlled here.
