# Databricks notebook source
# MAGIC %md
# MAGIC # SFTP file ingestion (SE-09) — Auto Loader → Bronze
# MAGIC Ingests the SFTP-landed `financial_aid_*.csv` files from the UC Volume into a
# MAGIC Bronze table using Auto Loader (cloudFiles) with an availableNow batch trigger —
# MAGIC a native, incremental, script-free ingestion path.

# COMMAND ----------
dbutils.widgets.text("catalog", "princeton_poc")
dbutils.widgets.text("schema_suffix", "")
CAT = dbutils.widgets.get("catalog")
SUF = dbutils.widgets.get("schema_suffix")
VOL = f"/Volumes/{CAT}/landing{SUF}/files/sftp"
BRONZE = f"{CAT}.bronze{SUF}.sftp_financial_aid"
CHK = f"/Volumes/{CAT}/landing{SUF}/files/_chk/sftp_financial_aid"

# COMMAND ----------
# MAGIC %md ## Auto Loader: Volume → Bronze (availableNow batch)
# COMMAND ----------
q = (spark.readStream.format("cloudFiles")
     .option("cloudFiles.format", "csv")
     .option("header", True)
     .option("cloudFiles.schemaLocation", CHK)
     .load(VOL)
     .writeStream
     .option("checkpointLocation", CHK)
     .trigger(availableNow=True)
     .toTable(BRONZE))
q.awaitTermination()

# COMMAND ----------
# MAGIC %md ## Assert Bronze row count (3 files × 200 rows = 600)
# COMMAND ----------
cnt = spark.table(BRONZE).count()
print(f"{BRONZE} rows: {cnt} (expect 600)")
assert cnt == 600, f"expected 600, got {cnt}"
print("PASS: SFTP-landed files ingested to Bronze via Auto Loader.")
