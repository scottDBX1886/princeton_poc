# Platform Administrator persona (PA-01 … PA-25)

Owner-scoped folder for the Platform Administrator RFP scenarios. Part of the single root DAB
bundle — see the repo root `README.md` for the persona-folder structure and
[`docs/superpowers/plans/2026-07-31-phase4-admin.md`](..//docs/superpowers/plans/2026-07-31-phase4-admin.md)
for the build plan (PA-A … PA-F → PA-01 … PA-25): access management, column/row security,
compute & capacity, cost & chargeback.

## Layout
- `resources/` — DAB resource definitions (grants, security policies, jobs, dashboards).
- `src/` — code / SQL (masking + row-filter functions, policy setup, audit queries).

## How this plugs into the bundle
The root `databricks.yml` includes `*/resources/*.yml`, so any `*.yml` you add under
`admin/resources/` is picked up automatically on `bundle deploy` — **no edit to the shared
`databricks.yml` is needed.**

- Resource ymls reference code via a path **relative to the yml's own directory**, e.g.
  a job in `admin/resources/` points at `../src/my_setup.sql`.
- Shared variables are defined once at the root: `${var.catalog}`, `${var.schema_suffix}`,
  `${var.storage_root}`, `${var.warehouse_id}`. Reference them; don't redefine them.
- **Isolation:** Admin scenarios are run by ONE designated person for the whole group against
  a dedicated `admin_demo` schema (copies of the sensitive tables) — masking/RLS demos must
  not change what everyone else sees. Do NOT apply policies to the shared foundation tables.

After adding resources, run `databricks bundle validate -t dev --profile <PROFILE>` to confirm
everything resolves.
