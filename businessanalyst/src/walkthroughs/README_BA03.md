# BA-03 / BA-06 / BA-07 — Ad-hoc extract to CSV / Excel / pipe (Designer + Genie agent)

**Persona:** Business Analyst (no SQL). Start from an **existing** platform object, describe the
extract to the Lakeflow Designer Genie agent, run it, and download in three formats.

## Primary path — Lakeflow Designer + Genie agent

1. Open **Lakeflow Designer** → **New** → **Add data** → pick the existing
   `princeton_poc_dev.silver_dev.enrollment` table (nothing to upload — it's the shared foundation fact).
2. Open the Designer **Genie agent** panel and paste (edit the department in plain English):
   ```text
   From the enrollment table, join to student, course, term, and department so each row shows
   student name, course title, term year and season, grade, gpa_points, and department name.
   Filter to the Johnson Department. Sort by year descending. This is for an ad-hoc extract I'll
   download as CSV/Excel.
   ```
3. The agent builds the join + filter flow on the canvas. **Run** it.
4. On the result grid, **Download** → **CSV** (BA-03) / **Excel** (BA-06) / **pipe-delimited / TSV** (BA-07).

> The Genie agent knows the join path from the space instructions, but the prompt states the intent
> plainly. `enrollment` has no `dept_id` — a course's department is `course.dept_id` — so "join to
> ... department" resolves through `course`.

## Fallback — pre-built saved query (if the live NL build stalls)

Saved query `businessanalyst/src/queries/enrollment_export.sql` produces the identical extract:
1. SQL Editor → open/paste the query → optionally set a filter, e.g. `(d.name = 'Johnson Department')`.
2. **Run** → **Download Results** → CSV / Excel / TSV-pipe. Verified against live data.

## Expected outcome

A filtered, human-readable extract with columns `enrollment_id, student_id, student_name,
course_id, course_title, term_id, year, season, grade, gpa_points, department`. The
Johnson-Department filter returns a smaller set (verified). All three download formats work.

## Notes

- **Read-only & concurrent-safe** — a query over the shared foundation.
- **Big export?** raise/remove the query's 10k `LIMIT`, or subscribe to the BA-02 dashboard's CSV.
