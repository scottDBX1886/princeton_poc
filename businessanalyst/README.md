# Business Analyst persona (BA-01 … BA-08)

Owner-scoped folder for the Business Analyst RFP scenarios. Part of the single root DAB
bundle — see the repo root `README.md` for the persona-folder structure and
[`docs/superpowers/plans/2026-07-31-phase3-businessanalyst.md`](../docs/superpowers/plans/2026-07-31-phase3-businessanalyst.md)
for the build plan (BA-A … BA-E → BA-01 … BA-08). The BA path leans on **Lakeflow Designer**
(visual no-code), Genie, and AI/BI dashboards.

## Layout
- `resources/` — DAB resource definitions (dashboards, pipelines, jobs) for this persona.
- `src/` — code / dashboard definitions / notebooks.

## How this plugs into the bundle
The root `databricks.yml` includes `*/resources/*.yml`, so any `*.yml` you add under
`businessanalyst/resources/` is picked up automatically on `bundle deploy` — **no edit to the
shared `databricks.yml` is needed.**

- Resource ymls reference code via a path **relative to the yml's own directory**, e.g.
  a pipeline in `businessanalyst/resources/` points at `../src/my_pipeline.py`.
- Shared variables are defined once at the root: `${var.catalog}`, `${var.schema_suffix}`,
  `${var.storage_root}`, `${var.warehouse_id}`. Reference them; don't redefine them.
- Read from the shared foundation dataset (`${var.catalog}.silver${var.schema_suffix}` etc.);
  write per-person outputs to `wksp_<user>` schemas so concurrent runs don't collide.

After adding resources, run `databricks bundle validate -t dev --profile <PROFILE>` to confirm
everything resolves.
