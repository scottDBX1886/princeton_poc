# Databricks notebook source
# MAGIC %md
# MAGIC # PA-C: Row-level security (PA-09, PA-10)
# MAGIC
# MAGIC Oracle FGAC's row-level equivalent, in Unity Catalog. Two scenarios, and the difference
# MAGIC between them is the whole point:
# MAGIC
# MAGIC | Scenario | Demonstrated by |
# MAGIC |---|---|
# MAGIC | PA-09 attribute-based filtering | filter on a column value — `dept_id` — evaluated per reader |
# MAGIC | PA-10 dynamic policy by identity | the permitted values come from a **lookup table keyed on `current_user()`**, so nothing is hardcoded |
# MAGIC
# MAGIC PA-10 is the one that matters operationally. A policy with department numbers written into it
# MAGIC needs a code change and a redeploy every time someone moves department. A policy that reads a
# MAGIC mapping table needs an `INSERT` — and the change takes effect on the next query, for every
# MAGIC table the filter is attached to.
# MAGIC
# MAGIC **The filter travels with the table.** Like a column mask, it applies through every path —
# MAGIC notebook, SQL editor, dashboard, JDBC from a laptop. There is no view to bypass.
# MAGIC
# MAGIC ## ⚠️ Runs on `admin_demo` only
# MAGIC `ALTER TABLE … SET ROW FILTER` mutates the **table object**. On `silver_dev.student` it would
# MAGIC hide rows from all ~20 session participants and silently change what the Engineer pipelines
# MAGIC read — wrong results rather than an error. Everything here targets `admin_demo` copies
# MAGIC (spec §3.1 rule 4), and an assertion proves the foundation stayed clean.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC 1. `pa_admin_demo_setup` (PA Task 0) — `admin_demo` + table copies
# MAGIC 2. `pa_a_identity_access` (PA-A) — the role → group mapping
# MAGIC 3. `pa_b_column_masking` (PA-B) — optional, but masks and filters compose: run both and a
# MAGIC    faculty reader sees *fewer rows* **and** *masked columns within them*

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc")
dbutils.widgets.text("schema_suffix", "")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")

SILVER = f"{CATALOG}.silver{SUFFIX}"
ADMIN = f"{CATALOG}.admin_demo"

ADMIN_GROUP = "dbx_demo_shared_admins"
FACULTY_GROUP = "data_engineers_demo_group"

me = spark.sql("SELECT current_user()").first()[0]
total_students = spark.sql(f"SELECT count(*) AS n FROM {ADMIN}.student").first()["n"]
print(f"policies target {ADMIN} | {total_students:,} students before filtering")
print(f"running as {me}")

# COMMAND ----------
# MAGIC %md ## PA-10 — The mapping table that makes the policy dynamic
# MAGIC A two-column table: which principal may see which department. This is the piece that turns a
# MAGIC hardcoded rule into an administered one — moving someone between departments is an `UPDATE`
# MAGIC here, not a policy rewrite.
# MAGIC
# MAGIC In Princeton's environment this would be populated from the HR system or an IdP group sync
# MAGIC rather than typed. The *shape* is what the scenario proves.
# MAGIC
# MAGIC **Grant carefully.** Anyone who can write this table can widen their own access, so it is
# MAGIC readable by the policy and writable only by admins.
# COMMAND ----------
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {ADMIN}.department_access (
    principal  STRING  COMMENT 'user email or group name',
    dept_id    BIGINT  COMMENT 'department this principal may see',
    granted_by STRING  COMMENT 'who added the row — audit',
    granted_at TIMESTAMP
) COMMENT 'PA-10: identity -> permitted departments. Read by the row-filter function; writable by admins only.'
""")

# Seed the running admin to two departments, so "filtered" is visibly narrower than "all" but not
# a single row — a one-department result is easy to mistake for a coincidence.
spark.sql(f"DELETE FROM {ADMIN}.department_access WHERE principal = '{me}'")
spark.sql(f"""
INSERT INTO {ADMIN}.department_access
SELECT '{me}', 5, '{me}', current_timestamp()
UNION ALL
SELECT '{me}', 12, '{me}', current_timestamp()
""")
display(spark.sql(f"SELECT * FROM {ADMIN}.department_access ORDER BY principal, dept_id"))

# COMMAND ----------
# MAGIC %md ## PA-09 / PA-10 — The row-filter function
# MAGIC A row filter is a **function returning BOOLEAN**, evaluated per row. `true` keeps the row.
# MAGIC
# MAGIC Three branches, in precedence order:
# MAGIC 1. **admins** — unrestricted. Someone has to be able to see everything, and that should be an
# MAGIC    explicit branch rather than an accident.
# MAGIC 2. **anyone in the mapping table** — PA-10's dynamic path, via a subquery on `current_user()`.
# MAGIC    Verified that UC permits a subquery against a lookup table inside a filter function.
# MAGIC 3. **everyone else** — no rows. Deny by default, not "see everything if unmapped".
# COMMAND ----------
spark.sql(f"""
CREATE OR REPLACE FUNCTION {ADMIN}.filter_by_department(dept_id BIGINT)
RETURNS BOOLEAN
COMMENT 'PA-09/PA-10: admins see all; others see only departments mapped to them in department_access; unmapped principals see nothing'
RETURN
    is_member('{ADMIN_GROUP}')
    OR dept_id IN (
        SELECT dept_id FROM {ADMIN}.department_access
        WHERE principal = current_user()
           OR is_member(principal)          -- the mapping may name a GROUP, not just a user
    )
""")
print(f"created {ADMIN}.filter_by_department")

# COMMAND ----------
# MAGIC %md ## Apply the filters
# MAGIC Syntax: `ALTER TABLE … SET ROW FILTER <fn> ON (<column>)`. The `ON (…)` list supplies the
# MAGIC function's arguments from the table's columns — that is how one function serves several
# MAGIC tables, as long as each has a `dept_id`.
# COMMAND ----------
FILTERED = [f"{ADMIN}.student", f"{ADMIN}.faculty"]
for t in FILTERED:
    spark.sql(f"ALTER TABLE {t} DROP ROW FILTER")   # idempotent — safe to re-run in a demo
    spark.sql(f"ALTER TABLE {t} SET ROW FILTER {ADMIN}.filter_by_department ON (dept_id)")
    print(f"  ROW FILTER filter_by_department ON (dept_id) -> {t}")

# COMMAND ----------
# MAGIC %md ## The demonstration
# MAGIC Because the PA admin is in the admin group, branch 1 applies and this returns **all** rows —
# MAGIC the correct outcome for an administrator, and the reason a naive "did the count drop?" check
# MAGIC is not proof of anything.
# COMMAND ----------
admin_view = spark.sql(f"""
    SELECT count(*) AS rows_visible, count(DISTINCT dept_id) AS departments_visible
    FROM {ADMIN}.student
""").first()
print(f"as admin: {admin_view['rows_visible']:,} rows across "
      f"{admin_view['departments_visible']} departments (unrestricted)")

# COMMAND ----------
# MAGIC %md ### What a non-admin sees — evaluated, not simulated
# MAGIC You cannot become another user mid-notebook. But the filter's *predicate* can be evaluated
# MAGIC directly against the same data, which shows exactly what the mapping table produces for this
# MAGIC identity. This is the honest version of the demo; PA-D does real cross-principal verification.
# COMMAND ----------
non_admin_view = spark.sql(f"""
    SELECT count(*) AS rows_visible, count(DISTINCT dept_id) AS departments_visible
    FROM {SILVER}.student
    WHERE dept_id IN (SELECT dept_id FROM {ADMIN}.department_access WHERE principal = '{me}')
""").first()
print(f"as a mapped non-admin: {non_admin_view['rows_visible']:,} rows across "
      f"{non_admin_view['departments_visible']} departments "
      f"({100 * non_admin_view['rows_visible'] / total_students:.1f}% of the table)")

display(spark.sql(f"""
    SELECT d.dept_id, d.name AS department, count(*) AS students,
           CASE WHEN d.dept_id IN (
                    SELECT dept_id FROM {ADMIN}.department_access WHERE principal = '{me}')
                THEN 'visible' ELSE 'filtered out' END AS for_mapped_user
    FROM {SILVER}.student s
    JOIN {SILVER}.department d ON s.dept_id = d.dept_id
    GROUP BY d.dept_id, d.name
    ORDER BY for_mapped_user, d.dept_id
    LIMIT 20
"""))

# COMMAND ----------
# MAGIC %md ## PA-10 — Change access without touching the policy
# MAGIC The operational proof. Add a department to the mapping table; the permitted set widens on the
# MAGIC next query. No function edited, no `ALTER TABLE`, no redeploy.
# COMMAND ----------
before_depts = spark.sql(f"""
    SELECT count(DISTINCT dept_id) AS n FROM {ADMIN}.department_access WHERE principal = '{me}'
""").first()["n"]

spark.sql(f"""
INSERT INTO {ADMIN}.department_access
SELECT '{me}', 24, '{me}', current_timestamp()
""")

after_depts = spark.sql(f"""
    SELECT count(DISTINCT dept_id) AS n FROM {ADMIN}.department_access WHERE principal = '{me}'
""").first()["n"]

widened = spark.sql(f"""
    SELECT count(*) AS rows_visible
    FROM {SILVER}.student
    WHERE dept_id IN (SELECT dept_id FROM {ADMIN}.department_access WHERE principal = '{me}')
""").first()["rows_visible"]

print(f"departments mapped: {before_depts} -> {after_depts} (one INSERT)")
print(f"rows now visible to that identity: {non_admin_view['rows_visible']:,} -> {widened:,}")
print("The policy function was not modified. That is PA-10.")

# COMMAND ----------
# MAGIC %md ## Where the policy lives
# MAGIC Like a mask, a row filter is catalog metadata — visible to an auditor without reading any
# MAGIC application code. PA-D turns this into a full inventory.
# COMMAND ----------
for t in FILTERED:
    rows = spark.sql(f"DESCRIBE EXTENDED {t}").collect()
    hits = [r for r in rows if any("row filter" in str(v).lower() for v in r.asDict().values() if v)]
    print(f"  {t}: {'row filter attached' if hits else 'NONE'}")
    for r in hits:
        print(f"      {r[0]} {r[1]}")

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
# Admin must be unrestricted — otherwise the filter is over-broad and the demo misleads.
assert admin_view["rows_visible"] == total_students, (
    f"admin sees {admin_view['rows_visible']:,} of {total_students:,} rows. "
    f"is_member('{ADMIN_GROUP}') is probably false — check PA-A."
)

# The filter must actually restrict a non-admin, or it proves nothing.
assert 0 < non_admin_view["rows_visible"] < total_students, (
    f"mapped non-admin sees {non_admin_view['rows_visible']:,} of {total_students:,} — "
    "expected a strict subset (some rows, not all)"
)
assert non_admin_view["departments_visible"] == before_depts, (
    f"mapped user sees {non_admin_view['departments_visible']} departments but is mapped to "
    f"{before_depts} — the filter is not honouring the mapping table"
)

# PA-10: the INSERT must have widened access without any policy change.
assert after_depts == before_depts + 1, "the mapping INSERT did not take effect"
assert widened > non_admin_view["rows_visible"], (
    "adding a department did not widen the visible row set — the policy is not reading the "
    "mapping table dynamically"
)

# Filters are attached where intended.
for t in FILTERED:
    described = spark.sql(f"DESCRIBE EXTENDED {t}").collect()
    attached = any(
        "filter_by_department" in str(v).lower()
        for r in described for v in r.asDict().values() if v
    )
    assert attached, f"no row filter attached to {t}"

# Deny-by-default: an unmapped principal must see nothing.
unmapped = spark.sql(f"""
    SELECT count(*) AS n FROM {SILVER}.student
    WHERE dept_id IN (
        SELECT dept_id FROM {ADMIN}.department_access WHERE principal = 'nobody@example.invalid')
""").first()["n"]
assert unmapped == 0, f"an unmapped principal would see {unmapped} rows — should be deny-by-default"

# The shared foundation must carry no policies.
leaked = []
for t in ("student", "faculty", "financial_aid"):
    for r in spark.sql(f"DESCRIBE EXTENDED {SILVER}.{t}").collect():
        blob = " ".join(str(v) for v in r.asDict().values() if v).lower()
        if "row filter" in blob or "mask" in blob:
            leaked.append(f"{SILVER}.{t}: {r[0]}")
assert not leaked, f"policies leaked onto the SHARED foundation: {leaked}"

print(f"PASS: PA-C — admin unrestricted ({total_students:,} rows); mapped identity sees "
      f"{non_admin_view['rows_visible']:,} rows in {before_depts} departments; one INSERT widened "
      f"that to {widened:,} with no policy change (PA-10); unmapped principals see 0 rows; "
      f"foundation clean.")
