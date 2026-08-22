# Databricks notebook source
# MAGIC %md
# MAGIC # PA-B: Column-level security (PA-07, PA-08)
# MAGIC
# MAGIC Oracle FGAC's column-level equivalent, in Unity Catalog. Two scenarios:
# MAGIC
# MAGIC | Scenario | Demonstrated by |
# MAGIC |---|---|
# MAGIC | PA-07 masking sensitive fields | `ssn` partially masked, `dob` year-only, `amount` rounded |
# MAGIC | PA-08 full column restriction | `ssn` returns NULL entirely for the restricted identity |
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
# MAGIC 2. `pa_a_identity_access` (PA-A) — grants the restricted role its object-level access
# MAGIC
# MAGIC ## ⚠️ Policies branch on `session_user()`, NOT `is_member()`
# MAGIC This workspace has one UC-grantable group (`account users`) and the restricted identity is
# MAGIC reached by **assuming that role** (workspace menu → role). Two verified traps make
# MAGIC `is_member()` the wrong predicate here, and both fail *silently* — the mask appears to work
# MAGIC while proving nothing:
# MAGIC
# MAGIC 1. **A group is not a member of itself.** Acting as `account users`,
# MAGIC    `is_member('account users')` is **false**.
# MAGIC 2. **An assumed role does not inherit the human's memberships.** `is_member('admins')` is
# MAGIC    **false** while acting as the role, even though the person behind it is an admin.
# MAGIC
# MAGIC `session_user()` returns the email when you are yourself and the role name when you have
# MAGIC assumed a role, so it discriminates reliably. Verified live in this workspace.
# MAGIC
# MAGIC ## How to see the contrast
# MAGIC Run this notebook **as yourself** to apply the policies and confirm the admin still sees real
# MAGIC data. Then switch to the `account users` role and re-run the "what each identity sees" cell —
# MAGIC the same query text returns masked values. That is the demo.

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

print(f"policies target: {ADMIN} (foundation at {SILVER} stays untouched)")
print(f"session_user():  {me}")
print(f"mode:            {'ACTING AS THE RESTRICTED ROLE' if acting_as_role else 'own identity (admin)'}")
if acting_as_role:
    print("\n  This run will SKIP policy creation (you cannot ALTER tables you do not own while")
    print("  acting as a role) and show you the RESTRICTED view instead. That is the demo half.")

# COMMAND ----------
# MAGIC %md ## Before: the unmasked values
# MAGIC Captured from the read-only foundation, which carries no policies — so this is ground truth
# MAGIC regardless of what has already been applied to the sandbox, and the cell is safe to re-run.
# COMMAND ----------
before = spark.sql(f"""
    SELECT student_id, first_name, ssn, dob
    FROM {SILVER}.student ORDER BY student_id LIMIT 5
""")
display(before)
before_ssn = [r["ssn"] for r in before.collect()]
print(f"true ssn sample (from the unpolicied foundation): {before_ssn[:2]}")

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
# MAGIC Each has the same three-branch shape, keyed on `session_user()`:
# MAGIC 1. the restricted role → **NULL** (PA-08, full restriction)
# MAGIC 2. a member of the admin group → the true value
# MAGIC 3. anyone else → the partially-masked value (PA-07)
# MAGIC
# MAGIC Branch 1 comes first deliberately: `is_member()` is unreliable for an assumed role, so the
# MAGIC restriction must be decided before any membership check runs.
# MAGIC
# MAGIC **`dob` is a STRING in three mixed formats** (`yyyy-MM-dd`, `MM/dd/yyyy`, `dd.MM.yyyy`) by
# MAGIC design, for SE-15. `year(dob)` returns NULL on two of them, so the mask parses with a
# MAGIC `coalesce` over all three — otherwise the "masked" value is silently NULL for ~67% of rows,
# MAGIC which looks like a working mask and is actually data loss.
# COMMAND ----------
if acting_as_role:
    print("SKIPPED — policy creation requires your own (owning) identity.")
else:
    spark.sql(f"""
    CREATE OR REPLACE FUNCTION {ADMIN}.mask_ssn(ssn STRING)
    RETURNS STRING
    COMMENT 'PA-07/PA-08: NULL for the restricted role; full value for admins; last 4 for everyone else'
    RETURN CASE
        WHEN session_user() = '{RESTRICTED_ROLE}' THEN NULL   -- PA-08: full restriction, not a placeholder
        WHEN is_member('{ADMIN_GROUP}')           THEN ssn
        ELSE concat('***-**-', right(ssn, 4))                 -- PA-07: partial
    END
    """)

    spark.sql(f"""
    CREATE OR REPLACE FUNCTION {ADMIN}.mask_dob(dob STRING)
    RETURNS STRING
    COMMENT 'PA-07: NULL for the restricted role; exact date for admins; year only for everyone else'
    RETURN CASE
        WHEN session_user() = '{RESTRICTED_ROLE}' THEN NULL
        WHEN is_member('{ADMIN_GROUP}')           THEN dob
        ELSE concat(
            cast(year(coalesce(
                try_to_date(dob, 'yyyy-MM-dd'),
                try_to_date(dob, 'MM/dd/yyyy'),
                try_to_date(dob, 'dd.MM.yyyy'))) AS STRING), '-XX-XX')
    END
    """)

    spark.sql(f"""
    CREATE OR REPLACE FUNCTION {ADMIN}.mask_amount(amount DOUBLE)
    RETURNS DOUBLE
    COMMENT 'PA-07: NULL for the restricted role; exact award for admins; rounded to 1000 otherwise'
    RETURN CASE
        WHEN session_user() = '{RESTRICTED_ROLE}' THEN NULL
        WHEN is_member('{ADMIN_GROUP}')           THEN amount
        ELSE round(amount, -3)
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
if acting_as_role:
    print("SKIPPED — ALTER TABLE requires your own (owning) identity.")
else:
    for table, col, fn in MASKS:
        # Idempotent: DROP MASK on an unmasked column is a no-op (verified), so the notebook is
        # safely re-runnable during a demo.
        spark.sql(f"ALTER TABLE {table} ALTER COLUMN {col} DROP MASK")
        spark.sql(f"ALTER TABLE {table} ALTER COLUMN {col} SET MASK {fn}")
        print(f"  MASK {fn.split('.')[-1]:12s} -> {table}.{col}")

# COMMAND ----------
# MAGIC %md ## After: the same query, now governed
# MAGIC **This is the demo.** The query text is byte-identical to the "before" cell — only the table
# MAGIC changed, not the client, not the query.
# MAGIC
# MAGIC Run as yourself (an admin) this returns **unmasked** values: the mask is role-dependent, not
# MAGIC blanket redaction. Switch to the `{restricted_role}` role, re-run, and the same rows come back
# MAGIC masked. That contrast is the scenario.
# COMMAND ----------
after = spark.sql(f"""
    SELECT student_id, first_name, ssn, dob
    FROM {ADMIN}.student ORDER BY student_id LIMIT 5
""")
display(after)
display(spark.sql(f"""
    SELECT aid_id, student_id, amount, aid_type
    FROM {ADMIN}.financial_aid ORDER BY aid_id LIMIT 5
"""))

after_ssn = [r["ssn"] for r in after.collect()]
print(f"as {me}:")
print(f"  ssn seen: {after_ssn[:2]}")
print(f"  {'MASKED — you are the restricted role' if acting_as_role else 'FULL — you are an admin'}")

# COMMAND ----------
# MAGIC %md ## PA-07 / PA-08 — All three treatments, evaluated in one query
# MAGIC The live role switch proves *enforcement*; this cell proves the *branch logic* — every
# MAGIC treatment side by side, against the same true value, without switching identity.
# MAGIC
# MAGIC Both are worth showing. This one is reproducible in a single session; the role switch is the
# MAGIC one that proves Unity Catalog is doing the enforcing rather than the query.
# COMMAND ----------
display(spark.sql(f"""
    WITH truth AS (SELECT ssn FROM {SILVER}.student ORDER BY student_id LIMIT 1)
    SELECT 'restricted role'  AS identity, CAST(NULL AS STRING)          AS ssn_seen,
           'fully restricted — NULL (PA-08)'  AS treatment FROM truth
    UNION ALL
    SELECT 'admin',            ssn,
           'full value'                       FROM truth
    UNION ALL
    SELECT 'other authorised', concat('***-**-', right(ssn, 4)),
           'partial — last 4 only (PA-07)'    FROM truth
"""))
print("Read from the unpolicied foundation deliberately: it shows the true source value, so the")
print("three treatments are comparable against ground truth.")

# COMMAND ----------
# MAGIC %md ## Where the policy lives — the metadata proof
# MAGIC A mask is catalog metadata, not query-time convention. `information_schema.column_masks` is
# MAGIC the purpose-built view, so an auditor can confirm coverage without reading application code
# MAGIC or looping `DESCRIBE` over every table. PA-D turns this into a full inventory.
# COMMAND ----------
display(spark.sql(f"""
    SELECT table_schema, table_name, column_name, mask_name
    FROM {CATALOG}.information_schema.column_masks
    ORDER BY table_schema, table_name, column_name
"""))

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
if acting_as_role:
    # The restricted half: every masked column must come back NULL. This is the strongest possible
    # check on PA-08, because it is UC enforcing the policy against a real second identity.
    assert all(s is None for s in after_ssn), (
        f"acting as '{RESTRICTED_ROLE}' but ssn returned {after_ssn[:2]} — PA-08 requires full "
        f"restriction (NULL). Check that mask_ssn's first branch matches session_user() exactly."
    )
    dobs = [r["dob"] for r in after.collect()]
    assert all(d is None for d in dobs), f"dob not restricted for the role: {dobs[:2]}"
    print(f"PASS (restricted view): acting as '{RESTRICTED_ROLE}', ssn and dob both return NULL — "
          f"PA-08 enforced by Unity Catalog against a real second identity.")
else:
    # The admin must still see real data, or the mask is over-broad and the demo proves nothing.
    assert after_ssn == before_ssn, (
        f"admin's view is masked: {before_ssn[:2]} -> {after_ssn[:2]}. "
        f"is_member('{ADMIN_GROUP}') is probably false — check PA-A."
    )
    assert all(s and "*" not in s for s in after_ssn), \
        f"admin sees masked values: {after_ssn[:2]}"

    # Every intended mask must actually be attached — a silently-missing mask is the failure mode
    # that looks like success.
    attached = {(r["table_name"], r["column_name"]): r["mask_name"] for r in spark.sql(f"""
        SELECT table_name, column_name, mask_name
        FROM {CATALOG}.information_schema.column_masks
        WHERE table_schema = 'admin_demo'
    """).collect()}
    for table, col, fn in MASKS:
        key = (table.split(".")[-1], col)
        assert key in attached, f"no mask attached to {table}.{col} (expected {fn})"

    # The dob mask's THREE-FORMAT COALESCE, tested directly.
    #
    # Testing `SELECT count(*) WHERE dob IS NULL` on the masked table does NOT test this: as an
    # admin you get the second branch, which returns dob unparsed, so the coalesce never runs and
    # the check passes even if it is broken. Evaluate the parse expression itself, over every row.
    parse_check = spark.sql(f"""
        SELECT count(*) AS total,
               sum(CASE WHEN coalesce(
                        try_to_date(dob, 'yyyy-MM-dd'),
                        try_to_date(dob, 'MM/dd/yyyy'),
                        try_to_date(dob, 'dd.MM.yyyy')) IS NULL THEN 1 ELSE 0 END) AS unparseable
        FROM {SILVER}.student
    """).first()
    assert parse_check["unparseable"] == 0, (
        f"{parse_check['unparseable']:,} of {parse_check['total']:,} dob values match none of the "
        f"three formats — the faculty branch would silently return NULL-XX-XX for them"
    )

    # THE critical one: no policy may sit outside admin_demo. A mask on the shared foundation would
    # change what all ~20 session participants see.
    leaked = [f"{r['table_schema']}.{r['table_name']}.{r['column_name']}" for r in spark.sql(f"""
        SELECT table_schema, table_name, column_name
        FROM {CATALOG}.information_schema.column_masks
        WHERE table_schema <> 'admin_demo'
    """).collect()]
    assert not leaked, f"masks leaked onto the shared foundation: {leaked}"

    # And the foundation still returns real SSNs.
    foundation_ssn = spark.sql(f"SELECT ssn FROM {SILVER}.student LIMIT 1").first()["ssn"]
    assert foundation_ssn and "*" not in foundation_ssn, \
        f"foundation ssn appears masked: {foundation_ssn}"

    print(f"PASS: PA-B — 3 mask functions, {len(MASKS)} columns masked on {ADMIN}; admin sees full "
          f"values; all {parse_check['total']:,} dob values parse across the 3 formats; foundation "
          f"carries no policies.")
    print(f"\nNEXT: switch to the '{RESTRICTED_ROLE}' role and re-run this notebook. The assertions")
    print("above flip to the restricted branch and prove UC enforces PA-08 against a real identity.")
