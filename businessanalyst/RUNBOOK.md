# Princeton POC — Business Analyst Runbook

No-code / low-code scenarios (BA-01…BA-08) — Genie, AI/BI dashboards, and Lakeflow Designer +
its Genie agent. Prerequisite: the shared foundation — see
[`foundation/RUNBOOK.md`](../foundation/RUNBOOK.md). Index: [`docs/runbook/README.md`](../docs/runbook/README.md).

_No-code / low-code only — the analyst never writes SQL. Five pre-built objects (a Genie space,
an AI/BI dashboard, a saved SQL export query, a sample upload + Designer canvas, and a saved
workflow job) cover BA-01…08. All read the shared foundation; the one object that writes
(BA-04/05/08) writes to the analyst's own `wksp_<user>` schema. Full walkthroughs in
`businessanalyst/src/walkthroughs/`._

## BA-01 — No-code browse, filter, preview (Genie + Catalog Explorer)

> **Built:** ✅ · **Prompt:** 🟡 written — not yet regenerated & verified

**What it proves:** an analyst discovers and filters the enrollment data with natural language
(Genie) and by browsing (Catalog Explorer) — zero SQL.

**Setup (SA, done):** shared, read-only Genie space **"Enrollment Explorer (BA-01)"** deployed as
a **DAB `genie_spaces` resource** (`businessanalyst/resources/ba_genie.genie_space.yml` +
serialized body `src/genie/enrollment_explorer.geniespace.json`) — **deployed & verified** (accepts
questions). Open it: `databricks bundle summary -t dev --profile datamarket | grep -A2 ba_enrollment_explorer`.

**How to test:** open the Genie space → click a starter question (*"Show me enrollment counts by
department"*) → refine in English (*"…for Fall 2024"*). Then Catalog Explorer →
`silver_dev.enrollment` → Sample Data. Walkthrough: `README_BA01.md`.

**Expected outcome:** Genie returns grouped enrollment summaries (all sample questions verified to
return live data); Catalog Explorer shows schema + sample rows. **Join gotcha** baked into the
space instructions: enrollment has no `dept_id` — a course's department is `course.dept_id`.

## BA-02 — Scheduled report & subscription (AI/BI dashboard)

> **Built:** ✅ · **Prompt:** — n/a (subscribe to a pre-built dashboard)

**What it proves:** an analyst subscribes to a pre-built dashboard for recurring delivery, or
exports it on demand — no SQL.

**Setup (SA, done):** AI/BI dashboard **"Enrollment by Department (BA-02)"** deployed as a DAB
resource (`businessanalyst/resources/ba_dashboard.dashboard.yml` +
`src/dashboards/enrollment_by_department.lvdash.json`), **verified ACTIVE**. KPIs, top-15
department bar, enrollment-by-year trend, dept×term detail table.

**How to test:** `databricks bundle summary -t dev --profile datamarket | grep -A2 ba_enrollment`
→ open the URL → **Schedule/Subscribe** (email/Slack, weekly), or **⋯ → Download** (CSV/Excel/PDF).
Walkthrough: `README_BA02.md`.

**Expected outcome:** a per-user subscription registers, or a file downloads. Queries pre-tested
on `silver_dev` (40 depts, 960 dept×term groups, avg GPA ≈ 3.1). Read-only → concurrent-safe.

> **Demo flow for BA-03/04/05 (Lakeflow Designer + its Genie agent).** The analyst starts from
> data — either an **existing platform object** (BA-03, BA-05) or a **file they upload** (BA-04) —
> then **describes what they want in plain English to the Designer's Genie agent**, which builds
> the flow. The runbook gives the exact prompt to paste. No SQL, no manual node-wiring. If the
> live NL build stalls, each entry's **pre-built fallback** (a verified job / saved query) produces
> the same result.

## BA-03 / BA-06 / BA-07 — Ad-hoc extract to CSV / Excel / pipe (Designer, from existing data)

> **Built:** ✅ · **Prompt:** 🟡 written — not yet regenerated & verified

**What it proves:** starting from an **existing** platform object, an analyst describes an extract
in natural language, Designer builds it, and they download the result in three formats — no SQL.

**Demo flow:**
1. **Start point — existing data:** in Lakeflow Designer, **Add data** → pick
   `princeton_poc_dev.silver_dev.enrollment` (the foundation fact — already there, nothing to upload).
2. **Prompt the Designer Genie agent** (paste, then edit the filter in plain English):
   ```text
   From the enrollment table, join to student, course, term, and department so each row shows
   student name, course title, term year and season, grade, gpa_points, and department name.
   Filter to the Johnson Department. Sort by year descending. This is for an ad-hoc extract I'll
   download as CSV/Excel.
   ```
3. Designer builds the join+filter flow. **Run**, then **Download** the result → CSV (BA-03) /
   Excel (BA-06) / pipe-delimited (BA-07).

**Pre-built fallback:** saved query `businessanalyst/src/queries/enrollment_export.sql` (same
join, editable filter lines, 10k `LIMIT`) — run it in the SQL editor and **Download Results**.
Walkthrough: `README_BA03.md`.

**Expected outcome:** a filtered, human-readable extract (student name, course title, term, grade,
GPA, department); the Johnson-Department filter returns a smaller set (verified). All three formats download cleanly.

## BA-04 — Upload + join + transform (Designer, from your own file)

> **Built:** ✅ · **Prompt:** 🟡 written — not yet regenerated & verified

**What it proves:** an analyst **uploads their own spreadsheet**, then has the Designer Genie agent
join it to platform data and transform it — no SQL.

**Demo flow:**
1. **Start point — upload:** in Lakeflow Designer → **Add data** → **Upload file** →
   `departments_budget_fy2025.csv` (columns: `dept_id, dept_name, budget_amount, approved_date`).
   *(A pre-staged copy also lives at `/Volumes/princeton_poc_dev/landing_dev/files/uploads/` if a
   live upload isn't convenient.)*
2. **Prompt the Designer Genie agent:**
   ```text
   Join my uploaded budget file to the enrollment data: my file has dept_id and budget_amount;
   join it through the course table (course.dept_id) to the enrollment fact, and join student to
   get status. Keep only active students. Rename budget_amount to total_budget and dept_name to
   department. Add a column budget_per_student = total_budget divided by the number of distinct
   students in that department. Save the result to my own schema.
   ```
3. Designer builds upload→join→filter→rename→derive→write. **Run.**

**Pre-built fallback:** job **"BA Workflow — Budget-Enriched Enrollment"**
(`businessanalyst/resources/ba_workflow.job.yml`) — **verified green (35,937 rows)**:
```bash
databricks bundle run ba_budget_enrollment_join -t dev --profile datamarket
```

**Expected outcome:** `wksp_<you>.ba_dept_budget_enrollment_summary` — enrollments enriched with
department budget + derived `budget_per_student` (e.g. Leblanc Dept 1,169,659 → 1,094.16/student).

## BA-05 / BA-08 — Light transform (Designer, from existing data) + save & reuse

> **Built:** ✅ · **Prompt:** 🟡 written — not yet regenerated & verified

**What it proves:** starting from an **existing** object, an analyst applies light transforms
(rename / filter / derived field) via a Designer Genie-agent prompt, then **saves the flow as a
reusable workflow** (BA-08).

**Demo flow:**
1. **Start point — existing data:** Designer → **Add data** → `princeton_poc_dev.silver_dev.student`
   (join `department` for the major name).
2. **Prompt the Designer Genie agent:**
   ```text
   From the student table joined to department, keep only active students. Rename the department
   name column to major, derive a full_name column by concatenating first_name and last_name, and
   add an email_domain column extracted from the part of the email after the @. Save the result to
   my own schema.
   ```
3. Designer builds the rename/filter/derive flow. **Run.**
4. **BA-08 — save & reuse:** **Save as** a workflow/job. Re-run any time (or schedule it); change
   the filter/params to reuse on new data without rebuilding the canvas.

**Pre-built fallback:** the same `ba_budget_enrollment_join` job demonstrates the save-and-reuse
pattern (parameters `upload_file`, `status_filter`, `catalog`, `schema_suffix`); re-run it or
schedule it. Walkthrough: `README_BA04_BA08.md`.

**Expected outcome:** a transformed table in `wksp_<you>` (renamed + derived columns, active-only),
and a saved workflow that re-runs on demand.

**Notes:** (1) **Isolation** — Designer/fallback both write to the analyst's own `wksp_<user>`,
not shared `silver_dev`, so ~20 analysts run concurrently. (2) **Join gotcha the Genie agent
handles:** `enrollment` has no `dept_id` — a course's department is `course.dept_id`; the prompts
state this so the agent joins correctly. (3) `countDistinct` in a Spark window is unsupported —
the fallback job aggregates distinct students per dept separately and joins back.
