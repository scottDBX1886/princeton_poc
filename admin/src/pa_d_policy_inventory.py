# Databricks notebook source
# MAGIC %md
# MAGIC # PA-D: Policy inventory & pre-rollout testing (PA-11, PA-12)
# MAGIC
# MAGIC | Scenario | Demonstrated by |
# MAGIC |---|---|
# MAGIC | PA-11 policy testing & validation ("faux user") | evaluate each role's treatment before rollout |
# MAGIC | PA-12 policy audit & documentation | catalog of every active mask and row filter |
# MAGIC
# MAGIC The reviewable SQL form is [`pa_d_policy_inventory.sql`](pa_d_policy_inventory.sql). This
# MAGIC notebook is the asserted path — it runs the inventory and fails loudly on a coverage gap or
# MAGIC a policy leak.
# MAGIC
# MAGIC ## On PA-11 — the "faux user" is RBAC role switching
# MAGIC There is no SQL impersonation *function*: `simulate_principal()`, `set_session_user()` and
# MAGIC `impersonate()` all return `UNRESOLVED_ROUTINE` (verified). A UC policy evaluates as the
# MAGIC caller, so no single session can self-test another identity by calling a function.
# MAGIC
# MAGIC But Databricks does support **assuming a role** — workspace-name menu → pick a role. That is
# MAGIC the faux-user mechanism this scenario asks for, and it is not a UI preview: while a role is
# MAGIC assumed it becomes the active SQL identity, and UC evaluates grants, row filters and column
# MAGIC masks against it. Verified in this workspace — as the `account users` role,
# MAGIC `session_user()` returns `account users` and `is_member('admins')` is `false`.
# MAGIC
# MAGIC So PA-11 has two mechanisms, in increasing strength:
# MAGIC 1. **Evaluate the policy logic** with the role parameterised — proves the branches are right,
# MAGIC    reproducible in one session, no identity switch. That is this notebook.
# MAGIC 2. **Assume the role and re-run** — proves UC *enforces* the policy. That is the real test,
# MAGIC    and it needs no colleague and no service principal.
# MAGIC
# MAGIC (1) alone does not prove enforcement, so this notebook reports it as branch-logic evidence and
# MAGIC points at (2) for the enforcement claim.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC `pa_bc_security_policies` (PA-B + PA-C) must have run — this inventories what they created.

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
dbutils.widgets.text("restricted_role", "account users")
dbutils.widgets.text("admin_group", "admins")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
RESTRICTED_ROLE = dbutils.widgets.get("restricted_role")
ADMIN_GROUP = dbutils.widgets.get("admin_group")

SILVER = f"{CATALOG}.silver{SUFFIX}"
ADMIN = f"{CATALOG}.admin_demo"
INFO = f"{CATALOG}.information_schema"
print(f"inventorying {CATALOG} | policy sandbox {ADMIN} | foundation {SILVER}")

# COMMAND ----------
# MAGIC %md ## PA-12 — Every column mask in the catalog
# MAGIC Unity Catalog exposes `information_schema.column_masks` and `row_filters` as purpose-built
# MAGIC views. That is the whole scenario: the policy catalog is a **table you can query**, not a
# MAGIC console screen you screenshot. No `DESCRIBE`-per-table loop, and no chance of missing a table
# MAGIC nobody remembered to check.
# COMMAND ----------
masks = spark.sql(f"""
    SELECT table_schema, table_name, column_name, mask_name, using_columns
    FROM {INFO}.column_masks
    ORDER BY table_schema, table_name, column_name
""")
display(masks)

# COMMAND ----------
# MAGIC %md ## PA-12 — Every row filter
# MAGIC `target_columns` is the `ON (…)` list — the columns feeding the filter function. It is how one
# MAGIC function serves several tables.
# COMMAND ----------
filters = spark.sql(f"""
    SELECT table_schema, table_name, filter_name, target_columns
    FROM {INFO}.row_filters
    ORDER BY table_schema, table_name
""")
display(filters)

# COMMAND ----------
# MAGIC %md ## PA-12 — What the policies actually do
# MAGIC Where a policy is attached is half the picture; this is the logic, so a reviewer can read the
# MAGIC branches without opening a notebook.
# COMMAND ----------
display(spark.sql(f"""
    SELECT routine_name, data_type AS returns, comment, routine_definition AS logic
    FROM {INFO}.routines
    WHERE routine_schema = 'admin_demo'
    ORDER BY routine_name
"""))

# COMMAND ----------
# MAGIC %md ## The coverage-gap check — the query an auditor actually wants
# MAGIC Not *"list the policies"* but *"list the sensitive columns with **no** policy."* The usual
# MAGIC failure in a governed estate isn't a wrong policy, it's an unprotected table nobody
# MAGIC inventoried.
# MAGIC
# MAGIC **Read the output honestly:** the `silver` rows come back `UNPROTECTED`, and that is
# MAGIC *correct here* — the shared foundation deliberately carries no policies (spec §3.1) so masking
# MAGIC never changes what the other personas read. In a real deployment those same rows would be
# MAGIC the finding, which is exactly why the check earns its place.
# COMMAND ----------
coverage = spark.sql(f"""
    SELECT c.table_schema, c.table_name, c.column_name, c.data_type,
           CASE WHEN m.mask_name IS NULL THEN 'UNPROTECTED' ELSE m.mask_name END AS mask_status
    FROM {INFO}.columns c
    LEFT JOIN {INFO}.column_masks m
           ON  c.table_schema = m.table_schema
           AND c.table_name   = m.table_name
           AND c.column_name  = m.column_name
    WHERE c.table_schema IN ('admin_demo', 'silver{SUFFIX}')
      AND (lower(c.column_name) LIKE '%ssn%'
        OR lower(c.column_name) LIKE '%dob%'
        OR lower(c.column_name) LIKE '%amount%'
        OR lower(c.column_name) LIKE '%email%')
    ORDER BY mask_status, c.table_schema, c.table_name, c.column_name
""")
display(coverage)

# COMMAND ----------
# MAGIC %md ## PA-11 (1) — Pre-rollout test harness
# MAGIC A parameterised twin of the production mask: same branch logic, identity as an argument
# MAGIC instead of a `session_user()` call. That makes every treatment testable from one session,
# MAGIC before anything is attached to a table.
# MAGIC
# MAGIC This proves the **branch logic**. It does not prove enforcement — for that, assume the role
# MAGIC and re-run PA-B/PA-C, which is mechanism (2) in the next cell.
# MAGIC
# MAGIC Named `test_…` and dropped at the end, so it can never be mistaken for a live policy.
# COMMAND ----------
spark.sql(f"""
CREATE OR REPLACE FUNCTION {ADMIN}.test_mask_ssn_as(ssn STRING, acting_as STRING)
RETURNS STRING
COMMENT 'PA-11 TEST HARNESS ONLY — mirrors mask_ssn with the identity parameterised. Never SET as a mask.'
RETURN CASE
    WHEN acting_as = '{RESTRICTED_ROLE}' THEN NULL              -- PA-08 full restriction
    WHEN acting_as = 'admin'             THEN ssn
    ELSE concat('***-**-', right(ssn, 4))                       -- PA-07 partial
END
""")

harness = spark.sql(f"""
    SELECT s.ssn                                                 AS true_value,
           {ADMIN}.test_mask_ssn_as(s.ssn, 'admin')              AS as_admin,
           {ADMIN}.test_mask_ssn_as(s.ssn, 'other')              AS as_faculty,
           {ADMIN}.test_mask_ssn_as(s.ssn, '{RESTRICTED_ROLE}')  AS as_student
    FROM (SELECT ssn FROM {SILVER}.student ORDER BY student_id LIMIT 3) s
""")
display(harness)

# COMMAND ----------
# MAGIC %md ### PA-11 (1) — row-filter equivalent
# MAGIC How many rows each identity keeps. The third row is the one that matters: **deny by default**,
# MAGIC not "see everything if unmapped."
# MAGIC
# MAGIC Read from the unpolicied foundation and evaluate the predicate directly, so this reports the
# MAGIC same numbers whoever runs it — the sandbox's own filter would otherwise skew the admin row.
# COMMAND ----------
row_test = spark.sql(f"""
    SELECT 'admin (unrestricted)' AS acting_as, count(*) AS rows_visible
    FROM {SILVER}.student
    UNION ALL
    SELECT 'restricted role ({RESTRICTED_ROLE})', count(*)
    FROM {SILVER}.student
    WHERE dept_id IN (SELECT dept_id FROM {ADMIN}.department_access
                      WHERE principal = '{RESTRICTED_ROLE}')
    UNION ALL
    SELECT 'unmapped principal', count(*)
    FROM {SILVER}.student
    WHERE dept_id IN (SELECT dept_id FROM {ADMIN}.department_access
                      WHERE principal = 'nobody@example.invalid')
""")
display(row_test)

# COMMAND ----------
# MAGIC %md ## PA-11 (2) — The enforcement test: assume the role
# MAGIC Mechanism (1) above proves the branch logic is right. It does **not** prove Unity Catalog
# MAGIC enforces it — the queries ran as you, with the identity supplied as a string argument.
# MAGIC
# MAGIC The enforcement test is a real identity switch, and it needs no colleague and no service
# MAGIC principal:
# MAGIC
# MAGIC 1. Workspace-name menu (top right) → hover the workspace → pick **`account users`**
# MAGIC 2. Re-run `pa_b_column_masking` and `pa_c_row_filters`. Both detect the assumed role and
# MAGIC    switch to their restricted assertions.
# MAGIC 3. Expect: `ssn` and `dob` return **NULL**, and `student` returns only the mapped departments.
# MAGIC 4. Switch back the same way.
# MAGIC
# MAGIC This cell records which mode the current session is in, so a screenshot of the notebook is
# MAGIC self-documenting about which identity produced the numbers above.
# COMMAND ----------
who = spark.sql(f"""
    SELECT session_user()                 AS session_user,
           is_member('{ADMIN_GROUP}')     AS is_member_admins
""").first()
acting_as_role = who["session_user"] == RESTRICTED_ROLE

print(f"session_user()             = {who['session_user']}")
print(f"is_member('{ADMIN_GROUP}') = {who['is_member_admins']}")
print(f"mode                       = {'ACTING AS THE RESTRICTED ROLE' if acting_as_role else 'own identity (admin)'}")
print()
if acting_as_role:
    print("Enforcement test IS live in this session. The policies are being applied to you by UC.")
else:
    print(f"Branch-logic evidence only. For the enforcement claim, switch to '{RESTRICTED_ROLE}'")
    print("and re-run PA-B / PA-C as described above.")

# COMMAND ----------
# MAGIC %md ## Who can rewrite a policy?
# MAGIC The privilege-escalation check, and the subtlest failure in the set. A restricted principal
# MAGIC holding `CREATE FUNCTION` or `MODIFY` on `admin_demo` could `CREATE OR REPLACE` the mask
# MAGIC function and lift its own restriction — the inventory would still report the policy as
# MAGIC "attached" while it did nothing.
# MAGIC
# MAGIC The same argument applies to `admin_demo.department_access`: write access to the mapping table
# MAGIC is write access to the row-filter policy. Expect the owner/admin only — the restricted role
# MAGIC should appear with `USE_SCHEMA` and its single table `SELECT`, nothing more.
# COMMAND ----------
display(spark.sql(f"""
    SELECT grantee, privilege_type
    FROM {INFO}.schema_privileges
    WHERE schema_name = 'admin_demo'
      AND privilege_type IN ('ALL_PRIVILEGES', 'CREATE_FUNCTION', 'MODIFY')
    ORDER BY grantee, privilege_type
"""))

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
mask_rows = masks.collect()
filter_rows = filters.collect()

# PA-B's four masks and PA-C's two filters must all be present.
assert len(mask_rows) >= 4, f"expected at least 4 column masks, found {len(mask_rows)} — has PA-B run?"
assert len(filter_rows) >= 2, f"expected at least 2 row filters, found {len(filter_rows)} — has PA-C run?"

expected_masks = {("student", "ssn"), ("student", "dob"),
                  ("faculty", "ssn"), ("financial_aid", "amount")}
found_masks = {(r["table_name"], r["column_name"]) for r in mask_rows if r["table_schema"] == "admin_demo"}
missing = expected_masks - found_masks
assert not missing, f"masks missing from the inventory: {missing}"

# THE critical one: no policy may sit outside admin_demo. A mask on the shared foundation would
# change what all ~20 session participants see.
leaked = [f"{r['table_schema']}.{r['table_name']}.{r['column_name']}"
          for r in mask_rows if r["table_schema"] != "admin_demo"]
leaked += [f"{r['table_schema']}.{r['table_name']}"
           for r in filter_rows if r["table_schema"] != "admin_demo"]
assert not leaked, f"policies found OUTSIDE admin_demo: {leaked}"

# Every sensitive column in admin_demo must be covered — this is the gap check with teeth.
gaps = [f"{r['table_name']}.{r['column_name']}" for r in coverage.collect()
        if r["table_schema"] == "admin_demo" and r["mask_status"] == "UNPROTECTED"
        and "email" not in r["column_name"].lower()]   # email is not classified sensitive here
assert not gaps, f"sensitive columns in admin_demo with no mask: {gaps}"

# PA-11: the three treatments must be genuinely different, or the policy isn't discriminating.
h = harness.first()
assert h["as_admin"] == h["true_value"], "admin treatment altered the value — policy is over-broad"
assert h["as_faculty"] != h["true_value"] and h["as_faculty"].endswith(h["true_value"][-4:]), \
    f"faculty treatment wrong: {h['as_faculty']} (expected ***-**-{h['true_value'][-4:]})"
assert h["as_student"] is None, \
    f"student treatment returned {h['as_student']!r} — PA-08 requires full restriction (NULL)"

# PA-11 row filter: all / subset / none.
rt = {r["acting_as"]: r["rows_visible"] for r in row_test.collect()}
restricted_key = f"restricted role ({RESTRICTED_ROLE})"
assert rt["unmapped principal"] == 0, \
    f"an unmapped principal would see {rt['unmapped principal']} rows — should be deny-by-default"
assert 0 < rt[restricted_key] < rt["admin (unrestricted)"], (
    f"the restricted role sees {rt[restricted_key]} of {rt['admin (unrestricted)']} — expected a "
    f"strict subset. If it is 0, the mapping table has no row for '{RESTRICTED_ROLE}' (session_user() "
    f"returns the ROLE NAME while a role is assumed, not an email)."
)

# The dob mask must not silently null rows through a failed date parse.
#
# Counting NULLs in admin_demo.student does NOT test this: as an admin you get the unmasked branch,
# which returns dob unparsed, so the coalesce never runs and the check passes even when broken.
# Evaluate the parse expression itself, over every row of the unpolicied source.
parse_check = spark.sql(f"""
    SELECT count(*) AS total,
           sum(CASE WHEN coalesce(
                    try_to_date(dob, 'yyyy-MM-dd'),
                    try_to_date(dob, 'MM/dd/yyyy'),
                    try_to_date(dob, 'dd.MM.yyyy')) IS NULL THEN 1 ELSE 0 END) AS unparseable
    FROM {SILVER}.student
""").first()
assert parse_check["unparseable"] == 0, (
    f"{parse_check['unparseable']:,} of {parse_check['total']:,} dob values match none of the three "
    f"formats — the masked branch would return NULL-XX-XX for them"
)

print(f"PASS: PA-D — {len(mask_rows)} masks + {len(filter_rows)} row filters inventoried, all "
      f"scoped to admin_demo; no sensitive column in the sandbox is unprotected; the three "
      f"treatments are distinct (full / partial / NULL); unmapped principals see 0 rows; all "
      f"{parse_check['total']:,} dob values parse across the 3 formats.")

# COMMAND ----------
# MAGIC %md ## Cleanup
# MAGIC Drop the test harness so it cannot be mistaken for a live policy in a later inventory.
# COMMAND ----------
spark.sql(f"DROP FUNCTION IF EXISTS {ADMIN}.test_mask_ssn_as")
remaining = spark.sql(f"""
    SELECT routine_name FROM {INFO}.routines
    WHERE routine_schema = 'admin_demo' AND routine_name LIKE 'test_%'
""").count()
assert remaining == 0, "test harness function was not dropped"
print("test harness dropped; only production policy functions remain in admin_demo.")
