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

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the pandas notebook)

**What it proves:** platform data moves into the Python ecosystem an analyst already knows,
transforms with pandas, and writes back as a governed Delta table.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a PySpark + pandas notebook for a data scientist working in Databricks.

Setup: derive my private output schema instead of hardcoding one — read current_user(), replace
every non-alphanumeric character with an underscore, prefix "wksp_", and CREATE SCHEMA IF NOT
EXISTS it in catalog princeton_poc_dev. Everything I write goes there; the foundation is
read-only. Read the catalog and schema suffix from notebook widgets ("catalog", "schema_suffix")
so this runs on dev, qa or prod unchanged.

1. Query princeton_poc_dev.gold_dev.enrollment_history for student_id, course_id, term_id, grade
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

> **Built:** 🟡 written, not executed · **Prompt:** 🟡 written (Assistant — generate the R notebook)

**What it proves:** the platform is a first-class R environment — connect, query governed tables,
run native R statistics, write back as Delta.

**⚠️ Needs a classic cluster with an R kernel.** Serverless has no R. Uses **`sparklyr`**, not
`SparkR` — SparkR was removed in DBR 16.0, and available runtimes here are 15.4 / 16.4 / 17.3 /
18.1 / 18.2.

<details>
<summary><strong>Code path (Databricks Assistant — generate the R notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write an R notebook for Databricks that analyses governed platform data.

Use sparklyr, NOT SparkR — SparkR was removed in DBR 16.0 and this has to run on a current
runtime. Connect with spark_connect(method = "databricks").

Read the catalog and schema suffix from notebook widgets ("catalog" default princeton_poc_dev,
"schema_suffix" default _dev) rather than hardcoding them. Derive my private output schema the
same way the Python notebooks do: query current_user(), gsub every non-alphanumeric character to
"_", prefix "wksp_", and CREATE SCHEMA IF NOT EXISTS it.

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

**How to test the pre-built path:** attach `ds_03_r_analysis_notebook.r` to a classic cluster,
Run All.

**Expected outcome:** `PASS: DS-03 R analysis — 5000 rows summarised, mean GPA ~3.08, 6 metrics
persisted to Delta.` Output: `wksp_<user>.ds_03_r_summary` (6 metric rows).

**Not yet verified.** Watch for two things on first run: `sparklyr` may need installing on the
cluster, and `spark_write_table` on a three-part UC name may need adjusting.

---

## DS-04 — Bring your own data (ad-hoc upload + blend)

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the blend notebook)

**What it proves:** an analyst brings a file the platform has never seen and joins it to governed
data without a pipeline or an ETL request.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a PySpark notebook that blends a file I uploaded with governed platform data.

Read catalog and schema suffix from notebook widgets. Derive my private schema from
current_user() (non-alphanumerics to underscores, "wksp_" prefix) and CREATE SCHEMA IF NOT EXISTS
it — the foundation is read-only.

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
   per department, keeping department name and division.

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

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the heavy-query + profiling notebook)

**What it proves:** a heavy analytical query over the multi-million-row fact — full scan, join,
aggregate, window — and *why* it was fast.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a PySpark notebook that runs a heavy analytical query over a multi-million-row fact table
and shows me why it was fast.

Read catalog and schema suffix from widgets; derive my private wksp_ schema from current_user()
for the one table this writes.

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

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the MLflow training notebook)

**What it proves:** the whole model lifecycle stays inside the platform — train on governed data,
autolog to an experiment, register in Unity Catalog, load back for inference.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a notebook that trains a classifier on governed Databricks data, logs it to MLflow, and
registers it in Unity Catalog.

Read catalog and schema suffix from widgets; derive my private wksp_ schema from current_user().

1. Training data: join <catalog>.gold<suffix>.enrollment_history to silver student and term.
   Features: course_id, term_id, dept_id, term year, term season, student status, and student age.
   Target: the grade column. LIMIT 50000.

   Two things to get right:
   - Do NOT include gpa_points as a feature. It is derived deterministically from grade — each
     grade maps to exactly one value — so it leaks the label and the model would score ~100%.
   - dob is a STRING in three mixed formats (yyyy-MM-dd, MM/dd/yyyy, dd.MM.yyyy) on purpose.
     year(dob) returns NULL for two of them, so compute age with a coalesce over try_to_date for
     all three formats.

2. One-hot encode season and status (they're unordered categories, not magnitudes). Factorize the
   grade labels FROM THE DATA rather than hardcoding a map — there are ten grades including the
   +/- ones, and a five-class map would silently drop about half the rows.

3. Compute the majority-class baseline accuracy on the test split and print it. This data is
   randomly generated, so beating that baseline slightly is the expected honest result.

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
   failed to parse; accuracy is at least the majority-class baseline; and the registered model
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

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the notebook + job schedule)

**What it proves:** an ad-hoc analysis becomes a governed, scheduled, monitored production job —
the same notebook, no rewrite in another tool.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook and its schedule)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a notebook that computes a daily enrollment summary, plus the Databricks Asset Bundle job
YAML that runs it on a schedule.

Notebook: read catalog and schema suffix from widgets, derive my private wksp_ schema from
current_user(), and summarise <catalog>.gold<suffix>.enrollment_history into ONE row —
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

---

## DS-08 — Version control for analytical code

> **Built:** ✅ · **Prompt:** — n/a (walkthrough; the evidence is this repo's own history)

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

---

## DS-09 — Visualization and charting

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the chart queries + views)

**What it proves:** query → chart → shareable dashboard without leaving the platform.

<details>
<summary><strong>Code path (Databricks Assistant — generate the notebook)</strong> — click to expand the copy-paste prompt</summary>

```text
Write a PySpark notebook with three chart-ready queries over governed enrollment data, plus the
views an AI/BI dashboard can read.

Read catalog and schema suffix from widgets; derive my private wksp_ schema from current_user().

1. GPA distribution, for a bar chart: band gpa_points into A (>=3.7), A- (>=3.3), B+ (>=3.0),
   B (>=2.7), C (>=2.0), D/F (below 2.0), and W for gpa_points IS NULL. Withdrawals MUST be their
   own band — if they fall into the ELSE branch they get reported as failing grades, which is
   wrong on a chart shown to a customer.

   Add an explicit numeric band_order column and ORDER BY that. Do NOT order by gpa_points: it
   isn't in the GROUP BY, so the query fails outright with UNRESOLVED_COLUMN. Alphabetical
   ordering is also wrong — 'A' before 'Below C' is luck, not intent.

2. Enrollments by department, for a bar chart: join the fact to silver department, count
   enrollments and distinct students, average gpa_points, keep name and division, top 15 by
   enrollment.

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
