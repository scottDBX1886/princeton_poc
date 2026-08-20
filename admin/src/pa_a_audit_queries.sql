-- =====================================================================================
-- PA-A / PA-05 — Access audit query set
--
-- The three questions an auditor actually asks, as standalone SQL. These are meant to be
-- run repeatedly and independently — during an access review, after an incident, or on a
-- schedule — which is why they live here rather than only inside a notebook.
--
-- Substitute <catalog> and <suffix> for the target, e.g. princeton_poc_dev and _dev.
--
-- ⚠️ ALWAYS filter on event_date. It is the partition column on both system tables, and
-- they hold tens of millions of rows per week — 53M over 7 days and 21,214 permission
-- changes in a single day in this workspace. An unfiltered query is slow enough that it
-- looks broken, and in a live review that reads as the platform being slow.
-- =====================================================================================


-- =====================================================================================
-- 1. WHO HOLDS WHAT, RIGHT NOW
--
-- Current state, from the catalog itself. No console clicking, no screenshotting a
-- permissions dialog — the grant model is queryable, which is what makes an access review
-- repeatable.
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

-- Catalog level — this is the PA-03 segregation control. A group absent from this list
-- cannot read anything in the catalog, whatever schema grants might suggest.
SELECT grantee, privilege_type
FROM <catalog>.information_schema.catalog_privileges
ORDER BY grantee, privilege_type;


-- =====================================================================================
-- 2. WHO CHANGED A PERMISSION, AND WHEN
--
-- Every grant and revoke is recorded with its actor. request_params.changes holds the
-- principal and the privileges added or removed, so the row is self-describing — you do
-- not have to diff two states to see what happened.
-- =====================================================================================

SELECT event_time,
       user_identity.email                   AS actor,
       action_name,
       request_params['securable_type']      AS securable_type,
       request_params['securable_full_name'] AS securable,
       request_params['changes']             AS changes
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND service_name = 'unityCatalog'
  AND action_name = 'updatePermissions'
ORDER BY event_time DESC
LIMIT 100;

-- Scoped to this POC's securables only — the workspace is shared, so the unscoped query
-- above returns other teams' activity too.
SELECT event_time,
       user_identity.email                   AS actor,
       request_params['securable_full_name'] AS securable,
       request_params['changes']             AS changes
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND service_name = 'unityCatalog'
  AND action_name = 'updatePermissions'
  AND request_params['securable_full_name'] LIKE '<catalog>%'
ORDER BY event_time DESC;


-- =====================================================================================
-- 3. WHO ACTUALLY READ THE SENSITIVE TABLES
--
-- The question that matters most, and the one a grants list cannot answer. A grant says
-- who COULD read; lineage says who DID. In an incident review that distinction is the
-- whole investigation.
-- =====================================================================================

SELECT created_by             AS who,
       source_table_full_name AS table_read,
       count(*)               AS reads,
       min(event_time)        AS first_read,
       max(event_time)        AS last_read
FROM system.access.table_lineage
WHERE event_date >= current_date() - INTERVAL 7 DAYS
  AND source_table_full_name IN (
      '<catalog>.silver<suffix>.student',
      '<catalog>.silver<suffix>.faculty',
      '<catalog>.silver<suffix>.financial_aid',
      '<catalog>.admin_demo.student',
      '<catalog>.admin_demo.faculty',
      '<catalog>.admin_demo.financial_aid')
GROUP BY created_by, source_table_full_name
ORDER BY reads DESC;


-- =====================================================================================
-- 4. ACCESS DENIALS
--
-- Denials are the signal that a policy is working — and also the first place to look when
-- someone reports "I can't see the data." Both readings matter in a review.
-- =====================================================================================

SELECT event_time,
       user_identity.email                   AS actor,
       action_name,
       request_params['securable_full_name'] AS securable,
       response.error_message
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 7 DAYS
  AND response.error_message ILIKE '%PERMISSION_DENIED%'
ORDER BY event_time DESC
LIMIT 100;


-- =====================================================================================
-- 5. SERVICE PRINCIPAL ACTIVITY (PA-06)
--
-- Workload identities, held separately from human ones. SP application IDs are UUIDs, so
-- they are distinguishable from user and group grantees by shape alone.
-- =====================================================================================

SELECT grantee, table_schema, table_name, privilege_type
FROM <catalog>.information_schema.table_privileges
WHERE grantee RLIKE '^[0-9a-f]{8}-[0-9a-f]{4}-'
ORDER BY grantee, table_schema, table_name;

-- Credential rotation events — confirms a rotation happened and who did it. Because
-- grants attach to the principal rather than the credential, a rotation should appear
-- here with NO corresponding updatePermissions row. That absence is the proof that
-- rotation does not disturb access.
SELECT event_time,
       user_identity.email AS actor,
       action_name,
       request_params
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 90 DAYS
  AND action_name ILIKE '%servicePrincipal%'
ORDER BY event_time DESC
LIMIT 50;
