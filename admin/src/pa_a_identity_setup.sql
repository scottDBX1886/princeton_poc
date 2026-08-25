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
-- THE TWO IDENTITIES, AND WHY THERE ARE ONLY TWO
--
-- This POC workspace has exactly ONE UC-grantable group: `account users` (SCIM
-- type=Group). `admins` and `users` are workspace-local (type=WorkspaceGroup) and Unity
-- Catalog rejects them with PRINCIPAL_DOES_NOT_EXIST.
--
-- We hold no account-admin rights, so we cannot mint account-level groups either --
-- verified: creating one SUCCEEDS but yields type=WorkspaceGroup, and the following GRANT
-- then fails. Holding ALL_PRIVILEGES on the catalog does not help; granting TO an existing
-- principal and CREATING a principal are separate planes of authority.
--
-- So the RFP's roles map onto the two identities that genuinely exist and genuinely differ:
--
--   RFP role              Identity here                        Reached by
--   --------------------  -----------------------------------  ---------------------
--   admin                 mehak.juneja@databricks.com          normal login
--   faculty / student     account users                        RBAC role switch
--
-- In Princeton's own tenancy these would be SCIM-provisioned princeton_admins /
-- princeton_faculty / princeton_students, and the policy functions would compare
-- session_user() against those names instead. Same pattern, different names.
-- -------------------------------------------------------------------------------------

-- -------------------------------------------------------------------------------------
-- RBAC ROLE SWITCHING -- the "faux user" mechanism (see PA-11)
--
-- Databricks supports ASSUMING A ROLE: workspace-name menu (top right) -> hover the
-- workspace -> pick a role. It is not a UI preview. While a role is assumed it becomes the
-- active SQL identity: the user's own permissions are replaced for the session and Unity
-- Catalog evaluates grants, row filters and column masks against the role.
--
-- Verified live in this workspace:
--
--                            as the user                      as `account users`
--   session_user()           mehak.juneja@databricks.com      account users
--   current_user()           mehak.juneja@databricks.com      account users
--   is_member('admins')      true                             FALSE
--
-- TWO TRAPS, both silent, both the reason policies below use session_user():
--
--   1. A group is not a member of itself. Acting as `account users`,
--      is_member('account users') is FALSE. A policy written as
--      `WHEN is_member('account users') THEN <restricted>` never fires.
--
--   2. An assumed role does not inherit the human's memberships. is_member('admins') is
--      FALSE while acting as the role, even though the person behind it is an admin.
--
-- session_user() returns the email when you are yourself and the role name when you have
-- assumed a role, so it discriminates reliably in both directions.
-- -------------------------------------------------------------------------------------

-- -------------------------------------------------------------------------------------
-- WHAT THIS FILE DOES NOT DO: REVOKE
--
-- `account users` holds ALL_PRIVILEGES on <catalog>. That group is every user and service
-- principal in the account, and it is the only UC-grantable group here -- so revoking it
-- would lock out every user with no second group to recover through, and the catalog owner
-- (account_admins) is not us. Nothing in the PA scenarios revokes anything.
--
-- The restriction is demonstrated instead by (a) the narrow grants below on a schema we
-- own, and (b) the dev/prod grant asymmetry that already exists (PA-03).
-- -------------------------------------------------------------------------------------


-- =====================================================================================
-- PA-02 / PA-04 -- Grant to a GROUP, at object level
--
-- Access follows the role. Onboarding becomes a group membership change; offboarding
-- revokes everything at once, because nothing was ever granted to a person.
--
-- Both grants target <catalog>.admin_demo -- a schema created and owned by the PA admin
-- (see pa_00_admin_demo_setup). Nothing here touches the shared foundation the other
-- personas read.
-- =====================================================================================

-- Schema traversal ONLY. Deliberately NOT `USE SCHEMA, SELECT`: a schema-wide SELECT would
-- make the next statement meaningless.
GRANT USE SCHEMA
    ON SCHEMA <catalog>.admin_demo
    TO `account users`;

-- ...and read on exactly one table. This narrower grant IS the object-level-permissions
-- scenario: the privilege sits on the OBJECT, not the container. No grant on `faculty` or
-- `financial_aid` means no access to them at all -- the absence is the control, and it
-- needs no policy to enforce.
GRANT SELECT
    ON TABLE <catalog>.admin_demo.student
    TO `account users`;


-- =====================================================================================
-- PA-03 -- Environment-level segregation
--
-- Environments are separate CATALOGS in one workspace, and this workspace ALREADY carries
-- the asymmetry -- it is the customer's own configuration, not something staged:
--
--   princeton_poc_dev    account users -> ALL_PRIVILEGES
--   princeton_poc_prod   account users -> BROWSE, USE_CATALOG, USE_SCHEMA   (no SELECT)
--                        account_admins -> ALL_PRIVILEGES
--
-- USE CATALOG gates everything beneath it, and SELECT is what actually reads data, so the
-- absence of SELECT on prod is absolute: no schema-level or table-level grant works around
-- a missing catalog-level SELECT. That is segregation, not a naming convention.
--
-- NOTHING NEEDS TO BE GRANTED OR REVOKED TO DEMONSTRATE THIS. The two queries below are
-- the scenario.
-- =====================================================================================

-- The grant state that makes prod a different environment, not just a different name.
SELECT grantee, privilege_type
FROM princeton_poc_prod.information_schema.catalog_privileges
ORDER BY grantee, privilege_type;
-- Expect: account_admins with ALL_PRIVILEGES, and `account users` with BROWSE, USE_CATALOG
-- and USE_SCHEMA but NO SELECT.

-- BROWSE without SELECT: metadata visible, data not. The subtle half of the scenario, and
-- the part that separates UC from filesystem-style permissions -- a data catalogue stays
-- useful for discovery while the data itself stays closed.
SHOW SCHEMAS IN princeton_poc_prod;                             -- SUCCEEDS (BROWSE/USE_SCHEMA)
SELECT count(*) FROM princeton_poc_prod.bronze.enrollments;      -- DENIED   (no SELECT)


-- =====================================================================================
-- PA-06 -- Service principals
--
-- A service principal is an identity for a WORKLOAD. Least privilege for a non-human
-- caller, and no human credential embedded anywhere. This workspace already runs three:
-- the runbook app, the mock REST API, and the E3 ingest job.
-- engineer/src/apps/grant_app_sp.sh shows the grant pattern.
--
-- The rotation argument in one line: grants attach to the PRINCIPAL, not the credential,
-- so rotating an SP secret is invisible to permissions. Full procedure in
-- PA_A_IDENTITY_STRATEGY.md.
-- =====================================================================================

-- Pattern (substitute the SP's application_id):
-- GRANT SELECT ON TABLE <catalog>.silver<suffix>.enrollment TO `<application-id>`;

-- Which SPs hold table grants. Application IDs are UUIDs, so they are distinguishable from
-- user and group grantees by shape alone.
SELECT grantee, table_schema, table_name, privilege_type
FROM <catalog>.information_schema.table_privileges
WHERE grantee RLIKE '^[0-9a-f]{8}-[0-9a-f]{4}-'
ORDER BY grantee, table_schema, table_name;


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

-- Expected: `account users` with USE_SCHEMA at schema level -- and NOT SELECT -- plus
-- exactly one table grant, on admin_demo.student. If `account users` shows schema-wide
-- SELECT, PA-04 is not being demonstrated: the access has been silently widened and the
-- faculty/financial_aid contrast is gone.

-- The identity functions every policy depends on. Run this, switch roles, run it again --
-- the values change, and that change is the whole mechanism.
SELECT session_user()                  AS session_user,
       current_user()                  AS current_user,
       is_member('admins')             AS is_member_admins,
       is_member('account users')      AS is_member_restricted;
-- As yourself:          your email, your email, true,  true
-- As `account users`:   account users, account users, FALSE, FALSE
--                                                     ^^^^^  ^^^^^
-- Both false is the counterintuitive part: an assumed role inherits no memberships, and a
-- group is not a member of itself. Hence session_user(), not is_member(), in every policy.
