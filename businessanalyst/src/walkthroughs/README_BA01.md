# BA-01 — No-code browse, filter, preview (Genie + Catalog Explorer)

**Persona:** Business Analyst (no SQL). **Two no-code paths** to discover the enrollment data.

## Path 1 — Genie (natural language)

1. Databricks → **Genie** → open **"Princeton Enrollment Explorer"**.
2. Click a starter question, e.g. **"Show me enrollment counts by department"**, or type your own.
3. Genie generates + runs the SQL and returns a table. **You wrote no SQL.**
4. Refine in plain English: *"…for Fall 2024 only"* or *"…just the top 10 departments"* → Ask again.

**Try these (all verified to return data):**
- "How many active vs graduated vs withdrawn students are there by department?"
- "What is the average GPA by department for Fall terms?"
- "How many students does each faculty member teach?"

## Path 2 — Catalog Explorer (browse + preview)

1. Databricks → **Catalog** → `princeton_poc_dev` → `silver_dev` → **`enrollment`**.
2. **Overview** tab shows the schema (enrollment_id, student_id, course_id, term_id, grade, gpa_points) and row count.
3. **Sample Data** tab previews the first rows — no query needed.
4. Browse the dimension tables the same way: `department`, `term`, `student`, `course`, `faculty`.
5. If Platform-Admin row-level security (Persona 4) is applied, the preview automatically shows only your authorized rows.

## Expected outcome

You've explored the dataset two ways — conversationally (Genie) and by browsing (Catalog Explorer) — without writing SQL. Genie returns grouped enrollment summaries; Catalog Explorer confirms the schema and sample rows.

## Notes / troubleshooting

- **Shared & read-only:** this Genie space reads the shared foundation, so the whole group can use it at once — nobody's questions affect anyone else.
- **Deployed by the bundle (not hand-created):** BA-01 is a real DAB `genie_spaces` resource —
  `businessanalyst/resources/ba_genie.genie_space.yml` + the serialized body
  `businessanalyst/src/genie/enrollment_explorer.geniespace.json`. It's created/updated on
  `databricks bundle deploy`, so it versions and promotes like every other object. Open it via
  `databricks bundle summary -t dev --profile dbx_shared_demo | grep -A2 ba_enrollment_explorer`.
- **Join gotcha (encoded in the space instructions):** `enrollment` has no `dept_id` — a *course's*
  department is `course.dept_id`, a *student's* major is `student.dept_id`. The instructions tell
  Genie this so it attributes enrollments correctly.
- **Gotcha for anyone editing the serialized JSON:** `data_sources.tables` **must be sorted by
  identifier** or the deploy fails with `INVALID_PARAMETER_VALUE`.
