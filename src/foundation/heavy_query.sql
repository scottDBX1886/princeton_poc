-- Reusable "heavy" analytical query — the compute load for PA-13..18 and DS-05.
-- Deterministic against a fixed-seed enrollment_history so run-time/cost comparisons
-- are repeatable (PA-19..25). Big scan + join + window + aggregate.
SELECT
    d.division,
    eh.dept_id,
    eh.term_id,
    count(*)                                                          AS enrollments,
    avg(eh.gpa_points)                                               AS avg_gpa,
    count(DISTINCT eh.student_id)                                    AS distinct_students,
    rank() OVER (PARTITION BY eh.term_id ORDER BY count(*) DESC)     AS dept_rank_in_term
FROM princeton_poc.gold.enrollment_history eh
JOIN princeton_poc.silver.department d
    ON eh.dept_id = d.dept_id
WHERE eh.gpa_points IS NOT NULL
GROUP BY d.division, eh.dept_id, eh.term_id
ORDER BY eh.term_id, dept_rank_in_term;
