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

> **Built:** ✅ · **Prompt:** — n/a (pre-built notebook; the analyst writes their own Python)

**What it proves:** platform data moves into the Python ecosystem an analyst already knows,
transforms with pandas, and writes back as a governed Delta table.

**How to test:** run `ds_02_python_pandas_notebook.py` (serverless).

**Expected outcome:** `PASS: DS-02 pandas round-trip — all grades mapped, derived GPA matches the
platform.` Output: `wksp_<user>.ds_02_pandas_output`, ~9,700 rows, zero nulls in `gpa_points` /
`gpa_rolling_3term`.

**Note for the read-out:** the notebook rebuilds the foundation's ten-grade scale and asserts its
derived value *equals* the fact's own `gpa_points`. A five-grade map (A/B/C/D/F only) NaNs every
+/− grade — 53% of this dataset.

---

## DS-03 — R notebook environment (sparklyr)

> **Built:** 🟡 written, not executed · **Prompt:** — n/a

**What it proves:** the platform is a first-class R environment — connect, query governed tables,
run native R statistics, write back as Delta.

**⚠️ Needs a classic cluster with an R kernel.** Serverless has no R. Uses **`sparklyr`**, not
`SparkR` — SparkR was removed in DBR 16.0, and available runtimes here are 15.4 / 16.4 / 17.3 /
18.1 / 18.2.

**How to test:** attach `ds_03_r_analysis_notebook.r` to a classic cluster, Run All.

**Expected outcome:** `PASS: DS-03 R analysis — 5000 rows summarised, mean GPA ~3.08, 6 metrics
persisted to Delta.` Output: `wksp_<user>.ds_03_r_summary` (6 metric rows).

**Not yet verified.** Watch for two things on first run: `sparklyr` may need installing on the
cluster, and `spark_write_table` on a three-part UC name may need adjusting.

---

## DS-04 — Bring your own data (ad-hoc upload + blend)

> **Built:** ✅ · **Prompt:** — n/a (pre-built notebook; the upload itself is a UI drag-and-drop)

**What it proves:** an analyst brings a file the platform has never seen and joins it to governed
data without a pipeline or an ETL request.

**How to test:** run `ds_04_byo_data_blend.py` (serverless). It stages an equivalent CSV so the
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

> **Built:** ✅ · **Prompt:** — n/a (pre-built notebook + query-profile walkthrough)

**What it proves:** a heavy analytical query over the multi-million-row fact — full scan, join,
aggregate, window — and *why* it was fast.

**How to test:** run `ds_05_large_dataset_query.py` (serverless).

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

> **Built:** ✅ · **Prompt:** — n/a (pre-built notebook; the analyst writes their own model code)

**What it proves:** the whole model lifecycle stays inside the platform — train on governed data,
autolog to an experiment, register in Unity Catalog, load back for inference.

**How to test:** run `ds_06b_mlflow_training.py` (serverless).

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

> **Built:** ✅ · **Prompt:** — n/a (SA-deployed job; the schedule is declared in the bundle)

**What it proves:** an ad-hoc analysis becomes a governed, scheduled, monitored production job —
the same notebook, no rewrite in another tool.

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

> **Built:** ✅ · **Prompt:** — n/a (notebook viz is a UI action; the dashboard is SA-deployed)

**What it proves:** query → chart → shareable dashboard without leaving the platform.

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
