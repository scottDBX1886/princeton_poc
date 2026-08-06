# E10 — DevOps / DAB + Git Walkthrough (SE-36, SE-37, SE-38, SE-39)

E10 is proven by the repository and bundle **themselves** — there is no notebook to run. This
guide shows where each of the four DevOps scenarios is evidenced, with commands the DMIA team
can run against this repo.

Repo: **https://github.com/scottDBX1886/princeton_poc** · one DAB bundle (`databricks.yml`) ·
three targets (`dev` / `qa` / `prod`), all validating.

---

## SE-36 — Source control integration

Every artifact is version-controlled in Git: `databricks.yml` (bundle manifest), the persona
folders (`foundation/`, `engineer/`, …) with all `src/` code and `resources/` YAML, and `docs/`.

```bash
git log --oneline | head -20        # each feat commit == one built object (E1…E11)
git show --stat HEAD                 # what changed in the latest commit
```

The history is the audit trail — ~34 commits, each a discrete, reviewable change. Branching +
pull requests (the standard review flow) are supported the same way any Git repo is; the CI job
below runs on every PR.

## SE-37 — Environment promotion (dev → qa → prod)

**One codebase, three environments,** selected by the bundle `-t <target>` flag. Each target
maps to its own catalog and (when provisioned) workspace, so the same commit deploys everywhere
with no code change:

| Target | Catalog | Schema suffix | Storage / warehouse |
|--------|---------|---------------|---------------------|
| `dev`  | `princeton_poc_dev`  | `_dev`  | set (internal test env) |
| `qa`   | `princeton_poc_test` | `_test` | placeholders — set before first qa deploy |
| `prod` | `princeton_poc`      | `` (none) | placeholders — set before first prod deploy |

```bash
# Same code, three deploys — the promotion story:
databricks bundle validate -t dev  --profile <dev_profile>    # → Validation OK!
databricks bundle validate -t qa   --profile <qa_profile>     # → Validation OK!
databricks bundle validate -t prod --profile <prod_profile>   # → Validation OK!

databricks bundle deploy -t dev  --profile <dev_profile>      # deploys to princeton_poc_dev
databricks bundle deploy -t qa   --profile <qa_profile>       # deploys to princeton_poc_test
databricks bundle deploy -t prod --profile <prod_profile>     # deploys to princeton_poc
```

> **All three targets validate today.** `qa`/`prod` carry placeholder `storage_root` and
> `warehouse_id` values (`<QA_STORAGE_URL>`, `<QA_WAREHOUSE_ID>`, …) — fill these with the real
> qa/prod workspace values before the first deploy there. `dev` is fully wired and is what the
> POC runs against. The parameterization (catalog + schema_suffix + storage_root + warehouse_id
> as per-target variables) is the whole point of SE-37: promotion is a config swap, not a code fork.

## SE-38 — CI/CD

`.github/workflows/deploy.yml` — two jobs:

- **`validate`** runs on **every push and PR to `main`**: `databricks bundle validate` for all
  three targets. No secrets required (validation is static), so it works immediately and is the
  gate that catches malformed bundles before they merge. *(This job would have caught the E9
  "dashboard warehouse_id is required" regression automatically.)*
- **`deploy`** runs on **manual dispatch** (`workflow_dispatch` → pick a target): validates, then
  `bundle deploy` + a `foundation_build` smoke test. Gated on repo secrets
  (`DATABRICKS_HOST` / `DATABRICKS_TOKEN`) and a GitHub **Environment** (which can require an
  approval for `prod`), so it only runs once the target workspace is provisioned — no auto-deploy
  to placeholder hosts.

To enable auto-deploy to qa for the customer: add the qa `DATABRICKS_HOST`/`DATABRICKS_TOKEN`
secrets and change the `deploy` job's trigger from `workflow_dispatch` to `push: [main]`.

## SE-39 — Rollback of a failed deployment

Because deployments come from Git, rollback is a Git operation + redeploy. Two idioms:

**Revert a bad commit (preferred — keeps history):**
```bash
git revert <bad_commit_sha>          # creates an inverse commit
git push                             # CI validates; dispatch a deploy to redeploy the good state
databricks bundle deploy -t prod --profile <prod_profile>
```

**Roll back to a tagged release:**
```bash
git checkout v0.1.0-engineer         # a known-good tagged state
databricks bundle deploy -t prod --profile <prod_profile>
```

This repo tags known-good states (e.g. `v0.1.0-engineer` = all Engineer scenarios built &
verified). `git tag` lists them. Deploying a prior tag re-materializes that exact bundle — the
deterministic rollback SE-39 asks for.

---

## SE-36…39 coverage

| Scenario | Evidence | Where |
|----------|----------|-------|
| SE-36 source control | Git repo + full commit history; all code/config/docs versioned | `git log`, GitHub repo |
| SE-37 env promotion | dev/qa/prod targets, same code → 3 catalogs; all validate | `databricks.yml` targets · `bundle validate -t <t>` |
| SE-38 CI/CD | GitHub Actions: validate-on-PR + dispatch deploy w/ smoke test | `.github/workflows/deploy.yml` |
| SE-39 rollback | `git revert` or deploy a prior **tag** → redeploy | `git tag`, `git revert`, `bundle deploy` |

**Expected outcome:** the repo + bundle + workflow *are* the deliverable. No separate build —
the act of engineering the POC under version control, with three validating targets and a CI
workflow, satisfies SE-36…39.
