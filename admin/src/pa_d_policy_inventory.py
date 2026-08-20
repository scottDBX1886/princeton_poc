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
# MAGIC ## On PA-11 — there is no impersonation function
# MAGIC The phase-4 plan suggested `simulate_principal()` via UCX. **It does not exist** — verified,
# MAGIC along with `set_session_user()` and `impersonate()`; all return `UNRESOLVED_ROUTINE`. A UC
# MAGIC policy is evaluated as the **caller**, so no single session can self-test another identity.
# MAGIC
# MAGIC Two honest mechanisms instead, and the difference matters:
# MAGIC 1. **Evaluate the policy logic** with the role parameterised — proves the branches are right.
# MAGIC 2. **Have a second real principal run the query** — proves UC *enforces* it.
# MAGIC
# MAGIC (1) is what you can do alone and is in this notebook. (2) is the stronger test and needs a
# MAGIC colleague; the SQL file documents it as a pre-session checklist item. Claiming (1) proves
# MAGIC enforcement would be overstating it.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC `pa_bc_security_policies` (PA-B + PA-C) must have run — this inventories what they created.

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc")
dbutils.widgets.text("schema_suffix", "")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")

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
# MAGIC %md ## PA-11 — Pre-rollout test harness
# MAGIC A parameterised twin of the production mask: same branch logic, role as an argument instead
# MAGIC of an `is_member()` call. That makes all three treatments testable from one session, before
# MAGIC anything is attached to a table.
# MAGIC
# MAGIC Named `test_…` and dropped at the end, so it can never be mistaken for a live policy.
# COMMAND ----------
spark.sql(f"""
CREATE OR REPLACE FUNCTION {ADMIN}.test_mask_ssn_as(ssn STRING, role STRING)
RETURNS STRING
COMMENT 'PA-11 TEST HARNESS ONLY — mirrors mask_ssn with the role parameterised. Never SET as a mask.'
RETURN CASE
    WHEN role = 'admin'   THEN ssn
    WHEN role = 'faculty' THEN concat('***-**-', right(ssn, 4))
    ELSE NULL
END
""")

harness = spark.sql(f"""
    SELECT s.ssn                                           AS true_value,
           {ADMIN}.test_mask_ssn_as(s.ssn, 'admin')        AS as_admin,
           {ADMIN}.test_mask_ssn_as(s.ssn, 'faculty')      AS as_faculty,
           {ADMIN}.test_mask_ssn_as(s.ssn, 'student')      AS as_student
    FROM (SELECT ssn FROM {SILVER}.student ORDER BY student_id LIMIT 3) s
""")
display(harness)

# COMMAND ----------
# MAGIC %md ### PA-11 — row-filter equivalent
# MAGIC How many rows each identity keeps. The third row is the one that matters: **deny by default**,
# MAGIC not "see everything if unmapped."
# COMMAND ----------
row_test = spark.sql(f"""
    SELECT 'admin (unrestricted)' AS acting_as, count(*) AS rows_visible
    FROM {SILVER}.student
    UNION ALL
    SELECT 'mapped non-admin', count(*)
    FROM {SILVER}.student
    WHERE dept_id IN (SELECT dept_id FROM {ADMIN}.department_access
                      WHERE principal = current_user())
    UNION ALL
    SELECT 'unmapped principal', count(*)
    FROM {SILVER}.student
    WHERE dept_id IN (SELECT dept_id FROM {ADMIN}.department_access
                      WHERE principal = 'nobody@example.invalid')
""")
display(row_test)

# COMMAND ----------
# MAGIC %md ## Who can rewrite a policy?
# MAGIC The privilege-escalation check. A faculty principal with `CREATE FUNCTION` on `admin_demo`
# MAGIC could `CREATE OR REPLACE` the mask function and lift their own restriction — the policy would
# MAGIC still show as "attached" in the inventory while doing nothing. Expect the admin group only.
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
assert rt["unmapped principal"] == 0, \
    f"an unmapped principal would see {rt['unmapped principal']} rows — should be deny-by-default"
assert 0 < rt["mapped non-admin"] < rt["admin (unrestricted)"], \
    f"mapped identity sees {rt['mapped non-admin']} of {rt['admin (unrestricted)']} — expected a strict subset"

# The dob mask must not have nulled rows via a failed date parse.
dob_nulls = spark.sql(f"SELECT count(*) AS n FROM {ADMIN}.student WHERE dob IS NULL").first()["n"]
assert dob_nulls == 0, f"{dob_nulls} rows have NULL dob — the three-format coalesce is incomplete"

print(f"PASS: PA-D — {len(mask_rows)} masks + {len(filter_rows)} row filters inventoried, all "
      f"scoped to admin_demo; no sensitive column in the sandbox is unprotected; the three role "
      f"treatments are distinct (full / partial / NULL); unmapped principals see 0 rows.")

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
