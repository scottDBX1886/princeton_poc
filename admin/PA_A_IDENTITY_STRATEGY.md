# PA-A — Identity & access strategy

Reference for the Platform Administrator scenarios PA-01 … PA-06. The executable half is
`admin/src/pa_a_identity_access.py`; this document is the *why*, plus the two procedures that are
policy rather than code (group onboarding and credential rotation).

---

## 1. Principles

1. **Grant to groups, never to users.** Onboarding becomes a group membership change, not a
   permissions ticket. It is also the only way an access review stays tractable — you audit a
   handful of groups, not hundreds of individual grants.
2. **Least privilege by layer.** Bronze is raw and unmasked, so only admins read it. Faculty get
   conformed Silver plus the curated Gold fact. Students get Gold only, further narrowed by row
   filters (PA-09/10).
3. **Environments are catalogs.** `USE CATALOG` gates everything beneath it, so withholding it is
   absolute segregation — there is no schema-level way around it.
4. **Workload identities are service principals, never a person's token.** A departing employee's
   PAT should never be able to break a pipeline.
5. **The audit trail is queryable.** `system.access.audit` and `system.access.table_lineage` are
   tables. Access review is SQL, not a support ticket.

---

## 2. Group taxonomy

| Group | Reads | Purpose |
|---|---|---|
| `princeton_poc_dev_admins` | bronze, silver, gold, `admin_demo` | Platform administrators; the only group that sees raw Bronze and can apply policies |
| `princeton_poc_dev_faculty` | silver, gold | Teaching and research staff — conformed dimensions and the enrollment fact |
| `princeton_poc_dev_students` | gold | Curated fact only, row-filtered to their own records |

**Names are catalog-prefixed on purpose.** Bare `Admins` / `Faculty` / `Students` in a shared
workspace would collide with another team's groups — and a column mask that resolves against
someone else's `Admins` is a security bug, not a naming annoyance. The prefix also makes the
environment obvious in an access review: `princeton_poc_test_faculty` is unmistakably not prod.

---

## 3. `is_member()`, not `is_account_group_member()`

This is the single most important implementation detail in the PA persona, and getting it wrong
fails silently.

```sql
is_account_group_member('admins')                  -- false
is_account_group_member('dbx_demo_shared_admins')  -- true   (account-level group)
is_member('admins')                                -- true   (workspace-local group)
```

Groups created in this workspace are `WorkspaceGroup` objects. `is_account_group_member()` cannot
see them, so a mask written as:

```sql
CASE WHEN is_account_group_member('princeton_poc_dev_admins') THEN ssn ELSE '[REDACTED]' END
```

returns `[REDACTED]` **for everyone, including the admin** — the demo appears to work while proving
nothing. Every policy in PA-B and PA-C therefore uses `is_member()`.

> If Princeton's own environment uses account-level groups provisioned by SCIM from their IdP,
> `is_account_group_member()` becomes the right function there. The *pattern* is identical; only the
> function name changes. Worth saying explicitly in the read-out so it doesn't look like a
> workaround.

### Two operational caveats found while building this

- **Members must be supplied at group creation.** A follow-up SCIM `PATCH` to add members returns
  `operation not permitted` for a workspace admin who is not an account admin. The notebook
  therefore seeds the admin group at creation; faculty and students are populated in the UI
  (**Settings → Identity and access → Groups**).
- **Group membership is cached.** After deleting a group, `is_member()` continued returning `true`
  for at least half a minute. For a live demo, make membership changes a few minutes before you need
  them to take effect — do not remove someone from a group on stage and expect the next query to
  redact.

---

## 4. Onboarding procedure (PA-01)

1. **Settings → Identity and access → Groups** → open the target group.
2. Add the user. Membership is the only step — no grants are edited.
3. Verify as the user: `SELECT is_member('princeton_poc_dev_faculty')` → `true`.
4. Confirm effective access: they can `SELECT` from `gold_dev.enrollment_history` and are denied on
   `bronze_dev`.

Offboarding is the same in reverse. Because every grant attaches to a group, removing membership
revokes everything at once — there is no per-object cleanup, which is exactly the failure mode of
user-level grants.

---

## 5. Service principals & credential rotation (PA-06)

A service principal is an identity for a *workload*. The POC already ships a working example:
`engineer/src/apps/grant_app_sp.sh` grants the mock REST API app's SP `SELECT` on a single table —
least privilege for a non-human caller.

### Why SPs rather than a personal token

| | Personal access token | Service principal |
|---|---|---|
| Tied to a person | Yes — breaks when they leave | No |
| Scope | Everything that person can do | Only what the SP is granted |
| Rotation | Manual, and breaks whatever embedded it | Secret rotates; grants untouched |
| Audit | Attributed to the human | Attributed to the workload |

### Rotation procedure

The key property: **grants attach to the principal, not the credential.** Rotating a secret is
therefore invisible to permissions.

1. **Settings → Identity and access → Service principals** → the SP → **Secrets** →
   *Generate secret*. Note the new client secret.
2. Update the consumer to the new secret — for this POC, the UC secret scope the app reads from.
3. Verify the workload still runs (for the mock API: `databricks bundle run` its verification task).
4. **Delete the old secret.** Two live secrets is the normal state *during* rotation and a finding
   afterwards.
5. Confirm in the audit trail:

```sql
SELECT event_time, user_identity.email AS actor, action_name,
       request_params['service_principal_id'] AS sp
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND action_name ILIKE '%servicePrincipal%'
ORDER BY event_time DESC;
```

Recommended cadence: **90 days**, or immediately on any suspicion of exposure. Because grants
survive rotation, there is no reason to delay it.

---

## 6. Access review query set (PA-05)

Three questions an auditor actually asks, each answerable in SQL:

**Who holds what, right now?**

```sql
SELECT grantee, table_schema, privilege_type
FROM princeton_poc_dev.information_schema.schema_privileges
WHERE grantee LIKE 'princeton_poc%'
ORDER BY grantee, table_schema;
```

**Who changed a permission, and when?**

```sql
SELECT event_time, user_identity.email AS actor,
       request_params['securable_full_name'] AS securable,
       request_params['changes'] AS changes
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 30 DAYS
  AND service_name = 'unityCatalog'
  AND action_name = 'updatePermissions'
ORDER BY event_time DESC;
```

**Who has actually read the sensitive tables?** — the question that matters most, and the one a
grants list cannot answer:

```sql
SELECT created_by AS who, source_table_full_name AS table_read,
       count(*) AS reads, max(event_time) AS last_read
FROM system.access.table_lineage
WHERE event_date >= current_date() - INTERVAL 7 DAYS
  AND source_table_full_name IN (
      'princeton_poc_dev.silver_dev.student',
      'princeton_poc_dev.silver_dev.faculty',
      'princeton_poc_dev.silver_dev.financial_aid')
GROUP BY created_by, source_table_full_name
ORDER BY reads DESC;
```

> **Always filter on `event_date`.** It is the partition column on both system tables, and they hold
> tens of millions of rows per week — 53M over seven days in this workspace. An unfiltered query is
> slow enough to look broken.

---

## 7. What this does *not* cover

Stated plainly so the read-out doesn't over-claim:

- **SCIM provisioning from an IdP.** Princeton would sync groups from Entra ID or Okta at the
  account level; this POC creates workspace groups by hand because we don't have account admin.
  The policy pattern is unchanged — only the provisioning source and the group-check function.
- **IP access lists and network policy.** Account-console configuration, outside this workspace.
- **Personal-token governance at scale.** Token lifetime policy is an account-level setting.

Each is a configuration difference in Princeton's own tenancy, not a capability gap — worth saying
that way round.
