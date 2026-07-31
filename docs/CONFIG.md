# Princeton POC — Deployment Configuration

All values are DAB variables declared in `databricks.yml`. Edit the per-target
`variables:` block, OR override at deploy with `--var name=value` (no file edit).
Precedence: databricks.yml default → per-target → `--var` → `BUNDLE_VAR_<name>` env var.

## Variables to set

| Variable | Purpose | Default | You must set it? |
|----------|---------|---------|------------------|
| `catalog` | Target UC catalog name (per-target for shared metastore) | dev=`princeton_poc_dev`, qa=`princeton_poc_test`, prod=`princeton_poc` | No — already set per target in `databricks.yml`. Flows to every job task via a job parameter → notebook widget. |
| `storage_root` | Catalog managed storage location — the **storage URL/path**, NOT the external-location name. UC resolves it to the governing external location automatically. | *(empty placeholder)* | **YES — before first deploy.** Set `<DEV/QA/PROD_STORAGE_URL>` per target, e.g. `abfss://unity-catalog@adlsdbxdemoshared.dfs.core.windows.net/princeton_poc_dev`. Drop the line to inherit metastore default. |
| `warehouse_id` | SQL warehouse for SQL tasks (by name lookup) | `"Serverless Starter Warehouse"` | **YES if that warehouse name doesn't exist** in the target workspace — change the lookup name. |
| `row_count` | Rows in `enrollment_history` fact | `5000000` | No — override to ~`50000000` for the POC: `--var row_count=50000000` |

## Per-workspace values (fill in)

| Target | `--profile` | catalog (preset) | `storage_root` (URL) | `warehouse_id` (later phases) |
|--------|-------------|------------------|----------------------|-------------------------------|
| dev (internal) | dbx_shared_demo | `princeton_poc_dev` | `abfss://unity-catalog@adlsdbxdemoshared.dfs.core.windows.net/` (set) | _____ |
| qa | dbx_shared_demo | `princeton_poc_test` | _____ | _____ |
| prod (Princeton POC) | _____ | `princeton_poc` | _____ (customer supplies) | _____ |

## Secrets (NOT bundle variables — never commit)
Credentials (SFTP password, OAuth client secret for the mock API) live in a UC secret
scope and are referenced by name. Set up in Plan 2 (apps), not here.

## Deploy
```bash
databricks bundle validate --strict -t <target> --profile <PROFILE>
databricks bundle deploy -t <target> --profile <PROFILE>
databricks bundle run foundation_build -t <target> --profile <PROFILE>
```
