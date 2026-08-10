# E1 — Multi-format file ingestion as a Lakeflow Spark Declarative Pipeline (SE-04/05/06/07)
#
# Five bronze streaming tables, one per source format, ingested with Auto Loader.
# This is the SDP (recommended) form of E1 — the engineer generates code like this from a
# Genie prompt, targets their own schema via the pipeline config, and deploys+runs it.
#
# Target catalog/schema come from the pipeline resource config (see e1_pipeline.pipeline.yml),
# NOT from this file — the pipeline creates its schema + tables in that destination.
# Auto Loader manages schemaLocation + checkpoints automatically; do not set them.

from pyspark import pipelines as dp

LANDING = spark.conf.get("landing_path")  # e.g. /Volumes/princeton_poc_dev/landing_dev/files


# SE-04 — CSV with quoted fields + embedded delimiters
@dp.table(name="e1_students_raw", comment="SE-04: CSV, quoted embedded commas preserved")
def e1_students_raw():
    return (spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "csv")
            .option("header", True).option("quote", '"').option("escape", '"')
            .option("cloudFiles.inferColumnTypes", True)
            .load(f"{LANDING}/students_csv"))


# SE-04 — pipe-delimited text
@dp.table(name="e1_enrollments_raw", comment="SE-04: pipe-delimited")
def e1_enrollments_raw():
    return (spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "csv")
            .option("header", True).option("sep", "|").option("quote", '"')
            .option("cloudFiles.inferColumnTypes", True)
            .load(f"{LANDING}/enrollments_pipe"))


# SE-05 — multi-sheet Excel, named sheet (Auto Loader excel format, DBR 17.1+)
@dp.table(name="e1_financial_aid_raw", comment="SE-05: Excel, AidDetail sheet")
def e1_financial_aid_raw():
    return (spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "excel")
            .option("dataAddress", "AidDetail").option("headerRows", 1)
            .option("cloudFiles.inferColumnTypes", True)
            # Excel via Auto Loader does not support schema evolution — must be 'none'.
            .option("cloudFiles.schemaEvolutionMode", "none")
            # Auto Loader monitors a DIRECTORY (not a single file); the .xlsx lives inside it.
            .load(f"{LANDING}/financial_aid_xlsx"))


# SE-06 — nested JSON
@dp.table(name="e1_course_catalog_raw", comment="SE-06: nested JSON")
def e1_course_catalog_raw():
    return (spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "json")
            .option("multiLine", True)
            .option("cloudFiles.inferColumnTypes", True)
            .load(f"{LANDING}/course_catalog_json"))


# SE-07 — XML with repeating elements + optional nodes
@dp.table(name="e1_faculty_raw", comment="SE-07: XML, optional <tenure> node -> null")
def e1_faculty_raw():
    return (spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "xml")
            .option("rowTag", "faculty")
            .option("cloudFiles.inferColumnTypes", True)
            .load(f"{LANDING}/faculty_xml"))
