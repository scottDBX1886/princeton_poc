# Princeton University — Data Platform Modernization POC

Databricks POC demonstrating ~60 RFP test scenarios across four personas
(Software/Data Engineer, Data Scientist, Business Analyst, Platform Administrator)
on one shared higher-ed data foundation.

## Documents
- **Design spec:** `docs/superpowers/specs/2026-07-30-princeton-poc-build-design.md` — what & why
- **Phase plans:** `docs/superpowers/plans/` — step-by-step build (phase 0, plan 2/3, phase 1–4)
- **Scenario tracker:** `docs/SCENARIO_TRACKER.md` — all 85 RFP scenario IDs + status (coverage source of truth)
- **Project board:** https://github.com/users/scottDBX1886/projects/2 — ~33 build objects (work-item tracking)
- **Deploy config:** `docs/CONFIG.md` — variables to fill in before deploy
- **Runbook:** `docs/runbook/README.md` — hand to the DMIA team to run each scenario live

## Quick start
1. Fill in `docs/CONFIG.md` values (`storage_root`, `warehouse_id`) and set them in `databricks.yml`.
2. Deploy + build the foundation:
   ```bash
   databricks bundle validate --strict -t dev --profile dbx_shared_demo
   databricks bundle deploy -t dev --profile dbx_shared_demo
   databricks bundle run foundation_build -t dev --profile dbx_shared_demo
   ```

## Structure
One DAB bundle, organized by **persona** so multiple contributors work without collisions.
Each persona folder owns its own `resources/` (DAB definitions) + `src/` (code); the
`databricks.yml` include glob (`*/resources/*.yml`) auto-discovers new persona folders, so
adding a persona needs **no edit to `databricks.yml`**.
- `databricks.yml` — bundle root + dev/qa/prod targets + shared variables (catalog, schema_suffix, storage_root, warehouse_id)
- `foundation/` — **shared** dataset all personas depend on: `resources/` (UC namespace + build job), `src/` (data generators, source-file writer, day-2 change script)
- `engineer/` — Software/Data Engineer scenarios: `resources/` (SDP pipelines, SFTP job, mock-API app), `src/` (notebooks, `sdp/`, `sftp/`, `apps/`)
- `datascientist/`, `businessanalyst/`, `admin/` — added by their owners following the same `resources/` + `src/` shape
- `docs/` — spec, plans, config, runbook, scenario tracker
