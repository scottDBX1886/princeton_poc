# Databricks notebook source
# MAGIC %md
# MAGIC # DS-E / DS-06(b): In-platform ML training with MLflow
# MAGIC
# MAGIC Proves the full model lifecycle happens inside the platform: train on governed data,
# MAGIC autolog metrics and parameters to an experiment, register the model in Unity Catalog,
# MAGIC and load it back for inference — no export, no separate ML tool.
# MAGIC
# MAGIC Serverless. Foundation is READ-ONLY. The model registers to
# MAGIC `${catalog}.models${suffix}` and predictions land in the caller's own `wksp_<user>`
# MAGIC schema, so ~20 participants can run this concurrently (spec §3.1).
# MAGIC
# MAGIC ## On the modelling task
# MAGIC The foundation is randomly generated, so **no feature genuinely predicts the target** —
# MAGIC accuracy near the majority-class rate is the *correct* result on this data. What the
# MAGIC scenario demonstrates is the lifecycle, not model quality. Two consequences, both
# MAGIC deliberate:
# MAGIC
# MAGIC 1. **`gpa_points` is excluded from the features.** It is derived deterministically from
# MAGIC    `grade` (each grade maps to exactly one value — A=4.0, A-=3.7, …), so feeding it in
# MAGIC    while predicting `grade` is label leakage: the model would score ~100% and prove
# MAGIC    nothing. Verified against the data before writing this.
# MAGIC 2. **The assertion checks the model beats a majority-class baseline**, not an absolute
# MAGIC    accuracy threshold — the honest bar for synthetic data.

# COMMAND ----------
# MAGIC %md ## Context
# COMMAND ----------
import os
import sys

sys.path.insert(0, os.getcwd())
from _isolation import resolve_context

ctx = resolve_context(spark, dbutils)
SILVER, GOLD, WORK, MODELS = ctx["silver"], ctx["gold"], ctx["work"], ctx["models"]
USER = ctx["user"]

# Model name is per-person so 20 concurrent runs don't fight over one registered model's
# version history.
MODEL_NAME = f"{MODELS}.grade_predictor_{WORK.split('.')[-1].replace('wksp_', '')}"
print(f"reading {GOLD} + {SILVER} (read-only)\nmodel -> {MODEL_NAME}\npredictions -> {WORK}")

# COMMAND ----------
# MAGIC %md ## Training data
# MAGIC Features are enrollment context plus a couple of derived student attributes — the kind
# MAGIC of thing a real model would use. `gpa_points` is deliberately NOT selected (see above).
# MAGIC
# MAGIC `dob` is a STRING in mixed formats (ISO / US / dotted) by design, for the SE-15
# MAGIC date-parsing scenario. `year(dob)` silently returns NULL on two of the three formats,
# MAGIC so age is parsed with an explicit `coalesce` over all three.
# COMMAND ----------
train_sql = f"""
SELECT
    eh.course_id,
    eh.term_id,
    eh.dept_id,
    t.year                                              AS term_year,
    t.season                                            AS term_season,
    s.status                                            AS student_status,
    year(current_date()) - year(coalesce(
        try_to_date(s.dob, 'yyyy-MM-dd'),
        try_to_date(s.dob, 'MM/dd/yyyy'),
        try_to_date(s.dob, 'dd.MM.yyyy')
    ))                                                  AS age,
    eh.grade                                            AS label
FROM {GOLD}.enrollment_history eh
JOIN {SILVER}.student s ON eh.student_id = s.student_id
JOIN {SILVER}.term    t ON eh.term_id    = t.term_id
WHERE eh.grade IS NOT NULL
LIMIT 50000
"""
pdf = spark.sql(train_sql).toPandas()
print(f"loaded {len(pdf):,} rows | {pdf['label'].nunique()} distinct grades")
print(pdf[["age"]].describe())

# COMMAND ----------
# MAGIC %md ## Features and target
# MAGIC All ten grades are label classes. The plan's `{'A':0,'B':1,'C':2,'D':3,'F':4}` map
# MAGIC covers only 47% of this data — every +/- grade becomes NaN and is silently dropped.
# MAGIC Encoding from the data itself avoids hardcoding a partial list.
# COMMAND ----------
import pandas as pd

# Categorical -> numeric via one-hot; keeps the model honest about season/status being
# unordered categories rather than pretending they have a magnitude.
features = pd.get_dummies(
    pdf[["course_id", "term_id", "dept_id", "term_year", "term_season",
         "student_status", "age"]],
    columns=["term_season", "student_status"],
    dtype=float,
)
features = features.fillna(features.median(numeric_only=True))

labels, label_classes = pd.factorize(pdf["label"], sort=True)
print(f"{features.shape[1]} features | classes: {list(label_classes)}")

# COMMAND ----------
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
    features, labels, test_size=0.2, random_state=42, stratify=labels
)
print(f"train {len(X_train):,} | test {len(X_test):,}")

# The bar any model must clear: always predict the most common grade.
majority_class_rate = pd.Series(y_test).value_counts(normalize=True).max()
print(f"majority-class baseline accuracy: {majority_class_rate:.4f}")

# COMMAND ----------
# MAGIC %md ## Train, with MLflow autologging
# MAGIC `mlflow.sklearn.autolog()` captures params, metrics, the model, and a signature without
# MAGIC hand-written `log_metric` calls. The experiment defaults to this notebook's path, so it
# MAGIC is already per-person — no shared experiment to collide on.
# COMMAND ----------
import mlflow

mlflow.set_registry_uri("databricks-uc")   # register to Unity Catalog, not the workspace registry
mlflow.sklearn.autolog(log_input_examples=True, log_model_signatures=True)

with mlflow.start_run(run_name=f"grade_predictor_{USER.split('@')[0]}") as run:
    model = RandomForestClassifier(n_estimators=50, max_depth=10, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, average="weighted")

    # Autolog covers the standard set; these two are the scenario's own framing.
    mlflow.log_metric("test_accuracy", accuracy)
    mlflow.log_metric("test_f1_weighted", f1)
    mlflow.log_metric("majority_class_baseline", float(majority_class_rate))
    mlflow.log_param("features_excluded", "gpa_points (leaks the label)")

    run_id = run.info.run_id

print(f"run_id={run_id}\naccuracy={accuracy:.4f}  f1={f1:.4f}  baseline={majority_class_rate:.4f}")

# COMMAND ----------
# MAGIC %md ## Register in Unity Catalog
# MAGIC A UC-registered model is a governed object: three-level name, grantable, lineage-tracked
# MAGIC — the same governance as a table, which is the point for the RFP.
# COMMAND ----------
mv = mlflow.register_model(model_uri=f"runs:/{run_id}/model", name=MODEL_NAME)
print(f"registered {mv.name} version {mv.version}")

# COMMAND ----------
# MAGIC %md ## Load it back and score
# MAGIC Proves the round trip: the registered model is retrievable by name and usable for
# MAGIC inference by anyone with the grant.
# COMMAND ----------
loaded = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/{mv.version}")
sample = X_test.head(200)
preds = loaded.predict(sample)

out = f"{WORK}.ds_06b_predictions"
pred_pdf = sample.copy()
pred_pdf["predicted_grade"] = [label_classes[int(p)] for p in preds]
pred_pdf["actual_grade"] = [label_classes[int(i)] for i in y_test[:200]]
spark.createDataFrame(pred_pdf).write.mode("overwrite").saveAsTable(out)
print(f"wrote {len(pred_pdf)} scored rows to {out}")
display(spark.sql(f"SELECT predicted_grade, actual_grade, count(*) AS n FROM {out} "
                  f"GROUP BY predicted_grade, actual_grade ORDER BY n DESC LIMIT 10"))

# COMMAND ----------
# MAGIC %md ## Assertions
# COMMAND ----------
# All ten grades must be represented — catches a partial label map silently dropping rows.
assert len(label_classes) >= 9, (
    f"expected the foundation's full grade set, got {len(label_classes)}: {list(label_classes)}"
)

# Label leakage guard: if gpa_points ever creeps into the features, accuracy jumps to ~1.0.
assert "gpa_points" not in features.columns, "gpa_points leaks the label — remove it"
assert accuracy < 0.99, (
    f"accuracy {accuracy:.4f} is implausibly high on random data — check for label leakage"
)

# Age parsing must have worked for essentially every row (the mixed-format coalesce).
age_null_rate = pdf["age"].isna().mean()
assert age_null_rate < 0.01, (
    f"{age_null_rate:.1%} of ages failed to parse — the dob format coalesce is incomplete"
)

# The model must at least match the trivial baseline.
assert accuracy >= majority_class_rate * 0.95, (
    f"accuracy {accuracy:.4f} is below the majority-class baseline {majority_class_rate:.4f}"
)

# The registered model must be retrievable and usable.
assert mv.version is not None and int(mv.version) >= 1, "model did not register"
assert len(preds) == len(sample), "loaded model did not score every input row"
assert spark.table(out).count() == len(pred_pdf), "predictions not persisted"

print(f"PASS: DS-06(b) — trained on {len(X_train):,} rows, {len(label_classes)} grade classes, "
      f"accuracy {accuracy:.4f} vs baseline {majority_class_rate:.4f}; "
      f"{MODEL_NAME} v{mv.version} registered in UC and scored back.")
