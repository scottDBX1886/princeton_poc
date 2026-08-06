# BA-04 / BA-05 / BA-08 — Upload + join + transform (no-code canvas), saved & reusable

**Persona:** Business Analyst. Upload a spreadsheet, join it to platform data, filter, rename,
derive a column, save the result — via the **Lakeflow Designer** drag-and-drop canvas — then
save the whole thing as a **reusable workflow** you can re-run any time.

## Pre-built objects

- Sample upload: `businessanalyst/src/sample_uploads/departments_budget_fy2025.csv` (40 real
  departments with FY25 budgets) — staged at
  `/Volumes/princeton_poc_dev/landing_dev/files/uploads/departments_budget_fy2025.csv`.
- Reusable job (BA-08): **"BA Workflow — Budget-Enriched Enrollment"**
  (`businessanalyst/resources/ba_workflow.job.yml`), backed by the runner
  `businessanalyst/src/jobs/budget_enrollment_join_runner.py`. **Verified: TERMINATED SUCCESS,
  35,937 rows.**

## BA-04 / BA-05 — the no-code canvas (Lakeflow Designer)

The analyst builds this on the Designer canvas (each step is a draggable node):

1. **Add Data** — upload / pick `departments_budget_fy2025.csv` from the volume.
2. **Join** — budget → `course` (on `dept_id`) → `enrollment`; join `student` for status.
   *(A course's department is `course.dept_id`; enrollment has no direct dept_id.)*
3. **Filter** — `student.status = 'active'` (BA-05: change this to `graduated`, or relax it, in the panel).
4. **Rename** — `budget_amount` → `total_budget`, `dept_name` → `department`, `approved_date` → `budget_approved`.
5. **Add column** — `budget_per_student = total_budget / distinct students in the department`.
6. **Save** — write to **your own** `wksp_<you>.ba_dept_budget_enrollment_summary`.

Click **Run**. No SQL written.

## BA-08 — save & reuse

- The canvas saves as the **"BA Workflow — Budget-Enriched Enrollment"** job. Re-run any time from
  **Jobs & Pipelines**, or via:
  ```bash
  databricks bundle run ba_budget_enrollment_join -t dev --profile dbx_shared_demo
  ```
- **Parameters** let you reuse it without editing: `upload_file` (drop a new budget file, e.g.
  `departments_budget_fy2026.csv`), `status_filter` (BA-05 variation), `catalog`/`schema_suffix`.
- Add a **schedule** in job settings for weekly auto-refresh.

## Expected outcome

Table `wksp_<you>.ba_dept_budget_enrollment_summary` — enrollment rows enriched with each
department's budget and a derived `budget_per_student`. **Verified:** 35,937 active-student rows,
e.g. *Leblanc Department* budget 1,169,659 → 1,094.16 per student.

## Notes / troubleshooting

- **Isolation:** writes to **your** `wksp_<you>` schema, never the shared `silver_dev` — so ~20
  analysts run it at once without collision. (This is a deliberate change from the original plan,
  which targeted shared `silver_dev`.)
- **`countDistinct` in a window is unsupported in Spark** — the runner computes distinct students
  per department as a separate aggregation and joins it back. (Noted because the Designer canvas's
  "distinct count" node compiles to the same safe pattern.)
- **File not found:** upload your CSV to `/Volumes/princeton_poc_dev/landing_dev/files/uploads/` first.
- **Different data (BA-05):** point `upload_file` at another spreadsheet, or change `status_filter`.
