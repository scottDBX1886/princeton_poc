-- =====================================================================================
-- PA-A — Identity & access grant statements (PA-01, PA-02, PA-03, PA-04)
--
-- The reviewable form of what admin/src/pa_a_identity_access.py executes. A Princeton DBA
-- coming from Oracle FGAC can read and audit this without reading PySpark; the notebook is
-- the orchestrated path that also asserts the outcome.
--
-- Run order: pa_00_admin_demo_setup (creates admin_demo) -> this file -> PA-B / PA-C policies.
--
-- Substitute <catalog> and <suffix> for the target, e.g. princeton_poc_dev and _dev.
-- The suffix carries its own leading underscore, so schema names concatenate directly:
-- gold<suffix> -> gold_dev. Prod passes an empty suffix, where the schema is plainly `gold`.
-- =====================================================================================

-- -------------------------------------------------------------------------------------
-- Two constraints that decide the shape of everything below. Both were hit while
-- building; both fail in ways that look like something else.
--
-- 1. Unity Catalog will NOT grant to a workspace-local group. Groups created inside a
--    workspace are SCIM type=WorkspaceGroup, and GRANT returns
--    PRINCIPAL_DOES_NOT_EXIST. Only ACCOUNT-level groups (type=Group) can hold UC
--    privileges. With no account-admin rights in this environment we map each RFP role
--    onto an account group that already exists rather than creating new ones.
--
-- 2. GRANT requires MANAGE on the securable. <catalog> is owned by another user, so
--    catalog-scoped grants return PERMISSION_DENIED. Everything here is scoped to
--    <catalog>.admin_demo, which the PA admin owns -- and which is where spec 3.1
--    requires the PA security scenarios to operate anyway.
--
-- Role -> account group mapping used throughout (see PA_A_IDENTITY_STRATEGY.md):
--    admin    dbx_demo_shared_admins        <- the PA admin IS a member
--    faculty  data_engineers_demo_group     <- not a member
--    student  dbx_demo_shared_dev_group     <- not a member
--
-- The membership asymmetry is deliberate: it is what makes the PA-B masking contrast
-- real rather than staged. In Princeton's own tenancy these would be SCIM-provisioned
-- princeton_admins / _faculty / _students, and the policy functions would use
-- is_account_group_member() instead of is_member(). Same pattern, different names.
-- -------------------------------------------------------------------------------------


-- =====================================================================================
-- PA-02 / PA-04 -- Grant to GROUPS, never to individual users
--
-- Access follows the role. Onboarding becomes a group membership change; offboarding
-- revokes everything at once, because nothing was ever granted to a person.
-- =====================================================================================

-- admin -- full control of the policy sandbox
GRANT ALL PRIVILEGES
    ON SCHEMA <catalog>.admin_demo
    TO `dbx_demo_shared_admins`;

-- faculty -- read the whole sandbox; masks (PA-07) and row filters (PA-09) do the narrowing
GRANT USE SCHEMA, SELECT
    ON SCHEMA <catalog>.admin_demo
    TO `data_engineers_demo_group`;

-- student -- PA-04 proper: schema traversal ONLY, no schema-wide SELECT ...
GRANT USE SCHEMA
    ON SCHEMA <catalog>.admin_demo
    TO `dbx_demo_shared_dev_group`;

-- ... and read on exactly one table. No grant on faculty or financial_aid means no access
-- to them at all. This narrower grant IS the object-level-permissions scenario: the
-- privilege sits on the object, not the container.
GRANT SELECT
    ON TABLE <catalog>.admin_demo.student
    TO `dbx_demo_shared_dev_group`;


-- =====================================================================================
-- PA-03 -- Environment-level segregation  [REQUIRES CATALOG MANAGE -- see note]
--
-- Environments are separate CATALOGS -- princeton_poc_dev, _test, _qa, princeton_poc --
-- all in one workspace. USE CATALOG gates everything beneath it, so withholding it is
-- absolute: no schema-level or table-level grant lets a principal around a missing
-- catalog grant. That is what makes it segregation rather than a naming convention.
--
-- The two statements below are the whole scenario: grant on dev, say nothing about prod.
-- They need MANAGE on each catalog, which the PA admin does not hold here, so they are
-- left commented. The notebook demonstrates the model by reading live grant state
-- instead; see the tracker, where PA-03 is honestly marked partial.
--
-- To close PA-03, the catalog owner runs these, and the demo becomes a paired query:
-- the same SELECT against both catalogs, one returning rows and one PERMISSION_DENIED.
-- =====================================================================================

-- GRANT USE CATALOG ON CATALOG princeton_poc_dev  TO `data_engineers_demo_group`;
-- (deliberately NO grant on princeton_poc -- the absence IS the control)


-- =====================================================================================
-- PA-06 -- Service principals
--
-- A service principal is an identity for a WORKLOAD. Least privilege for a non-human
-- caller, and no human credential embedded anywhere. The POC already ships a working
-- example: engineer/src/apps/grant_app_sp.sh grants the mock REST API app's SP SELECT on
-- a single table.
--
-- The rotation argument in one line: grants attach to the PRINCIPAL, not the credential,
-- so rotating an SP secret is invisible to permissions. Full procedure in
-- PA_A_IDENTITY_STRATEGY.md.
-- =====================================================================================

-- Pattern (substitute the SP's application_id):
-- GRANT SELECT ON TABLE <catalog>.silver<suffix>.enrollment TO `<application-id>`;


-- =====================================================================================
-- Verify -- read the grants back from information_schema
--
-- Column-name gotcha: schema_privileges uses schema_name; table_privileges uses
-- table_schema. Mixing them gives UNRESOLVED_COLUMN.
-- =====================================================================================

SELECT grantee, privilege_type
FROM <catalog>.information_schema.schema_privileges
WHERE schema_name = 'admin_demo'
ORDER BY grantee, privilege_type;

SELECT grantee, table_name, privilege_type
FROM <catalog>.information_schema.table_privileges
WHERE table_schema = 'admin_demo'
ORDER BY grantee, table_name, privilege_type;

-- Expected: ALL_PRIVILEGES for the admin group; USE_SCHEMA + SELECT for faculty;
-- USE_SCHEMA only for student at schema level, plus exactly one table grant on
-- admin_demo.student. If the student group shows schema-wide SELECT, PA-04 is not being
-- demonstrated -- the access has been silently widened.
