# Databricks notebook source
# MAGIC %md
# MAGIC # PA Task 0 — `admin_demo` schema + copies of the sensitive tables
# MAGIC
# MAGIC Prerequisite for PA-B (column masking), PA-C (row-level security) and PA-D (policy
# MAGIC test + inventory). Nothing here is an RFP scenario on its own; it is the safety
# MAGIC harness those scenarios run inside.
# MAGIC
# MAGIC **Why copies.** `ALTER TABLE … SET COLUMN MASK` / `SET ROW FILTER` mutate the table
# MAGIC *object*, not the caller's session. Applying a mask to `silver_dev.student` would
# MAGIC change what all ~20 session participants see when they read it — and would break the
# MAGIC Engineer pipelines that read the same tables. So the Admin persona demonstrates on
# MAGIC private copies in `${catalog}.admin_demo` and the shared foundation stays untouched
# MAGIC (spec §3.1 rule 4).
# MAGIC
# MAGIC Unlike the other personas there is no per-person `wksp_<user>` split here: PA
# MAGIC scenarios are run ONCE by ONE designated admin while the group observes, so a single
# MAGIC shared `admin_demo` schema is correct.
# MAGIC
# MAGIC Re-runnable: `CREATE OR REPLACE` rebuilds the copies from the foundation, which also
# MAGIC drops any masks/filters a previous PA demo left on them — the documented reset path.

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc")
dbutils.widgets.text("schema_suffix", "")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")

SILVER = f"{CATALOG}.silver{SUFFIX}"     # read-only source of truth
ADMIN = f"{CATALOG}.admin_demo"          # no suffix: one admin schema per catalog

# The three tables the RFP's security scenarios target, and why each is sensitive:
#   student       — ssn, dob (PA-07 masking), dept_id (PA-09/10 row filtering)
#   faculty       — ssn (PA-07), dept_id (PA-09/10)
#   financial_aid — amount (PA-07/08 the CLS target named in the spec)
SENSITIVE_TABLES = ["student", "faculty", "financial_aid"]

print(f"source: {SILVER} (read-only) -> copies: {ADMIN}")

# COMMAND ----------
# MAGIC %md ## Create the schema
# COMMAND ----------
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {ADMIN} "
          f"COMMENT 'Platform Administrator demo copies (PA-B/C/D). "
          f"Masks and row filters are applied HERE, never to the shared foundation.'")
print(f"schema ready: {ADMIN}")

# COMMAND ----------
# MAGIC %md ## Copy the sensitive tables
# MAGIC `CREATE OR REPLACE TABLE … AS SELECT` gives a deep copy: independent data and an
# MAGIC independent set of column masks / row filters. A view would NOT work — a view over
# MAGIC `silver_dev.student` cannot carry its own mask, and masking the view's source would
# MAGIC hit the shared table we are trying to protect.
# COMMAND ----------
for t in SENSITIVE_TABLES:
    src, dst = f"{SILVER}.{t}", f"{ADMIN}.{t}"
    spark.sql(f"CREATE OR REPLACE TABLE {dst} AS SELECT * FROM {src}")
    print(f"  {dst:52s} <- {src}")

# COMMAND ----------
# MAGIC %md ## Assertions
# MAGIC Row counts and column sets must match the foundation exactly — a copy that silently
# MAGIC lost rows or columns would make every downstream PA demo prove the wrong thing.
# COMMAND ----------
for t in SENSITIVE_TABLES:
    src_cnt = spark.table(f"{SILVER}.{t}").count()
    dst_cnt = spark.table(f"{ADMIN}.{t}").count()
    assert src_cnt == dst_cnt, f"{t}: copy has {dst_cnt} rows, foundation has {src_cnt}"

    src_cols = [f.name for f in spark.table(f"{SILVER}.{t}").schema.fields]
    dst_cols = [f.name for f in spark.table(f"{ADMIN}.{t}").schema.fields]
    assert src_cols == dst_cols, f"{t}: column mismatch\n  {src_cols}\n  {dst_cols}"
    print(f"  {t:15s} {dst_cnt:>7,} rows | {len(dst_cols)} cols | matches foundation")

# The PII/CLS columns the later tasks depend on must actually be present.
expected = {"student": ["ssn", "dob", "dept_id"],
            "faculty": ["ssn", "dept_id"],
            "financial_aid": ["amount", "student_id"]}
for t, cols in expected.items():
    have = [f.name for f in spark.table(f"{ADMIN}.{t}").schema.fields]
    missing = [c for c in cols if c not in have]
    assert not missing, f"{t}: PA-B/PA-C target columns missing: {missing}"

# COMMAND ----------
# MAGIC %md ## Confirm the foundation is untouched
# MAGIC The whole point of Task 0. If a mask or filter has leaked onto a shared table, this
# MAGIC fails loudly rather than letting a later demo mislead the customer.
# COMMAND ----------
leaked = []
for t in SENSITIVE_TABLES:
    for row in spark.sql(f"DESCRIBE EXTENDED {SILVER}.{t}").collect():
        blob = " ".join(str(v) for v in row.asDict().values()).lower()
        if "mask" in blob or "row filter" in blob:
            leaked.append(f"{SILVER}.{t}: {row[0]}")
assert not leaked, f"policies found on the SHARED foundation: {leaked}"

print(f"PASS: {ADMIN} holds masked-policy-ready copies of "
      f"{', '.join(SENSITIVE_TABLES)}; foundation carries no policies.")
