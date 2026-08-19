# Databricks notebook source
# MAGIC %md
# MAGIC # E5 — "Kitchen-sink" transformation pipeline (SE-11 … SE-20)
# MAGIC One pipeline demonstrating ten transformation capabilities against the shared
# MAGIC foundation. Each section maps to one RFP scenario. Outputs go to a per-person
# MAGIC `wksp_<you>` schema (foundation stays read-only).
# MAGIC
# MAGIC | § | Scenario |
# MAGIC |---|----------|
# MAGIC | SE-11 | Lookup / reference-data enrichment (matched + unmatched handling) |
# MAGIC | SE-12 | Join — inner / left-outer / full-outer |
# MAGIC | SE-13 | String manipulation (substring, concat, split, trim, case) |
# MAGIC | SE-14 | Null detection & conditional logic (coalesce, if/then/else) |
# MAGIC | SE-15 | Date & time handling (parse mixed formats, extract parts, diffs) |
# MAGIC | SE-16 | Type casting & validation (valid → typed; invalid → reject path) |
# MAGIC | SE-17 | Aggregation & running totals (control-break by composite key) |
# MAGIC | SE-18 | Pivot — rows→columns and back |
# MAGIC | SE-19 | Last-record-in-group identification |
# MAGIC | SE-20 | Grouped iteration → one summary row per group |

# COMMAND ----------
import re
from pyspark.sql import functions as F
from pyspark.sql.window import Window

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
SILVER = f"{CATALOG}.silver{SUFFIX}"

user = spark.sql("SELECT current_user()").first()[0]
WS = "wksp_" + re.sub(r"[^a-zA-Z0-9]", "_", user)
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{WS}")
OUT = f"{CATALOG}.{WS}"

student = spark.table(f"{SILVER}.student")
enrollment = spark.table(f"{SILVER}.enrollment")
course = spark.table(f"{SILVER}.course")
department = spark.table(f"{SILVER}.department")
financial_aid = spark.table(f"{SILVER}.financial_aid")
term = spark.table(f"{SILVER}.term")

# COMMAND ----------
# MAGIC %md ## SE-11 — Lookup / reference-data enrichment (matched + unmatched)
# MAGIC Enrich each student with their department name via a lookup; unmatched → flagged.
# COMMAND ----------
dept_lookup = department.select("dept_id", F.col("name").alias("dept_name"))
se11 = (student.join(dept_lookup, "dept_id", "left")
        .withColumn("dept_match", F.when(F.col("dept_name").isNotNull(), F.lit("matched"))
                                   .otherwise(F.lit("UNMATCHED"))))
print("SE-11 unmatched rows:", se11.filter(F.col("dept_match") == "UNMATCHED").count())

# COMMAND ----------
# MAGIC %md ## SE-12 — Joins: inner / left-outer / full-outer
# COMMAND ----------
s = student.select("student_id", "dept_id")
a = financial_aid.select("student_id", "amount")
print("SE-12 inner:", s.join(a, "student_id", "inner").count(),
      "| left:", s.join(a, "student_id", "left").count(),
      "| full:", s.join(a, "student_id", "full").count())

# COMMAND ----------
# MAGIC %md ## SE-13 — String manipulation (substring, concat, split, trim, case)
# COMMAND ----------
se13 = (student.select("student_id", "first_name", "last_name", "email")
        .withColumn("full_name", F.concat_ws(", ", F.upper("last_name"), F.initcap("first_name")))
        .withColumn("email_domain", F.split(F.col("email"), "@").getItem(1))
        .withColumn("initials", F.concat(F.substring("first_name", 1, 1),
                                          F.substring(F.regexp_replace("last_name", "[^A-Za-z]", ""), 1, 1))))
se13.select("student_id", "full_name", "email_domain", "initials").show(3, truncate=False)

# COMMAND ----------
# MAGIC %md ## SE-14 — Null detection & conditional logic
# COMMAND ----------
se14 = (student
        .withColumn("email_filled", F.coalesce(F.col("email"), F.lit("no-email@princeton.edu")))
        .withColumn("email_was_null", F.col("email").isNull())
        .withColumn("standing", F.when(F.col("status") == "active", "In Good Standing")
                                 .when(F.col("status") == "graduated", "Alumnus")
                                 .otherwise("Inactive")))
print("SE-14 null emails replaced:", se14.filter(F.col("email_was_null")).count())

# COMMAND ----------
# MAGIC %md ## SE-15 — Date handling (parse mixed formats, extract parts, diffs, tz-convert)
# MAGIC dob arrives as mixed strings (ISO / MM/DD/YYYY / DD.MM.YYYY). Coalesce over
# MAGIC multiple to_date patterns parses all three natively (no UDF). The foundation is
# MAGIC date-only, so time-zone conversion is shown on a real UTC load timestamp.
# COMMAND ----------
se15 = (student.withColumn("dob_parsed",
            # try_to_date returns NULL on format mismatch (to_date throws in ANSI mode),
            # so coalescing over the three known formats parses all of them safely.
            F.coalesce(F.expr("try_to_date(dob, 'yyyy-MM-dd')"),
                       F.expr("try_to_date(dob, 'MM/dd/yyyy')"),
                       F.expr("try_to_date(dob, 'dd.MM.yyyy')")))
        .withColumn("birth_year", F.year("dob_parsed"))
        .withColumn("birth_dow", F.date_format("dob_parsed", "EEEE"))
        .withColumn("age_years", F.floor(F.datediff(F.current_date(), F.col("dob_parsed")) / 365.25))
        # SE-15 time-zone conversion: stamp a UTC load time and convert it between zones.
        .withColumn("load_ts_utc", F.current_timestamp())
        .withColumn("load_ts_eastern", F.from_utc_timestamp(F.col("load_ts_utc"), "America/New_York"))
        .withColumn("load_ts_pacific", F.from_utc_timestamp(F.col("load_ts_utc"), "America/Los_Angeles")))
print("SE-15 dob parse failures (should be 0):", se15.filter(F.col("dob_parsed").isNull()).count())
se15.select("dob", "dob_parsed", "birth_year", "birth_dow", "age_years",
            "load_ts_utc", "load_ts_eastern", "load_ts_pacific").show(3, truncate=False)

# COMMAND ----------
# MAGIC %md ## SE-16 — Type casting & validation (valid → typed; invalid → reject path)
# MAGIC Cast gpa_points to double; rows that fail the cast route to a reject table
# MAGIC instead of aborting the pipeline. (We inject a couple of bad values to prove it.)
# COMMAND ----------
# Inject bad values, then MATERIALIZE once (write to a temp table) so the injection is
# computed a single time — splitting a lazy chain that re-derives injected values can
# yield inconsistent membership. try_cast tolerates the bad value (plain cast throws in ANSI).
enr_cast = (enrollment
    .withColumn("gpa_raw", F.when(F.col("enrollment_id") % 5000 == 0, F.lit("N/A"))
                            .otherwise(F.col("gpa_points").cast("string")))
    .withColumn("gpa_typed", F.expr("try_cast(gpa_raw as double)")))
enr_cast.write.mode("overwrite").saveAsTable(f"{OUT}.e5_cast_staged")
staged = spark.table(f"{OUT}.e5_cast_staged")
# reject = had a non-null raw value that failed to cast (bad data); valid = everything else
reject = staged.filter(F.col("gpa_raw").isNotNull() & F.col("gpa_typed").isNull())
valid = staged.subtract(reject)
reject.write.mode("overwrite").saveAsTable(f"{OUT}.e5_cast_rejects")
print(f"SE-16 valid: {valid.count()}  rejected: {reject.count()} "
      f"(bad values routed to e5_cast_rejects; pipeline did not abort)")

# COMMAND ----------
# MAGIC %md ## SE-17 — Aggregation & running totals with control-break (composite key)
# MAGIC Running enrollment count per (dept_id, term_id), resetting at each dept boundary.
# COMMAND ----------
enr_dept = enrollment.join(student.select("student_id", "dept_id"), "student_id", "left")
by_dept_term = (enr_dept.groupBy("dept_id", "term_id").agg(F.count("*").alias("enrollments")))
w_run = Window.partitionBy("dept_id").orderBy("term_id").rowsBetween(Window.unboundedPreceding, Window.currentRow)
se17 = by_dept_term.withColumn("running_total_in_dept", F.sum("enrollments").over(w_run))
se17.write.mode("overwrite").saveAsTable(f"{OUT}.e5_running_totals")
print("SE-17 running totals written:", se17.count())
se17.orderBy("dept_id", "term_id").show(6)

# COMMAND ----------
# MAGIC %md ## SE-18 — Pivot (rows→columns) and unpivot (columns→rows)
# MAGIC Grade counts per department, pivoted wide; then melted back to long.
# COMMAND ----------
wide = (enr_dept.groupBy("dept_id").pivot("grade").count().na.fill(0))
wide.write.mode("overwrite").saveAsTable(f"{OUT}.e5_grade_pivot")
grade_cols = [c for c in wide.columns if c != "dept_id"]
long = wide.selectExpr("dept_id",
    "stack({n}, {pairs}) as (grade, cnt)".format(
        n=len(grade_cols),
        pairs=", ".join([f"'{c}', `{c}`" for c in grade_cols])))
print("SE-18 pivot cols:", grade_cols)
print("SE-18 unpivot rows:", long.count())

# COMMAND ----------
# MAGIC %md ## SE-19 — Last-record-in-group identification
# MAGIC Flag the latest enrollment (by term) per student.
# COMMAND ----------
w_last = Window.partitionBy("student_id").orderBy(F.desc("term_id"))
se19 = (enrollment.withColumn("rn", F.row_number().over(w_last))
        .withColumn("is_last_in_group", F.col("rn") == 1))
se19.filter("is_last_in_group").drop("rn").write.mode("overwrite").saveAsTable(f"{OUT}.e5_last_enrollment")
print("SE-19 last-per-student rows:", se19.filter("is_last_in_group").count())

# COMMAND ----------
# MAGIC %md ## SE-20 — Grouped iteration → one summary row per group
# MAGIC Per student: accumulate a GPA summary + concatenated grade history (single row/group).
# COMMAND ----------
se20 = (enrollment.groupBy("student_id").agg(
            F.count("*").alias("courses_taken"),
            F.round(F.avg("gpa_points"), 3).alias("avg_gpa"),
            F.sort_array(F.collect_list("grade")).alias("grade_history"),
            F.sum(F.when(F.col("grade") == "F", 1).otherwise(0)).alias("failures")))
se20.write.mode("overwrite").saveAsTable(f"{OUT}.e5_student_summary")
print("SE-20 one-row-per-student summaries:", se20.count())
se20.show(3, truncate=False)

# COMMAND ----------
# MAGIC %md ## Verify — all E5 outputs present
# COMMAND ----------
for t in ["e5_cast_rejects", "e5_running_totals", "e5_grade_pivot",
          "e5_last_enrollment", "e5_student_summary"]:
    print(f"{t}: {spark.table(f'{OUT}.{t}').count()}")
print("PASS: SE-11..SE-20 transformation patterns demonstrated ->", OUT)
