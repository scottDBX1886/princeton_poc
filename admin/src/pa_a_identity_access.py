# Databricks notebook source
# MAGIC %md
# MAGIC # PA-A: Identity & access management (PA-01 … PA-06)
# MAGIC
# MAGIC Establishes the role model every later PA scenario depends on, grants Unity Catalog
# MAGIC privileges to groups, and proves the grants and the audit trail work.
# MAGIC
# MAGIC | Scenario | Covered by |
# MAGIC |---|---|
# MAGIC | PA-01 user provisioning & role assignment | role → group mapping + membership check |
# MAGIC | PA-02 group-based access control | UC grants keyed on group, never on a user |
# MAGIC | PA-03 environment-level segregation | catalog-scoped grants (`_dev` / `_test` / `_qa` / prod) |
# MAGIC | PA-04 object-level permissions | schema- and table-level grants |
# MAGIC | PA-05 permission audit trail | `system.access.audit` + `system.access.table_lineage` |
# MAGIC | PA-06 service principals & credential rotation | SP grants + rotation procedure |
# MAGIC
# MAGIC ## ⚠️ Two hard constraints in this environment — read before running
# MAGIC
# MAGIC **1. Unity Catalog will not grant to a workspace-local group.** Groups created in this
# MAGIC workspace come back as `WorkspaceGroup`, and `GRANT … TO <that group>` fails with
# MAGIC `PRINCIPAL_DOES_NOT_EXIST`. Only **account-level** groups (SCIM `type=Group`) can hold UC
# MAGIC privileges. We have no account-admin rights here, so this notebook uses account groups that
# MAGIC already exist rather than creating new ones.
# MAGIC
# MAGIC **2. Grants require MANAGE on the securable.** `princeton_poc_dev` is owned by another user,
# MAGIC so catalog-scoped grants return `PERMISSION_DENIED`. This notebook therefore grants at
# MAGIC **`admin_demo` scope**, which the PA admin owns — and which is where spec §3.1 requires PA
# MAGIC scenarios to operate anyway, so the constraint and the design agree.
# MAGIC
# MAGIC **Policy checks use `is_member()`, not `is_account_group_member()`.** `is_member()` is the
# MAGIC workspace-level check and resolves both group types; the account-level function cannot see
# MAGIC workspace groups and would make every mask fall through to its ELSE branch — redacting for
# MAGIC everyone, including the admin, while appearing to work.
# MAGIC
# MAGIC ## Role → group mapping
# MAGIC The RFP describes Admin / Faculty / Student roles. Rather than invent groups we cannot grant
# MAGIC to, each role maps to an existing account group. **State this mapping out loud in the demo** —
# MAGIC the group names are inherited from the shared workspace, not chosen. In Princeton's own
# MAGIC tenancy these would be `princeton_admins` / `princeton_faculty` / `princeton_students`,
# MAGIC provisioned by SCIM from their IdP; nothing else about the pattern changes.
# MAGIC
# MAGIC ## Isolation
# MAGIC PA scenarios run ONCE by ONE designated admin for the whole group (spec §3.1 rule 4). Every
# MAGIC grant below is scoped to `admin_demo`, so the ~20 observers' reads of the shared foundation
# MAGIC are untouched.

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")

SILVER = f"{CATALOG}.silver{SUFFIX}"
GOLD = f"{CATALOG}.gold{SUFFIX}"
ADMIN = f"{CATALOG}.admin_demo"

# RFP role -> an existing ACCOUNT-level group (the only kind UC will grant to).
# ADMIN_ROLE must be a group the running admin belongs to, so the PA-B masking demo has an
# authorised reader; the other two must be groups they do NOT belong to, so the same query
# demonstrably redacts. Verified: is_member('dbx_demo_shared_admins') is true for the PA admin,
# and false for the other two.
ROLES = {
    "admin":   "dbx_demo_shared_admins",
    "faculty": "data_engineers_demo_group",
    "student": "dbx_demo_shared_dev_group",
}
print(f"catalog:    {CATALOG}\npolicy sandbox: {ADMIN}")
for role, group in ROLES.items():
    print(f"  {role:8s} -> {group}")

# COMMAND ----------
# MAGIC %md ## PA-01 — Roles resolve to real principals
# MAGIC Provisioning a person is a group membership change, not a permissions edit. Proving the role
# MAGIC model works means proving `is_member()` resolves each group — that is what every policy in
# MAGIC PA-B and PA-C branches on.
# COMMAND ----------
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
me = spark.sql("SELECT current_user()").first()[0]

# Only account-level groups (type=Group) can hold UC grants.
account_groups = {
    g.display_name for g in w.groups.list()
    if (g.meta and g.meta.resource_type == "Group")
}
print(f"account-level (UC-grantable) groups in this workspace: {len(account_groups)}\n")

membership = {}
for role, group in ROLES.items():
    grantable = group in account_groups
    is_mem = spark.sql(f"SELECT is_member('{group}') AS r").first()["r"]
    membership[role] = is_mem
    print(f"  {role:8s} {group:32s} grantable={grantable}  is_member({me.split('@')[0]})={is_mem}")

print(f"\nThe PA admin is in the '{[r for r, m in membership.items() if m]}' role only — "
      "which is what makes the PA-B masking contrast real rather than staged.")

# COMMAND ----------
# MAGIC %md ## PA-02 / PA-04 — Grant to GROUPS, at object level
# MAGIC Access follows the role. Onboarding becomes a membership change; offboarding revokes
# MAGIC everything at once because nothing was ever granted to an individual.
# MAGIC
# MAGIC Grants are scoped to `admin_demo` (owned by the PA admin) and encode the RFP's access model:
# MAGIC - **admin** — full control of the policy sandbox
# MAGIC - **faculty** — read the tables, but see masked PII (PA-07) and filtered rows (PA-09)
# MAGIC - **student** — table-level read on the fact only; no access to `faculty` or `financial_aid`
# COMMAND ----------
GRANTS = [
    # (privileges, securable_type, securable, group)
    ("ALL PRIVILEGES",     "SCHEMA", ADMIN,                  ROLES["admin"]),

    # Faculty: schema-level read across the sandbox — masks and row filters do the narrowing.
    ("USE SCHEMA, SELECT", "SCHEMA", ADMIN,                   ROLES["faculty"]),

    # Student: object-level, deliberately narrower. This IS PA-04 — permissions on the specific
    # object, not the container. No grant on faculty or financial_aid means no access at all.
    ("USE SCHEMA",         "SCHEMA", ADMIN,                   ROLES["student"]),
    ("SELECT",             "TABLE",  f"{ADMIN}.student",      ROLES["student"]),
]

for privs, kind, securable, group in GRANTS:
    spark.sql(f"GRANT {privs} ON {kind} {securable} TO `{group}`")
    print(f"  GRANT {privs:18s} ON {kind:6s} {securable:42s} -> {group}")

# COMMAND ----------
# MAGIC %md ## PA-04 — The effective grants, from `information_schema`
# MAGIC Queryable source of truth, no console clicking. Note the column is **`schema_name`**, not
# MAGIC `table_schema` — the latter belongs to the table-level views.
# COMMAND ----------
display(spark.sql(f"""
    SELECT grantee, privilege_type
    FROM {CATALOG}.information_schema.schema_privileges
    WHERE schema_name = 'admin_demo'
      AND grantee IN ('{ROLES["admin"]}', '{ROLES["faculty"]}', '{ROLES["student"]}')
    ORDER BY grantee, privilege_type
"""))

display(spark.sql(f"""
    SELECT grantee, table_name, privilege_type
    FROM {CATALOG}.information_schema.table_privileges
    WHERE table_schema = 'admin_demo'
    ORDER BY grantee, table_name, privilege_type
"""))

# COMMAND ----------
# MAGIC %md ## PA-03 — Environment-level segregation
# MAGIC Environments are separate **catalogs** — `princeton_poc_dev`, `_test`, `_qa`,
# MAGIC `princeton_poc` — all in this one workspace. `USE CATALOG` gates everything beneath it, so
# MAGIC withholding it is absolute: there is no schema-level way around a missing catalog grant.
# MAGIC
# MAGIC Below: which principals hold catalog-level privileges here. A group absent from this list
# MAGIC cannot read *anything* in the catalog, whatever schema grants might say.
# MAGIC
# MAGIC > Catalog-scoped GRANTs need MANAGE on the catalog, which the PA admin does not hold here
# MAGIC > (`princeton_poc_dev` is owned by another user). The segregation *model* is demonstrated by
# MAGIC > reading the grant state; applying it per environment is a one-line GRANT for whoever owns
# MAGIC > the catalog.
# COMMAND ----------
display(spark.sql(f"""
    SELECT grantee, privilege_type, '{CATALOG}' AS catalog
    FROM {CATALOG}.information_schema.catalog_privileges
    ORDER BY grantee, privilege_type
"""))

# COMMAND ----------
# MAGIC %md ## PA-05 — Permission audit trail
# MAGIC Every grant is recorded with its actor. **Always filter on `event_date`** — it is the
# MAGIC partition column and this table holds tens of millions of rows per week (53M over 7 days
# MAGIC here). An unfiltered query is slow enough to look broken.
# COMMAND ----------
display(spark.sql("""
    SELECT event_time,
           user_identity.email                   AS actor,
           action_name,
           request_params['securable_full_name'] AS securable,
           request_params['changes']             AS changes
    FROM system.access.audit
    WHERE event_date >= current_date() - INTERVAL 1 DAY
      AND service_name = 'unityCatalog'
      AND action_name = 'updatePermissions'
    ORDER BY event_time DESC
    LIMIT 25
"""))

# COMMAND ----------
# MAGIC %md ### PA-05 — who has actually READ the sensitive tables?
# MAGIC The question an auditor really asks, and the one a grants list cannot answer. A grant says
# MAGIC who *could*; lineage says who *did*.
# COMMAND ----------
display(spark.sql(f"""
    SELECT created_by                AS who,
           source_table_full_name    AS table_read,
           count(*)                  AS reads,
           max(event_time)           AS last_read
    FROM system.access.table_lineage
    WHERE event_date >= current_date() - INTERVAL 7 DAYS
      AND source_table_full_name IN (
          '{SILVER}.student', '{SILVER}.faculty', '{SILVER}.financial_aid',
          '{ADMIN}.student',  '{ADMIN}.faculty',  '{ADMIN}.financial_aid')
    GROUP BY created_by, source_table_full_name
    ORDER BY reads DESC
    LIMIT 25
"""))

# COMMAND ----------
# MAGIC %md ## PA-06 — Service principals & credential rotation
# MAGIC The POC already ships a working example: `engineer/src/apps/grant_app_sp.sh` grants the mock
# MAGIC REST API app's service principal `SELECT` on a single table — least privilege for a workload
# MAGIC identity, with no human credential involved.
# MAGIC
# MAGIC The rotation argument in one line: **grants attach to the principal, not the credential.**
# MAGIC Rotating an SP secret is therefore invisible to permissions — which is exactly what an
# MAGIC embedded personal token cannot offer. Full procedure in
# MAGIC [`PA_A_IDENTITY_STRATEGY.md`](../PA_A_IDENTITY_STRATEGY.md).
# COMMAND ----------
sps = list(w.service_principals.list())
print(f"service principals in this workspace: {len(sps)}")
for sp in sps[:8]:
    print(f"  {sp.display_name}  (application_id {sp.application_id})")

# SP grants — application IDs are UUIDs, so they are distinguishable from user/group grantees.
display(spark.sql(f"""
    SELECT grantee, table_schema, table_name, privilege_type
    FROM {CATALOG}.information_schema.table_privileges
    WHERE grantee RLIKE '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-'
    ORDER BY grantee, table_schema, table_name
    LIMIT 25
"""))

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
# Every role must map to a group UC can actually grant to. This is the check that would have
# caught the WorkspaceGroup dead end before a demo.
for role, group in ROLES.items():
    assert group in account_groups, (
        f"role '{role}' maps to '{group}', which is not an account-level group — "
        "UC cannot grant to it (PRINCIPAL_DOES_NOT_EXIST)"
    )

# The admin role must resolve for the running user, or PA-B's masking demo has no authorised
# reader and every column redacts for everyone.
assert membership["admin"], (
    f"is_member('{ROLES['admin']}') is false for {me}. PA-B/PA-C branch on this; without it the "
    "masking demo redacts for everyone and proves nothing."
)

# ...and at least one role must NOT resolve, or there is no contrast to demonstrate.
assert not all(membership.values()), (
    "the PA admin belongs to every role group — the masking demo needs a role they are NOT in"
)

# Grants landed at admin_demo scope for all three roles.
schema_grants = {(r["grantee"], r["privilege_type"]) for r in spark.sql(f"""
    SELECT grantee, privilege_type
    FROM {CATALOG}.information_schema.schema_privileges
    WHERE schema_name = 'admin_demo'
""").collect()}
for role, group in ROLES.items():
    assert any(g == group for g, _ in schema_grants), \
        f"{role} ({group}) holds no privilege on admin_demo"

# Least privilege: the student role must NOT hold schema-wide SELECT — its read is table-scoped.
student_privs = {p for g, p in schema_grants if g == ROLES["student"]}
assert "SELECT" not in student_privs, (
    f"student role has schema-wide SELECT on admin_demo; PA-04 requires object-level scoping. "
    f"Found: {student_privs}"
)

# The table-level grant that replaces it must exist.
table_grants = {(r["grantee"], r["table_name"]) for r in spark.sql(f"""
    SELECT grantee, table_name FROM {CATALOG}.information_schema.table_privileges
    WHERE table_schema = 'admin_demo'
""").collect()}
assert (ROLES["student"], "student") in table_grants, \
    "student role is missing its table-level SELECT on admin_demo.student"

print(f"PASS: PA-A — 3 roles mapped to UC-grantable account groups; is_member() resolves "
      f"'{[r for r, m in membership.items() if m][0]}' and not the others (real contrast for PA-B); "
      f"schema + table grants applied at admin_demo scope; student role is object-scoped.")
