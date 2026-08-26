# Princeton POC — Data Scientist Runbook

Scenario entries for the Data Scientist persona (DS-01…DS-09). Prerequisite: the shared
foundation — see [`foundation/RUNBOOK.md`](../foundation/RUNBOOK.md). Index + coverage map:
[`docs/runbook/README.md`](../docs/runbook/README.md).

*Nine of ten scenarios built and verified. Eight notebooks plus two reference guides live in*
`datascientist/src/`*; the AI/BI dashboard body is in* `datascientist/src/dashboards/`*. All read
the shared foundation read-only — every scenario that writes goes to the caller's own*
`wksp_<user>` *schema, derived from* `current_user()` *by* `_isolation.py`*, so ~20 participants
run these concurrently without collision. Per-ID status:*
[`docs/SCENARIO_TRACKER.md`](../docs/SCENARIO_TRACKER.md).

> **Compute:** serverless for everything **except DS-03**, which needs a classic cluster with an
> R kernel (serverless notebooks are Python/SQL/Scala only).

---

## Naming convention — required in every generation prompt

<a name="naming-convention"></a>

Every prompt below opens with this block. It is not boilerplate: a generated notebook that gets
it wrong **runs fine on dev and breaks on qa and prod**, which is the worst way to find out.
The authority is [`foundation/src/00_uc_setup.py`](../foundation/src/00_uc_setup.py) — the task
that actually creates the catalog and schemas.

```text
Read two notebook widgets: "catalog" (default princeton_poc_dev) and "schema_suffix"
(default _dev). The schema_suffix VALUE already contains its leading underscore, so build
schema names by direct concatenation with NO separator:

    f"{catalog}.gold{suffix}"        correct   -> princeton_poc_dev.gold_dev
    f"{catalog}.gold_{suffix}"       WRONG     -> princeton_poc_dev.gold__dev

This matters because the bundle passes schema_suffix="_dev" for dev, "_test" for qa, and an
EMPTY STRING for prod — where the schema is plainly "gold". Putting an underscore in the
f-string yields "gold_" on prod and "gold__test" on qa: both nonexistent.

The five foundation schemas all follow it: bronze{suffix}, silver{suffix}, gold{suffix},
landing{suffix}, models{suffix}. So does the landing volume path:
/Volumes/{catalog}/landing{suffix}/files/

Write nothing to those schemas — they are the shared read-only foundation. Derive my private
output schema instead: query current_user(), replace every non-alphanumeric character with an
underscore, prefix "wksp_", and CREATE SCHEMA IF NOT EXISTS it in {catalog}. That is what lets
~20 people run the same notebook at once without colliding.
```

**Why it's stated this explicitly:** the first prompt-tested generation (DS-02) produced
`f"gold_{schema_suffix}"` with a widget default of `"dev"` — correct on dev by coincidence,
broken on every other target. The prompt had said only "read the catalog and schema suffix from
widgets", which wasn't enough.

### Two more rules, both learned from a failed generation

Every prompt below carries these for the same reason — each one cost a debugging cycle during
prompt testing, and each is invisible until runtime:

| Rule | Why |
|---|---|
| **Name real columns explicitly.** The department table is `(dept_id, name, division, building)` — the name column is `name`, not `department_name`. | DS-04's generation invented `department_name` from the prompt's phrase "keeping department name and division" and failed with `UNRESOLVED_COLUMN`. Prose that reads naturally to a human reads as a column name to a code generator. |
| **Always write Delta with `mode("overwrite")` *and* `.option("overwriteSchema","true")`.** | DS-04's second failure: after fixing the column name, the re-run hit `DELTA_METADATA_MISMATCH` because the table already existed with the old schema. These notebooks are re-run constantly during a demo. |
| **Suffix generated tables with `_prompt`.** | DS-07 collided with the pre-built `ds_07_daily_summary`, which already existed with `unique_students` where the prompt asked for "distinct students". The generation hit `DELTA_METADATA_MISMATCH`, then a `unionByName` failure, and burned two cycles recovering — and overwrote the baseline output in the process. Generated and pre-built must not share table names. |

---

## DS-01 — SQL + Genie exploration

> **Built:** ✅ · **Prompt:** 🟢 tested (`princeton_poc_dev`: all 3 NL prompts generated correct SQL and matched the notebook's numbers — verified)

**What it proves:** a data scientist explores governed data either in SQL or in natural language,
and both paths reach the same answer.

**Setup (SA, done):** Genie space `[princeton_poc_dev] Data Foundation`, created by the
`genie_setup` task of `foundation_build`. Grounded on `gold_dev.enrollment_history` plus the five
silver dimensions.

**How to test — no-code path.** Open the Genie space and paste each prompt. Each maps to a query
in `ds_01_sql_genie_exploration.py`, so the numbers are checkable:

| Prompt | Expect |
|---|---|
| `Which departments have the most enrollments?` | Palmer Department **256,483**, then Edwards 251,111, Mckay 249,697 |
| `Show me average student GPA by term` | 24 terms, GPA **3.078–3.091** — flat by design (random data) |
| `Which faculty members teach the most students, and in what department?` | **Robert Sampson** (id 1950), **7,784** students, Valdez Department |

All three were run through the Genie API and generated correct SQL — the department prompt
produced a `WITH` clause plus `rank()`, matching the notebook's window function unprompted.

**How to test — code path.** Run `ds_01_sql_genie_exploration.py` (serverless). Three queries:
window function, CTE + aggregate, multi-table join with two LEFT joins.

**Expected outcome:** `PASS: DS-01 exploration queries returned ranked, bounded, joinable
results.` Output: `wksp_<user>.ds_01_dept_enrollment_rank` (20 rows).

---

## DS-02 — Python notebook environment (pandas)

> **Built:** ✅ · **Prompt:** 🟢 tested (`princeton_poc_dev`: Assistant-generated notebook reproduced the pre-built output exactly — 9,711 rows, 6,975 students, 10-grade map, per-student rolling GPA — verified)

**What it proves:** platform data moves into the Python ecosystem an analyst already knows,
transforms with pandas, and writes back as a governed Delta table.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a PySpark + pandas notebook for a data scientist working in Databricks.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix value ALREADY includes its leading underscore, so concatenate with no separator —
f"{catalog}.gold{suffix}", never f"gold_{suffix}". The bundle passes _dev / _test / "" (empty, for
prod), so an underscore in the f-string breaks qa and prod while passing on dev. Same for the
volume path: /Volumes/{catalog}/landing{suffix}/files/.

Write nothing to bronze/silver/gold — that is the shared read-only foundation. Derive my private
output schema from current_user(): replace every non-alphanumeric character with an underscore,
prefix "wksp_", and CREATE SCHEMA IF NOT EXISTS it.

Any Delta table you write, write with mode("overwrite") AND
.option("overwriteSchema", "true"). These notebooks get re-run and edited; without
overwriteSchema, the second run fails with DELTA_METADATA_MISMATCH the moment a column name or
type changes from the previous run.

Suffix every table you create with "_prompt" — e.g. ds_07_daily_summary_prompt. The pre-built
notebooks already own the unsuffixed names in this same schema, and their column names may differ
from what you generate. Writing to the same table clashes on schema and destroys the pre-built
output, which is the baseline we compare against.

1. Query <catalog>.gold<suffix>.enrollment_history for student_id, course_id, term_id, grade
   and gpa_points, filtering out rows where gpa_points IS NULL (those are withdrawals, grade
   'W'), LIMIT 10000, and bring it into pandas with toPandas().

2. Add a column that maps grade to grade points using the FULL ten-grade scale — A 4.0, A- 3.7,
   B+ 3.3, B 3.0, B- 2.7, C+ 2.3, C 2.0, D 1.0, F 0.0, W null. Do not use a five-grade
   A/B/C/D/F map: every +/- grade would become NaN, which is about half the data.

3. Add a 3-term rolling mean of gpa_points PER STUDENT, ordered by term_id — sort by
   (student_id, term_id) and use groupby("student_id")[...].transform() with a rolling window.
   A rolling mean over the unsorted frame would average unrelated students together.

4. Write student_id, term_id, grade, gpa_points and the rolling column, de-duplicated, to a
   Delta table ds_02_pandas_output in my wksp_ schema.

5. Assert: the grade map left zero unmapped rows; the mapped points equal the fact's own
   gpa_points to within a float tolerance (proving I reproduced the platform's scale rather than
   inventing one); the rolling mean stays inside 0.0-4.0; and the persisted row count matches
   what I wrote.
```

</details>

**Expect the generated notebook to match** `ds_02_python_pandas_notebook.py`: ~9,700 rows out,
zero nulls, rolling mean within 0–4. The pre-built notebook is the fallback if the prompt drifts.

**How to test the pre-built path:** run `ds_02_python_pandas_notebook.py` (serverless).

**Expected outcome:** `PASS: DS-02 pandas round-trip — all grades mapped, derived GPA matches the
platform.` Output: `wksp_<user>.ds_02_pandas_output`, ~9,700 rows, zero nulls in `gpa_points` /
`gpa_rolling_3term`.

**Note for the read-out:** the notebook rebuilds the foundation's ten-grade scale and asserts its
derived value *equals* the fact's own `gpa_points`. A five-grade map (A/B/C/D/F only) NaNs every
+/− grade — 53% of this dataset.

---

## DS-03 — R notebook environment (sparklyr)

> **Built:** 🟡 code review only · **Prompt:** 🟡 written (Assistant — generate the R notebook)
>
> **This scenario is presented as reviewed code, not a live run — by decision, not omission.**
> There is no classic compute in the POC environment and serverless has no R kernel, so DS-03
> cannot execute here. Walk the code and state the constraint plainly; don't promise a run.

**What it proves:** the platform is a first-class R environment — connect, query governed tables,
run native R statistics, write back as Delta.

**Why it can't run here.** R needs a classic cluster with an R kernel; serverless supports
Python/SQL/Scala only. The POC environment has no classic compute, so this is the one DS scenario
demonstrated by code review.

The code uses **`sparklyr`**, not `SparkR` — SparkR was removed in DBR 16.0, and the runtimes
available here are 15.4 / 16.4 / 17.3 / 18.1 / 18.2. Anyone reviewing it should see the current
supported R interface, not a deprecated one.

**What to say to the customer:** R is fully supported on Databricks — it needs classic compute
rather than serverless, which is a compute-type choice, not a capability gap. If Princeton wants R
in their own environment, they provision a classic cluster and this notebook runs unchanged.

<details>
<summary><strong>Code path (Databricks Assistant — generate the R notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write an R notebook for Databricks that analyses governed platform data.

Use sparklyr, NOT SparkR — SparkR was removed in DBR 16.0 and this has to run on a current
runtime. Connect with spark_connect(method = "databricks").

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix value ALREADY includes its leading underscore, so paste0(catalog, ".gold", suffix) — never
add another "_". The bundle passes _dev / _test / "" (empty, for prod), so an extra underscore
breaks qa and prod while passing on dev.

Write nothing to the foundation schemas. Derive my private output schema from current_user():
gsub every non-alphanumeric character to "_", prefix "wksp_", and CREATE SCHEMA IF NOT EXISTS it.

1. Query <catalog>.gold<suffix>.enrollment_history for gpa_points and grade where gpa_points IS
   NOT NULL, LIMIT 5000, and collect() it into a local R data frame.

2. Run native R statistics on it and print them: summary(), quantile() at the quartiles, sd(),
   and table() of the grade distribution. The point is that these are base R functions on
   platform data with no export step.

3. Build a small data frame of metrics — n, mean, sd, min, max and median of gpa_points — and
   write it back as a Delta table ds_03_r_summary in my wksp_ schema. Use sdf_copy_to() then
   spark_write_table().

4. Assert with stopifnot(): rows were returned; the mean GPA is inside 0.0-4.0; and the written
   table reads back through Spark with the same row count and no NA values.
```

</details>

**How to review:** open `ds_03_r_analysis_notebook.r` and walk the four sections — connect via
`spark_connect(method = "databricks")`, query the governed table through `sdf_sql()`, run base-R
statistics (`summary`, `quantile`, `sd`, `table`) on the collected frame, and write the metrics back
as Delta with `sdf_copy_to()` + `spark_write_table()`.

If a classic cluster ever becomes available: attach and Run All. Expected —

**Expected outcome:** `PASS: DS-03 R analysis — 5000 rows summarised, mean GPA ~3.08, 6 metrics
persisted to Delta.` Output: `wksp_<user>.ds_03_r_summary` (6 metric rows).

**Not yet verified.** Watch for two things on first run: `sparklyr` may need installing on the
cluster, and `spark_write_table` on a three-part UC name may need adjusting.

---

## DS-04 — Bring your own data (ad-hoc upload + blend)

> **Built:** ✅ · **Prompt:** 🟢 tested (`princeton_poc_dev`: generated notebook produced 40 depts / 4 matched / stale key excluded — 2 prompt gaps found and fixed, see below)

**What it proves:** an analyst brings a file the platform has never seen and joins it to governed
data without a pipeline or an ETL request.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a PySpark notebook that blends a file I uploaded with governed platform data.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix value ALREADY includes its leading underscore, so concatenate with no separator —
f"{catalog}.gold{suffix}", never f"gold_{suffix}". The bundle passes _dev / _test / "" (empty, for
prod), so an underscore in the f-string breaks qa and prod while passing on dev. Same for the
volume path: /Volumes/{catalog}/landing{suffix}/files/.

Write nothing to bronze/silver/gold — that is the shared read-only foundation. Derive my private
output schema from current_user(): replace every non-alphanumeric character with an underscore,
prefix "wksp_", and CREATE SCHEMA IF NOT EXISTS it.

Any Delta table you write, write with mode("overwrite") AND
.option("overwriteSchema", "true"). These notebooks get re-run and edited; without
overwriteSchema, the second run fails with DELTA_METADATA_MISMATCH the moment a column name or
type changes from the previous run.

Suffix every table you create with "_prompt" — e.g. ds_07_daily_summary_prompt. The pre-built
notebooks already own the unsuffixed names in this same schema, and their column names may differ
from what you generate. Writing to the same table clashes on schema and destroys the pre-built
output, which is the baseline we compare against.

1. My CSV lives at /Volumes/<catalog>/landing<suffix>/files/uploads/<my wksp_ name>/ — a
   PER-USER folder, not the shared landing root, because the root holds the foundation's own
   source files and ~20 of us are doing this at once. Create the folder if it doesn't exist. For
   a self-contained demo, first write a small CSV there with columns dept_id (bigint),
   external_rank (int), benchmark_score (double), covering only a handful of departments plus one
   dept_id that does NOT exist in the platform (a stale external extract always has one).

2. Read that CSV with an EXPLICIT schema — do not use inferSchema. It's untrusted input, and
   inference will type dept_id inconsistently with the platform's bigint and break the join
   silently.

3. Aggregate the platform side: join <catalog>.gold<suffix>.enrollment_history to
   <catalog>.silver<suffix>.department on dept_id, and count enrollments plus distinct students
   per department.

   Use the ACTUAL column names — the department table is (dept_id, name, division, building).
   The department's name column is literally `name`, NOT `department_name`. Alias it in the
   SELECT if you want a friendlier label, but group by `name`.

4. LEFT join the platform side to my uploaded file on dept_id — platform on the left. Every real
   department must survive; the ones absent from my file get NULL benchmarks. Write the result to
   ds_04_byo_blended in my wksp_ schema.

5. Assert: the LEFT join did not change the platform-side row count (if it did, my file has
   duplicate dept_ids and fanned the result out); at least one department matched (if none did,
   the join keys are typed wrong); the stale dept_id is NOT in the output; and matched plus
   unmatched covers every department.
```

</details>

**How to test the pre-built path:** run `ds_04_byo_data_blend.py` (serverless). It stages an equivalent CSV so the
notebook is self-contained; in a live demo, drag a CSV into the Volume via Catalog Explorer
instead — the ingestion path below it is identical.

**Expected outcome:** `PASS: DS-04 blended 5 externally-ranked departments with 35 unranked
retained; stale external key correctly excluded.` Output: `wksp_<user>.ds_04_byo_blended`
(40 rows).

**Worth showing:** the external file deliberately contains `dept_id 999`, which doesn't exist in
the platform. The LEFT join keeps all 40 real departments and drops the stale key — a real
external extract always has some.

**Isolation note:** the upload lands in `files/uploads/wksp_<user>/`, not the shared landing root,
which holds the foundation's own source files.

---

## DS-05 — Large-dataset handling

> **Built:** ✅ · **Prompt:** 🟢 tested (`princeton_poc_dev`: generated notebook ran clean first time — 5,000,000 -> 960 rows, avoided all three invented-SQL traps)

**What it proves:** a heavy analytical query over the multi-million-row fact — full scan, join,
aggregate, window — and *why* it was fast.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a PySpark notebook that runs a heavy analytical query over a multi-million-row fact table
and shows me why it was fast.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix value ALREADY includes its leading underscore, so concatenate with no separator —
f"{catalog}.gold{suffix}", never f"gold_{suffix}". The bundle passes _dev / _test / "" (empty, for
prod), so an underscore in the f-string breaks qa and prod while passing on dev. Same for the
volume path: /Volumes/{catalog}/landing{suffix}/files/.

Write nothing to bronze/silver/gold — that is the shared read-only foundation. Derive my private
output schema from current_user(): replace every non-alphanumeric character with an underscore,
prefix "wksp_", and CREATE SCHEMA IF NOT EXISTS it.

Any Delta table you write, write with mode("overwrite") AND
.option("overwriteSchema", "true"). These notebooks get re-run and edited; without
overwriteSchema, the second run fails with DELTA_METADATA_MISMATCH the moment a column name or
type changes from the previous run.

Suffix every table you create with "_prompt" — e.g. ds_07_daily_summary_prompt. The pre-built
notebooks already own the unsuffixed names in this same schema, and their column names may differ
from what you generate. Writing to the same table clashes on schema and destroys the pre-built
output, which is the baseline we compare against.

1. Report the scale first: row count, distinct students, terms and departments in
   <catalog>.gold<suffix>.enrollment_history, plus DESCRIBE DETAIL on it to show numFiles,
   sizeInBytes and clusteringColumns.

2. The heavy query: join the fact to <catalog>.silver<suffix>.department on dept_id, filter to
   gpa_points IS NOT NULL, group by division, dept_id and term_id, and compute count(*),
   avg(gpa_points), count(DISTINCT student_id), plus rank() OVER (PARTITION BY term_id ORDER BY
   count(*) DESC).

3. BEFORE running it, print the physical plan with df.explain(mode="formatted") captured off
   stdout via io.StringIO and contextlib.redirect_stdout, so I can assert on the plan text. Do
   NOT use the internal _jdf.queryExecution().explainString() API — it doesn't work in a notebook
   session.

4. Then run it with .collect() and time it — a bare spark.sql() only builds a plan, so timing
   that measures nothing.

5. Time a filter on the clustered columns (term_id and dept_id) against a full scan, side by side.

6. Write one timing row — query name, fact rows, result rows, elapsed seconds, num_files, size —
   to ds_05_query_metrics in my wksp_ schema.

7. Assert: the fact really has at least a million rows (this scenario is meaningless on a small
   table); the result row count equals departments x terms exactly, not just "greater than zero";
   there is exactly one rank-1 department per term; avg GPA sits inside 0.0-4.0; and the plan text
   contains "Photon" and a broadcast join.

Do NOT use "SET spark.databricks.queryProfile.enabled" or "DESCRIBE QUERY PROFILE" — neither is
real Databricks SQL. For post-hoc metrics, query system.query.history instead, and note in a
comment that it lags roughly 15 minutes so it cannot verify the run that just happened.
```

</details>

**How to test the pre-built path:** run `ds_05_large_dataset_query.py` (serverless).

**Expected outcome:** `PASS: DS-05 — 5,000,000 rows aggregated to 960 groups in ~2s on Photon
with a broadcast join.` Output: `wksp_<user>.ds_05_query_metrics` (1 timing row).

**Two things to know before demonstrating:**

- **`system.query.history` lags ~15 minutes.** The last cell reads bytes/files/rows from it and
  will likely return nothing for the run you just did. That's expected, not a failure — point at
  an earlier run, or run the cell later. Don't promise live telemetry.
- **The liquid-clustering comparison shows no win at 5M rows.** Measured: full scan 0.66s vs
  clustered filter 0.63s, because `numFiles = 1` — the whole fact is one 34 MiB file with nothing
  to prune. Clustering *is* declared on `(term_id, dept_id)`; the payoff needs many files.
  Regenerate at `--var row_count=50000000` before presenting this as a clustering story.

---

## DS-06(a) — Local connectivity (Python / R / SAS / SPSS)

> **Built:** ✅ reference guide · **Prompt:** — n/a (no run artifact by design)

**What it proves:** analysts work from their own machine in the tool they already use, and Unity
Catalog governs the **connection** — row filters and column masks apply identically from a laptop.

**Now also covers Databricks Connect** — running PySpark from a local IDE against remote
Databricks compute, per Scott's note. That is the stronger demo for a data-science team: it is the
full DataFrame API in VS Code / PyCharm, executing on the cluster, not SQL over a wire. Section 6 of
the guide.

**How to test:** follow [`src/ds_06a_connectivity_guide.md`](src/ds_06a_connectivity_guide.md).
Read the live host and HTTP path from **SQL Warehouse → Connection details**; the guide
deliberately carries no hostname, because a stale one is the most common reason these snippets
fail.

**Expected outcome:** the Python snippet returns rows — the fastest signal that host, HTTP path,
and token are all correct.

**The demo that lands:** run the same snippet as an admin, then as a restricted user, after PA-07
masking is applied to `admin_demo.student`. Same file, same query, different output. That is
governance proving it isn't a UI-layer feature.

---

## DS-06(b) — In-platform ML training (MLflow + UC)

> **Built:** ✅ · **Prompt:** 🟢 tested (`princeton_poc_dev`: generated notebook trained, registered a UC model, and scored 200 rows — accuracy 0.192 vs baseline 0.201, correctly near-baseline; 3 prompt gaps found and fixed)

**What it proves:** the whole model lifecycle stays inside the platform — train on governed data,
autolog to an experiment, register in Unity Catalog, load back for inference.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a notebook that trains a classifier on governed Databricks data, logs it to MLflow, and
registers it in Unity Catalog.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix value ALREADY includes its leading underscore, so concatenate with no separator —
f"{catalog}.gold{suffix}", never f"gold_{suffix}". The bundle passes _dev / _test / "" (empty, for
prod), so an underscore in the f-string breaks qa and prod while passing on dev. Same for the
volume path: /Volumes/{catalog}/landing{suffix}/files/.

Write nothing to bronze/silver/gold — that is the shared read-only foundation. Derive my private
output schema from current_user(): replace every non-alphanumeric character with an underscore,
prefix "wksp_", and CREATE SCHEMA IF NOT EXISTS it.

Any Delta table you write, write with mode("overwrite") AND
.option("overwriteSchema", "true"). These notebooks get re-run and edited; without
overwriteSchema, the second run fails with DELTA_METADATA_MISMATCH the moment a column name or
type changes from the previous run.

Suffix every table you create with "_prompt" — e.g. ds_07_daily_summary_prompt. The pre-built
notebooks already own the unsuffixed names in this same schema, and their column names may differ
from what you generate. Writing to the same table clashes on schema and destroys the pre-built
output, which is the baseline we compare against.

1. Training data: join <catalog>.gold<suffix>.enrollment_history to silver student and term.
   Features: course_id, term_id, dept_id, term year, term season, student status, and student age.
   Target: the grade column. LIMIT 50000.

   Two things to get right:
   - Do NOT include gpa_points as a feature. It is derived deterministically from grade — each
     grade maps to exactly one value — so it leaks the label and the model would score ~100%.
   - dob is a STRING in three mixed formats (yyyy-MM-dd, MM/dd/yyyy, dd.MM.yyyy) on purpose.
     year(dob) returns NULL for two of them, so compute age with a coalesce over try_to_date for
     all three formats.
   - After toPandas(), cast the age column with pd.to_numeric(...). Spark FLOOR/DATEDIFF returns a
     Decimal, which lands in pandas as dtype object — sklearn then treats it as categorical and the
     model silently degrades. Fill any remaining NaN with the column median and cast the whole
     feature frame to float.

2. One-hot encode season and status (they're unordered categories, not magnitudes). Factorize the
   grade labels FROM THE DATA rather than hardcoding a map — there are ten grades including the
   +/- ones, and a five-class map would silently drop about half the rows.

3. Compute the majority-class baseline accuracy on the test split and print it.

   IMPORTANT — expect accuracy to land NEAR the baseline, roughly 0.19-0.23, and possibly a little
   BELOW it. That is the correct outcome on randomly generated data with ten classes: there is no
   real signal to learn, so the model cannot beat "always guess the most common grade" by much, and
   sampling variance can put it just under. Do NOT try to fix this by tuning the model, adding
   class_weight="balanced", deepening the trees, or re-engineering features — the data has no
   signal and you will only burn cycles. The scenario demonstrates the LIFECYCLE, not model quality.

4. Train a RandomForestClassifier with an 80/20 stratified split. Use mlflow.sklearn.autolog()
   with input examples and model signatures rather than hand-written log_metric calls. Also log
   test accuracy, weighted F1, and the baseline.

5. Set the registry to Unity Catalog with mlflow.set_registry_uri("databricks-uc") and register
   the model under <catalog>.models<suffix>. Include my user in the model name so 20 concurrent
   runs don't fight over one model's version history.

6. Load the registered model back with mlflow.pyfunc.load_model, score 200 test rows, and write
   predicted vs actual grade to ds_06b_predictions in my wksp_ schema.

7. Assert: all ten grade classes are present; gpa_points is NOT among the feature columns;
   accuracy is BELOW 0.99 (anything higher means a feature is leaking the label); under 1% of ages
   failed to parse; accuracy is at least `baseline * 0.95` (a tolerance, NOT a hard `>= baseline` —
   see step 3, variance on random data legitimately puts it just under); and the registered model
   loads and scores every input row.
```

</details>

**How to test the pre-built path:** run `ds_06b_mlflow_training.py` (serverless).

**Expected outcome:** `PASS: DS-06(b) — trained on 40,000 rows, 10 grade classes, accuracy ~0.225
vs baseline ~0.20`. Registers `models_dev.grade_predictor_<user>` v1 and writes
`wksp_<user>.ds_06b_predictions` (200 scored rows).

**Say this out loud in the read-out.** Accuracy near 22% is the **correct** result: ten grade
classes on randomly generated data, where chance is ~10% and the majority-class baseline ~20%.
The scenario demonstrates the *lifecycle*, not model quality. Anything near 100% would mean a
feature is leaking the label — `gpa_points` is deliberately excluded because it maps 1:1 to
`grade`, and an assertion fails above 0.99 accuracy to keep it that way. A real accuracy story
needs Princeton's own data with genuine signal.

---

## DS-07 — Scheduling / operationalizing a notebook

> **Built:** ✅ · **Prompt:** 🟢 tested (`princeton_poc_dev`: generated notebook + job YAML; 5M -> one row, idempotent. Hit a table-name collision with the pre-built output — prompt now requires a `_prompt` suffix)

**What it proves:** an ad-hoc analysis becomes a governed, scheduled, monitored production job —
the same notebook, no rewrite in another tool.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook and its schedule)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a notebook that computes a daily enrollment summary, plus the Databricks Asset Bundle job
YAML that runs it on a schedule.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix value ALREADY includes its leading underscore, so concatenate with no separator —
f"{catalog}.gold{suffix}", never f"gold_{suffix}". The bundle passes _dev / _test / "" (empty, for
prod), so an underscore in the f-string breaks qa and prod while passing on dev. Same for the
volume path: /Volumes/{catalog}/landing{suffix}/files/.

Write nothing to bronze/silver/gold — that is the shared read-only foundation. Derive my private
output schema from current_user(): replace every non-alphanumeric character with an underscore,
prefix "wksp_", and CREATE SCHEMA IF NOT EXISTS it.

Any Delta table you write, write with mode("overwrite") AND
.option("overwriteSchema", "true"). These notebooks get re-run and edited; without
overwriteSchema, the second run fails with DELTA_METADATA_MISMATCH the moment a column name or
type changes from the previous run.

Suffix every table you create with "_prompt" — e.g. ds_07_daily_summary_prompt. The pre-built
notebooks already own the unsuffixed names in this same schema, and their column names may differ
from what you generate. Writing to the same table clashes on schema and destroys the pre-built
output, which is the baseline we compare against.

Then summarise <catalog>.gold<suffix>.enrollment_history into ONE row —
current_date() as run_date, total enrollments, distinct students, distinct courses, average
gpa_points, median via approx_percentile, a count of rows where gpa_points IS NULL (withdrawals),
and current_timestamp(). Write it to ds_07_daily_summary in my wksp_ schema.

Make it idempotent: the table accumulates one row per DAY, so before appending, DELETE any
existing row for today's run_date. A scheduled job always gets re-run by hand during a demo, and
a plain append would double-count.

Do NOT call .cache() on the summary DataFrame — serverless rejects it with
"NOT_SUPPORTED_WITH_SERVERLESS: PERSIST TABLE is not supported". It works interactively and fails
as a job, which is the worst place to find out.

Then show the accumulating history — the last 14 run_dates ordered descending.

Assert: the summarised total equals a fresh count of the fact table; avg and median GPA are inside
0.0-4.0; withdrawals are greater than zero but fewer than all rows; and no run_date has more than
one row.

Job YAML: a serverless job on a daily 09:00 cron with timezone America/New_York (Princeton local,
not UTC), pause_status PAUSED so it doesn't start firing for everyone the moment it deploys,
max_concurrent_runs 1, and catalog + schema_suffix passed through as job parameters and notebook
base_parameters. Do NOT specify a new_cluster with a node_type_id — an instance type like
i3.xlarge is AWS-only and breaks on Azure or GCP.
```

</details>

**Setup (SA, done):** job `[princeton_poc_dev] DS-07 Scheduled daily analysis`, declared in
`resources/ds_07_scheduled.job.yml`. **The schedule is version-controlled**, which is the point —
a cron clicked into the Jobs UI has no history.

**How to test:**

```bash
databricks bundle run ds_07_scheduled_analysis -t dev --profile <PROFILE>
```

Then in the Jobs UI: open the job → **Schedule** shows `0 0 9 * * ?`, timezone
`America/New_York`, status **PAUSED**. Resume it deliberately; an unpaused daily schedule starts
firing for everyone the moment anyone deploys.

**Expected outcome:** `TERMINATED SUCCESS`, and `PASS: DS-07 — summarised 5,000,000 enrollments to
one row for <date>`. Output: `wksp_<user>.ds_07_daily_summary`, one row **per day**.

**Re-run it.** The job deletes the current `run_date` before appending, so re-running replaces
rather than duplicates — an assertion proves one row per date. A demo will always re-run.

**Re-verified in the customer workspace (`dbc-7ef61dd7-1b75`) 2026-08-26** — job `TERMINATED SUCCESS`
in ~50s, and the output checked rather than the exit code trusted:

| Metric | Value |
|---|---|
| enrollments | **5,000,000** |
| students / courses | 30,000 / 5,000 |
| avg / median GPA | 3.0841 / 3.3 |
| withdrawals | **249,652** |

Every figure matches the retired-workspace baseline, which confirms the synthetic data here is the same
generation — so DS baselines carry across the move. Idempotency held: 2 rows for 2 distinct `run_date`s
after a second run, not 2 rows for one date.

> **The serverless `.cache()` trap is still guarded** (`ds_07_scheduled_analysis.py:62`). That failure —
> `[NOT_SUPPORTED_WITH_SERVERLESS] PERSIST TABLE` — only appears when the notebook runs as a **job**,
> never interactively, so a job run is the only test that exercises it. This one is clean.

---

## DS-08 — Version control for analytical code

> **Built:** ✅ · **Prompt:** 🟢 tested (`princeton_poc_dev`: Genie space over `system.access.audit` — both NL prompts generated correct partition-filtered SQL and returned real notebook-change history)

**What it proves:** analytical code is versioned, reviewable, and reproducible — notebooks, not
just pipelines.

**How to test:** follow
[`src/ds_08_version_control_guide.md`](src/ds_08_version_control_guide.md). There is nothing to
execute; the demo is the Git panel on a real notebook plus the repo's actual history.

**Expected outcome:** commit history visible per notebook, including two commits authored *in the
browser* (`32270a8`, `efa2b64`) — bugs found by running a notebook, fixed in the workspace, and
committed from the Git panel.

**The story worth telling:** `efa2b64` was committed to a branch *after* that branch's PR had
merged, so `main` still carried the bug — and it only manifests when the notebook runs as a
scheduled *job*. It was recoverable because it was committed. **A commit on a branch is not a
commit in `main`.**

**Also show:** notebook permissions and *data* permissions are independent. `CAN_VIEW` on a
notebook grants no `SELECT` — a restricted recipient reads the code and gets `PERMISSION_DENIED`.
Sharing analytical code is safe by default.

### No-code path — audit the code, in natural language

There is no notebook to *generate* for DS-08, so the prompt path is a different question: can a
data scientist interrogate the **audit trail over analytical code** without SQL? Genie space
`[princeton_poc_dev] Analytical Code Audit (DS-08)`, grounded on `system.access.audit`, created by
the `genie_setup` task of `foundation_build`.

| Prompt | Verified result |
|---|---|
| `Which notebooks did I change in the last week, and when?` | 40 notebooks, with last-modified times — SQL correctly used `current_user()` |
| `Who has modified notebooks in the last 7 days, and how many times each?` | Per-user modification counts across the workspace |
| `Show notebook activity by action type over the last week` | grouped by `action_name` |
| `Which users deleted or renamed notebooks recently?` | `deleteNotebook` / `renameNotebook` events |

Both tested prompts generated correct SQL — `service_name='notebook'`, the actor from
`user_identity.email`, and critically an **`event_date` partition filter** to bound the scan. The
space's instructions require that filter; without it a query over `system.access.audit` scans
tens of millions of rows.

**Why this closes the loop on DS-08.** Version control answers *what changed and who reviewed it*;
the audit trail answers *who touched it in the workspace, and when* — including actions that never
reach a commit. Together they are the full accountability story for analytical code, and both are
queryable rather than requiring an admin to pull logs.

---

## DS-09 — Visualization and charting

> **Built:** ✅ · **Prompt:** 🟢 tested (`princeton_poc_dev`: generated notebook produced both views — 24 terms / 40 depts — clean, with the corrected column-name rule in place)

**What it proves:** query → chart → shareable dashboard without leaving the platform.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a PySpark notebook with three chart-ready queries over governed enrollment data, plus the
views an AI/BI dashboard can read.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix value ALREADY includes its leading underscore, so concatenate with no separator —
f"{catalog}.gold{suffix}", never f"gold_{suffix}". The bundle passes _dev / _test / "" (empty, for
prod), so an underscore in the f-string breaks qa and prod while passing on dev. Same for the
volume path: /Volumes/{catalog}/landing{suffix}/files/.

Write nothing to bronze/silver/gold — that is the shared read-only foundation. Derive my private
output schema from current_user(): replace every non-alphanumeric character with an underscore,
prefix "wksp_", and CREATE SCHEMA IF NOT EXISTS it.

Any Delta table you write, write with mode("overwrite") AND
.option("overwriteSchema", "true"). These notebooks get re-run and edited; without
overwriteSchema, the second run fails with DELTA_METADATA_MISMATCH the moment a column name or
type changes from the previous run.

Suffix every table you create with "_prompt" — e.g. ds_07_daily_summary_prompt. The pre-built
notebooks already own the unsuffixed names in this same schema, and their column names may differ
from what you generate. Writing to the same table clashes on schema and destroys the pre-built
output, which is the baseline we compare against.

1. GPA distribution, for a bar chart: band gpa_points into A (>=3.7), A- (>=3.3), B+ (>=3.0),
   B (>=2.7), C (>=2.0), D/F (below 2.0), and W for gpa_points IS NULL. Withdrawals MUST be their
   own band — if they fall into the ELSE branch they get reported as failing grades, which is
   wrong on a chart shown to a customer.

   Add an explicit numeric band_order column and ORDER BY that. Do NOT order by gpa_points: it
   isn't in the GROUP BY, so the query fails outright with UNRESOLVED_COLUMN. Alphabetical
   ordering is also wrong — 'A' before 'Below C' is luck, not intent.

2. Enrollments by department, for a bar chart: join the fact to silver department, count
   enrollments and distinct students, average gpa_points, top 15 by enrollment.

   Use the ACTUAL column names — department is (dept_id, name, division, building). The name
   column is literally `name`, NOT `department_name`; alias it for display if you like, but
   group by `name`.

3. Enrollment trend by term, for a line chart: join the fact to silver term, count enrollments and
   average gpa_points per term. Build a term_label like "2018 Fall" so the axis is readable, but
   ORDER BY term_id — seasons are not alphabetical, so sorting by season would mis-order the
   academic year.

4. Persist the trend and department queries as VIEWS in MY wksp_ schema, with the view text written
   out explicitly. Do NOT create them in gold_dev — that's the shared read-only foundation and 20
   people would overwrite each other on the same view name. Do NOT build the view body from
   df._jdf.sql() either; it's an internal API and doesn't reliably return runnable SQL.

5. Assert: the GPA bands sum to the FULL fact row count (a gap in the CASE would silently drop
   rows); a withdrawal band exists; band_order is monotonic; the department query returns exactly
   15 rows; the trend covers every term in term_id order (a line chart would zigzag otherwise);
   both views return rows; and no ds_09 object leaked into the shared foundation schema.
```

</details>

**Setup (SA, done):** dashboard `[princeton_poc_dev] Student Analytics (DS-09)`, from
`resources/ds_09_dashboard.dashboard.yml`.

**How to test — dashboard (stakeholder view).** Open it. Eight widgets: four counters, a GPA
distribution bar, a top-15 department bar, an enrollment trend line, and a detail table. Expect
**5,000,000 / 30,000 / 3.084 / 249,652** in the counters.

**How to test — notebook (analyst view).** Run `ds_09_visualizations.py`, then on each of the
three query cells click **+ → Visualization**:

| Cell | Chart | Axes |
|---|---|---|
| GPA distribution | Bar | X `gpa_band`, Y `enrollments` |
| By department | Bar | X `enrollments`, Y `department` |
| Enrollment trend | Line | X `term_label`, Y `enrollments` |

`display()` renders a table by default — the chart is one click, and it persists with the
notebook.

**Expected outcome:** `PASS: DS-09 — 7 GPA bands covering all 5,000,000 enrollments, 15
departments, 24 terms in order.` Outputs: `wksp_<user>.ds_09_enrollment_trend` (24 rows) and
`ds_09_dept_summary` (40 rows).

**⚠️ If every widget shows "Unable to render visualization":** the dashboard is bound to a
warehouse that doesn't exist in the current workspace. `databricks.yml` sets `warehouse_id` per
target; deploy with `--var warehouse_id=<a warehouse in THIS workspace>`. The queries and widget
specs are fine — this failure looks like a dashboard bug and isn't one.

---

## Known gaps

| Item | Status |
|---|---|
| **DS-03** | Written, not run — needs a classic cluster with an R kernel |
| **DS-05 clustering story** | Needs the fact regenerated at ~50M rows to show a real pruning win |
| **Dashboard catalog** | `ds_09_student_analytics.lvdash.json` hardcodes `princeton_poc_dev` — `.lvdash.json` isn't variable-interpolated by the bundle (same constraint as BA-02) |
