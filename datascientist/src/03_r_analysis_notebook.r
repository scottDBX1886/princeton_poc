# Databricks notebook source
# MAGIC %md
# MAGIC # DS-B / DS-03: R notebook environment (sparklyr)
# MAGIC
# MAGIC Proves the platform is a first-class R environment: connect, query governed tables,
# MAGIC run native R statistics, and write results back as Delta.
# MAGIC
# MAGIC ## ⚠️ Compute requirement — classic, not serverless
# MAGIC Unlike every other notebook in this POC, **DS-03 needs a classic all-purpose cluster
# MAGIC with an R kernel**; serverless notebooks support Python/SQL/Scala only.
# MAGIC
# MAGIC It also uses **`sparklyr`**, not `SparkR` — SparkR was removed in DBR 16.0, and the
# MAGIC runtimes available here are 15.4 / 16.4 / 17.3 / 18.1 / 18.2. `sparklyr` is the
# MAGIC supported R interface to Spark and works across all of them.
# MAGIC
# MAGIC **To run:** attach to a classic cluster (any listed DBR), then Run All.
# MAGIC
# MAGIC Foundation is READ-ONLY; output goes to the caller's own `wksp_<user>` schema.

# COMMAND ----------
# MAGIC %md ## Context
# MAGIC The Python helper isn't importable from an R kernel, so the per-person schema is
# MAGIC derived here with the same rule: `current_user()` with non-alphanumerics collapsed to
# MAGIC underscores. Must stay in step with `_isolation.py:user_schema_name`.
# COMMAND ----------
library(sparklyr)
library(dplyr)

sc <- spark_connect(method = "databricks")

catalog <- "princeton_poc_dev"
suffix <- "_dev"

current_user <- sdf_sql(sc, "SELECT current_user() AS u") %>% collect() %>% pull(u)
user_schema <- paste0("wksp_", gsub("[^a-zA-Z0-9]", "_", current_user))
work <- paste0(catalog, ".", user_schema)
gold <- paste0(catalog, ".gold", suffix)

sdf_sql(sc, paste0("CREATE SCHEMA IF NOT EXISTS ", work))
cat(sprintf("reading %s (read-only) | writing to %s\n", gold, work))

# COMMAND ----------
# MAGIC %md ## Query the governed table, collect to a local R data frame
# COMMAND ----------
query <- sprintf(
  "SELECT gpa_points, grade FROM %s.enrollment_history WHERE gpa_points IS NOT NULL LIMIT 5000",
  gold
)
enrollments <- sdf_sql(sc, query) %>% collect()

cat(sprintf("loaded %d rows into R\n", nrow(enrollments)))

# COMMAND ----------
# MAGIC %md ## Native R statistics
# MAGIC `summary()`, `quantile()`, `sd()`, `table()` — base R on platform data, no export step.
# COMMAND ----------
cat("\nGPA summary:\n"); print(summary(enrollments$gpa_points))
cat("\nGPA quartiles:\n"); print(quantile(enrollments$gpa_points, probs = seq(0, 1, 0.25)))
cat("\nGrade distribution:\n"); print(table(enrollments$grade))

# COMMAND ----------
# MAGIC %md ## Write the summary back as Delta
# COMMAND ----------
summary_df <- data.frame(
  metric = c("n", "mean_gpa", "sd_gpa", "min_gpa", "max_gpa", "median_gpa"),
  value = c(
    nrow(enrollments),
    mean(enrollments$gpa_points, na.rm = TRUE),
    sd(enrollments$gpa_points, na.rm = TRUE),
    min(enrollments$gpa_points, na.rm = TRUE),
    max(enrollments$gpa_points, na.rm = TRUE),
    median(enrollments$gpa_points, na.rm = TRUE)
  ),
  stringsAsFactors = FALSE
)

out <- paste0(work, ".ds_03_r_summary")
sdf_copy_to(sc, summary_df, name = "ds_03_tmp", overwrite = TRUE) %>%
  spark_write_table(name = out, mode = "overwrite")

cat(sprintf("wrote %d metric rows to %s\n", nrow(summary_df), out))

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
stopifnot(nrow(enrollments) > 0)

# Mean must sit inside the 0-4 scale the foundation's grade map defines.
mean_gpa <- mean(enrollments$gpa_points, na.rm = TRUE)
stopifnot(mean_gpa >= 0.0, mean_gpa <= 4.0)

# The written table must be readable back through Spark with every metric intact.
persisted <- sdf_sql(sc, paste0("SELECT * FROM ", out)) %>% collect()
stopifnot(nrow(persisted) == nrow(summary_df))
stopifnot(!any(is.na(persisted$value)))

cat(sprintf("PASS: DS-03 R analysis — %d rows summarised, mean GPA %.3f, %d metrics persisted to Delta.\n",
            nrow(enrollments), mean_gpa, nrow(persisted)))
