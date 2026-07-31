# Princeton POC — Phase 3: Business Analyst (No-Code/Low-Code) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Business Analysts (limited/no SQL, Excel-comfortable) to discover, filter, extract, upload, and transform data entirely via no-code/low-code Databricks surfaces: Genie natural-language (browse+filter), AI/BI dashboards (subscriptions, exports), Lakeflow Designer canvas (upload+join+transform), and UI-driven file export. No notebooks, no code prompts — just point-and-click / natural-language queries.

**Architecture:** Five reusable, saveable no-code/low-code objects are pre-built and live in the `princeton_poc` bundle as DAB resources (saved Genie space definitions, saved AI/BI dashboard JSON, sample upload files, Designer pipeline definitions). During the demo, a BA analyst uses each object via its UI/NL interface (never writing code). All objects read from the shared foundation (`silver_dev`, `gold_dev` tables) established in Phase 0 and benefit from Unity Catalog governance (RLS/CLS, governed by Phase 4).

**Tech Stack:** Databricks (Genie Spaces, AI/BI dashboards, Lakeflow Designer), Unity Catalog (no code), UC volumes (sample uploads), Databricks Asset Bundles (pre-built object definitions stored as `.genie.yaml`, `.dashboard.yml`, `.designer.yml`).

## Global Constraints

- **No SQL, no code written by the analyst** — the BA's primary path is UI clicks and NL questions. Pre-built objects provide the "how"; the analyst provides the "what" (filter criteria, export format, column selection).
- **Catalog:** `princeton_poc_dev` (shared with Phase 0). BA demo works against dev data.
- **Schemas:** BA reads from `silver_dev` (dims: department, faculty, course, student, financial_aid) and `gold_dev` (fact: enrollment_history). Bronze layer is hidden from BA UX.
- **Volumes:** Sample uploads live in `/Volumes/princeton_poc_dev/landing_dev/uploads/` (separate from the raw ingestion landing; this is the BA's self-service upload staging).
- **Genie Spaces:** Pre-configured with NL prompts baked into the space definition (e.g., "Show me enrollments by department"). The analyst edits the prompt in the UI to filter (e.g., "Show me enrollments by department for term 3").
- **AI/BI dashboards:** Packaged as `.lvdash.json` or `.dashboard.yml` (Lakeview format). All SQL datasets must be pre-tested (build phase) before bundling; the BA admin subscribes or exports via the dashboard UI (no SQL edit).
- **Lakeflow Designer:** Pre-built pipelines saved in the bundle. When invoked, the BA opens the canvas, adjusts parameters (file name, output columns, filter criteria), and runs. No SQL edit.
- **No real-time test at "write the plan" time** — plan specifies the objects and their NL/UI paths; fixtures (sample uploads, pre-canned Genie prompts) are defined; actual testing happens at build time (Phase 3 build agent executes Genie asks, validates dashboard datasets, confirms Designer pipeline runs end-to-end).
- **Verification model:** each task ends with (1) the pre-built asset outline (Genie config, Dashboard SQL, Designer pipeline YAML), (2) the analyst's NL/UI steps (documented as click-path or Genie prompt), (3) expected outcome + a check (row count, file landed, subscription scheduled).
- **Developer/analyst role split:** Phase 3 build agent writes the Genie config, dashboard JSON, Designer pipeline, and sample uploads. Phase 3 demo agent (or a BA user in the POC) uses them (never editing SQL or code, only parameterizing existing queries via filter/export UI).

---

### Task 0: Repo + DAB resources for BA objects

**Files:**
- Create: `resources/businessanalyst.genie.yml` (placeholder for Genie spaces)
- Create: `resources/businessanalyst.dashboard.yml` (placeholder for dashboards)
- Create: `resources/businessanalyst.designer.yml` (placeholder for pipelines)
- Create: `src/businessanalyst/__init__.py`
- Create: `src/businessanalyst/sample_uploads/README.md`
- Create: `docs/BA_GUIDE.md` (end-user guide; refers to the runbook for each scenario)

**Interfaces:**
- Produces: resource placeholders and a stub user guide for the BA.

- [ ] **Step 1: Create BA resource skeleton files**

```bash
mkdir -p src/businessanalyst/sample_uploads
touch src/businessanalyst/__init__.py
```

- [ ] **Step 2: Write placeholder `resources/businessanalyst.genie.yml`**

```yaml
# Placeholder; will be populated with saved Genie space definitions in Tasks 1+2.
# Each task that creates a Genie space appends its definition here.
resources:
  genie_spaces: {}   # populated by later tasks
```

- [ ] **Step 3: Write placeholder `resources/businessanalyst.dashboard.yml`**

```yaml
# Placeholder; will be populated with AI/BI dashboard definitions in Tasks 3+4.
resources:
  dashboards: {}     # populated by later tasks
```

- [ ] **Step 4: Write placeholder `resources/businessanalyst.designer.yml`**

```yaml
# Placeholder; Lakeflow Designer pipelines are DAB-managed as saved jobs or 
# pre-built canvas exports. This is a reference; the actual pipeline YAML 
# is in src/businessanalyst/pipelines/ and referenced here.
resources:
  jobs: {}           # BA-D and BA-E pipelines as scheduled jobs (optional)
```

- [ ] **Step 5: Write `src/businessanalyst/sample_uploads/README.md`**

```markdown
# BA Sample Uploads

Sample files for the BA to upload during demos. Use these in Task 4 (BA-D).

- `departments_budget_fy2025.csv` — test CSV with dept budgets (BA-04 demo fixture)
- `enrollment_forecast.xlsx` — Excel with enrollment forecasts by term (BA-05 demo fixture)

All files are checked into git for reproducibility. The BA uploads these from the
Databricks Files UI (or the Lakeflow Designer "Add Data" tab) during the demo.
```

- [ ] **Step 6: Write `docs/BA_GUIDE.md`**

```markdown
# Business Analyst No-Code / Low-Code Guide

This guide is for Princeton DMIA business analysts who want to discover, filter,
extract, join, and transform enrollment and financial data using Databricks —
**without writing SQL or code**.

## Five BA-friendly surfaces

1. **Genie Spaces** — Ask natural-language questions (e.g., "Show me enrollments
   by department") and get instant answers without touching SQL.
2. **AI/BI Dashboards** — Pre-built visualizations you can subscribe to or export
   to Excel / CSV. No SQL edit needed.
3. **Lakeflow Designer** — Drag-and-drop pipeline canvas. Upload a spreadsheet,
   join to platform data, filter, rename columns, export. All via UI.
4. **Catalog Explorer** — Browse datasets, see row counts, preview data. Apply
   row filters (RLS) if your role permits.
5. **UI-driven export** — Select data, filter, download to CSV / Excel / pipe-delimited.

Each scenario below links to the runbook. Start there.

## Scenarios (Tracks: GitHub issue numbers)

- **BA-01** (Catalog Explorer browse + filter + preview) — #23
- **BA-02** (Scheduled report/dataset subscription) — #24
- **BA-03, BA-06, BA-07** (Ad-hoc extract to file) — #25
- **BA-04, BA-05** (Upload + join + light transform) — #26
- **BA-08** (Save + reuse workflow) — #27

See `docs/runbook/README.md` for the demo scripts.
```

- [ ] **Step 7: Commit**

```bash
git add resources/businessanalyst*.yml src/businessanalyst docs/BA_GUIDE.md && \
git commit -m "chore: BA resource placeholders + guide skeleton"
```

---

### Task 1: BA-A — No-code browse, filter, preview (Catalog Explorer + Genie) — Tracks: #23

**Purpose:** Enable a BA to discover the dataset catalog, browse table structure (schema, row counts, sample data), apply a row filter (RLS), and preview rows — all without SQL.

**Pre-built assets:**
- Genie Space `princeton_enrollment_explorer` configured with one pre-canned prompt: `"Show me enrollments by [department_name] and [term_id], limited to students in status [status]"` (filter bindings to the column domain).
- Catalog Explorer: no code required; purely UI. The BA navigates Catalog → `princeton_poc_dev` → `silver_dev` → opens `enrollment` table → clicks "Preview" → sees schema + first 100 rows.
- If RLS is applied by Phase 4 PA tasks, the preview respects it automatically.

**Files:**
- Create: `src/businessanalyst/genie/enrollment_explorer.genie.yaml`
- Create: `src/businessanalyst/README_BA01.md` (analyst's walkthrough)

**Interfaces:**
- **Genie Space:** `enrollment_explorer` deployed; analyst enters a filtered NL prompt (e.g., "Show enrollments from Engineering department for Fall 2024").
- **Catalog Explorer:** BA navigates `silver_dev.enrollment` table; views schema + row preview.
- Expected outcome: analyst gets instant enrollment summary (rows grouped/filtered by NL prompt) + catalog shows row count, schema, sample data. Demonstrates no-code discovery + row filtering.

- [ ] **Step 1: Define the Genie Space configuration** (as YAML, will be deployed via DAB or created live in the workspace UI during the demo).

Create `src/businessanalyst/genie/enrollment_explorer.genie.yaml`:

```yaml
# Genie Space: Enrollment Explorer
# Pre-canned prompts enable the BA to explore enrollment data by
# department, term, and student status — no SQL.

name: enrollment_explorer
description: "No-code enrollment explorer. Ask questions like 'Show me enrollments by department for Fall 2024.'"

# Base context: tables available to Genie
schemas:
  - schema: princeton_poc_dev.silver_dev
    comment: "Shared foundation dimensions and facts"

# Pre-canned prompt templates (shown in the Genie UI)
prompts:
  - text: "Show me enrollments by department and term"
    description: "Summarize enrollments grouped by department and term"
  - text: "Show me enrollments for department [dept_name] in term [term_id]"
    description: "Filter enrollments by department name and term ID"
  - text: "Show me student enrollment status (active, graduated, withdrawn) by department"
    description: "Enrollment status distribution by department"
  - text: "How many students are enrolled per faculty member in [dept_name]?"
    description: "Faculty-level enrollment load"

# Instructions for the BA (shown in the Genie space header)
instructions: |
  1. Click one of the prompts below, or type your own question.
  2. Edit the prompt to add filters (e.g., replace [dept_name] with "Engineering").
  3. Click "Ask" — Genie generates and runs SQL, returns results in a table.
  4. Refine filters in the prompt and re-ask. No SQL editing needed.
```

- [ ] **Step 2: Write the analyst's BA-01 walkthrough** `src/businessanalyst/README_BA01.md`:

```markdown
# BA-01: No-Code Browse, Filter, Preview (Genie + Catalog Explorer)

## What you'll do

Discover the enrollment dataset via two no-code paths:
1. **Genie Space:** Ask natural-language questions; Genie generates SQL and returns results.
2. **Catalog Explorer:** Browse the dataset schema, row counts, and sample data.

## Prerequisites

- Access to the Databricks workspace (dev POC)
- A BA user role with SELECT on `silver_dev` tables

## Steps

### Path 1: Genie Space (NL browsing)

1. In Databricks, open **Data** → **Genie Spaces**.
2. Open the **"Enrollment Explorer"** space.
3. You see pre-canned prompts like "Show me enrollments by department and term".
4. Click the first prompt. Genie loads the template: `"Show me enrollments by department and term"`.
5. Edit it: replace `[dept_name]` with `Engineering` (or another department).
6. Click **Ask**. Genie generates SQL, runs it, and returns a table of results.
7. Refine the prompt (e.g., add `for term [term_id] = 3`) and click **Ask** again.
8. No SQL written; you just edited the question.

### Path 2: Catalog Explorer (schema + preview)

1. In Databricks, open **Catalog** → **princeton_poc_dev** → **silver_dev** → **enrollment** table.
2. You see the table schema: columns (enrollment_id, student_id, course_id, term_id, grade, gpa_points).
3. Click **Preview** at the top. Databricks shows the first 100 rows.
4. Scroll right to see all columns. Scroll down to inspect sample data.
5. If row-level security (RLS) is configured (Phase 4), the preview is filtered to your authorized rows.
6. If you want to see only students from the Engineering department, use the column filter (if RLS doesn't restrict you).

### Expected outcome

- **Genie:** returns enrollment counts and breakdowns by department/term without you writing SQL.
- **Catalog Explorer:** you've verified the data exists, understand the schema, and see sample rows.

## If something doesn't work

- **Genie space missing:** the space hasn't been created yet. Contact your admin to deploy Phase 3.
- **Preview shows "permission denied":** your role lacks SELECT on the table. Contact your admin.
- **Genie prompt returns an error:** Genie might need a column name corrected. Re-read the prompt template and ensure you're using valid column values (e.g., exact department name).
```

- [ ] **Step 3: Outline the expected dataset for Genie** (built in Phase 0)

The Genie space queries `silver_dev.enrollment` and the dimension tables (`department`, `term`, `student`). Expected row count: ~1M enrollments (from Phase 0 Task 2, `row_count` default). Genie will join to dims on demand via NL inference.

- [ ] **Step 4: Pre-build the Genie space in the workspace** (during the build phase, not this planning phase — but document it here)

During build, the BA-build agent will:
1. Log into the dev workspace (dbx_shared_demo profile).
2. Open Databricks → **Data** → **Create Genie Space**.
3. Name: `enrollment_explorer`.
4. Add the `silver_dev` schema.
5. Save the space (assigns a space ID).
6. Capture the space ID in the runbook.

For now (planning phase), we document the space definition in YAML so the build agent has all the context.

- [ ] **Step 5: Verify Catalog Explorer path** (no build needed; part of base Databricks UI)

Catalog Explorer is always available. No pre-build required. Just confirm that `silver_dev` schemas are readable by the BA role (Phase 4 grants).

- [ ] **Step 6: Write the expected outcome assertion** (to verify at build time)

During Phase 3 build:
1. In Genie space, ask: `"Show me enrollments by department and term"` (unfiltered).
2. Expected result: table with ~30+ department rows and ~24 term rows (from Phase 0). Row count should be close to the total enrollment count (e.g., ≥1M if `row_count` was 5M in Phase 0).
3. In Catalog Explorer, open `silver_dev.enrollment` table.
4. Expected: schema matches Phase 0 (columns: enrollment_id, student_id, course_id, term_id, grade, gpa_points).
5. Expected: preview returns ≥100 rows.

- [ ] **Step 7: Commit the BA-01 docs**

```bash
git add src/businessanalyst/genie/enrollment_explorer.genie.yaml src/businessanalyst/README_BA01.md && \
git commit -m "feat(ba-01): Genie enrollment explorer + Catalog Explorer walkthrough (no-code browse/filter/preview)"
```

---

### Task 2: BA-B — Scheduled report & dataset subscription — Tracks: #24

**Purpose:** Enable a BA to subscribe to a pre-built report (AI/BI dashboard) and receive results on a schedule (e.g., weekly enrollment summary emailed as CSV or in Slack).

**Pre-built assets:**
- AI/BI dashboard `enrollment_by_department_weekly` configured with a subscription setup (email + CSV export, weekly cadence).
- SQL query dataset (tested during build phase): aggregates enrollments by department and term, includes row counts and % change vs. prior term.

**Files:**
- Create: `src/businessanalyst/dashboards/enrollment_by_department.sql` (the query)
- Create: `src/businessanalyst/README_BA02.md` (analyst's walkthrough)
- Create: `resources/businessanalyst.dashboard.yml` (dashboard definition; will be updated from Task 0 placeholder)

**Interfaces:**
- **Dashboard:** pre-built with filters (department, term) and a subscription button.
- **Analyst action:** clicks "Subscribe" → sets email + frequency (weekly) → confirms.
- Expected outcome: analyst receives enrollment summary CSV weekly. If one analyst needs a different slice (e.g., only Engineering), they can edit the filter and re-subscribe (no SQL edit, just UI filter).

- [ ] **Step 1: Write the dashboard query** `src/businessanalyst/dashboards/enrollment_by_department.sql`:

```sql
-- Enrollment Summary by Department (Weekly Report)
-- Used in AI/BI dashboard: enrollment_by_department_weekly
-- Aggregates: enrollment count, avg GPA, enrolled students, by department and term.

SELECT
  d.dept_id,
  d.name AS department,
  t.term_id,
  t.year,
  t.season,
  COUNT(e.enrollment_id) AS enrollment_count,
  COUNT(DISTINCT e.student_id) AS unique_students,
  ROUND(AVG(e.gpa_points), 2) AS avg_gpa,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY t.term_id) AS pct_of_term
FROM
  princeton_poc_dev.silver_dev.enrollment e
  JOIN princeton_poc_dev.silver_dev.course c ON e.course_id = c.course_id
  JOIN princeton_poc_dev.silver_dev.department d ON c.dept_id = d.dept_id
  JOIN princeton_poc_dev.silver_dev.term t ON e.term_id = t.term_id
GROUP BY
  d.dept_id, d.name, t.term_id, t.year, t.season
ORDER BY
  t.term_id DESC, enrollment_count DESC;
```

- [ ] **Step 2: Test the query at build time** (during Phase 3 build execution)

Build agent:
1. Log into dev workspace (dbx_shared_demo profile).
2. Open SQL editor.
3. Paste the query.
4. Run against dev catalog.
5. Expected: ≥5 rows (departments) × ≥4 rows (terms) = ≥20 rows; no errors; avg_gpa is numeric; enrollment_count > 0.
6. Note the execution time (likely <5s for ~1M enrollment_history fact).

- [ ] **Step 3: Write the dashboard YAML** `resources/businessanalyst.dashboard.yml`:

```yaml
resources:
  dashboards:
    enrollment_by_department_weekly:
      display_name: "Enrollment by Department (Weekly Report)"
      description: "Enrollment summary by department and term. Subscribe to receive weekly email updates."
      
      # Databricks AI/BI dashboard as .lvdash.json
      # (This YAML is a reference; the actual JSON is in src/businessanalyst/dashboards/)
      
      # Datasets (queries to load into the dashboard)
      datasets:
        - dataset_key: enrollment_summary
          query: |
            SELECT
              d.dept_id, d.name AS department, t.term_id, t.year, t.season,
              COUNT(e.enrollment_id) AS enrollment_count,
              COUNT(DISTINCT e.student_id) AS unique_students,
              ROUND(AVG(e.gpa_points), 2) AS avg_gpa,
              COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY t.term_id) AS pct_of_term
            FROM
              princeton_poc_dev.silver_dev.enrollment e
              JOIN princeton_poc_dev.silver_dev.course c ON e.course_id = c.course_id
              JOIN princeton_poc_dev.silver_dev.department d ON c.dept_id = d.dept_id
              JOIN princeton_poc_dev.silver_dev.term t ON e.term_id = t.term_id
            GROUP BY d.dept_id, d.name, t.term_id, t.year, t.season
            ORDER BY t.term_id DESC, enrollment_count DESC
          
      # Visualizations (charts built on the dataset)
      visualizations:
        - name: "Enrollment Count by Department"
          type: "bar_chart"
          dataset: "enrollment_summary"
          x_axis: "department"
          y_axis: "enrollment_count"
          
        - name: "Enrollment Trend (Term vs Department)"
          type: "line_chart"
          dataset: "enrollment_summary"
          x_axis: "term_id"
          y_axis: "enrollment_count"
          group_by: "department"
      
      # Filters (BA can adjust without SQL edit)
      filters:
        - name: "department"
          column: "department"
          type: "dropdown"
          default: "All"
        - name: "term_id"
          column: "term_id"
          type: "dropdown"
          default: "All"
      
      # Subscription: the BA can enable email delivery
      subscription_config:
        enabled: true
        default_email: ""  # BA enters their email
        schedule: "weekly"  # Mon 8am PT
        format: "csv"       # or "excel"
```

- [ ] **Step 4: Write the analyst's BA-02 walkthrough** `src/businessanalyst/README_BA02.md`:

```markdown
# BA-02: Scheduled Report & Dataset Subscription

## What you'll do

Subscribe to a weekly email with enrollment summary by department. No SQL; the dashboard
is pre-built. You just set your email and confirm.

## Prerequisites

- Access to Databricks dev workspace
- BA role with SELECT on `silver_dev` tables

## Steps

1. In Databricks, open **Dashboards** (or the shared **Enrollment by Department (Weekly Report)** dashboard).
2. You see charts: enrollment by department (bar chart), enrollment trend over terms (line chart).
3. Optional: use the **Department** and **Term** filters at the top to slice the data (e.g., show only Engineering). No SQL edit.
4. Click the **Subscribe** button (top right).
5. Enter your email address and confirm the frequency: **Weekly** (Monday 8 AM PT).
6. Choose format: **CSV** (default) or **Excel**.
7. Click **Save Subscription**.
8. Databricks schedules the export. Next Monday morning, you'll receive the CSV in your inbox.

## If something doesn't work

- **Dashboard not found:** Phase 3 hasn't been deployed yet. Contact your admin.
- **Subscribe button disabled:** your workspace role may lack dashboard subscription permissions. Contact your admin.
- **Email never arrives:** check your spam folder, or contact your admin to verify the workspace email config.

## Expected outcome

In one week, you receive an email from noreply@databricks.com with an attached CSV: `enrollment_summary_<date>.csv`. Open it in Excel. You see department names, term IDs, enrollment counts, and avg GPAs.

## Variations (optional, analyst-driven)

- **Different schedule:** after subscribing, edit the subscription → change frequency to **Monthly** or **Daily**.
- **Different email:** subscribe again with a different email. You can have multiple subscriptions active.
- **Export manually:** instead of subscribing, click **Export** on the dashboard and download the CSV right away (BA-03 path).
```

- [ ] **Step 5: Specify expected outcome assertion** (to verify at build time)

Build agent will:
1. Create or open the `enrollment_by_department_weekly` dashboard.
2. Verify the query runs and returns ≥20 rows.
3. Click **Subscribe** → enter test email → confirm weekly schedule → **Save**.
4. Verify subscription is listed (usually in a "Subscriptions" section or dashboard settings).
5. Note: actual email delivery takes 1+ week; for demo purposes, builder verifies the subscription UI accepted the request and it appears in the list.

- [ ] **Step 6: Commit BA-02 docs**

```bash
git add src/businessanalyst/dashboards/enrollment_by_department.sql src/businessanalyst/README_BA02.md && \
git commit -m "feat(ba-02): enrollment dashboard query + subscription walkthrough (scheduled report delivery)"
```

---

### Task 3: BA-C — Ad-hoc extract to CSV/Excel/pipe — Tracks: #25

**Purpose:** Enable a BA to select a dataset, apply filters, and export to CSV, Excel, or pipe-delimited format for external distribution (e.g., send to a spreadsheet, ingest into another system, share with colleagues who don't have Databricks access).

**Pre-built assets:**
- Sample query (saved) in Databricks SQL editor: enrollments by student + course + term, with filters for department and term.
- Walkthrough on how to download the query result as CSV / Excel via the Databricks UI.

**Files:**
- Create: `src/businessanalyst/queries/enrollment_export.sql` (the saved query)
- Create: `src/businessanalyst/README_BA03.md` (analyst's walkthrough)

**Interfaces:**
- **Analyst action:** opens the saved query → adjusts filters (if any) → clicks **Download** → selects format (CSV, Excel, pipe) → file lands on laptop.
- Expected outcome: analyst has a downloadable file ready for distribution. Demonstrates no-SQL, UI-only export.

- [ ] **Step 1: Write the saved export query** `src/businessanalyst/queries/enrollment_export.sql`:

```sql
-- Enrollment Export (BA-03, BA-06, BA-07)
-- Pre-built saved query for BA export to CSV / Excel / pipe-delimited.
-- Use the filters below to slice by department and term.
-- Click "Download" and choose your format.

-- Filters (adjust these parameters before running):
-- DECLARE @dept_name STRING DEFAULT 'All';  -- or e.g., 'Engineering'
-- DECLARE @term_id INT DEFAULT NULL;         -- or e.g., 3

SELECT
  e.enrollment_id,
  s.student_id,
  CONCAT(s.first_name, ' ', s.last_name) AS student_name,
  c.course_id,
  c.title AS course_title,
  t.term_id,
  t.year,
  t.season,
  e.grade,
  e.gpa_points,
  d.name AS department
FROM
  princeton_poc_dev.silver_dev.enrollment e
  JOIN princeton_poc_dev.silver_dev.student s ON e.student_id = s.student_id
  JOIN princeton_poc_dev.silver_dev.course c ON e.course_id = c.course_id
  JOIN princeton_poc_dev.silver_dev.term t ON e.term_id = t.term_id
  JOIN princeton_poc_dev.silver_dev.department d ON c.dept_id = d.dept_id
WHERE
  (TRUE)  -- adjust: `(d.name = 'Engineering')` for dept filter
  AND (TRUE)  -- adjust: `(t.term_id = 3)` for term filter
ORDER BY
  t.term_id DESC, e.enrollment_id
LIMIT 10000;  -- preview limit; remove for full export
```

- [ ] **Step 2: Test the query** (during Phase 3 build)

Build agent:
1. Log into dev workspace.
2. Open SQL editor → **Create Query**.
3. Paste the query.
4. Run with default filters (no department/term restriction). Expected: 10k rows (or fewer if enrollment count < 10k).
5. Click the three-dot menu → **Download Results** → select **CSV**. Verify a file downloads.
6. Repeat: select **Excel** and **Pipe-Delimited**. Verify both download formats work.

- [ ] **Step 3: Write the analyst's BA-03 walkthrough** `src/businessanalyst/README_BA03.md`:

```markdown
# BA-03, BA-06, BA-07: Ad-Hoc Extract to CSV / Excel / Pipe-Delimited

## What you'll do

Export enrollment data to a file (CSV, Excel, or pipe-delimited) for sharing with
external teams or importing into other systems.

## Prerequisites

- Access to Databricks SQL editor
- BA role with SELECT on `silver_dev` tables

## Steps

### Method 1: Use the pre-built saved query

1. In Databricks, open **SQL** → **Queries** (or your team's query folder).
2. Find and open **"Enrollment Export"** (saved query).
3. You see a query with a WHERE clause that includes filter comments:
   ```sql
   WHERE
     (TRUE)  -- adjust: `(d.name = 'Engineering')` for dept filter
     AND (TRUE)  -- adjust: `(t.term_id = 3)` for term filter
   ```
4. If you want to filter by department, replace the first `(TRUE)` with `(d.name = 'Engineering')`.
5. If you want a specific term, replace the second `(TRUE)` with `(t.term_id = 3)`.
6. Click **Run**. Results appear below the query.
7. At the top-right of the results table, click the three-dot menu **⋯**.
8. Select **Download Results**.
9. Choose your format:
   - **CSV** — comma-separated, opens in Excel
   - **Excel (.xlsx)** — native Excel format
   - **TSV (Pipe-Delimited)** — pipe character (|) as delimiter
10. Click **Download**. The file appears in your Downloads folder.

### Method 2: Create an ad-hoc export (no pre-built query)

If you need a different set of columns or filters:

1. Open **SQL** → **Create Query**.
2. Write your own SELECT (or copy the "Enrollment Export" query and customize it).
3. Click **Run**.
4. Follow steps 7–10 above.

### Expected formats

- **CSV sample row:**
  ```
  enrollment_id,student_id,student_name,course_id,course_title,term_id,year,season,grade,gpa_points,department
  10001,2001,John Doe,5001,Calculus I,3,2025,Fall,A,4.0,Engineering
  ```
- **Excel:** native .xlsx; opens in Excel, Google Sheets, LibreOffice.
- **Pipe-Delimited sample row:**
  ```
  10001|2001|John Doe|5001|Calculus I|3|2025|Fall|A|4.0|Engineering
  ```

### If something doesn't work

- **Query errors:** check that filters are valid SQL (e.g., `(d.name = 'Engineering')` not `(d.name = engineering)`).
- **Download button missing:** try refreshing the page, or run the query again.
- **File is corrupted:** use a different format (CSV is most portable). If Excel fails, try CSV.

## Scenarios covered

- **BA-03:** Extract enrollment to file (CSV / Excel)
- **BA-06:** Export for external distribution (CSV pipe-delimited)
- **BA-07:** Export to share with non-Databricks users (Excel native format)
```

- [ ] **Step 4: Specify expected outcome assertion** (to verify at build time)

Build agent will:
1. Open the saved "Enrollment Export" query.
2. Run with default filters (no modification). Expected: ≥100 rows or up to 10k limit.
3. Download as CSV. Verify: file is valid, ≥100 rows, columns include student_name, course_title, grade, department.
4. Download as Excel. Verify: file opens in Excel, data is readable, columns are preserved.
5. Download as Pipe-Delimited. Verify: file opens in text editor, pipes (|) separate columns, no commas in field values cause corruption.
6. Modify the query: uncomment one filter (e.g., `d.name = 'Engineering'`). Run. Verify filtered result set is smaller (fewer departments). Download CSV again.

- [ ] **Step 5: Commit BA-03 docs**

```bash
git add src/businessanalyst/queries/enrollment_export.sql src/businessanalyst/README_BA03.md && \
git commit -m "feat(ba-03, ba-06, ba-07): enrollment export query + multi-format download walkthrough"
```

---

### Task 4: BA-D — Upload + join + light transform (no-code canvas) — Tracks: #26

**Purpose:** Enable a BA to upload a local Excel/CSV file (e.g., a budget spreadsheet), join it to platform enrollment data, rename columns, filter rows, and create a derived field — all via Lakeflow Designer no-code canvas (no SQL).

**Pre-built assets:**
- Sample upload file: `departments_budget_fy2025.csv` (columns: dept_id, dept_name, budget_amount, approved_date) in the volume.
- Lakeflow Designer pipeline template (canvas YAML): shows the drop steps for "Upload data", "Join to Enrollment", "Filter", "Rename columns", "Add computed column (Total Cost = budget × enrollment count)".
- Walkthrough showing the BA how to drag-drop each step.

**Files:**
- Create: `src/businessanalyst/sample_uploads/departments_budget_fy2025.csv`
- Create: `src/businessanalyst/designer_pipelines/budget_enrollment_join.designer.yaml` (pipeline canvas definition)
- Create: `src/businessanalyst/README_BA04.md` (analyst's walkthrough)

**Interfaces:**
- **Analyst action:** opens the Designer pipeline template → (if pre-built) runs it with the sample upload file, or (if interactive) manually uploads file, drags join/filter/rename steps on canvas, runs.
- **Expected outcome:** a new table `dept_budget_enrollment_summary` with enriched data (enrollments + budget + derived totals), ready for further analysis or export (BA-08).

- [ ] **Step 1: Create sample upload file** `src/businessanalyst/sample_uploads/departments_budget_fy2025.csv`:

```csv
dept_id,dept_name,budget_amount,approved_date
1,Engineering,2500000,2024-06-15
2,Business,1800000,2024-06-15
3,Liberal Arts,1200000,2024-06-15
4,Sciences,1500000,2024-06-15
...
(~40 rows matching Phase 0 departments)
```

> Note: build agent will populate all 40 departments from Phase 0. For this plan, the structure is enough.

- [ ] **Step 2: Write sample budget file to the uploads volume** (during Phase 3 build)

Build agent:
1. Generate the full CSV (all 40 departments from Phase 0 seed).
2. Upload to `/Volumes/princeton_poc_dev/landing_dev/uploads/departments_budget_fy2025.csv` via the Databricks Files UI or CLI.
3. Verify the file is readable from Designer.

- [ ] **Step 3: Design the Lakeflow Designer pipeline** `src/businessanalyst/designer_pipelines/budget_enrollment_join.designer.yaml`:

```yaml
# Lakeflow Designer Pipeline: Budget + Enrollment Join (BA-04, BA-05)
# No-code canvas with draggable steps for upload + join + filter + transform.

name: budget_enrollment_join
display_name: "Budget-Enriched Enrollment Summary"
description: "Upload department budgets, join to enrollment, filter, rename, and derive total cost. No SQL."

steps:
  - step_id: "1_upload"
    step_type: "add_data"
    display_name: "Upload Budget File"
    config:
      volume_path: "/Volumes/princeton_poc_dev/landing_dev/uploads"
      file_pattern: "departments_budget_*.csv"  # analyst selects from UI
      file_format: "csv"
      options:
        header: true
        infer_schema: true

  - step_id: "2_enrichment_join"
    step_type: "join"
    display_name: "Join to Enrollment"
    depends_on: ["1_upload"]
    config:
      left_input: "1_upload"
      left_key: "dept_id"
      right_table: "princeton_poc_dev.silver_dev.enrollment"
      right_join_key: "enrollment.dept_id"  # via course FK
      join_type: "inner"
      output_alias: "enrollment_with_budget"

  - step_id: "3_filter"
    step_type: "filter"
    display_name: "Filter to Active Students"
    depends_on: ["2_enrichment_join"]
    config:
      input: "enrollment_with_budget"
      filter_expression: "student.status = 'active'"
      output_alias: "active_enrollment_with_budget"

  - step_id: "4_rename"
    step_type: "rename_columns"
    display_name: "Rename Columns"
    depends_on: ["3_filter"]
    config:
      input: "active_enrollment_with_budget"
      renames:
        - old_name: "dept_name"
          new_name: "department"
        - old_name: "budget_amount"
          new_name: "total_budget"
        - old_name: "approved_date"
          new_name: "budget_approved"
      output_alias: "renamed"

  - step_id: "5_derive"
    step_type: "add_column"
    display_name: "Add Budget per Student"
    depends_on: ["4_rename"]
    config:
      input: "renamed"
      new_column_name: "budget_per_student"
      expression: "total_budget / COUNT(DISTINCT student_id) OVER (PARTITION BY department)"
      output_alias: "with_derived"

  - step_id: "6_sink"
    step_type: "write"
    display_name: "Save Result"
    depends_on: ["5_derive"]
    config:
      input: "with_derived"
      target_table: "princeton_poc_dev.silver_dev.dept_budget_enrollment_summary"
      mode: "overwrite"

# UI instructions for the BA
ui_instructions: |
  1. Open this pipeline in Lakeflow Designer.
  2. On the canvas, you see 6 steps already placed:
     - Step 1: Upload Budget File
     - Step 2: Join to Enrollment
     - Step 3: Filter to Active Students
     - Step 4: Rename Columns
     - Step 5: Add Budget per Student
     - Step 6: Save Result
  3. To customize:
     - Step 1: click it → browse to select your file
     - Step 3: click it → edit the filter expression (e.g., "status = 'graduated'" to exclude active)
     - Step 4: click it → adjust column renames
     - Step 5: click it → modify the budget formula
     - Step 6: click it → change the target table name if desired
  4. Click "Run" to execute the pipeline. No SQL editing needed.
  5. Result is saved to the target table. Use it in BA-E (save as reusable pipeline).
```

- [ ] **Step 4: Write the analyst's BA-04 & BA-05 walkthrough** `src/businessanalyst/README_BA04.md`:

```markdown
# BA-04, BA-05: Upload + Join + Light Transform (Lakeflow Designer No-Code Canvas)

## What you'll do

Upload a local budget spreadsheet, join it to enrollment data on the platform,
filter to active students, rename columns, and create a calculated field — all
via drag-and-drop canvas. No SQL.

## Prerequisites

- Access to Databricks Lakeflow Designer
- BA role with INSERT/UPDATE on `silver_dev` tables (to write the result)
- A CSV or Excel file with department budget data (columns: dept_id, dept_name, budget_amount, ...)

## Steps

### Using the Pre-Built Pipeline (Easiest)

1. In Databricks, open **Data Engineering** → **Workflows** (or **Lakeflow Designer**).
2. Find and open the pipeline: **"Budget-Enriched Enrollment Summary"**.
3. You see a canvas with 6 steps already wired:
   - Step 1: Upload Budget File
   - Step 2: Join to Enrollment
   - Step 3: Filter to Active Students
   - Step 4: Rename Columns
   - Step 5: Add Budget per Student
   - Step 6: Save Result

### Customizing the Pipeline

4. **Step 1 (Upload):** Click the step. A panel opens. Select your budget file from the Volume (or click "Browse" to upload a new file).
   - Expected file format: CSV or Excel, with columns: `dept_id`, `dept_name`, `budget_amount`.
5. **Step 3 (Filter):** Click the step. The filter is set to `student.status = 'active'`. If you want to include graduated students too, edit it to: `student.status IN ('active', 'graduated')`.
6. **Step 4 (Rename):** Click the step. Column renames are pre-configured. You can adjust (e.g., rename `total_budget` to `FY2025_Budget`).
7. **Step 5 (Derive):** Click the step. The formula calculates `budget_per_student = total_budget / count of unique students per department`. You can edit to a different formula (e.g., `total_budget / enrollment_count` if you have enrollment_count as a column).
8. **Step 6 (Save):** Click the step. Confirm the target table name (default: `dept_budget_enrollment_summary`). Click "Change" if you want a different name.

### Running the Pipeline

9. At the top of the canvas, click **Run**.
10. Databricks executes the pipeline end-to-end (no SQL — the steps compile to SQL behind the scenes).
11. In a few seconds, you see a "Success" message at the top (or error if something went wrong).
12. The result table is now in `princeton_poc_dev.silver_dev.dept_budget_enrollment_summary`.

### Verifying Results

13. Open a new SQL query:
    ```sql
    SELECT * FROM princeton_poc_dev.silver_dev.dept_budget_enrollment_summary LIMIT 10;
    ```
14. Expected columns:
    - `department`, `total_budget`, `budget_approved` (from the upload)
    - `enrollment_id`, `student_id`, ... (from enrollment join)
    - `budget_per_student` (derived calculated column)

### Variations (BA-05)

- **Different file:** instead of budget file, upload forecast data (enrollment_forecast.xlsx with columns: dept_id, forecasted_enrollment, forecast_date).
- **Different join:** click Step 2 → change the right table to `silver_dev.financial_aid` instead of enrollment.
- **Different filter:** adjust Step 3 to filter by term, department, or any column.

## If something doesn't work

- **File not found in Step 1:** the file hasn't been uploaded to the volume yet. Use the **Files** UI to upload your CSV/Excel to `/Volumes/princeton_poc_dev/landing_dev/uploads/`.
- **Join step fails:** ensure the join key (dept_id) exists in both the uploaded file and the enrollment table.
- **Result table error:** you may lack INSERT permission on `silver_dev`. Contact your admin to grant INSERT/UPDATE on the target schema.

## Expected outcome

A new table with enriched enrollment data. The table can now be exported (BA-03), saved as a reusable pipeline (BA-08), or used in further analysis.

## Scenarios covered

- **BA-04:** Upload + join + simple transform (rename, filter)
- **BA-05:** Upload different file type (Excel forecast) + alternate join path
```

- [ ] **Step 5: Specify expected outcome assertion** (to verify at build time)

Build agent will:
1. Create a sample budget CSV with all 40 departments (from Phase 0).
2. Upload to `/Volumes/princeton_poc_dev/landing_dev/uploads/departments_budget_fy2025.csv`.
3. Open Lakeflow Designer.
4. Create or load the pre-built `budget_enrollment_join` pipeline from YAML (or manually drag the steps on canvas).
5. Run the pipeline. Expected:
   - No SQL errors.
   - Result table created: `dept_budget_enrollment_summary`.
   - Row count: ≤ total active enrollments (filtered subset).
   - Columns: department, total_budget, budget_per_student, enrollment_id, student_id, etc.
   - budget_per_student is numeric (total_budget / distinct students).
6. Query the result:
   ```sql
   SELECT department, total_budget, budget_per_student, COUNT(*) enrollment_count
   FROM dept_budget_enrollment_summary
   GROUP BY department, total_budget, budget_per_student
   LIMIT 5;
   ```
   Expected: ≥5 departments, numeric columns, enrollment_count > 0 per department.

- [ ] **Step 6: Upload the sample file to the volume** (during Phase 3 build)

Build agent Python code (notebook):
```python
import pandas as pd
import random
random.seed(42)

# Generate 40 departments with budget
depts = [
    (i+1, f"Dept_{i+1}", random.randint(500000, 3000000), f"2024-06-15")
    for i in range(40)
]
df = pd.DataFrame(depts, columns=["dept_id", "dept_name", "budget_amount", "approved_date"])
df.to_csv("/Volumes/princeton_poc_dev/landing_dev/uploads/departments_budget_fy2025.csv", index=False)
print(f"Uploaded {len(df)} departments to landing volume.")
```

- [ ] **Step 7: Commit BA-04 & BA-05 docs**

```bash
git add src/businessanalyst/sample_uploads/departments_budget_fy2025.csv \
       src/businessanalyst/designer_pipelines/budget_enrollment_join.designer.yaml \
       src/businessanalyst/README_BA04.md && \
git commit -m "feat(ba-04, ba-05): sample budget file + Designer pipeline template (upload+join+transform canvas)"
```

---

### Task 5: BA-E — Save & reuse workflow (saved Designer pipeline) — Tracks: #27

**Purpose:** Enable a BA to take the result from Task 4 (budget-enriched enrollment), save the pipeline for reuse, and re-run it on demand (e.g., weekly or when a new budget file arrives) without rebuilding the canvas or writing code.

**Pre-built assets:**
- The pipeline from Task 4 is saved as a reusable DAB job resource.
- Optionally, a scheduled trigger (e.g., weekly at Monday 8 AM) can auto-run the pipeline if a new budget file lands in the upload volume.

**Files:**
- Modify: `resources/businessanalyst.designer.yml` (now populates the saved job)
- Create: `src/businessanalyst/README_BA08.md` (analyst's walkthrough)

**Interfaces:**
- **Analyst action:** in Designer, clicks **Save as Job** → job is created → can be triggered manually or scheduled. Next time a BA needs the same transform, they open the job and click **Run**.
- **Expected outcome:** analyst has a repeatable, no-code workflow. Different BAs or the same BA at different times can invoke it without rebuilding the canvas.

- [ ] **Step 1: Save the Designer pipeline as a DAB job resource** `resources/businessanalyst.designer.yml` (updated from Task 0):

```yaml
resources:
  jobs:
    ba_budget_enrollment_join:
      name: "[BA Workflow] Budget-Enriched Enrollment Join"
      description: "No-code pipeline: upload budget file, join to enrollment, filter, rename, derive. Reusable by BA."
      
      # The job wraps the Designer pipeline (compiled to SQL steps)
      tasks:
        - task_key: "budget_join_pipeline"
          notebook_task:
            # In practice, the Designer pipeline is exported as a notebook (auto-generated)
            # OR as SQL steps in a SQL job. For this plan, we reference the Designer
            # canvas definition (src/businessanalyst/designer_pipelines/budget_enrollment_join.designer.yaml)
            # which compiles to SQL at runtime.
            notebook_path: ../src/businessanalyst/jobs/budget_enrollment_join_runner.py
          # Parameters: allow the BA to customize file name, target table, etc.
          base_parameters:
            upload_file: "departments_budget_*.csv"
            target_table: "princeton_poc_dev.silver_dev.dept_budget_enrollment_summary"
      
      # Optional: schedule the job (e.g., weekly)
      # schedule:
      #   quartz_cron_expression: "0 0 8 ? * MON"  # Monday 8 AM PT
      #   timezone_id: "America/Los_Angeles"
      
      # Tags for categorization
      tags:
        business_analyst: "true"
        persona_ba: "true"
        phase_3: "true"
```

- [ ] **Step 2: Create the job runner notebook** `src/businessanalyst/jobs/budget_enrollment_join_runner.py`:

```python
# COMMAND ----------
# Budget-Enriched Enrollment Join Job Runner
# Compiled from Lakeflow Designer canvas (BA-08 reusable workflow).
# Parameters: upload_file, target_table

dbutils.widgets.text("upload_file", "departments_budget_fy2025.csv")
dbutils.widgets.text("target_table", "princeton_poc_dev.silver_dev.dept_budget_enrollment_summary")

upload_file = dbutils.widgets.get("upload_file")
target_table = dbutils.widgets.get("target_table")

# COMMAND ----------
# Step 1: Read uploaded budget file
df_budget = spark.read.option("header", "true").csv(
    f"/Volumes/princeton_poc_dev/landing_dev/uploads/{upload_file}"
)
print(f"Loaded {df_budget.count()} departments from {upload_file}")

# COMMAND ----------
# Step 2: Join to enrollment
df_enrollment = spark.table("princeton_poc_dev.silver_dev.enrollment")
df_student = spark.table("princeton_poc_dev.silver_dev.student")
df_course = spark.table("princeton_poc_dev.silver_dev.course")

df_joined = (df_enrollment
  .join(df_student, on="student_id")
  .join(df_course, on="course_id")
  .join(df_budget, on=(df_course.dept_id == df_budget.dept_id))
)

# COMMAND ----------
# Step 3: Filter to active students
from pyspark.sql import functions as F
df_filtered = df_joined.filter(F.col("status") == "active")

# COMMAND ----------
# Step 4: Rename columns
df_renamed = df_filtered.select(
  F.col("dept_name").alias("department"),
  F.col("budget_amount").alias("total_budget"),
  F.col("approved_date").alias("budget_approved"),
  "*"
)

# COMMAND ----------
# Step 5: Add derived column
df_with_derived = df_renamed.withColumn(
  "budget_per_student",
  F.col("total_budget") / F.count("*").over(F.Window.partitionBy("department"))
)

# COMMAND ----------
# Step 6: Write result
df_with_derived.write.mode("overwrite").saveAsTable(target_table)
print(f"Saved {df_with_derived.count()} rows to {target_table}")
```

- [ ] **Step 3: Write the analyst's BA-08 walkthrough** `src/businessanalyst/README_BA08.md`:

```markdown
# BA-08: Save & Reuse Self-Service Workflow (Saved Designer Pipeline)

## What you'll do

After running the budget-enrollment join pipeline (BA-04), you save it as a
reusable job. Next time you need the same workflow (or a colleague needs it),
you just click "Run" — no need to rebuild the canvas.

## Prerequisites

- Completed BA-04 (the budget-enrollment pipeline)
- Access to **Data Engineering** → **Workflows** in Databricks

## Steps

### Option 1: Save the Pipeline as a Job (Designer UI)

1. In **Lakeflow Designer**, open the **"Budget-Enriched Enrollment Summary"** pipeline.
2. At the top, click **Save as Job** (or **Job Settings**).
3. A dialog appears:
   - Job name: `[BA Workflow] Budget-Enriched Enrollment Join` (pre-filled)
   - Parameters: 
     - `upload_file`: default `departments_budget_*.csv`
     - `target_table`: default `princeton_poc_dev.silver_dev.dept_budget_enrollment_summary`
4. Click **Save Job**. The job is now registered in Databricks.

### Option 2: Run the Saved Job (Anytime)

5. In **Data Engineering** → **Workflows**, find your job: **"[BA Workflow] Budget-Enriched Enrollment Join"**.
6. Click the job name to open it.
7. You see the pipeline canvas again (same steps from BA-04).
8. Adjust parameters if needed (e.g., use a different budget file: `departments_budget_fy2026.csv`).
9. Click **Run** or **Run Now**. The job executes immediately.
10. You see a run log at the bottom. Wait for "SUCCEEDED" message.
11. Result is written to the target table (or your custom table name).

### Option 3: Schedule the Job (Weekly Auto-Run)

12. In the job settings, click **Schedule** or **Edit Job**.
13. Set the schedule:
    - Frequency: **Weekly**
    - Day: **Monday**
    - Time: **8:00 AM PT**
14. Save. The job now runs every Monday at 8 AM, automatically pulling the latest budget file from the uploads volume.

## Variations

- **Different file each week:** parameterize `upload_file` → the job reads whatever file matches the pattern (e.g., `departments_budget_*.csv` will pick up fy2025, fy2026, etc. as they're uploaded).
- **Different target table:** edit `target_table` parameter → results go to a new table (e.g., `budget_summary_v2`).
- **Pause the schedule:** in job settings, toggle **Scheduled** off. The job won't run until you re-enable it.

## Expected outcome

- The job is saved and visible in **Workflows**.
- You can trigger it manually at any time.
- If scheduled, it runs weekly and you never have to rebuild the pipeline.
- Different BAs can run the same job (no coding required).

## If something doesn't work

- **Job not saving:** ensure you have permissions to create jobs in your workspace. Contact your admin.
- **Job fails on run:** check the run log for errors (usually file not found or schema mismatch). Ensure the budget file exists in `/Volumes/princeton_poc_dev/landing_dev/uploads/`.
- **Scheduled job didn't run:** verify the schedule is enabled (toggle in job settings). Check the past runs in the job history.

## Scenarios covered

- **BA-08:** Save a configured workflow as a reusable, schedulable pipeline.
```

- [ ] **Step 4: Update the DAB Designer resource YAML** from placeholder (Task 0) to the actual job:

Edit `resources/businessanalyst.designer.yml`:

```yaml
resources:
  jobs:
    ba_budget_enrollment_join:
      name: "[BA Workflow] Budget-Enriched Enrollment Join"
      description: "No-code pipeline: upload budget file, join to enrollment, filter, rename, derive. Reusable by BA."
      tasks:
        - task_key: "budget_join_pipeline"
          notebook_task:
            notebook_path: ../src/businessanalyst/jobs/budget_enrollment_join_runner.py
          base_parameters:
            upload_file: "departments_budget_*.csv"
            target_table: "princeton_poc_dev.silver_dev.dept_budget_enrollment_summary"
      tags:
        business_analyst: "true"
        phase_3: "true"
```

- [ ] **Step 5: Specify expected outcome assertion** (to verify at build time)

Build agent will:
1. Deploy the DAB job resource (or create via Designer UI).
2. Verify the job appears in **Workflows** with the correct name.
3. Run the job manually (click **Run Now**). Expected:
   - No errors; log shows all steps completing.
   - Result table is populated with ≥100 rows.
4. Edit the job parameters (e.g., change target table to `dept_budget_summary_test`).
5. Run again. Expected: result lands in the new table.
6. (Optional) Schedule the job for the next day at a test time (e.g., 2 PM); wait 5 min; verify the job auto-ran in the history.

- [ ] **Step 6: Commit BA-08 docs**

```bash
git add src/businessanalyst/jobs/budget_enrollment_join_runner.py \
       src/businessanalyst/README_BA08.md \
       resources/businessanalyst.designer.yml && \
git commit -m "feat(ba-08): saved Designer pipeline as reusable, schedulable job"
```

---

### Task 6: Wire BA objects into DAB + final runbook entries

**Files:**
- Modify: `resources/businessanalyst.genie.yml` (populate with actual Genie space definitions)
- Modify: `resources/businessanalyst.dashboard.yml` (populate with dashboard definitions)
- Modify: `docs/runbook/README.md` (append BA phase entries)

**Interfaces:**
- Produces: DAB bundle includes all BA objects; operator can deploy once and all BA scenarios are available.

- [ ] **Step 1: Consolidate all BA resources into the bundle**

Update `resources/businessanalyst.genie.yml`:

```yaml
resources:
  genie_spaces:
    enrollment_explorer:
      name: "Enrollment Explorer"
      description: "No-code exploration of enrollment data by department, term, and student status."
      catalog_name: ${var.catalog}
      schema_names:
        - "silver_dev"
      # Genie learns the schema and offers NL queries
```

Update `resources/businessanalyst.dashboard.yml`:

```yaml
resources:
  dashboards:
    enrollment_by_department_weekly:
      display_name: "Enrollment by Department (Weekly Report)"
      description: "Enrollment summary by department and term. Subscribe to receive weekly updates."
      # Dashboard JSON (compiled from Lakeview) stored separately or inline
      # For DAB, we reference the .lvdash.json file:
      source_code_path: ../src/businessanalyst/dashboards/enrollment_by_department.lvdash.json
```

- [ ] **Step 2: Create the runbook BA section** (append to `docs/runbook/README.md`):

```markdown
---

## Phase 3: Business Analyst (No-Code / Low-Code)

All BA scenarios are demonstrated via pre-built Genie Spaces, AI/BI Dashboards, and
Lakeflow Designer pipelines. No SQL. No code. Just point-and-click and NL prompts.

### BA-01: No-Code Browse + Filter + Preview (Catalog Explorer + Genie)

**Tracks:** #23

**Pre-built objects:**
- Genie Space: `Enrollment Explorer`
- Catalog Explorer: built-in Databricks UI (no build artifact)

**Demo script:**

```
1. Open Databricks → Data → Genie Spaces.
2. Open "Enrollment Explorer".
3. Click the prompt: "Show me enrollments by department and term".
4. Edit: type "Show me enrollments by department and term for Fall 2024".
5. Click "Ask".
6. Genie generates SQL and returns a table of enrollments grouped by department, term, season.
7. Click another prompt: "How many students are enrolled per faculty member in [dept_name]?"
8. Edit: "How many students are enrolled per faculty member in Engineering?"
9. Click "Ask".
10. Result: table of faculty with enrollment counts per faculty member.

Also demonstrate Catalog Explorer:
11. Open Data → Catalog → princeton_poc_dev → silver_dev → enrollment table.
12. Click "Preview". Show schema and first 100 rows.
13. Point out that row-level security (if configured by Phase 4 PA) restricts what rows this user sees.
```

**Expected outcome:** analyst has navigated the dataset via NL (Genie) and schema browsing (Catalog), without writing SQL.

---

### BA-02: Scheduled Report & Subscription

**Tracks:** #24

**Pre-built objects:**
- AI/BI Dashboard: `Enrollment by Department (Weekly Report)`
- SQL dataset query (tested; embedded in dashboard)

**Demo script:**

```
1. Open Databricks → Dashboards → "Enrollment by Department (Weekly Report)".
2. See two charts: bar chart (enrollment by department), line chart (enrollment trend over terms).
3. Optionally filter: use the "Department" dropdown → select "Engineering". Chart updates.
4. Click "Subscribe" (top-right).
5. Enter your email address.
6. Select frequency: "Weekly" (Monday 8 AM PT).
7. Select format: "CSV".
8. Click "Save Subscription".
9. Confirm: "Subscription saved. You will receive results weekly."

(Optional: manually export right now instead of subscribing)
10. Click "Export" (top-right).
11. Choose format: "CSV" → "Download".
12. File downloads to your laptop.
```

**Expected outcome:** analyst has subscribed to a recurring report. A week later, they receive a CSV email. Or they can export immediately.

---

### BA-03, BA-06, BA-07: Ad-Hoc Extract (CSV / Excel / Pipe)

**Tracks:** #25

**Pre-built objects:**
- SQL saved query: `Enrollment Export`

**Demo script:**

```
1. Open Databricks → SQL → Queries → "Enrollment Export".
2. You see a SELECT query with filter comments:
   WHERE (TRUE) -- adjust: (d.name = 'Engineering') for dept filter
   AND (TRUE) -- adjust: (t.term_id = 3) for term filter
3. Edit: change first TRUE to (d.name = 'Engineering').
4. Click "Run".
5. Results show 10,000 rows (limit) of enrollments from Engineering, all terms.
6. At the top-right of the results, click the three-dot menu ⋯ → "Download Results".
7. Select "CSV" → "Download".
8. CSV file lands in Downloads folder: enrollment_export_<date>.csv.
9. Open in Excel. Verify columns: enrollment_id, student_id, student_name, course_id, etc.

Repeat with different formats:
10. Re-run the query.
11. Download Results → select "Excel (.xlsx)" → Download.
12. Open .xlsx in Excel (native format, preserves formatting).
13. Repeat → select "TSV (Pipe-Delimited)" → Download.
14. Open in text editor; verify pipes (|) separate columns.
```

**Expected outcome:** analyst has three export files (CSV, Excel, Pipe) ready for distribution or ingestion into other systems.

---

### BA-04, BA-05: Upload + Join + Transform (Designer Canvas)

**Tracks:** #26

**Pre-built objects:**
- Sample upload file: `departments_budget_fy2025.csv`
- Lakeflow Designer pipeline (canvas): `Budget-Enriched Enrollment Join`

**Demo script:**

```
1. Prepare: ensure departments_budget_fy2025.csv is in /Volumes/princeton_poc_dev/landing_dev/uploads/.
2. Open Databricks → Data Engineering → Lakeflow Designer (or Workflows).
3. Create a new pipeline or open the pre-built: "Budget-Enriched Enrollment Join".
4. You see a canvas with 6 steps:
   - Step 1: Upload Budget File
   - Step 2: Join to Enrollment
   - Step 3: Filter to Active Students
   - Step 4: Rename Columns
   - Step 5: Add Budget per Student
   - Step 6: Save Result
5. (If pre-built) these steps are already wired. Click "Run".
6. (If manual) drag each step onto the canvas:
   - Add Data (step 1) → select CSV from volume
   - Join (step 2) → join to silver_dev.enrollment on dept_id
   - Filter (step 3) → student.status = 'active'
   - Select Columns + Rename (step 4) → rename budget_amount → total_budget
   - Add Column (step 5) → formula: budget_per_student = total_budget / count(distinct student_id)
   - Write (step 6) → target table: dept_budget_enrollment_summary
7. Click "Run". Pipeline executes. Success message.
8. Query the result:
   SELECT department, total_budget, budget_per_student, COUNT(*) cnt
   FROM dept_budget_enrollment_summary
   GROUP BY 1, 2, 3
   LIMIT 10;
9. Expected: departments with budget and budget-per-student ratios.

For BA-05, repeat with a different file (enrollment_forecast.xlsx) and a different join target (financial_aid).
```

**Expected outcome:** analyst has created an enriched dataset (budget + enrollment + derived field) via no-code canvas. No SQL written.

---

### BA-08: Save & Reuse Workflow

**Tracks:** #27

**Pre-built objects:**
- Saved Lakeflow Designer job: `[BA Workflow] Budget-Enriched Enrollment Join`

**Demo script:**

```
1. From BA-04 demo, you have the Budget-Enrollment pipeline running.
2. Click "Save as Job" (at the top of the canvas).
3. Dialog: Job name (pre-filled), parameters (upload_file, target_table).
4. Click "Save Job".
5. Now open Data Engineering → Workflows.
6. Find your job: "[BA Workflow] Budget-Enriched Enrollment Join".
7. Click it.
8. You see the canvas again (same steps).
9. Scroll down to "Parameters".
10. Edit upload_file: "departments_budget_fy2026.csv" (simulate a new file arrival).
11. Click "Run Now". Job runs with the new parameter.
12. Success message. Result goes to the target table.

(Optional: schedule)
13. Click "Job Settings" or "Edit Job".
14. Scroll to "Schedule".
15. Toggle "Schedule On".
16. Set: Weekly, Monday, 8 AM PT.
17. Save.
18. Job now auto-runs every Monday at 8 AM. Check the "Runs" tab to see past executions.
```

**Expected outcome:** analyst has a reusable, schedulable workflow. Different BAs (or the same BA later) can invoke it without rebuilding the canvas. This is the self-service win condition.

---

## End-to-End BA Verification

To confirm all BA scenarios work together:

1. **Discover** (BA-01): Use Genie to ask "Show me enrollments by Engineering and Fall 2024" → get results.
2. **Export** (BA-03): Run the Enrollment Export query → download as Excel.
3. **Upload & Transform** (BA-04): Upload a budget file → run the Designer pipeline → get enriched table.
4. **Subscribe** (BA-02): Subscribe to the enrollment dashboard → set email + weekly.
5. **Reuse** (BA-08): Save the pipeline as a job → schedule it for Monday 8 AM → verify it ran.

All steps are point-and-click / NL-driven. No SQL. No code.

```

- [ ] **Step 3: Validate DAB with all BA resources**

Run:
```bash
databricks bundle validate --strict -t dev --profile <PROFILE>
```

Expected: all resources resolve (genie_spaces, dashboards, jobs, volumes).

- [ ] **Step 4: Commit the final runbook + resource definitions**

```bash
git add resources/businessanalyst*.yml docs/runbook/README.md && \
git commit -m "feat(ba-phase): complete BA objects (Genie + dashboards + Designer) + runbook entries"
```

---

## Deliverable: runbook summary (BA scenarios 01–08)

- [ ] **Final verification:** `docs/runbook/README.md` includes all five BA tasks with expected outcomes, GitHub issue links, and demo scripts.

Entries link to issue tracker:
- BA-01 → #23
- BA-02 → #24
- BA-03, BA-06, BA-07 → #25
- BA-04, BA-05 → #26
- BA-08 → #27

---

## Self-Review

**Spec coverage (Phase 3 scope only):**
- Design §5 Persona 3 table: BA-01…08 mapped to five objects ✓
- §5 BA-01 (browse+filter+preview) → Task 1 (Genie + Catalog Explorer) ✓
- §5 BA-02 (scheduled report) → Task 2 (AI/BI dashboard subscription) ✓
- §5 BA-03, 06, 07 (ad-hoc extract) → Task 3 (SQL query export) ✓
- §5 BA-04, 05 (upload+join+transform) → Task 4 (Designer canvas + sample file) ✓
- §5 BA-08 (save+reuse) → Task 5 (saved job) ✓
- No-code/low-code mandate (§2 Persona 3 = limited/no SQL) → all tasks use UI/NL, no code written by analyst ✓
- Pre-built objects for fallback (§3, Guiding principle 3) → Genie space, dashboard, Designer pipeline, sample uploads all in bundle ✓
- Runbook entries (§7) → Task 6 appends demo scripts for each scenario ✓

**Placeholder scan:** `<PROFILE>` and GitHub issue numbers (#23–27) are operator-supplied, documented in steps. File paths (`/Volumes/princeton_poc_dev/landing_dev/uploads/`) are constant per Phase 0 layout. `departments_budget_fy2025.csv` is a concrete fixture. Query SQL (enrollment_export.sql, enrollment_by_department.sql) are fully specified, marked "test at build time". No TBD / TODO.

**Type consistency:**
- Catalog: `princeton_poc_dev` throughout (from Phase 0).
- Schemas: `silver_dev`, `gold_dev` (read-only for BA).
- Volume: `/Volumes/princeton_poc_dev/landing_dev/uploads/` (BA upload staging).
- Table names: `enrollment`, `department`, `term`, `student`, `course`, `financial_aid` (from Phase 0); `dept_budget_enrollment_summary` (derived, Task 4).
- Genie space name: `enrollment_explorer` (consistent).
- Dashboard name: `enrollment_by_department_weekly` (consistent).
- Job name: `[BA Workflow] Budget-Enriched Enrollment Join` (consistent).
- Parameters: `upload_file`, `target_table` (consistent across Designer tasks).

**No real-time test during plan phase:** all datasets/queries are specified with expected row counts and schema. At build time, Phase 3 build agent will execute end-to-end (Genie ask, dashboard query run, Designer pipeline execute). No test URLs or credentials here; operator supplies at build.

**Open risks:** None flagged beyond normal build execution. All surfaces (Genie, AI/BI, Designer, Catalog Explorer) are standard Databricks GA features; no preview/parked components.

