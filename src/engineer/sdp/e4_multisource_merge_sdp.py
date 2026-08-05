# E4 — Multi-source merge as a Lakeflow SDP (SE-10)
#
# Reconciles three DIFFERENT source types that were each landed in Bronze by their own
# ingestion step (the correct medallion pattern):
#   - FILE  source: e1_students_raw        (landed by E1 from the landing Volume)
#   - API   source: e3_enrollments_from_api (landed by E3 from the OAuth REST API)
#   - DB    source: silver_dev.student      (a governed Delta table — the database-sourced input)
# Joins them on student_id, tags provenance, and publishes one reconciled materialized view.
#
# SE-10 asks for >=3 source TYPES merged in one logical pipeline — satisfied here.
# (SDP can't call the OAuth-gated API itself, so the API leg is consumed from the Bronze
#  table E3 already landed — ingestion auth stays in E3 where it belongs.)

from pyspark import pipelines as dp
from pyspark.sql import functions as F

WKSP = spark.conf.get("wksp_schema")      # e.g. princeton_poc_dev.wksp_<user> (file+API Bronze live here)
SILVER = spark.conf.get("silver_schema")  # e.g. princeton_poc_dev.silver_dev  (DB-sourced input)


@dp.materialized_view(
    name="e4_enrollment_reconciled",
    comment="SE-10: reconcile file (E1) + API (E3) + DB (Silver) sources on student_id")
def e4_enrollment_reconciled():
    # FILE source — students ingested from flat files (tag provenance)
    file_students = (spark.read.table(f"{WKSP}.e1_students_raw")
                     .select("student_id", "first_name", "last_name", "dept_id")
                     .withColumn("student_source", F.lit("file")))

    # DB source — the governed Silver student table (database-sourced)
    db_students = (spark.read.table(f"{SILVER}.student")
                   .select("student_id", "status")
                   .withColumn("db_source", F.lit("db")))

    # API source — enrollments ingested from the REST API
    api_enrollments = (spark.read.table(f"{WKSP}.e3_enrollments_from_api")
                       .select("enrollment_id", "student_id", "course_id", "term_id",
                               "grade", "gpa_points")
                       .withColumn("enrollment_source", F.lit("api")))

    # Reconcile: file students enriched with DB status, joined to API enrollments on student_id
    students = file_students.join(db_students, "student_id", "left")
    return (api_enrollments.join(students, "student_id", "left")
            .withColumn("source_system",
                        F.concat_ws("+", "student_source", "db_source", "enrollment_source"))
            .select("enrollment_id", "student_id", "first_name", "last_name", "dept_id",
                    "status", "course_id", "term_id", "grade", "gpa_points", "source_system"))
