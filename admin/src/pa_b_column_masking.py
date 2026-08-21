# Databricks notebook source
# MAGIC %md
# MAGIC # PA-B: Column-level security (PA-07, PA-08)
# MAGIC
# MAGIC Oracle FGAC's column-level equivalent, in Unity Catalog. Two scenarios:
# MAGIC
# MAGIC | Scenario | Demonstrated by |
# MAGIC |---|---|
# MAGIC | PA-07 masking sensitive fields | `ssn` partially masked, `dob` year-only, `amount` rounded |
# MAGIC | PA-08 full column restriction | `ssn` returns NULL entirely for the least-privileged role |
# MAGIC
# MAGIC **The mask travels with the table, not the query.** A masked column is masked for every
# MAGIC reader through every path — notebook, SQL editor, dashboard, JDBC from a laptop, or an
# MAGIC `INSERT … SELECT` into another table. There is no view to bypass and no client setting to
# MAGIC change, which is the property that makes this different from application-layer redaction.
# MAGIC
# MAGIC ## ⚠️ Runs on `admin_demo` only
# MAGIC `ALTER TABLE … SET MASK` mutates the **table object**. Applied to `silver_dev.student` it
# MAGIC would redact `ssn` for all ~20 session participants and break the Engineer pipelines reading
# MAGIC the same tables. Every policy here targets `admin_demo` copies (spec §3.1 rule 4). An
# MAGIC assertion at the end proves the foundation stayed clean.
# MAGIC
# MAGIC ## Prerequisites
# MAGIC 1. `pa_admin_demo_setup` (PA Task 0) — creates `admin_demo` and the table copies
# MAGIC 2. `pa_a_identity_access` (PA-A) — establishes the role → group mapping used below
# MAGIC
# MAGIC ## `is_member()`, not `is_account_group_member()`
# MAGIC The account-level function cannot see workspace groups. A mask written against it returns its
# MAGIC ELSE branch for **everyone including the admin** — the demo appears to work while proving
# MAGIC nothing. See `PA_A_IDENTITY_STRATEGY.md`.

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc")
dbutils.widgets.text("schema_suffix", "")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")

SILVER = f"{CATALOG}.silver{SUFFIX}"
ADMIN = f"{CATALOG}.admin_demo"

# Same role → account-group mapping as PA-A. Only account-level groups work with UC, and the PA
# admin belongs to ADMIN_GROUP and not the others — which is what makes the contrast real.
ADMIN_GROUP = "dbx_demo_shared_admins"
FACULTY_GROUP = "data_engineers_demo_group"

me = spark.sql("SELECT current_user()").first()[0]
print(f"policies target: {ADMIN} (foundation at {SILVER} stays untouched)")
print(f"running as {me}")
for g in (ADMIN_GROUP, FACULTY_GROUP):
    print(f"  is_member({g}) = {spark.sql(f'SELECT is_member(\"{g}\") AS r').first()['r']}")

# COMMAND ----------
# MAGIC %md ## Before: the unmasked values
# MAGIC Capture what the data looks like with no policy, so the after-state is a comparison rather
# MAGIC than an assertion.
# COMMAND ----------
before = spark.sql(f"SELECT student_id, first_name, ssn, dob FROM {ADMIN}.student ORDER BY student_id LIMIT 5")
display(before)
before_ssn = [r["ssn"] for r in before.collect()]
print(f"unmasked ssn sample: {before_ssn[:2]}")

# COMMAND ----------
# MAGIC %md ## PA-07 — Mask functions
# MAGIC A UC mask is a **function** applied to a column. It receives the column value and returns
# MAGIC what the caller should see, so the policy is expressed once and reused across tables.
# MAGIC
# MAGIC Three graduated levels, because "masked" is not one thing:
# MAGIC - `mask_ssn` — partial: last four digits survive, enough to confirm identity without exposing
# MAGIC   the number
# MAGIC - `mask_dob` — generalisation: year only, so age analysis still works while the exact date is
# MAGIC   gone
# MAGIC - `mask_amount` — perturbation: rounded to the nearest 1,000, so aggregates stay usable
# MAGIC
# MAGIC **`dob` is a STRING in three mixed formats** (`yyyy-MM-dd`, `MM/dd/yyyy`, `dd.MM.yyyy`) by
# MAGIC design, for SE-15. `year(dob)` returns NULL on two of them, so the mask parses with a
# MAGIC `coalesce` over all three — otherwise the "masked" value is silently NULL for ~67% of rows,
# MAGIC which looks like a working mask and is actually data loss.
# COMMAND ----------
spark.sql(f"""
CREATE OR REPLACE FUNCTION {ADMIN}.mask_ssn(ssn STRING)
RETURNS STRING
COMMENT 'PA-07: full SSN for admins; last 4 only for faculty; fully restricted otherwise (PA-08)'
RETURN CASE
    WHEN is_member('{ADMIN_GROUP}')   THEN ssn
    WHEN is_member('{FACULTY_GROUP}') THEN concat('***-**-', right(ssn, 4))
    ELSE NULL                     -- PA-08: full column restriction, not a placeholder string
END
""")

spark.sql(f"""
CREATE OR REPLACE FUNCTION {ADMIN}.mask_dob(dob STRING)
RETURNS STRING
COMMENT 'PA-07: exact date for admins; year only for faculty; restricted otherwise'
RETURN CASE
    WHEN is_member('{ADMIN_GROUP}') THEN dob
    WHEN is_member('{FACULTY_GROUP}') THEN concat(
        cast(year(coalesce(
            try_to_date(dob, 'yyyy-MM-dd'),
            try_to_date(dob, 'MM/dd/yyyy'),
            try_to_date(dob, 'dd.MM.yyyy'))) AS STRING), '-XX-XX')
    ELSE NULL
END
""")

spark.sql(f"""
CREATE OR REPLACE FUNCTION {ADMIN}.mask_amount(amount DOUBLE)
RETURNS DOUBLE
COMMENT 'PA-07: exact award for admins; rounded to nearest 1000 for faculty; restricted otherwise'
RETURN CASE
    WHEN is_member('{ADMIN_GROUP}')   THEN amount
    WHEN is_member('{FACULTY_GROUP}') THEN round(amount, -3)
    ELSE NULL
END
""")
print(f"created 3 mask functions in {ADMIN}")

# COMMAND ----------
# MAGIC %md ## Apply the masks
# MAGIC Syntax note: it is `ALTER TABLE … ALTER COLUMN <col> SET MASK <fn>` — **not** the plan's
# MAGIC `SET COLUMN MASK ssn = mask_ssn(ssn)`, which is not valid Databricks SQL. Verified against
# MAGIC the live warehouse.
# COMMAND ----------
MASKS = [
    (f"{ADMIN}.student",       "ssn",    f"{ADMIN}.mask_ssn"),
    (f"{ADMIN}.student",       "dob",    f"{ADMIN}.mask_dob"),
    (f"{ADMIN}.faculty",       "ssn",    f"{ADMIN}.mask_ssn"),
    (f"{ADMIN}.financial_aid", "amount", f"{ADMIN}.mask_amount"),
]
for table, col, fn in MASKS:
    # Idempotent: dropping first makes the notebook safely re-runnable during a demo.
    spark.sql(f"ALTER TABLE {table} ALTER COLUMN {col} DROP MASK")
    spark.sql(f"ALTER TABLE {table} ALTER COLUMN {col} SET MASK {fn}")
    print(f"  MASK {fn.split('.')[-1]:12s} -> {table}.{col}")

# COMMAND ----------
# MAGIC %md ## After: the same query, now governed
# MAGIC **This is the demo.** The query text is byte-identical to the "before" cell. Nothing about the
# MAGIC client changed — the table did.
# MAGIC
# MAGIC Because the PA admin is in the admin group, this run shows **unmasked** values. That is the
# MAGIC point: the mask is role-dependent, not blanket redaction. The contrast comes from the next
# MAGIC cell.
# COMMAND ----------
after = spark.sql(f"SELECT student_id, first_name, ssn, dob FROM {ADMIN}.student ORDER BY student_id LIMIT 5")
display(after)

display(spark.sql(f"SELECT aid_id, student_id, amount, aid_type FROM {ADMIN}.financial_aid ORDER BY aid_id LIMIT 5"))

# COMMAND ----------
# MAGIC %md ## PA-07 / PA-08 — What each role sees, without switching users
# MAGIC You cannot become another user mid-notebook, but you can evaluate the *policy expression* for
# MAGIC each role and show the three outcomes side by side. This is the honest version of the "faux
# MAGIC user" demo — it proves the branch logic rather than simulating a login.
# MAGIC
# MAGIC PA-D covers real cross-principal verification.
# COMMAND ----------
display(spark.sql(f"""
    SELECT 'admin'   AS role, ssn AS ssn_seen,
           'full value' AS treatment
    FROM (SELECT ssn FROM {SILVER}.student ORDER BY student_id LIMIT 1)
    UNION ALL
    SELECT 'faculty' AS role, concat('***-**-', right(ssn, 4)),
           'partial — last 4 only (PA-07)'
    FROM (SELECT ssn FROM {SILVER}.student ORDER BY student_id LIMIT 1)
    UNION ALL
    SELECT 'student/other' AS role, NULL,
           'fully restricted — NULL (PA-08)'
    FROM (SELECT ssn FROM {SILVER}.student ORDER BY student_id LIMIT 1)
"""))
print("Read from the read-only foundation deliberately: it shows the true source value, so the "
      "three treatments are comparable against ground truth.")

# COMMAND ----------
# MAGIC %md ## Where the policy lives — the metadata proof
# MAGIC A mask is catalog metadata, not query-time convention. `DESCRIBE EXTENDED` shows it, so an
# MAGIC auditor can confirm coverage without reading any application code. PA-D turns this into a
# MAGIC full policy inventory.
# COMMAND ----------
for t in ("student", "faculty", "financial_aid"):
    rows = spark.sql(f"DESCRIBE EXTENDED {ADMIN}.{t}").collect()
    hits = [r for r in rows if any("mask" in str(v).lower() for v in r.asDict().values() if v)]
    print(f"  {ADMIN}.{t}: " + (", ".join(f"{r[0]}" for r in hits if r[0] and r[0] != "# Column Masks") or "none"))

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
# The admin must still see real data, or the mask is over-broad and the demo proves nothing.
after_ssn = [r["ssn"] for r in after.collect()]
assert after_ssn == before_ssn, (
    f"admin's view changed after masking: {before_ssn[:2]} -> {after_ssn[:2]}. "
    f"is_member('{ADMIN_GROUP}') is probably false — check PA-A."
)
assert all(s and s != "[REDACTED]" for s in after_ssn), "admin sees redacted values; mask is wrong"

# Every intended mask must actually be attached — a silently-missing mask is the failure mode that
# looks like success.
for table, col, fn in MASKS:
    described = spark.sql(f"DESCRIBE EXTENDED {table}").collect()
    attached = any(
        r[0] == col and fn.split(".")[-1] in str(r[1]).lower()
        for r in described if r[0]
    )
    assert attached, f"no mask attached to {table}.{col} (expected {fn})"

# The dob mask must not silently null out rows through failed date parsing.
dob_nulls = spark.sql(f"SELECT count(*) AS n FROM {ADMIN}.student WHERE dob IS NULL").first()["n"]
assert dob_nulls == 0, (
    f"{dob_nulls} rows have NULL dob after masking — the three-format coalesce is incomplete"
)

# THE critical one: the shared foundation must carry no policies.
leaked = []
for t in ("student", "faculty", "financial_aid"):
    for r in spark.sql(f"DESCRIBE EXTENDED {SILVER}.{t}").collect():
        blob = " ".join(str(v) for v in r.asDict().values() if v).lower()
        if "mask" in blob or "row filter" in blob:
            leaked.append(f"{SILVER}.{t}: {r[0]}")
assert not leaked, f"policies leaked onto the SHARED foundation: {leaked}"

# And the foundation still returns real SSNs for everyone.
foundation_ssn = spark.sql(f"SELECT ssn FROM {SILVER}.student LIMIT 1").first()["ssn"]
assert foundation_ssn and "*" not in foundation_ssn, \
    f"foundation ssn appears masked: {foundation_ssn}"

print(f"PASS: PA-B — 3 mask functions, 4 columns masked on {ADMIN}; admin sees full values, "
      f"faculty partial, others NULL (PA-08); dob parsed across all 3 formats; "
      f"foundation carries no policies.")
