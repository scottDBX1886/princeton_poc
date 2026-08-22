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

## 2. The two identities in this workspace

The RFP describes Admin / Faculty / Student roles. This workspace supports **two** distinct
identities, and the constraint is worth stating plainly because it shaped everything else:

| RFP role | Identity here | Reached by |
|---|---|---|
| **admin** | `mehak.juneja@databricks.com` (member of `admins`) | normal login |
| **faculty / student** | `account users` | **RBAC role switch** |

### Why not three purpose-built groups

Unity Catalog grants only to **account-level** groups (SCIM `type=Group`). This workspace has
exactly one: `account users`. `admins` and `users` are `type=WorkspaceGroup`, and `GRANT` to either
returns `PRINCIPAL_DOES_NOT_EXIST`.

Creating `princeton_admins` / `_faculty` / `_students` does not work either, and it fails in a way
worth knowing about: **the SCIM create succeeds** and returns a group — but with
`meta.resourceType = WorkspaceGroup`, so the subsequent `GRANT` fails. Verified end to end.

Holding `ALL_PRIVILEGES` on the catalog does not help. Granting **to** an existing principal and
**creating** an account-level principal are separate planes of authority; the second needs
account-admin rights, which a workspace admin does not have.

> In Princeton's own tenancy these would be SCIM-provisioned `princeton_admins` /
> `princeton_faculty` / `princeton_students` from their IdP, and the policy functions would compare
> `session_user()` against those names. **The pattern is identical; only the names change.** Worth
> saying out loud in the read-out so the two-identity model doesn't read as a limitation of the
> platform.

---

## 3. RBAC role switching — the "faux user" mechanism

Databricks supports **assuming a role**: workspace-name menu (top right) → hover the workspace →
pick a role. This is not a UI preview or a visibility filter. While a role is assumed it becomes the
**active SQL identity**: the user's own permissions are replaced for the session, and Unity Catalog
evaluates grants, row filters and column masks against the role.

This is what PA-11 ("faux user" testing) asks for, and it needs no colleague, no service principal
and no account-admin rights.

Verified live in this workspace:

| | as the user | as `account users` |
|---|---|---|
| `session_user()` | `mehak.juneja@databricks.com` | `account users` |
| `current_user()` | `mehak.juneja@databricks.com` | `account users` |
| `is_member('admins')` | `true` | **`false`** |

### Policies branch on `session_user()`, not `is_member()`

Two traps, both verified, both silent — the mask appears to work while proving nothing:

1. **A group is not a member of itself.** Acting as `account users`,
   `is_member('account users')` is **false**. A policy written as
   `WHEN is_member('account users') THEN <restricted>` never fires.
2. **An assumed role inherits none of the human's memberships.** `is_member('admins')` is **false**
   while acting as the role, even though the person behind it is an admin.

`session_user()` returns the email when you are yourself and the role name when you have assumed a
role, so it discriminates reliably in both directions. Every PA-B / PA-C policy therefore matches
the restricted role **first**, before any `is_member()` check runs:

```sql
CASE
  WHEN session_user() = 'account users' THEN NULL        -- PA-08: full restriction
  WHEN is_member('admins')              THEN ssn         -- unrestricted
  ELSE concat('***-**-', right(ssn, 4))                  -- PA-07: partial
END
```

### An assumed role does not hide who you are

The question a security reviewer will ask. `system.access.audit.identity_metadata` carries
`run_by` (the authenticated human) alongside `run_as` (the assumed role), so accountability survives
the switch. That is what makes role switching acceptable as a production access pattern rather than
a hole in the audit trail. PA-05 queries it directly.

### Operational caveat

**Group membership is cached.** After a membership change, `is_member()` can keep returning the old
answer for up to a minute. Make membership changes a few minutes before you need them — do not
remove someone from a group on stage and expect the next query to redact.

---

## 4. Onboarding procedure (PA-01)

In Princeton's tenancy, with SCIM-provisioned groups:

1. **Settings → Identity and access → Groups** → open the target group.
2. Add the user. Membership is the only step — no grants are edited.
3. Verify as the user: `SELECT is_member('princeton_faculty')` → `true`.
4. Confirm effective access: they can `SELECT` from `gold.enrollment_history` and are denied on
   `bronze`.

Offboarding is the same in reverse. Because every grant attaches to a group, removing membership
revokes everything at once — there is no per-object cleanup, which is exactly the failure mode of
user-level grants.

**In this POC workspace**, where new account-level groups cannot be created, the equivalent
demonstration is the role switch: assume `account users`, observe the narrowed access, switch back.
Same conclusion — access follows the identity, not the person — reached with the identities that
exist here.

### What is never done here: `REVOKE`

`account users` holds `ALL_PRIVILEGES` on `princeton_poc_dev`. That group is **every user and
service principal in the account**, it is the only UC-grantable group in this workspace, and the
catalog owner is `account_admins` — which we are not in. Revoking it would lock out every user with
no second group to recover through.

So no PA scenario revokes anything. Restriction is demonstrated by narrow grants on a schema we own
(`admin_demo`) and by the dev/prod grant asymmetry that already exists (PA-03).

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
