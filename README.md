# Princeton University — Data Platform Modernization POC

Databricks POC demonstrating ~60 RFP test scenarios across four personas
(Software/Data Engineer, Data Scientist, Business Analyst, Platform Administrator)
on one shared higher-ed data foundation.

## Documents
- **Design spec:** `docs/superpowers/specs/2026-07-30-princeton-poc-build-design.md` — what & why
- **Phase 0 plan:** `docs/superpowers/plans/2026-07-30-phase0-foundation.md` — foundation build, step by step
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
- `databricks.yml` — bundle root + dev/qa/prod targets
- `resources/` — DAB resource definitions (UC namespace, jobs)
- `src/foundation/` — data generators, source-file writer, day-2 change script
- `docs/` — spec, plan, config, runbook
