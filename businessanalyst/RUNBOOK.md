# Princeton POC — Business Analyst Runbook

No-code / low-code scenarios (BA-01…BA-08) — Genie, AI/BI dashboards, and Lakeflow Designer +
its Genie agent. Prerequisite: the shared foundation — see
`[foundation/RUNBOOK.md](../foundation/RUNBOOK.md)`. Index: `[docs/runbook/README.md](../docs/runbook/README.md)`.

*No-code / low-code only — the analyst never writes SQL. Five pre-built objects (a Genie space,
an AI/BI dashboard, a saved SQL export query, a sample upload + Designer canvas, and a saved
workflow job) cover BA-01…08. All read the shared foundation; the one object that writes
(BA-04/05/08) writes to the analyst's own* `wksp_<user>` *schema. Full walkthroughs in*
`businessanalyst/src/walkthroughs/`*.*

## BA-01 — No-code browse, filter, preview (Genie + Catalog Explorer)

> **Built:** ✅ · **Prompt:** 🟢 tested (princeton_poc: Designer Visual Data prep + Genie Code filter — verified)

**What it proves:** an analyst discovers and filters the enrollment data with natural language
(Genie) and by browsing (Catalog Explorer) — zero SQL.

**How to test:** 

1. Create new "Visual Data prep".
2. Enter the following prompt into the Genie Code chat on the canvas.
  `Add gold_enrollment_course_inner and apply filter on "grade" for only values "C" and "C+"`
  1. Verify the filter condition applied correctly.

**Expected outcome:** Data browseable through a visual interface; row-level filter applied without SQL; result set previewable.

## BA-02 — Scheduled report & subscription (AI/BI dashboard)

> **Built:** ✅ · **Prompt:** — n/a (subscribe to a pre-built dashboard)

**What it proves:** an analyst subscribes to a pre-built dashboard for recurring delivery, or
exports it on demand — no SQL.

**How to test:** 

```
1. Open dashbaord "[princeton_poc_dev] Workload Monitoring (E9 · SE-34)"
2. In upper Right corner, click "Schedule"
3. Click "+Schedule"
4. Leave Schedule section as the default.
5. Click "Advanced settings"
6. On "Custom Email subject", add your name to end of value
7. Select a SQL warehouse
8. Click "Subscribe" check box.
9. Click "Attachments"
10. Under "INclude Pages", select "All pages"
11. In "Include data", select "avg job-task duration(min)" and "Run history - all worksloads (last 30 days)
12. Click "Create"
13. On the newly created schedule for your user, hover over the schedule and on the far right, open menu and click "Run now".  Let this run and an email will be sent to you.
```

**Expected outcome:** Report or file delivered at the scheduled time without analyst intervention on delivery day.

## BA-03 / BA-06 / BA-07 — Ad-hoc extract to CSV / Excel / pipe (Designer, from existing data)

> **Built:** ✅ · **Prompt:** 🟢 tested (princeton_poc: Designer CSV/Excel download + Excel & pipe-delimited outputs to Volume — verified)

**What it proves:** Business analyst can easily add data objects, apply filters as-hoc and export data in CSV/EXCEL.  The same dataflow can be outputed to a shared consumable location in Excel/delimited flat file.

**Demo flow:**

### BA-03 - adhoc csv/excel download

1. **Start point — existing dataflow:** In the designer data prep from the previous steps, select the ***Filter***
2. On the **Output** data preview panel.  You will see a **Download** button, click the arrow to select either ***CSV/EXcel***
3. Open downloaded file to confirm data.



### BA-06  - shared excel output

1. In the canvas, enter the following prompt
  ```
   Add an output that saves the filtered data as EXCEL and outputs to /Volumes/princeton_poc_dev/landing_dev/files.  Please add my user name to file name.
  ```
2. Click the ***output_excel*** object, and click **Run**
3. Once run is successful, open ***/Volumes/princeton_poc_dev/landing_dev/files*** and locate your newly created excel file.  You can click on it, to open a data preview



### BA-07 - shared delimited output

1. Back in the canvas of the data prep, enter the following prompt
  ```
   Add an output that saves the filtered data as pipe (|) delimited file and save in /Volumes/princeton_poc_dev/landing_dev/files.  I want a single file in the volume with extension .txt
  ```
2. Once the new output is created, it will say something similiar to ***Single pipe-delimited file written to: /Volumes/princeton_poc_dev/landing_dev/files/scott_johnson_grade_c_filter.txt***
3. Navigate to that volume and you will find the newly created .txt file.  When you click on the file, the data preview will show the pipe (|) delimiter

**Expected outcome:** File downloaded successfully; data matches filter criteria; file opens correctly in Excel. Excel file opens with headers; column widths reasonable; data types preserved. File produced with correct delimiter; encoding and line endings suitable for external consumption.

## BA-04 — Upload + join + transform (Designer, from your own file)

> **Built:** ✅ · **Prompt:** — n/a (manual upload + drag Join / Split Join — verified on princeton_poc)

**What it proves:** an analyst **uploads their own spreadsheet**, then has the Designer Genie agent
join it to platform data and transform it — no SQL.

**Demo flow:**

1. **Start point** - open volume: ***/Volumes/princeton_poc_dev/landing_dev/files/downloads/*** and **download** the file ***students.csv*** to your local desktop/downloads diretory
2. **Open visual data prep from previous work**
3. Open a local file explore to navigate to the downloaded ***students.csv*** file.  Left click and drag the file onto the data prep canvas.  Follow the wizard upload.  Select **Overwrite files with the same filename** and for **Destintation Volume**, select ***princeton_poc_dev.landing_dev***.  Then click **Upload**.  THis will create a new data source object.
4. In the **Operators** panel on the left in the canvas, find the **Join** transformation, left click and drag onto the canvas.
5. Drag the **gold_enrollment_course_inner** data output to the left inbound of the join and **students** to the right inbound data port of the join.
6. Double click on the join to bring up the configuration panel, if not already visable.
7. Select ***student_id*** for both data objects as the join condition.  Select ***Split Join***.  Then click **Apply**
8. The ***Split Join*** will allow you to see matched records and un-matched records from each dataset respectively.

**Expected outcome:** Join produces a combined dataset; analyst can see matched and unmatched rows; no scripting required.

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