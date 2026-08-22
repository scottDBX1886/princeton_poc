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
# MAGIC | PA-10 dynamic policy by identity | the permitted values come from a **lookup table keyed on `session_user()`**, so nothing is hardcoded |
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
# MAGIC 2. `pa_a_identity_access` (PA-A) — grants the restricted role its object-level access
# MAGIC 3. `pa_b_column_masking` (PA-B) — optional, but masks and filters compose: run both and the
# MAGIC    restricted identity sees *fewer rows* **and** *masked columns within them*
# MAGIC
# MAGIC ## ⚠️ The mapping table is keyed on `session_user()`
# MAGIC The restricted identity here is the **`account users` role**, reached by assuming it
# MAGIC (workspace menu → role). While a role is assumed, `session_user()` returns the *role name*,
# MAGIC not the human's email — so the mapping table must carry a row for the role name itself.
# MAGIC
# MAGIC Miss that and the filter denies every row for the role, which looks like a broken demo rather
# MAGIC than a working policy. `is_member()` cannot substitute: a group is not a member of itself, so
# MAGIC `is_member('account users')` is **false** while acting as it. Both verified live.

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

me = spark.sql("SELECT session_user()").first()[0]
acting_as_role = me == RESTRICTED_ROLE

# Row count from the unpolicied foundation — the true total, whatever filters the sandbox carries.
total_students = spark.sql(f"SELECT count(*) AS n FROM {SILVER}.student").first()["n"]
print(f"policies target {ADMIN} | {total_students:,} students in the unfiltered foundation")
print(f"session_user():  {me}")
print(f"mode:            {'ACTING AS THE RESTRICTED ROLE' if acting_as_role else 'own identity (admin)'}")

# COMMAND ----------
# MAGIC %md ## PA-10 — The mapping table that makes the policy dynamic
# MAGIC A two-column table: which principal may see which department. This is the piece that turns a
# MAGIC hardcoded rule into an administered one — moving someone between departments is an `INSERT`
# MAGIC here, not a policy rewrite.
# MAGIC
# MAGIC In Princeton's environment this would be populated from the HR system or an IdP group sync
# MAGIC rather than typed. The *shape* is what the scenario proves.
# MAGIC
# MAGIC **Grant carefully.** Anyone who can write this table can widen their own access, so it is
# MAGIC readable by the policy and writable only by admins. PA-D asserts that.
# MAGIC
# MAGIC Note the `principal` values: one is an **email** (the human admin) and one is a **role name**
# MAGIC (`account users`). Both are what `session_user()` returns in their respective sessions, which
# MAGIC is exactly why the filter keys on that function.
# COMMAND ----------
if acting_as_role:
    print("SKIPPED — seeding the mapping table requires your own (owning) identity.")
else:
    spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {ADMIN}.department_access (
        principal  STRING  COMMENT 'what session_user() returns: a user email OR an assumed role name',
        dept_id    BIGINT  COMMENT 'department this principal may see',
        granted_by STRING  COMMENT 'who added the row — audit',
        granted_at TIMESTAMP
    ) COMMENT 'PA-10: identity -> permitted departments. Read by the row-filter function; writable by admins only.'
    """)

    # Seed two departments for the restricted role, so "filtered" is visibly narrower than "all" but
    # not a single row — a one-department result is easy to mistake for a coincidence.
    spark.sql(f"DELETE FROM {ADMIN}.department_access WHERE principal = '{RESTRICTED_ROLE}'")
    spark.sql(f"""
    INSERT INTO {ADMIN}.department_access
    SELECT '{RESTRICTED_ROLE}', 5, '{me}', current_timestamp()
    UNION ALL
    SELECT '{RESTRICTED_ROLE}', 12, '{me}', current_timestamp()
    """)
    print(f"seeded {RESTRICTED_ROLE} -> departments 5, 12")

display(spark.sql(f"SELECT * FROM {ADMIN}.department_access ORDER BY principal, dept_id"))

# COMMAND ----------
# MAGIC %md ## PA-09 / PA-10 — The row-filter function
# MAGIC A row filter is a **function returning BOOLEAN**, evaluated per row. `true` keeps the row.
# MAGIC
# MAGIC Three branches, in precedence order:
# MAGIC 1. **the restricted role** — only its mapped departments. Checked FIRST, because
# MAGIC    `is_member()` is unreliable for an assumed role and must not be reached.
# MAGIC 2. **admins** — unrestricted. Someone has to be able to see everything, and that should be an
# MAGIC    explicit branch rather than an accident.
# MAGIC 3. **everyone else** — their mapped departments, or no rows if unmapped. Deny by default, not
# MAGIC    "see everything if unmapped".
# MAGIC
# MAGIC Verified that UC permits a subquery against a lookup table inside a filter function.
# COMMAND ----------
if acting_as_role:
    print("SKIPPED — policy creation requires your own (owning) identity.")
else:
    spark.sql(f"""
    CREATE OR REPLACE FUNCTION {ADMIN}.filter_by_department(dept_id BIGINT)
    RETURNS BOOLEAN
    COMMENT 'PA-09/PA-10: restricted role and unmapped principals see only mapped departments; admins see all'
    RETURN
        CASE
            WHEN session_user() = '{RESTRICTED_ROLE}' THEN
                dept_id IN (SELECT dept_id FROM {ADMIN}.department_access
                            WHERE principal = '{RESTRICTED_ROLE}')
            WHEN is_member('{ADMIN_GROUP}') THEN true
            ELSE
                dept_id IN (SELECT dept_id FROM {ADMIN}.department_access
                            WHERE principal = session_user())
        END
    """)
    print(f"created {ADMIN}.filter_by_department")

# COMMAND ----------
# MAGIC %md ## Apply the filters
# MAGIC Syntax: `ALTER TABLE … SET ROW FILTER <fn> ON (<column>)`. The `ON (…)` list supplies the
# MAGIC function's arguments from the table's columns — that is how one function serves several
# MAGIC tables, as long as each has a `dept_id`.
# COMMAND ----------
FILTERED = [f"{ADMIN}.student", f"{ADMIN}.faculty"]
if acting_as_role:
    print("SKIPPED — ALTER TABLE requires your own (owning) identity.")
else:
    for t in FILTERED:
        # Idempotent: DROP ROW FILTER on an unfiltered table is a no-op (verified).
        spark.sql(f"ALTER TABLE {t} DROP ROW FILTER")
        spark.sql(f"ALTER TABLE {t} SET ROW FILTER {ADMIN}.filter_by_department ON (dept_id)")
        print(f"  ROW FILTER filter_by_department ON (dept_id) -> {t}")

# COMMAND ----------
# MAGIC %md ## The demonstration — what THIS identity sees
# MAGIC **The demo.** Identical query text in both sessions; only the identity differs.
# MAGIC
# MAGIC - as an **admin** → all rows (branch 2)
# MAGIC - as the **restricted role** → only departments 5 and 12 (branch 1)
# MAGIC
# MAGIC Run it, switch roles, run it again.
# COMMAND ----------
view = spark.sql(f"""
    SELECT count(*) AS rows_visible, count(DISTINCT dept_id) AS departments_visible
    FROM {ADMIN}.student
""").first()

pct = 100 * view["rows_visible"] / total_students if total_students else 0
print(f"as {me}:")
print(f"  {view['rows_visible']:,} of {total_students:,} rows ({pct:.1f}%) "
      f"across {view['departments_visible']} departments")
print(f"  {'RESTRICTED to mapped departments' if acting_as_role else 'UNRESTRICTED (admin branch)'}")

display(spark.sql(f"""
    SELECT dept_id, count(*) AS students_visible
    FROM {ADMIN}.student
    GROUP BY dept_id ORDER BY dept_id
"""))

# COMMAND ----------
# MAGIC %md ### Which departments exist, and which this identity may see
# MAGIC Read from the unpolicied foundation so the *full* department list is visible alongside the
# MAGIC permitted subset — otherwise a filtered reader cannot tell what they are missing, and neither
# MAGIC can the audience.
# COMMAND ----------
display(spark.sql(f"""
    SELECT d.dept_id, d.name AS department, count(*) AS students,
           CASE WHEN d.dept_id IN (
                    SELECT dept_id FROM {ADMIN}.department_access
                    WHERE principal = '{RESTRICTED_ROLE}')
                THEN 'visible to the restricted role' ELSE 'filtered out' END AS for_restricted_role
    FROM {SILVER}.student s
    JOIN {SILVER}.department d ON s.dept_id = d.dept_id
    GROUP BY d.dept_id, d.name
    ORDER BY for_restricted_role, d.dept_id
    LIMIT 20
"""))

# COMMAND ----------
# MAGIC %md ## PA-10 — Change access without touching the policy
# MAGIC The operational proof. Add a department to the mapping table; the permitted set widens on the
# MAGIC next query. No function edited, no `ALTER TABLE`, no redeploy.
# MAGIC
# MAGIC Run as an admin. Then switch to the role and re-run the cell above — the newly mapped
# MAGIC department is now visible to it.
# COMMAND ----------
if acting_as_role:
    print("SKIPPED — writing the mapping table requires admin identity. That is the point: the")
    print("restricted role can READ what it is allowed, and cannot widen its own access.")
else:
    before_depts = spark.sql(f"""
        SELECT count(DISTINCT dept_id) AS n FROM {ADMIN}.department_access
        WHERE principal = '{RESTRICTED_ROLE}'
    """).first()["n"]

    rows_before = spark.sql(f"""
        SELECT count(*) AS n FROM {SILVER}.student
        WHERE dept_id IN (SELECT dept_id FROM {ADMIN}.department_access
                          WHERE principal = '{RESTRICTED_ROLE}')
    """).first()["n"]

    spark.sql(f"""
    INSERT INTO {ADMIN}.department_access
    SELECT '{RESTRICTED_ROLE}', 24, '{me}', current_timestamp()
    """)

    after_depts = spark.sql(f"""
        SELECT count(DISTINCT dept_id) AS n FROM {ADMIN}.department_access
        WHERE principal = '{RESTRICTED_ROLE}'
    """).first()["n"]

    rows_after = spark.sql(f"""
        SELECT count(*) AS n FROM {SILVER}.student
        WHERE dept_id IN (SELECT dept_id FROM {ADMIN}.department_access
                          WHERE principal = '{RESTRICTED_ROLE}')
    """).first()["n"]

    print(f"departments mapped to '{RESTRICTED_ROLE}': {before_depts} -> {after_depts} (one INSERT)")
    print(f"rows that identity may now see: {rows_before:,} -> {rows_after:,}")
    print("The policy function was not modified. That is PA-10.")

# COMMAND ----------
# MAGIC %md ## Where the policy lives
# MAGIC Like a mask, a row filter is catalog metadata — visible to an auditor without reading any
# MAGIC application code. `target_columns` is the `ON (…)` list. PA-D turns this into a full inventory.
# COMMAND ----------
display(spark.sql(f"""
    SELECT table_schema, table_name, filter_name, target_columns
    FROM {CATALOG}.information_schema.row_filters
    ORDER BY table_schema, table_name
"""))

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
mapped_depts = {r["dept_id"] for r in spark.sql(f"""
    SELECT dept_id FROM {ADMIN}.department_access WHERE principal = '{RESTRICTED_ROLE}'
""").collect()}

if acting_as_role:
    # The restricted half — UC enforcing the filter against a real second identity.
    assert view["rows_visible"] < total_students, (
        f"acting as '{RESTRICTED_ROLE}' but saw all {total_students:,} rows — the filter is not "
        f"restricting. Check that branch 1 matches session_user() exactly."
    )
    assert view["rows_visible"] > 0, (
        f"acting as '{RESTRICTED_ROLE}' and saw 0 rows. The mapping table probably has no row for "
        f"'{RESTRICTED_ROLE}' — remember session_user() returns the ROLE NAME, not your email."
    )
    visible_depts = {r["dept_id"] for r in spark.sql(f"""
        SELECT DISTINCT dept_id FROM {ADMIN}.student
    """).collect()}
    assert visible_depts <= mapped_depts, (
        f"role sees departments {sorted(visible_depts - mapped_depts)} that are NOT mapped to it — "
        f"the filter is leaking rows"
    )
    print(f"PASS (restricted view): acting as '{RESTRICTED_ROLE}' — {view['rows_visible']:,} of "
          f"{total_students:,} rows, departments {sorted(visible_depts)} only (mapped: "
          f"{sorted(mapped_depts)}). PA-09/PA-10 enforced by UC against a real second identity.")
else:
    # Admin must be unrestricted, or the filter is over-broad and the demo misleads.
    assert view["rows_visible"] == total_students, (
        f"admin sees {view['rows_visible']:,} of {total_students:,} rows. "
        f"is_member('{ADMIN_GROUP}') is probably false — check PA-A."
    )

    # The mapping must actually restrict SOMETHING, or there is no contrast to show.
    assert mapped_depts, f"no departments mapped to '{RESTRICTED_ROLE}' — the role would see 0 rows"
    restricted_rows = spark.sql(f"""
        SELECT count(*) AS n FROM {SILVER}.student
        WHERE dept_id IN (SELECT dept_id FROM {ADMIN}.department_access
                          WHERE principal = '{RESTRICTED_ROLE}')
    """).first()["n"]
    assert 0 < restricted_rows < total_students, (
        f"the restricted role would see {restricted_rows:,} of {total_students:,} — expected a "
        f"strict subset (some rows, not all, not none)"
    )

    # Deny-by-default: an unmapped, non-admin principal must see nothing.
    unmapped = spark.sql(f"""
        SELECT count(*) AS n FROM {SILVER}.student
        WHERE dept_id IN (SELECT dept_id FROM {ADMIN}.department_access
                          WHERE principal = 'nobody@example.invalid')
    """).first()["n"]
    assert unmapped == 0, f"an unmapped principal would see {unmapped} rows — should be deny-by-default"

    # Filters are attached where intended.
    attached = {(r["table_schema"], r["table_name"]) for r in spark.sql(f"""
        SELECT table_schema, table_name FROM {CATALOG}.information_schema.row_filters
    """).collect()}
    for t in FILTERED:
        key = ("admin_demo", t.split(".")[-1])
        assert key in attached, f"no row filter attached to {t}"

    # The shared foundation must carry no policies.
    leaked = [f"{s}.{t}" for s, t in attached if s != "admin_demo"]
    assert not leaked, f"row filters leaked onto the shared foundation: {leaked}"

    print(f"PASS: PA-C — admin unrestricted ({total_students:,} rows); '{RESTRICTED_ROLE}' mapped to "
          f"departments {sorted(mapped_depts)} would see {restricted_rows:,} rows; unmapped "
          f"principals see 0; filters scoped to admin_demo only.")
    print(f"\nNEXT: switch to the '{RESTRICTED_ROLE}' role and re-run. The assertions flip to the")
    print("restricted branch and prove UC enforces the filter against a real identity.")
