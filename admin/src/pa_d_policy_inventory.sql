-- =====================================================================================
-- PA-D — Policy inventory & pre-rollout testing (PA-11, PA-12)
--
-- Two scenarios, both answerable in SQL rather than by clicking through a console:
--   PA-11  test a policy BEFORE rollout — the Oracle "faux user" equivalent
--   PA-12  a catalog of every active mask and row filter in the system
--
-- Substitute <catalog> and <suffix> for the target, e.g. princeton_poc_dev and _dev.
-- Prerequisite: PA-B and PA-C policies applied (this inventories what they created).
-- =====================================================================================


-- =====================================================================================
-- PA-12 — POLICY INVENTORY
--
-- Unity Catalog exposes two purpose-built views. These are the answer to "prove you know
-- every place sensitive data is protected" — no DESCRIBE-per-table loop, no parsing
-- output, no chance of missing a table nobody remembered.
--
-- This matters more than it first sounds: the usual failure in a governed estate is not a
-- wrong policy, it is an UNPROTECTED table nobody inventoried. Section 3 below covers that.
-- =====================================================================================

-- Every column mask in the catalog: which table, which column, which function.
SELECT table_schema,
       table_name,
       column_name,
       mask_name,
       using_columns          -- extra columns passed to the mask function, if any
FROM <catalog>.information_schema.column_masks
ORDER BY table_schema, table_name, column_name;

-- Every row filter: which table, which function, and the columns feeding it.
SELECT table_schema,
       table_name,
       filter_name,
       target_columns         -- the ON (...) list — the filter function's arguments
FROM <catalog>.information_schema.row_filters
ORDER BY table_schema, table_name;

-- Expected for this POC: 4 masks (student.ssn, student.dob, faculty.ssn,
-- financial_aid.amount) and 2 row filters (student, faculty), all in admin_demo and none
-- anywhere else. Any row outside admin_demo means a policy has leaked onto the shared
-- foundation, which would change what all ~20 session participants see.


-- =====================================================================================
-- 2. THE POLICY FUNCTIONS THEMSELVES
--
-- An inventory of WHERE policies are attached is half the picture. This is WHAT they do —
-- the function definitions, so a reviewer can read the branch logic without opening a
-- notebook.
-- =====================================================================================

SELECT routine_name,
       data_type              AS returns,
       routine_definition     AS logic,
       comment
FROM <catalog>.information_schema.routines
WHERE routine_schema = 'admin_demo'
ORDER BY routine_name;

-- Who may use the policy functions. A principal who can REPLACE a mask function can
-- rewrite the policy, so EXECUTE and ownership here are as sensitive as the table grants.
SELECT grantee, routine_name, privilege_type
FROM <catalog>.information_schema.routine_privileges
WHERE routine_schema = 'admin_demo'
ORDER BY grantee, routine_name;


-- =====================================================================================
-- 3. COVERAGE GAP CHECK — the query an auditor actually wants
--
-- Not "list the policies" but "list the sensitive columns with NO policy." Inventory tells
-- you what is protected; this tells you what is exposed.
-- =====================================================================================

SELECT c.table_schema,
       c.table_name,
       c.column_name,
       c.data_type,
       CASE WHEN m.mask_name IS NULL THEN 'UNPROTECTED' ELSE m.mask_name END AS mask_status
FROM <catalog>.information_schema.columns c
LEFT JOIN <catalog>.information_schema.column_masks m
       ON  c.table_schema = m.table_schema
       AND c.table_name   = m.table_name
       AND c.column_name  = m.column_name
WHERE c.table_schema IN ('admin_demo', 'silver<suffix>')
  AND (lower(c.column_name) LIKE '%ssn%'
    OR lower(c.column_name) LIKE '%dob%'
    OR lower(c.column_name) LIKE '%amount%'
    OR lower(c.column_name) LIKE '%email%')
ORDER BY mask_status, c.table_schema, c.table_name, c.column_name;

-- Reading this honestly: the silver<suffix> rows SHOULD come back UNPROTECTED. The shared
-- foundation deliberately carries no policies (spec 3.1) — PA scenarios operate on the
-- admin_demo copies so masking never changes what the other personas read. The check earns
-- its place because in a real deployment those same rows would be the finding.


-- =====================================================================================
-- PA-11 — PRE-ROLLOUT POLICY TESTING
--
-- The Oracle "faux user" question: before this goes live, what will each role actually
-- see?
--
-- There is no impersonation FUNCTION: simulate_principal(), set_session_user() and
-- impersonate() all return UNRESOLVED_ROUTINE (verified). A policy is evaluated as the
-- caller, so you cannot self-test another identity by calling something.
--
-- But Databricks does support ASSUMING A ROLE -- workspace-name menu -> pick a role -- and
-- that IS the faux-user mechanism. While a role is assumed it becomes the active SQL
-- identity, and Unity Catalog evaluates grants, row filters and column masks against it.
-- Verified in this workspace: as `account users`, session_user() returns 'account users'
-- and is_member('admins') is false.
--
-- Two mechanisms, in increasing strength. Section 4a proves the branch LOGIC in one
-- session; 4b proves UC ENFORCES it, and needs no colleague and no service principal.
-- =====================================================================================

-- ---------------------------------------------------------------------------------------
-- 4a. Evaluate the policy expression per role, in one query
--
-- Create a parameterised twin of the production mask with the role as an argument rather
-- than an is_member() call. Same branch logic, testable for every role at once. This is a
-- TEST artifact — it is never attached to a table.
-- ---------------------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION <catalog>.admin_demo.test_mask_ssn_as(ssn STRING, role STRING)
RETURNS STRING
COMMENT 'PA-11 TEST HARNESS ONLY — mirrors mask_ssn with the role parameterised. Never SET as a mask.'
RETURN CASE
    WHEN role = 'admin'   THEN ssn
    WHEN role = 'faculty' THEN concat('***-**-', right(ssn, 4))
    ELSE NULL
END;

-- All three treatments of a real value, side by side. Run this BEFORE attaching the mask.
SELECT s.ssn                                                                AS true_value,
       <catalog>.admin_demo.test_mask_ssn_as(s.ssn, 'admin')                AS as_admin,
       <catalog>.admin_demo.test_mask_ssn_as(s.ssn, 'faculty')              AS as_faculty,
       <catalog>.admin_demo.test_mask_ssn_as(s.ssn, 'student')              AS as_student
FROM (SELECT ssn FROM <catalog>.silver<suffix>.student ORDER BY student_id LIMIT 3) s;

-- Expected: full value for admin; ***-**-NNNN for faculty; NULL for student. If as_admin
-- is not the true value the policy is over-broad; if as_student is anything other than
-- NULL, PA-08's full restriction is not being applied.

-- Row-filter equivalent — how many rows each identity would keep.
SELECT 'admin (unrestricted)' AS acting_as,
       count(*)               AS rows_visible
FROM <catalog>.silver<suffix>.student
UNION ALL
SELECT 'mapped non-admin', count(*)
FROM <catalog>.silver<suffix>.student
WHERE dept_id IN (SELECT dept_id FROM <catalog>.admin_demo.department_access
                  WHERE principal = current_user())
UNION ALL
SELECT 'unmapped principal', count(*)
FROM <catalog>.silver<suffix>.student
WHERE dept_id IN (SELECT dept_id FROM <catalog>.admin_demo.department_access
                  WHERE principal = 'nobody@example.invalid');

-- Expected: all rows / a strict subset / zero. The third row is the important one — deny
-- by default, not "see everything if unmapped."

-- ---------------------------------------------------------------------------------------
-- 4b. Assume the role and re-run (the enforcement test)
--
-- 4a proves the branch logic; it does not prove UC enforces it -- those queries ran as you,
-- with the identity passed in as a string. The real test is an identity switch:
--
--   1. Workspace-name menu (top right) -> hover the workspace -> pick `account users`
--   2. Re-run the query below, and re-run pa_b_column_masking / pa_c_row_filters
--   3. Switch back the same way
--
-- This is safe to do live: it changes nothing about the data or the policies, only which
-- identity is asking.
-- ---------------------------------------------------------------------------------------

-- Acting as `account users`, run:
SELECT student_id, ssn, dob FROM <catalog>.admin_demo.student LIMIT 5;
-- Expect: ssn NULL, dob NULL (PA-08 full restriction), and only the departments mapped to
-- 'account users' in admin_demo.department_access (PA-09/PA-10).
--
-- Then confirm the identity actually changed -- if session_user() still returns your email,
-- the role switch did not take effect and the result above proves nothing:
SELECT session_user() AS acting_as, is_member('admins') AS is_admin;
-- Expect: 'account users', false.

-- Then confirm the read appears in the audit trail with their identity:
SELECT event_time,
       created_by             AS who,
       source_table_full_name AS table_read
FROM system.access.table_lineage
WHERE event_date >= current_date() - INTERVAL 1 DAY
  AND source_table_full_name = '<catalog>.admin_demo.student'
ORDER BY event_time DESC
LIMIT 20;


-- =====================================================================================
-- 5. ROLLOUT READINESS — run these four before going live
-- =====================================================================================

-- (1) Every intended policy is attached. Expect 4 masks + 2 filters, all in admin_demo.
SELECT 'column masks' AS policy_type, count(*) AS attached
FROM <catalog>.information_schema.column_masks
WHERE table_schema = 'admin_demo'
UNION ALL
SELECT 'row filters', count(*)
FROM <catalog>.information_schema.row_filters
WHERE table_schema = 'admin_demo';

-- (2) No policy has leaked onto the shared foundation. Expect zero rows.
SELECT 'LEAK: mask on foundation' AS finding, table_schema, table_name, column_name
FROM <catalog>.information_schema.column_masks
WHERE table_schema <> 'admin_demo'
UNION ALL
SELECT 'LEAK: row filter on foundation', table_schema, table_name, NULL
FROM <catalog>.information_schema.row_filters
WHERE table_schema <> 'admin_demo';

-- (3) The masks did not silently null a column through a parsing failure — the dob mask
-- coalesces three date formats, and getting that wrong looks like a working mask.
SELECT count(*) AS rows_with_null_dob
FROM <catalog>.admin_demo.student
WHERE dob IS NULL;

-- (4) The policy-defining functions are not writable by the roles they govern. A faculty
-- principal with CREATE FUNCTION on admin_demo could replace mask_ssn and lift their own
-- restriction. Expect only the admin group.
SELECT grantee, privilege_type
FROM <catalog>.information_schema.schema_privileges
WHERE schema_name = 'admin_demo'
  AND privilege_type IN ('ALL_PRIVILEGES', 'CREATE_FUNCTION', 'MODIFY')
ORDER BY grantee;


-- =====================================================================================
-- Cleanup — remove the test harness so it cannot be mistaken for a live policy
-- =====================================================================================

-- DROP FUNCTION IF EXISTS <catalog>.admin_demo.test_mask_ssn_as;
