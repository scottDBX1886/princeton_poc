# BA-03 / BA-06 / BA-07 — Ad-hoc extract to CSV / Excel / pipe-delimited

**Persona:** Business Analyst. Pull a slice of enrollment data and download it as a file for
colleagues or other systems — three formats, no code.

## Pre-built object

Saved query **`businessanalyst/src/queries/enrollment_export.sql`** — joins
enrollment → student → course → term → department into one flat, human-readable result
(student name, course title, term, grade, GPA, department). Verified live.

## Steps

1. Databricks → **SQL Editor** → paste (or open the saved) **Enrollment Export** query.
2. *(Optional)* filter: replace a `(TRUE)` in the `WHERE` with a real condition —
   e.g. `(d.name = 'Johnson Department')` or `(t.year = 2025 AND t.season = 'Fall')`. No filter = leave `(TRUE)`.
3. **Run.** Results appear (capped at 10,000 rows for an interactive download; raise the `LIMIT` for a full extract).
4. Above the results grid, click **⋯ / Download** and pick the format:
   - **CSV** → `BA-03` (comma-separated, opens in Excel)
   - **Excel (.xlsx)** → `BA-06` (native workbook)
   - **TSV / pipe** → `BA-07` (delimited for external distribution)
5. The file lands in your Downloads folder.

## Expected outcome

- Unfiltered: up to 10,000 rows with columns `enrollment_id, student_id, student_name,
  course_id, course_title, term_id, year, season, grade, gpa_points, department`.
- With `(d.name = 'Johnson Department')`: a smaller, single-department extract (verified to return rows).
- Each of CSV / Excel / pipe downloads cleanly.

## Notes / troubleshooting

- **Read-only** — a `SELECT`, safe to run concurrently by the whole group.
- **Filter is valid SQL** — quote string values (`'Johnson Department'`, not `Johnson Department`).
- **Big export?** Raise or remove the `LIMIT`; for very large extracts, subscribe to the BA-02
  dashboard's CSV instead, or write to a Volume.
