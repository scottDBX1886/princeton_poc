# Databricks notebook source
# MAGIC %md
# MAGIC # 00 — UC namespace setup (default storage)
# MAGIC Creates the catalog, schemas, and landing volume via **SQL on serverless**, which
# MAGIC triggers Databricks **default storage** provisioning. This is intentionally NOT a DAB
# MAGIC `catalogs` resource: the DAB/UC REST API creates a location-less catalog with no backing
# MAGIC storage (tables/volumes then fail with `credentialName = None`), whereas `CREATE CATALOG`
# MAGIC on a serverless warehouse provisions default managed storage automatically.
# MAGIC See docs/aws/storage/default-storage. Runs as the first task of the foundation job so the
# MAGIC catalog exists before any pipeline/dashboard/table references it.

# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")

# COMMAND ----------
# Catalog on DEFAULT STORAGE — no LOCATION clause (serverless provisions storage).
spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG} COMMENT 'Princeton POC shared data foundation'")

for layer, comment in [
    ("bronze",  "Raw ingested data"),
    ("silver",  "Conformed dimensions + facts"),
    ("gold",    "Curated / aggregated"),
    ("landing", "Source-file landing"),
    ("models",  "UC-registered MLflow models (DS-06(b) / DS-E)"),
]:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{layer}{SUFFIX} COMMENT '{comment}'")

# Managed landing volume (inherits catalog default storage).
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.landing{SUFFIX}.files")

# COMMAND ----------
# Verify
schemas = [r.databaseName for r in spark.sql(f"SHOW SCHEMAS IN {CATALOG}").collect()]
print(f"catalog {CATALOG} schemas:", schemas)
vols = spark.sql(f"SHOW VOLUMES IN {CATALOG}.landing{SUFFIX}").collect()
print("landing volumes:", [v.volume_name for v in vols])
assert f"silver{SUFFIX}" in schemas, "silver schema missing"
print("PASS: UC namespace ready on default storage")
