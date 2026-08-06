-- BA-03 / BA-06 / BA-07 — Enrollment Export (ad-hoc extract to CSV / Excel / pipe-delimited)
--
-- Pre-built saved query for the Business Analyst. Run it in the SQL editor, then use
-- Download Results → CSV / Excel / TSV. No SQL knowledge needed beyond (optionally) editing
-- the two filter lines. Verified against silver_dev on the dev warehouse.
--
-- To filter: replace a `(TRUE)` below with a real condition, e.g.
--   (d.name = 'Johnson Department')      -- one department
--   (t.year = 2025 AND t.season = 'Fall') -- one term
-- Leave as (TRUE) for no filter on that dimension.

SELECT
  e.enrollment_id,
  s.student_id,
  concat(s.first_name, ' ', s.last_name) AS student_name,
  c.course_id,
  c.title       AS course_title,
  t.term_id,
  t.year,
  t.season,
  e.grade,
  e.gpa_points,
  d.name        AS department
FROM princeton_poc_dev.silver_dev.enrollment e
  JOIN princeton_poc_dev.silver_dev.student s    ON e.student_id = s.student_id
  JOIN princeton_poc_dev.silver_dev.course c     ON e.course_id  = c.course_id
  JOIN princeton_poc_dev.silver_dev.term t       ON e.term_id    = t.term_id
  JOIN princeton_poc_dev.silver_dev.department d ON c.dept_id     = d.dept_id
WHERE
  (TRUE)   -- department filter — e.g. (d.name = 'Johnson Department')
  AND (TRUE)   -- term filter — e.g. (t.year = 2025 AND t.season = 'Fall')
ORDER BY t.year DESC, e.enrollment_id
LIMIT 10000;   -- guardrail for interactive download; raise/remove for a full extract
