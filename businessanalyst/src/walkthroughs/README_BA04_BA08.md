# BA-04 / BA-05 / BA-08 — Upload + join + transform (Designer + Genie agent), saved & reusable

**Persona:** Business Analyst (no SQL). The demo flow: start from data — **upload your own file**
(BA-04) or an **existing object** (BA-05) — then **tell the Lakeflow Designer Genie agent** what to
build. Save the flow for reuse (BA-08). A verified pre-built job is the fallback if the live NL
build stalls.

---

## BA-04 — upload your own file, then prompt the agent to join + transform

1. **Lakeflow Designer** → **Add data** → **Upload file** → `departments_budget_fy2025.csv`
   (columns: `dept_id, dept_name, budget_amount, approved_date`). A pre-staged copy also lives at
   `/Volumes/princeton_poc_dev/landing_dev/files/uploads/` if a live upload isn't convenient.
2. Paste to the **Designer Genie agent**:
   ```text
   Join my uploaded budget file to the enrollment data: my file has dept_id and budget_amount;
   join it through the course table (course.dept_id) to the enrollment fact, and join student to
   get status. Keep only active students. Rename budget_amount to total_budget and dept_name to
   department. Add a column budget_per_student = total_budget divided by the number of distinct
   students in that department. Save the result to my own schema.
   ```
3. The agent builds upload → join → filter → rename → derive → write. **Run.**

## BA-05 — start from an existing object, prompt light transforms

1. **Lakeflow Designer** → **Add data** → `princeton_poc_dev.silver_dev.student` (join `department`).
2. Paste to the **Designer Genie agent**:
   ```text
   From the student table joined to department, keep only active students. Rename the department
   name column to major, derive a full_name column by concatenating first_name and last_name, and
   add an email_domain column extracted from the part of the email after the @. Save the result to
   my own schema.
   ```
3. The agent builds the rename/filter/derive flow. **Run.**

## BA-08 — save & reuse

- In Designer, **Save as** a workflow/job. Re-run it any time, change a parameter (different file,
  different filter), or **schedule** it — no rebuilding the canvas. Different analysts run the same
  saved workflow.

---

## Fallback — pre-built, verified job (if the live NL build stalls)

Job **"BA Workflow — Budget-Enriched Enrollment"** (`businessanalyst/resources/ba_workflow.job.yml`,
runner `businessanalyst/src/jobs/budget_enrollment_join_runner.py`) — **verified: TERMINATED
SUCCESS, 35,937 rows**. It is the compiled equivalent of the BA-04 canvas and demonstrates BA-08
reuse via parameters:
```bash
databricks bundle run ba_budget_enrollment_join -t dev --profile dbx_shared_demo
```
Parameters: `upload_file`, `status_filter` (the BA-05 variation), `catalog`, `schema_suffix`.

## Expected outcome

`wksp_<you>.ba_dept_budget_enrollment_summary` — enrollments enriched with department budget +
derived `budget_per_student` (e.g. *Leblanc Department* 1,169,659 → 1,094.16 per student). BA-05's
transform yields a renamed/derived, active-only table; BA-08 leaves a saved workflow you re-run on demand.

## Notes / troubleshooting

- **Isolation:** Designer and the fallback both write to **your** `wksp_<you>` schema, never shared
  `silver_dev` — so ~20 analysts run at once without collision.
- **Join gotcha the agent handles:** `enrollment` has no `dept_id`; a course's department is
  `course.dept_id`. The prompts state the join path so the agent resolves it correctly.
- **`countDistinct` in a Spark window is unsupported** — the fallback runner computes distinct
  students per department as a separate aggregation and joins it back (the Designer "distinct count"
  node compiles to the same safe pattern).
- **File not found (BA-04):** upload your CSV, or use the pre-staged copy under `files/uploads/`.
