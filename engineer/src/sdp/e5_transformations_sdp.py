# E5 — "Kitchen-sink" transformations as a Lakeflow SDP (SE-11 … SE-20)
#
# Batch transforms over the shared foundation Silver → materialized views (one per
# scenario group). SE-16 (cast validation / reject path) uses Expectations declaratively:
# a "valid" MV that drops bad casts, plus a "rejects" MV that keeps them for inspection.
#
# Reads the shared read-only foundation; the pipeline publishes MVs into the per-person
# target schema set in e5_pipeline.pipeline.yml.

from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.window import Window

SILVER = spark.conf.get("silver_schema")  # e.g. princeton_poc_dev.silver_dev


# SE-11/12/13/14/16 — student enriched: lookup + join + string + null/conditional + typed
@dp.materialized_view(name="e5_student_enriched",
                      comment="SE-11 dept lookup, SE-12 left join aid, SE-13 string, SE-14 null/conditional")
def e5_student_enriched():
    student = spark.read.table(f"{SILVER}.student")
    dept = spark.read.table(f"{SILVER}.department").select(
        "dept_id", F.col("name").alias("dept_name"))
    aid = (spark.read.table(f"{SILVER}.financial_aid")
           .groupBy("student_id").agg(F.sum("amount").alias("total_aid")))
    return (student
        .join(dept, "dept_id", "left")                                    # SE-11 lookup
        .join(aid, "student_id", "left")                                  # SE-12 left join
        .withColumn("dept_match", F.when(F.col("dept_name").isNotNull(), "matched").otherwise("UNMATCHED"))
        .withColumn("full_name", F.concat_ws(", ", F.upper("last_name"), F.initcap("first_name")))  # SE-13
        .withColumn("email_domain", F.split("email", "@").getItem(1))     # SE-13 split
        .withColumn("aid_amount", F.coalesce("total_aid", F.lit(0.0)))    # SE-14 coalesce
        .withColumn("standing", F.when(F.col("status") == "active", "In Good Standing")  # SE-14 conditional
                                 .when(F.col("status") == "graduated", "Alumnus")
                                 .otherwise("Inactive"))
        .select("student_id", "full_name", "email_domain", "dept_name",
                "dept_match", "aid_amount", "standing", "status"))


# SE-15 — date handling: parse mixed formats, extract parts, calculate diffs, convert time zones
@dp.materialized_view(name="e5_student_dates",
                      comment="SE-15 parse mixed dob formats (try_to_date), extract parts, age, tz-convert a load timestamp")
def e5_student_dates():
    return (spark.read.table(f"{SILVER}.student")
        .withColumn("dob_parsed", F.coalesce(
            F.expr("try_to_date(dob, 'yyyy-MM-dd')"),
            F.expr("try_to_date(dob, 'MM/dd/yyyy')"),
            F.expr("try_to_date(dob, 'dd.MM.yyyy')")))
        .withColumn("birth_year", F.year("dob_parsed"))
        .withColumn("birth_dow", F.date_format("dob_parsed", "EEEE"))
        .withColumn("age_years", F.floor(F.datediff(F.current_date(), F.col("dob_parsed")) / 365.25))
        # SE-15 time-zone conversion: the foundation is date-only, so stamp a real UTC load
        # timestamp and convert it between zones — the load-time-in-local-zone pattern.
        .withColumn("load_ts_utc", F.current_timestamp())
        .withColumn("load_ts_eastern", F.from_utc_timestamp(F.col("load_ts_utc"), "America/New_York"))
        .withColumn("load_ts_pacific", F.from_utc_timestamp(F.col("load_ts_utc"), "America/Los_Angeles"))
        .select("student_id", "dob", "dob_parsed", "birth_year", "birth_dow", "age_years",
                "load_ts_utc", "load_ts_eastern", "load_ts_pacific"))


# SE-16 — cast validation. Valid rows only: expectation drops rows whose gpa fails to cast.
# (Bad values injected to prove the reject path; W-grades legitimately have null gpa.)
@dp.materialized_view(name="e5_gpa_valid",
                      comment="SE-16 valid casts (expect_or_drop quarantines bad ones)")
@dp.expect_or_drop("gpa_castable", "gpa_typed IS NOT NULL OR gpa_raw IS NULL")
def e5_gpa_valid():
    return (spark.read.table(f"{SILVER}.enrollment")
        .withColumn("gpa_raw", F.when(F.col("enrollment_id") % 5000 == 0, F.lit("N/A"))
                                .otherwise(F.col("gpa_points").cast("string")))
        .withColumn("gpa_typed", F.expr("try_cast(gpa_raw as double)")))


# SE-16 — the reject path made visible: the rows the expectation would drop.
@dp.materialized_view(name="e5_gpa_rejects",
                      comment="SE-16 reject path — bad casts captured for inspection")
def e5_gpa_rejects():
    return (spark.read.table(f"{SILVER}.enrollment")
        .withColumn("gpa_raw", F.when(F.col("enrollment_id") % 5000 == 0, F.lit("N/A"))
                                .otherwise(F.col("gpa_points").cast("string")))
        .withColumn("gpa_typed", F.expr("try_cast(gpa_raw as double)"))
        .filter("gpa_raw IS NOT NULL AND gpa_typed IS NULL"))


# SE-17 — aggregation + running totals with control-break by (dept, term)
@dp.materialized_view(name="e5_running_totals",
                      comment="SE-17 running enrollment total per dept, reset at dept boundary")
def e5_running_totals():
    enr_dept = (spark.read.table(f"{SILVER}.enrollment")
                .join(spark.read.table(f"{SILVER}.student").select("student_id", "dept_id"),
                      "student_id", "left"))
    by = enr_dept.groupBy("dept_id", "term_id").agg(F.count("*").alias("enrollments"))
    w = Window.partitionBy("dept_id").orderBy("term_id").rowsBetween(Window.unboundedPreceding, Window.currentRow)
    return by.withColumn("running_total_in_dept", F.sum("enrollments").over(w))


# SE-18 — pivot: grade counts per department, wide
@dp.materialized_view(name="e5_grade_pivot", comment="SE-18 pivot grades to columns per dept")
def e5_grade_pivot():
    enr_dept = (spark.read.table(f"{SILVER}.enrollment")
                .join(spark.read.table(f"{SILVER}.student").select("student_id", "dept_id"),
                      "student_id", "left"))
    return enr_dept.groupBy("dept_id").pivot("grade").count().na.fill(0)


# SE-19 — last-record-in-group: latest enrollment per student
@dp.materialized_view(name="e5_last_enrollment", comment="SE-19 last enrollment per student")
def e5_last_enrollment():
    w = Window.partitionBy("student_id").orderBy(F.desc("term_id"))
    return (spark.read.table(f"{SILVER}.enrollment")
            .withColumn("rn", F.row_number().over(w))
            .filter("rn = 1").drop("rn"))


# SE-20 — grouped iteration → one summary row per student
@dp.materialized_view(name="e5_student_summary", comment="SE-20 one summary row per student")
def e5_student_summary():
    return (spark.read.table(f"{SILVER}.enrollment").groupBy("student_id").agg(
        F.count("*").alias("courses_taken"),
        F.round(F.avg("gpa_points"), 3).alias("avg_gpa"),
        F.sort_array(F.collect_list("grade")).alias("grade_history"),
        F.sum(F.when(F.col("grade") == "F", 1).otherwise(0)).alias("failures")))
