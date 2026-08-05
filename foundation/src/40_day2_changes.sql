-- ============================================================================
-- DAY-2 CHANGE SCRIPT  (standalone — run manually during a demo, NOT auto-run)
-- ============================================================================
-- Drives the change-capture / SCD / schema-drift scenarios from ONE small script:
--   SE-03  CDC (new/changed/deleted)     SE-21 SCD Type 1     SE-22 SCD Type 2
--   SE-23  change capture                SE-41 schema drift
--
-- The known counts below ARE the oracle: after running, the CDF assert should show
-- exactly 10 inserts, 20 updates, 5 deletes, plus the added column.
--
-- RUNBOOK: this script is called out step-by-step in docs/runbook/README.md.
--
-- CATALOG: this script runs manually (not via the bundle), so set the catalog for the
-- session to match the target you deployed to:
--   princeton_poc_dev (dev) | princeton_poc_test (qa) | princeton_poc (prod)
-- Then USE it so the unqualified table names below resolve.
-- ============================================================================
USE CATALOG princeton_poc_dev;   -- <-- change to princeton_poc_test / princeton_poc as needed

-- Step 0 (one-time): enable Change Data Feed on the SCD target.
ALTER TABLE silver.student
  SET TBLPROPERTIES (delta.enableChangeDataFeed = true);

-- Step 1 (capture the floor BEFORE the changes below — note this version number):
--   DESCRIBE HISTORY silver.student LIMIT 1;

-- ---------------------------------------------------------------------------
-- INSERTS: 10 net-new students (offset IDs so they don't collide)
-- ---------------------------------------------------------------------------
INSERT INTO silver.student
  (student_id, first_name, last_name, ssn, dob, dept_id, status, email)
SELECT student_id + 100000, first_name, last_name, ssn, dob, dept_id, 'active', email
FROM silver.student
ORDER BY student_id
LIMIT 10;

-- ---------------------------------------------------------------------------
-- UPDATES: 20 status changes active -> graduated (SCD T1 overwrite / T2 trigger)
-- ---------------------------------------------------------------------------
UPDATE silver.student
SET status = 'graduated'
WHERE student_id IN (
  SELECT student_id FROM silver.student
  WHERE status = 'active' AND student_id < 100000
  ORDER BY student_id LIMIT 20
);

-- ---------------------------------------------------------------------------
-- DELETES: 5 students removed at source (hard-delete detection SE-03)
-- ---------------------------------------------------------------------------
DELETE FROM silver.student
WHERE student_id IN (
  SELECT student_id FROM silver.student
  WHERE student_id < 100000
  ORDER BY student_id DESC LIMIT 5
);

-- ---------------------------------------------------------------------------
-- SCHEMA DRIFT: add a column (SE-41). Rename / type-change are the harder variants
-- to demo live if desired.
-- ---------------------------------------------------------------------------
ALTER TABLE silver.student ADD COLUMN citizenship STRING;

-- ---------------------------------------------------------------------------
-- Step 2 (assert via CDF — substitute the version noted in Step 1):
--   SELECT _change_type, count(*)
--   FROM table_changes('silver.student', <pre_change_version>)
--   GROUP BY _change_type;
-- Expect: insert=10, update_preimage=20, update_postimage=20, delete=5
-- ---------------------------------------------------------------------------
