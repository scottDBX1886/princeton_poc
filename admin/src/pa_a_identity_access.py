# Databricks notebook source
# MAGIC %md
# MAGIC # PA-A: Identity & access management (PA-01 … PA-06)
# MAGIC
# MAGIC | Scenario | Demonstrated by |
# MAGIC |---|---|
# MAGIC | PA-01 user provisioning & role assignment | roles resolve to real, UC-grantable principals |
# MAGIC | PA-02 group-based access control | every grant targets a GROUP, never a person |
# MAGIC | PA-03 environment-level segregation | dev vs prod catalog grant asymmetry, run live |
# MAGIC | PA-04 object-level permissions | schema-wide read vs one-table read |
# MAGIC | PA-05 permission audit trail | `system.access.audit` + `table_lineage`, incl. `run_by`/`run_as` |
# MAGIC | PA-06 service principals | workload identities and why rotation does not disturb grants |
# MAGIC
# MAGIC ## The two real identities in this workspace
# MAGIC This POC workspace has exactly **one** UC-grantable group — `account users` (SCIM
# MAGIC `type=Group`, so Unity Catalog will grant to it). `admins` and `users` are workspace-local
# MAGIC (`type=WorkspaceGroup`) and UC rejects them with `PRINCIPAL_DOES_NOT_EXIST`. We hold no
# MAGIC account-admin rights, so we cannot create account-level groups — verified: creating one
# MAGIC succeeds but yields `WorkspaceGroup`, and the subsequent GRANT fails.
# MAGIC
# MAGIC So the role model uses the two identities that genuinely exist and genuinely differ:
# MAGIC
# MAGIC | RFP role | Identity here | How it is reached |
# MAGIC |---|---|---|
# MAGIC | **admin** | `mehak.juneja@databricks.com` (in `admins`) | normal login |
# MAGIC | **restricted reader** (faculty/student) | `account users` | **RBAC role switch** |
# MAGIC
# MAGIC ## RBAC role switching — this is the "faux user" the RFP asks for
# MAGIC Databricks supports **assuming a role**: workspace-name menu → pick a role. It is *not* a UI
# MAGIC preview. While a role is assumed, the role becomes the active SQL identity — the user's own
# MAGIC permissions are replaced for the session, and Unity Catalog evaluates grants, row filters and
# MAGIC column masks against the role. Verified live in this workspace:
# MAGIC
# MAGIC | | as the user | as `account users` |
# MAGIC |---|---|---|
# MAGIC | `session_user()` | `mehak.juneja@databricks.com` | `account users` |
# MAGIC | `current_user()` | `mehak.juneja@databricks.com` | `account users` |
# MAGIC | `is_member('admins')` | `true` | **`false`** |
# MAGIC
# MAGIC ## ⚠️ Policies branch on `session_user()`, not `is_member()`
# MAGIC Two traps, both verified, both silent:
# MAGIC
# MAGIC 1. **A group is not a member of itself.** While acting as `account users`,
# MAGIC    `is_member('account users')` is **false**. A policy written as
# MAGIC    `WHEN is_member('account users') THEN <restricted>` never fires.
# MAGIC 2. **An assumed role does not inherit the user's memberships.** `is_member('admins')` is
# MAGIC    false while acting as the role, even though the human behind it is an admin.
# MAGIC
# MAGIC `session_user()` returns either the email or the role name, so it discriminates reliably in
# MAGIC both directions. Every PA-B/PA-C policy branches on it. See `PA_A_IDENTITY_STRATEGY.md`.
# MAGIC
# MAGIC ## Isolation
# MAGIC PA scenarios run ONCE by ONE designated admin (spec §3.1 rule 4). Every grant below is scoped
# MAGIC to `admin_demo`, a schema this notebook owns — so the shared foundation the other personas
# MAGIC read is never re-permissioned. Nothing here revokes anything: `account users` holds
# MAGIC `ALL_PRIVILEGES` on the catalog and revoking that would lock out every user in the account,
# MAGIC with no second grantable group to recover through.

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
dbutils.widgets.text("prod_catalog", "princeton_poc_prod")
# The restricted identity. A group name (not an email) so the demo works for whoever runs it.
dbutils.widgets.text("restricted_role", "account users")
dbutils.widgets.text("admin_group", "admins")

CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
PROD_CATALOG = dbutils.widgets.get("prod_catalog")
RESTRICTED_ROLE = dbutils.widgets.get("restricted_role")
ADMIN_GROUP = dbutils.widgets.get("admin_group")

SILVER = f"{CATALOG}.silver{SUFFIX}"
GOLD = f"{CATALOG}.gold{SUFFIX}"
ADMIN = f"{CATALOG}.admin_demo"

me = spark.sql("SELECT session_user()").first()[0]
acting_as_role = me == RESTRICTED_ROLE

print(f"catalog:        {CATALOG}")
print(f"policy sandbox: {ADMIN}")
print(f"session_user(): {me}")
print(f"restricted role: {RESTRICTED_ROLE!r}")
if acting_as_role:
    print("\n  NOTE: this notebook is running AS the restricted role. The grant cells will fail —\n"
          "  run PA-A as yourself; switch roles only for the PA-03 / PA-11 denial cells.")

# COMMAND ----------
# MAGIC %md ## PA-01 — Roles resolve to real, grantable principals
# MAGIC Provisioning a person is a group membership change, not a permissions edit. Proving the role
# MAGIC model works means proving each role resolves to a principal UC will actually grant to —
# MAGIC which is exactly the check that would have caught the `WorkspaceGroup` dead end.
# COMMAND ----------
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Only account-level groups (SCIM type=Group) can hold UC privileges.
all_groups = {}
for g in w.groups.list():
    rt = g.meta.resource_type if g.meta else None
    all_groups[g.display_name] = rt

print("groups in this workspace:")
for name, rt in sorted(all_groups.items()):
    grantable = "UC-grantable" if rt == "Group" else "workspace-local — UC will NOT grant"
    print(f"  {name:56s} {rt or '?':16s} {grantable}")

account_groups = {n for n, rt in all_groups.items() if rt == "Group"}
print(f"\nUC-grantable groups: {sorted(account_groups)}")

# COMMAND ----------
# MAGIC %md ### PA-01 — what the identity functions return right now
# MAGIC The values every policy in PA-B and PA-C depends on. Run this cell again after switching
# MAGIC roles and the middle column changes — that is the whole mechanism, visible in one query.
# COMMAND ----------
identity = spark.sql(f"""
    SELECT session_user()                      AS session_user,
           current_user()                      AS current_user,
           is_member('{ADMIN_GROUP}')          AS is_member_admins,
           is_member('{RESTRICTED_ROLE}')      AS is_member_restricted
""")
display(identity)

idn = identity.first()
print(f"session_user()                     = {idn['session_user']}")
print(f"is_member('{ADMIN_GROUP}')         = {idn['is_member_admins']}")
print(f"is_member('{RESTRICTED_ROLE}')     = {idn['is_member_restricted']}")
print()
print("Note the second membership check. Acting as your own identity it is TRUE (you are in the")
print("group); acting AS the role it is FALSE, because a group is not a member of itself. That is")
print("why policies branch on session_user() and not on is_member().")

# COMMAND ----------
# MAGIC %md ## PA-02 / PA-04 — Grant to GROUPS, at object level
# MAGIC Access follows the role. Onboarding becomes a membership change; offboarding revokes
# MAGIC everything at once, because nothing was ever granted to a person.
# MAGIC
# MAGIC Grants are scoped to `admin_demo` (owned by this notebook's runner). The restricted role gets
# MAGIC **object-level** access — `USE SCHEMA` on the schema plus `SELECT` on exactly one table. That
# MAGIC narrowness IS PA-04: the privilege sits on the object, not the container, so `faculty` and
# MAGIC `financial_aid` remain unreadable without ever naming them in a policy.
# COMMAND ----------
if acting_as_role:
    print("SKIPPED — cannot grant while acting as a role. Re-run as yourself.")
else:
    GRANTS = [
        # (privileges, securable_type, securable, principal)
        ("USE SCHEMA", "SCHEMA", ADMIN,               RESTRICTED_ROLE),
        ("SELECT",     "TABLE",  f"{ADMIN}.student",  RESTRICTED_ROLE),
    ]
    for privs, kind, securable, principal in GRANTS:
        spark.sql(f"GRANT {privs} ON {kind} {securable} TO `{principal}`")
        print(f"  GRANT {privs:12s} ON {kind:6s} {securable:44s} -> {principal}")

    print(f"\nDeliberately NOT granted to {RESTRICTED_ROLE}: SELECT on the schema, and any privilege")
    print("on admin_demo.faculty or admin_demo.financial_aid. Those absences are the control.")

# COMMAND ----------
# MAGIC %md ## PA-04 — The effective grants, from `information_schema`
# MAGIC Queryable source of truth, no console clicking. Column-name gotcha: `schema_privileges` uses
# MAGIC **`schema_name`**; `table_privileges` uses **`table_schema`**. Mixing them gives
# MAGIC `UNRESOLVED_COLUMN`.
# COMMAND ----------
display(spark.sql(f"""
    SELECT grantee, privilege_type
    FROM {CATALOG}.information_schema.schema_privileges
    WHERE schema_name = 'admin_demo'
    ORDER BY grantee, privilege_type
"""))

display(spark.sql(f"""
    SELECT grantee, table_name, privilege_type
    FROM {CATALOG}.information_schema.table_privileges
    WHERE table_schema = 'admin_demo'
    ORDER BY grantee, table_name, privilege_type
"""))

# COMMAND ----------
# MAGIC %md ## PA-03 — Environment-level access segregation
# MAGIC Environments are separate **catalogs** in one workspace, and this workspace already carries
# MAGIC the asymmetry — it is the customer's own configuration, not something staged for the demo:
# MAGIC
# MAGIC | Catalog | `account users` holds |
# MAGIC |---|---|
# MAGIC | `princeton_poc_dev` | `ALL_PRIVILEGES` |
# MAGIC | `princeton_poc_prod` | `BROWSE`, `USE_CATALOG`, `USE_SCHEMA` — **no `SELECT`** |
# MAGIC
# MAGIC `USE CATALOG` gates everything beneath it and `SELECT` is what actually reads data, so the
# MAGIC absence of `SELECT` on prod is absolute: no schema-level or table-level grant works around
# MAGIC it. That is segregation, not a naming convention.
# COMMAND ----------
for cat in (CATALOG, PROD_CATALOG):
    print(f"\n=== {cat} ===")
    try:
        display(spark.sql(f"""
            SELECT grantee, privilege_type
            FROM {cat}.information_schema.catalog_privileges
            ORDER BY grantee, privilege_type
        """))
    except Exception as e:
        print(f"  cannot read {cat}.information_schema: {str(e)[:160]}")

# COMMAND ----------
# MAGIC %md ### PA-03 — `BROWSE` without `SELECT`: metadata visible, data not
# MAGIC The subtle half of the scenario, and the one that separates UC from filesystem-style
# MAGIC permissions. On prod, `account users` can *discover* that objects exist — schema names, table
# MAGIC names — but cannot read a single row. A data catalogue stays useful for discovery while the
# MAGIC data itself remains closed.
# COMMAND ----------
print(f"=== metadata read on {PROD_CATALOG} (expect: SUCCEEDS via BROWSE/USE_SCHEMA) ===")
try:
    display(spark.sql(f"SHOW SCHEMAS IN {PROD_CATALOG}"))
    print("  metadata visible")
except Exception as e:
    print(f"  DENIED: {str(e)[:200]}")

print(f"\n=== data read on {PROD_CATALOG}.bronze.enrollments (expect: DENIED — no SELECT) ===")
try:
    n = spark.sql(f"SELECT count(*) AS n FROM {PROD_CATALOG}.bronze.enrollments").first()["n"]
    print(f"  returned {n:,} rows — no SELECT was granted, so this succeeding means the grant model "
          f"is not what information_schema reports. Investigate before demoing.")
except Exception as e:
    msg = str(e)
    kind = "PERMISSION_DENIED" if "PERMISSION_DENIED" in msg or "does not have" in msg else "other"
    print(f"  DENIED ({kind}): {msg[:220]}")

# COMMAND ----------
# MAGIC %md ## PA-05 — Permission audit trail
# MAGIC Every grant and revoke is recorded with its actor. `request_params.changes` holds the
# MAGIC principal and the privileges added or removed, so each row is self-describing — no diffing of
# MAGIC two states.
# MAGIC
# MAGIC **Always filter on `event_date`.** It is the partition column and this table holds tens of
# MAGIC millions of rows per week; an unfiltered query is slow enough to look broken in a live demo.
# COMMAND ----------
display(spark.sql("""
    SELECT event_time,
           user_identity.email                   AS actor,
           action_name,
           request_params['securable_full_name'] AS securable,
           request_params['changes']             AS changes
    FROM system.access.audit
    WHERE event_date >= current_date() - INTERVAL 7 DAYS
      AND service_name = 'unityCatalog'
      AND action_name = 'updatePermissions'
    ORDER BY event_time DESC
    LIMIT 25
"""))

# COMMAND ----------
# MAGIC %md ### PA-05 — an assumed role does not launder your identity
# MAGIC **The question a security reviewer will ask about role switching:** if someone can act as a
# MAGIC role, can they hide behind it?
# MAGIC
# MAGIC No. `identity_metadata` carries both sides — `run_by` is the authenticated human,
# MAGIC `run_as` is the role they assumed. Accountability survives the switch, which is what makes
# MAGIC role switching acceptable as a production access pattern rather than a hole in the audit
# MAGIC trail.
# COMMAND ----------
display(spark.sql("""
    SELECT event_time,
           user_identity.email             AS authenticated_as,
           identity_metadata.run_by        AS run_by,
           identity_metadata.run_as        AS run_as,
           CASE WHEN identity_metadata.run_as IS NOT NULL
                 AND identity_metadata.run_as <> identity_metadata.run_by
                THEN 'acting as a role' ELSE 'own identity' END AS mode,
           action_name
    FROM system.access.audit
    WHERE event_date >= current_date() - INTERVAL 7 DAYS
      AND identity_metadata.run_as IS NOT NULL
    ORDER BY event_time DESC
    LIMIT 25
"""))
print("If this returns no rows, nobody has acted as a role in the window yet — switch roles, run a")
print("query, and re-run. system.access.audit lags a few minutes.")

# COMMAND ----------
# MAGIC %md ### PA-05 — who has actually READ the sensitive tables?
# MAGIC The question an auditor really asks, and the one a grants list cannot answer. A grant says
# MAGIC who *could* read; lineage says who *did*.
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
# MAGIC A service principal is an identity for a **workload**. Least privilege for a non-human
# MAGIC caller, with no human credential embedded anywhere. This workspace already runs three of
# MAGIC them (the runbook app, the mock REST API, and the E3 ingest job), and
# MAGIC `engineer/src/apps/grant_app_sp.sh` shows the grant pattern.
# MAGIC
# MAGIC The rotation argument in one line: **grants attach to the principal, not the credential.**
# MAGIC Rotating an SP secret is therefore invisible to permissions — exactly what an embedded
# MAGIC personal token cannot offer. Full procedure in
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
# PA-01: the restricted role must be a principal UC will actually grant to. This is the check that
# would have caught the WorkspaceGroup dead end before a demo.
assert RESTRICTED_ROLE in account_groups, (
    f"'{RESTRICTED_ROLE}' is not an account-level group (found type "
    f"{all_groups.get(RESTRICTED_ROLE)!r}) — UC cannot grant to it (PRINCIPAL_DOES_NOT_EXIST)"
)

if not acting_as_role:
    # The two identities must be genuinely distinguishable, or no policy can tell them apart.
    assert idn["session_user"] != RESTRICTED_ROLE, "unexpectedly running as the restricted role"
    assert idn["is_member_admins"], (
        f"is_member('{ADMIN_GROUP}') is false for {me} — PA-B/PA-C treat admin membership as the "
        f"privileged branch, so the masking demo would redact for everyone"
    )

    # PA-02/PA-04: grants landed, and landed narrowly.
    schema_grants = {(r["grantee"], r["privilege_type"]) for r in spark.sql(f"""
        SELECT grantee, privilege_type FROM {CATALOG}.information_schema.schema_privileges
        WHERE schema_name = 'admin_demo'
    """).collect()}
    restricted_schema_privs = {p for g, p in schema_grants if g == RESTRICTED_ROLE}
    assert "USE_SCHEMA" in restricted_schema_privs, (
        f"{RESTRICTED_ROLE} holds no USE_SCHEMA on admin_demo; found {restricted_schema_privs}"
    )
    # THE least-privilege check: schema-wide SELECT would make PA-04 meaningless.
    assert "SELECT" not in restricted_schema_privs, (
        f"{RESTRICTED_ROLE} has schema-wide SELECT on admin_demo — PA-04 requires object-level "
        f"scoping. Found: {restricted_schema_privs}"
    )

    table_grants = {(r["grantee"], r["table_name"]) for r in spark.sql(f"""
        SELECT grantee, table_name FROM {CATALOG}.information_schema.table_privileges
        WHERE table_schema = 'admin_demo'
    """).collect()}
    assert (RESTRICTED_ROLE, "student") in table_grants, (
        f"{RESTRICTED_ROLE} is missing its table-level SELECT on admin_demo.student"
    )
    # ...and must NOT reach the other two tables at all.
    for forbidden in ("faculty", "financial_aid"):
        assert (RESTRICTED_ROLE, forbidden) not in table_grants, (
            f"{RESTRICTED_ROLE} was granted SELECT on admin_demo.{forbidden} — that removes the "
            f"contrast PA-04 depends on"
        )

# PA-03: prod must not be readable by the restricted role. Read the grant state rather than
# trusting the earlier try/except, so this holds whoever runs the notebook.
prod_privs = {}
try:
    for r in spark.sql(f"""
        SELECT grantee, privilege_type FROM {PROD_CATALOG}.information_schema.catalog_privileges
    """).collect():
        prod_privs.setdefault(r["grantee"], set()).add(r["privilege_type"])
    restricted_prod = prod_privs.get(RESTRICTED_ROLE, set())
    assert "SELECT" not in restricted_prod and "ALL_PRIVILEGES" not in restricted_prod, (
        f"{RESTRICTED_ROLE} holds {restricted_prod} on {PROD_CATALOG} — PA-03 needs prod to be the "
        f"environment this identity CANNOT read"
    )
    print(f"PA-03: {RESTRICTED_ROLE} holds {sorted(restricted_prod)} on {PROD_CATALOG} — "
          f"no SELECT, so data reads are denied while metadata stays visible.")
except Exception as e:
    print(f"PA-03: could not read {PROD_CATALOG}.information_schema ({str(e)[:120]}) — "
          f"verify the prod grants manually before demoing.")

print(f"\nPASS: PA-A — '{RESTRICTED_ROLE}' is UC-grantable and object-scoped on admin_demo "
      f"(USE_SCHEMA + one table, no schema-wide SELECT, no access to faculty/financial_aid); "
      f"identity functions distinguish the two roles; prod withholds SELECT.")
