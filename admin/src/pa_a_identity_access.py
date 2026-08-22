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

    print(f"\nGranted explicitly to {RESTRICTED_ROLE}: USE_SCHEMA on the schema and SELECT on exactly")
    print("one table. Read the next cell before concluding anything about denial, though — in THIS")
    print("catalog those grants are redundant, and the reason is the interesting part.")

# COMMAND ----------
# MAGIC %md ## PA-04 — Object-level permissions, and why `inherited_from` is the column that matters
# MAGIC Queryable source of truth, no console clicking. Column-name gotcha: `schema_privileges` uses
# MAGIC **`schema_name`**; `table_privileges` uses **`table_schema`**. Mixing them gives
# MAGIC `UNRESOLVED_COLUMN`.
# MAGIC
# MAGIC ## ⚠️ Read `inherited_from`, not just `privilege_type`
# MAGIC **Unity Catalog privileges cascade downward.** `account users` holds `ALL_PRIVILEGES` on this
# MAGIC *catalog*, so it already has full access to every schema and table beneath — including any
# MAGIC schema created later. The `inherited_from` column makes that visible: `CATALOG` means the
# MAGIC privilege was never granted here at all, it descended.
# MAGIC
# MAGIC So in `princeton_poc_dev` **withholding a grant does not produce a denial** — there is nothing
# MAGIC to withhold. This is worth showing rather than hiding: it is the single most common
# MAGIC least-privilege mistake in a real UC estate. A team scopes a narrow grant on a table, believes
# MAGIC access is restricted, and a catalog-level `ALL_PRIVILEGES` two levels up has been overriding it
# MAGIC the whole time. `information_schema` is how you catch it, and the query below is the audit.
# MAGIC
# MAGIC The **denial** side of PA-04 is therefore demonstrated in `princeton_poc_prod`, where no such
# MAGIC inherited grant exists — see the next section.
# COMMAND ----------
display(spark.sql(f"""
    SELECT grantee, privilege_type, inherited_from
    FROM {CATALOG}.information_schema.schema_privileges
    WHERE schema_name = 'admin_demo'
    ORDER BY grantee, privilege_type
"""))

display(spark.sql(f"""
    SELECT grantee, table_name, privilege_type, inherited_from
    FROM {CATALOG}.information_schema.table_privileges
    WHERE table_schema = 'admin_demo'
    ORDER BY grantee, table_name, privilege_type
"""))

# COMMAND ----------
# MAGIC %md ### PA-04 — The over-permission audit
# MAGIC The query a governance reviewer actually wants: **which principals hold privileges they were
# MAGIC never explicitly granted?** Anything with `inherited_from` set is reaching this object from
# MAGIC above, and no object-level grant can narrow it — only revoking at the source can.
# MAGIC
# MAGIC In a real deployment this is the finding. Here it is expected, and the fix (revoking
# MAGIC `ALL_PRIVILEGES` from `account users`) is deliberately **not** applied: that group is every user
# MAGIC and service principal in the account, it is the only UC-grantable group in this workspace, and
# MAGIC the catalog owner is `account_admins` — so revoking it would lock out every user with no second
# MAGIC group to recover through.
# COMMAND ----------
display(spark.sql(f"""
    SELECT grantee,
           table_name,
           privilege_type,
           inherited_from,
           'reaches this table from above — object-level grants cannot narrow it' AS finding
    FROM {CATALOG}.information_schema.table_privileges
    WHERE table_schema = 'admin_demo'
      AND inherited_from IS NOT NULL
      AND inherited_from <> 'NONE'
    ORDER BY grantee, table_name
"""))
print("Every row here is a privilege that did NOT come from this schema or table. That is why the")
print("PA-04 denial is demonstrated against princeton_poc_prod instead, where nothing is inherited.")

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
# MAGIC
# MAGIC **This also carries PA-04's denial.** Because dev grants `ALL_PRIVILEGES` at catalog level and
# MAGIC privileges cascade, no object in dev can be made unreadable to `account users`. Prod grants no
# MAGIC `SELECT` at any level, so it is where object-level restriction is actually observable. The demo
# MAGIC is the same query against two catalogs, not two objects in one.
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
# MAGIC %md ### PA-03 / PA-04 — The paired query: same SQL, two environments
# MAGIC The demonstration. Identical statement shape, one returns rows and one is denied — and the
# MAGIC only difference is which catalog it names.
# MAGIC
# MAGIC Plus the subtle half that separates UC from filesystem-style permissions: on prod,
# MAGIC `account users` can *discover* that objects exist — schema and table names — while reading not
# MAGIC one row. A data catalogue stays useful for discovery with the data itself closed.
# COMMAND ----------
DEV_TABLE = f"{CATALOG}.bronze{SUFFIX}.enrollments_raw"
PROD_TABLE = f"{PROD_CATALOG}.bronze.enrollments"

results = {}

print(f"=== 1. metadata read on {PROD_CATALOG} (expect SUCCEEDS — BROWSE + USE_SCHEMA) ===")
try:
    display(spark.sql(f"SHOW SCHEMAS IN {PROD_CATALOG}"))
    results["prod_metadata"] = "visible"
    print("  metadata visible\n")
except Exception as e:
    results["prod_metadata"] = "denied"
    print(f"  DENIED: {str(e)[:200]}\n")

print(f"=== 2. data read in DEV — {DEV_TABLE} (expect SUCCEEDS) ===")
try:
    n = spark.sql(f"SELECT count(*) AS n FROM {DEV_TABLE}").first()["n"]
    results["dev_data"] = n
    print(f"  {n:,} rows\n")
except Exception as e:
    results["dev_data"] = None
    print(f"  UNEXPECTEDLY DENIED: {str(e)[:200]}\n")

print(f"=== 3. data read in PROD — {PROD_TABLE} (expect DENIED — no SELECT at any level) ===")
try:
    n = spark.sql(f"SELECT count(*) AS n FROM {PROD_TABLE}").first()["n"]
    results["prod_data"] = n
    print(f"  returned {n:,} rows. information_schema reports no SELECT on prod, so this succeeding "
          f"means the grant model is not what it appears — investigate before demoing.")
except Exception as e:
    msg = str(e)
    denied = "PERMISSION_DENIED" in msg or "does not have" in msg
    missing = "TABLE_OR_VIEW_NOT_FOUND" in msg or "does not exist" in msg
    results["prod_data"] = "denied" if denied else ("missing" if missing else "error")
    label = ("PERMISSION_DENIED — the access control is what stopped it" if denied else
             "TABLE NOT FOUND — this proves nothing about access control; pick a table that exists"
             if missing else "other error")
    print(f"  {label}\n  {msg[:220]}")

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

    # PA-02: the explicit grants landed. `inherited_from = 'NONE'` isolates what THIS notebook
    # granted from what descends from the catalog — without that filter the assertion cannot tell
    # the two apart, which is the mistake this whole section exists to document.
    explicit_schema = {r["privilege_type"] for r in spark.sql(f"""
        SELECT privilege_type FROM {CATALOG}.information_schema.schema_privileges
        WHERE schema_name = 'admin_demo' AND grantee = '{RESTRICTED_ROLE}'
          AND (inherited_from IS NULL OR inherited_from = 'NONE')
    """).collect()}
    assert "USE_SCHEMA" in explicit_schema, (
        f"{RESTRICTED_ROLE} holds no explicitly-granted USE_SCHEMA on admin_demo; found "
        f"{explicit_schema or 'nothing'}"
    )

    explicit_tables = {r["table_name"] for r in spark.sql(f"""
        SELECT table_name FROM {CATALOG}.information_schema.table_privileges
        WHERE table_schema = 'admin_demo' AND grantee = '{RESTRICTED_ROLE}'
          AND privilege_type = 'SELECT'
          AND (inherited_from IS NULL OR inherited_from = 'NONE')
    """).collect()}
    assert "student" in explicit_tables, (
        f"{RESTRICTED_ROLE} is missing its explicit table-level SELECT on admin_demo.student; "
        f"found {explicit_tables or 'nothing'}"
    )
    assert explicit_tables == {"student"}, (
        f"PA-04 grants exactly one table explicitly, but found {sorted(explicit_tables)} — a second "
        f"explicit grant widens access beyond what the scenario claims"
    )

    # PA-04: DO NOT assert that faculty/financial_aid are unreachable in this catalog. They are
    # reachable, and the reason is the finding: `account users` holds ALL_PRIVILEGES on the CATALOG,
    # and UC privileges cascade downward, so no object-level grant can narrow them. Assert the
    # inheritance is real and reported, so the notebook proves the mechanism instead of denying it.
    inherited = {(r["table_name"], r["privilege_type"]) for r in spark.sql(f"""
        SELECT table_name, privilege_type FROM {CATALOG}.information_schema.table_privileges
        WHERE table_schema = 'admin_demo' AND grantee = '{RESTRICTED_ROLE}'
          AND inherited_from IS NOT NULL AND inherited_from <> 'NONE'
    """).collect()}
    if inherited:
        print(f"NOTE: {RESTRICTED_ROLE} reaches {len({t for t, _ in inherited})} admin_demo table(s) "
              f"by INHERITANCE from the catalog: {sorted({t for t, _ in inherited})}.")
        print("      Object-level grants cannot narrow an inherited privilege — only revoking at the")
        print("      source can, and that is deliberately not done here (it would lock out every")
        print(f"      user in the account). The PA-04 denial is shown against {PROD_CATALOG} instead.")

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

# PA-03/PA-04: the paired query must actually have behaved as claimed — dev readable, prod denied.
# Asserting the OBSERVED outcome, not just the grant state, is what makes this a demo rather than a
# description.
assert results.get("dev_data") is not None, (
    f"the dev read failed — without a working 'allowed' side there is no pair to contrast"
)
assert results.get("prod_data") == "denied", (
    f"expected PERMISSION_DENIED reading {PROD_TABLE}, got {results.get('prod_data')!r}. "
    f"If 'missing', the table does not exist and the demo proves nothing about access control — "
    f"point it at a table that does exist in prod."
)
assert results.get("prod_metadata") == "visible", (
    f"metadata on {PROD_CATALOG} was not readable, so the BROWSE-without-SELECT contrast is lost"
)

print(f"\nPASS: PA-A — '{RESTRICTED_ROLE}' is UC-grantable, explicitly granted USE_SCHEMA + one "
      f"table SELECT on admin_demo; identity functions distinguish the two roles; and the paired "
      f"query behaved as claimed — {results['dev_data']:,} rows in dev, PERMISSION_DENIED in "
      f"{PROD_CATALOG}, with prod metadata still visible (BROWSE without SELECT).")
print("\nHonest caveat, stated in the notebook above: in dev, `account users` inherits "
      "ALL_PRIVILEGES\nfrom the catalog, so object-level grants there cannot produce a denial. That "
      "is why the\ndenial half of PA-03/PA-04 is demonstrated against prod.")
