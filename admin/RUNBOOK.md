# Princeton POC — Platform Administrator Runbook

Scenario entries for the Platform Administrator persona (PA-01…PA-25). Security scenarios run
on the `admin_demo` schema (copies of the sensitive tables) so masking/RLS demos never mutate
the shared foundation. Index: [`docs/runbook/README.md`](../docs/runbook/README.md).

Status: [`docs/SCENARIO_TRACKER.md`](../docs/SCENARIO_TRACKER.md).

---

# PA-A — Identity & Access Management (PA-01 … PA-06)

**What this group proves:** an administrator provisions people by role, grants access to groups
rather than individuals, scopes permissions down to a single object, and can answer "who could read
this" *and* "who actually did" in SQL.

**Artifacts:**
- `admin/src/pa_a_identity_access.py` — the executable, asserted path (deployed as a job)
- `admin/src/pa_a_identity_setup.sql` — the same grants as reviewable SQL, for a DBA who wants to
  audit the access model without reading PySpark
- `admin/src/pa_a_audit_queries.sql` — the PA-05 query set as standalone SQL: current grants, who
  changed a permission, **who actually read** the sensitive tables, denials, and SP activity
- `admin/PA_A_IDENTITY_STRATEGY.md` — the two procedures that are policy rather than code

**Build status:** the executable object is `admin/src/pa_a_identity_access.py`, deployed as job
`[<catalog>] PA-A — Identity & access (PA-01…06)`. Strategy and the two procedures that are policy
rather than code (onboarding, credential rotation) are in
[`PA_A_IDENTITY_STRATEGY.md`](PA_A_IDENTITY_STRATEGY.md).

**Prereq:** `admin_demo` must exist — run `pa_admin_demo_setup` first (PA Task 0).

## ⚠️ Two environment constraints that shape this scenario

Both were hit while building, and both fail in ways that look like something else:

1. **Unity Catalog will not grant to a workspace-local group.** Groups created in this workspace
   are SCIM `type=WorkspaceGroup`, and `GRANT … TO <group>` returns `PRINCIPAL_DOES_NOT_EXIST`.
   Only **account-level** groups (`type=Group`) can hold UC privileges. This workspace has exactly
   one: `account users`.
2. **We cannot create account-level groups.** Verified: the SCIM create *succeeds* but returns
   `meta.resourceType = WorkspaceGroup`, so the following `GRANT` fails. Holding `ALL_PRIVILEGES`
   on the catalog does not help — granting **to** a principal and **creating** an account-level
   principal are separate planes of authority, and the second needs account-admin rights.
3. **Nothing is ever revoked.** `account users` holds `ALL_PRIVILEGES` on `princeton_poc_dev`. That
   group is every user and service principal in the account, it is the only grantable group here,
   and the catalog owner (`account_admins`) is not us — so revoking it would lock everyone out with
   no way back. Restriction is shown by narrow grants on `admin_demo` (which we own) and by the
   dev/prod asymmetry that already exists.

## The two identities

| RFP role | Identity here | Reached by |
|---|---|---|
| **admin** | your own login (member of `admins`) | normal session |
| **faculty / student** | `account users` | **RBAC role switch** |

**RBAC role switching is the "faux user" mechanism** (and what PA-11 needs). Workspace-name menu
→ hover the workspace → pick a role. Not a UI preview: while assumed, the role *is* the active SQL
identity, and UC evaluates grants, masks and row filters against it. Verified live:

| | as you | as `account users` |
|---|---|---|
| `session_user()` | your email | `account users` |
| `is_member('admins')` | `true` | **`false`** |

### ⚠️ Policies branch on `session_user()`, not `is_member()`

Two traps, both verified, both silent — the mask appears to work while proving nothing:

1. **A group is not a member of itself.** Acting as `account users`,
   `is_member('account users')` is **false**, so `WHEN is_member('account users') THEN …` never
   fires.
2. **An assumed role inherits none of the human's memberships.** `is_member('admins')` is **false**
   while acting as the role, even though the person behind it is an admin.

`session_user()` returns your email normally and the role name while a role is assumed, so it
discriminates reliably. Every policy matches the restricted role **first**, before any
`is_member()` check.

> In Princeton's own tenancy these would be SCIM-provisioned `princeton_admins` / `_faculty` /
> `_students`, and the policies would compare `session_user()` against those names. **The pattern is
> identical; only the names change.** Say that out loud so the two-identity model doesn't read as a
> platform limitation.

## Generation prompt — PA-01, PA-02, PA-04

> **Prompt:** 🟡 written — **one generate-and-verify attempt made 2026-08-24, and it exposed a defect
> in this prompt.** Re-test pending against the corrected text below.

<details>
<summary><strong>What the 2026-08-24 attempt found</strong> — worth reading before re-testing</summary>

The generation got the hard part right: it branched on `session_user()` (5 uses), issued no `REVOKE`,
created no groups, granted nothing at catalog scope, discovered SCIM types correctly, skipped the
grant cells when run as the role, and handled the `schema_name` vs `table_schema` gotcha. The identity
model — the thing most worth testing — was correct.

But it **passed by weakening two of its own assertions.** The prompt demanded the restricted role
"holds NOTHING on faculty or financial_aid". That is impossible here: `account users` holds
`ALL_PRIVILEGES` on the *catalog*, and UC privileges cascade, so it reaches both tables no matter what
we withhold. The generation split its checks into `blocking_failures` (the first four) and
`unexpected_access_failures` (those two), printed a warning for the latter, and reported
`RBAC validation passed`.

**That is a prompt defect, not a model failure.** I fixed this exact cascade problem in the notebook on
2026-08-22 and left the stale instruction in the prompt — so the prompt and the notebook had drifted.
The generation also never used `inherited_from`, because the prompt never mentioned it.

The prompt now: names the cascade explicitly with the verified privilege rows, forbids asserting the
impossible, requires the `inherited_from = 'NONE'` filter to separate explicit from inherited grants,
requires asserting that the inherited privileges **are** present (the over-permission finding), and
states that hard failures are required — no warn-and-continue.

**Lesson worth keeping:** a generation that rationalises its way to green is telling you the prompt
asked for something untrue. That is what prompt testing is for.

</details>

One notebook produces all three of these scenarios, so there is one prompt rather than three.
Each scenario is then written up separately below, because each is graded separately in the RFP.

<details>
<summary><strong>Assistant prompt (generate the identity & access notebook)</strong> — click to expand</summary>

```text
Write a PySpark notebook that sets up role-based access control in Unity Catalog and proves it works.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix value ALREADY includes its leading underscore, so concatenate with no separator —
f"{catalog}.silver{suffix}", never f"silver_{suffix}". The bundle passes _dev / _test / "" (empty,
for prod), so an underscore in the f-string breaks qa and prod while passing on dev.

Also read widgets "restricted_role" (default "account users") and "admin_group" (default "admins").
Never hardcode either name.

Three hard constraints — get these wrong and it fails at runtime in ways that look like other
things:

1. Unity Catalog will NOT grant to a workspace-local group. Groups created in a workspace are SCIM
   type=WorkspaceGroup and GRANT returns PRINCIPAL_DOES_NOT_EXIST. Only ACCOUNT-level groups
   (type=Group) can hold UC privileges, and this workspace has exactly ONE: "account users". So do
   NOT create groups — discover the existing account-level ones with the SDK (w.groups.list(), keep
   those where meta.resource_type == "Group") and print the type of every group so the distinction
   is visible.
2. Do NOT issue any REVOKE. "account users" holds ALL_PRIVILEGES on the catalog; it is every user in
   the account and the only grantable group here, so revoking it locks everyone out with no way
   back. GRANT is additive, so re-granting what the pre-built applied is a harmless no-op.
3. Grant at <catalog>.admin_demo scope, NOT catalog scope. The admin owns admin_demo, not the
   catalog.

The restricted identity is reached by RBAC ROLE SWITCHING (workspace menu -> role), which makes the
role the active SQL identity. Two verified traps, both silent:
  - a group is not a member of itself, so is_member('account users') is FALSE while acting as it
  - an assumed role inherits none of the human's memberships, so is_member('admins') is FALSE too
Therefore branch on session_user(), which returns the email normally and the role name while a role
is assumed. Match the restricted role FIRST, before any is_member() check.

Steps:
1. List every group with its SCIM resource type, marking which are UC-grantable. Then print
   session_user(), current_user(), is_member(admin_group) and is_member(restricted_role) in one
   query, and explain in a print() why the last one is False for a real member (a group is not a
   member of itself) — that is the trap the reader most needs to see.
2. Grant on <catalog>.admin_demo: USE SCHEMA to restricted_role, plus SELECT on ONLY the
   admin_demo.student table — no schema-wide SELECT, and nothing at all on faculty or
   financial_aid. That narrowness is the object-level-permissions intent.
3. Read the effective grants back from information_schema, and SELECT THE inherited_from COLUMN.
   This is the crux of the scenario, so do not skip it. Note the column names differ:
   schema_privileges uses schema_name, table_privileges uses table_schema. Mixing them gives
   UNRESOLVED_COLUMN.

   READ THIS BEFORE WRITING ANY ASSERTION. Unity Catalog privileges CASCADE DOWNWARD, and in this
   workspace `account users` holds ALL_PRIVILEGES on the CATALOG. So it already reaches every table in
   every schema — including admin_demo.faculty and admin_demo.financial_aid, and including any schema
   created later. Verified live:

     admin_demo.student         SELECT          inherited_from = NONE               <- granted here
     admin_demo.student         ALL_PRIVILEGES  inherited_from = princeton_poc_dev  <- cascaded
     admin_demo.faculty         ALL_PRIVILEGES  inherited_from = princeton_poc_dev  <- cascaded
     admin_demo.financial_aid   ALL_PRIVILEGES  inherited_from = princeton_poc_dev  <- cascaded

   Therefore WITHHOLDING A GRANT IN THIS CATALOG CANNOT PRODUCE A DENIAL. There is nothing to
   withhold. Do NOT assert that the restricted role "holds nothing" on faculty or financial_aid — that
   assertion is impossible here and will fail. Do not weaken it to a warning either; assert something
   true instead (step 5).

   Do not attempt to fix this by revoking. See constraint 2.

4. Detect whether the notebook is itself running as the restricted role (session_user() ==
   restricted_role) and SKIP the grant cells with a clear message if so — you cannot grant while
   acting as a role, and a hard failure mid-demo looks like a broken notebook.

5. Assert, and every one of these must be a hard failure — no warn-and-continue:
   a. restricted_role is UC-grantable (an account-level SCIM Group).
   b. Filtering on inherited_from = 'NONE' or NULL to isolate what THIS notebook granted:
      restricted_role holds an EXPLICIT USE_SCHEMA on admin_demo, an EXPLICIT SELECT on
      admin_demo.student, and NO explicit grant on faculty or financial_aid. Without the
      inherited_from filter an assertion cannot tell what you granted from what cascaded — which is
      the whole confusion this step exists to prevent.
   c. restricted_role holds no EXPLICIT schema-wide SELECT on admin_demo.
   d. The inherited privileges ARE present and reported — assert that at least one row on
      faculty/financial_aid has inherited_from set. That is the over-permission finding, and asserting
      it means the notebook proves the cascade rather than pretending it is absent.

6. Add an over-permission audit cell: list every privilege reaching admin_demo where inherited_from
   is set. In a real estate those rows are the finding — a team scopes a narrow table grant, believes
   access is restricted, and a catalog-level ALL_PRIVILEGES two levels up has been overriding it the
   whole time. information_schema is how you catch it.

7. State in a markdown cell where the DENIAL is actually demonstrated: <prod_catalog>
   (princeton_poc_prod), where `account users` holds BROWSE + USE_CATALOG + USE_SCHEMA but NO SELECT
   at any level. The demo is one statement shape against two catalogs — dev returns rows, prod returns
   PERMISSION_DENIED — not two objects in one catalog.

   Also note the second reason an admin cannot self-verify this: a workspace admin is a METASTORE
   ADMIN, and metastore admins bypass UC grants entirely. Run as an admin, the prod read SUCCEEDS. So
   an admin's own session can never confirm a restriction — only the role switch can.
```

</details>

## PA-01 — User provisioning & role assignment

> **Built:** ✅ (verified in the customer wksp) · **Prompt:** 🟡 re-test needed — see the shared prompt above

**What it proves:** a person is provisioned by *role*. Access follows group membership, so
onboarding never touches a grant.

**How to test:** run the job, or the notebook interactively. It reports, per role, whether the
group is UC-grantable and whether `is_member()` resolves for the caller.

Provisioning is then a **membership change only** — **Settings → Identity and access → Groups**
→ add the user. Verify as them: `SELECT is_member('<their group>')` → `true`.

**Expected outcome:** the group listing shows which groups are UC-grantable (`type=Group`) and which
are not (`type=WorkspaceGroup`), and the identity query shows `session_user()` plus both membership
checks. Run it, switch to the `account users` role, run it again — `session_user()` changes and
`is_member('admins')` flips to `false`. That change is the mechanism.

**⚠️ Membership is cached.** After a group change, `is_member()` kept returning the old answer for
30+ seconds. Make membership changes a few minutes before you need them on screen — do not remove
someone from a group live and expect the next query to redact.

## PA-02 — Group-based access control

> **Built:** ✅ (verified in the customer wksp) · **Prompt:** 🟡 re-test needed — see the shared prompt above

**What it proves:** every grant targets a group, never an individual. Onboarding is a membership
change; offboarding revokes everything at once, because nothing was granted to a person.

**How to test:** read the grants back — the notebook does this, or run the query in
[`src/pa_a_audit_queries.sql`](src/pa_a_audit_queries.sql) section 1.

**Expected outcome:** on `admin_demo`, `account users` holds `USE_SCHEMA` and one table-level
`SELECT` — and the grantee is a **group**, not a person. Contrast with the `information_schema` rows
for the service principals (PA-06), which are the other kind of grantee that is not a human.

## PA-03 — Environment-level access segregation

> **Built:** ✅ · **Prompt:** — n/a (reads live grant state; nothing to generate)

**What it proves:** environments are separate **catalogs** in one workspace, and this workspace
already carries the asymmetry — it is the customer's own configuration, not something staged for the
demo:

| Catalog | `account users` holds |
|---|---|
| `princeton_poc_dev` | `ALL_PRIVILEGES` |
| `princeton_poc_prod` | `BROWSE`, `USE_CATALOG`, `USE_SCHEMA` — **no `SELECT`** |

`USE CATALOG` gates everything beneath it and `SELECT` is what actually reads data, so the absence of
`SELECT` on prod is absolute: no schema- or table-level grant works around it. That is segregation
rather than a naming convention.

**Nothing needs granting or revoking to demonstrate this.** Two queries are the scenario:

```sql
SHOW SCHEMAS IN princeton_poc_prod;                          -- SUCCEEDS (BROWSE/USE_SCHEMA)
SELECT count(*) FROM princeton_poc_prod.bronze.enrollments;   -- DENIED   (no SELECT)
```

**The `BROWSE`-without-`SELECT` point is the sophisticated half**, and it is free: metadata is
visible, data is not. A data catalogue stays useful for discovery while the data itself stays closed
— a distinction Oracle FGAC handles quite differently, and worth drawing out.

**How to test:** the notebook runs both halves and reports which succeeded. It reads the grant state
from `information_schema.catalog_privileges` too, so the assertion holds whoever runs it.

> **Note:** `princeton_poc_prod` is nearly empty (`bronze.enrollments` only; `silver`/`gold` have no
> tables). So use `bronze.enrollments` for the denial — a query against `prod.silver.student` fails
> with `TABLE_OR_VIEW_NOT_FOUND`, which proves nothing about access control and a sharp DBA will say
> so.

## PA-04 — Source & target object-level permissions

> **Built:** ✅ (verified in the customer wksp) · **Prompt:** 🟡 re-test needed — see the shared prompt above

**What it proves:** a privilege can sit on a single **object**, not just the container — the
granularity an RFP means by "source and target object-level permissions."

**The demonstration is the restricted role.** It holds `USE_SCHEMA` on `admin_demo` but **no
schema-wide `SELECT`** — only `SELECT` on `admin_demo.student`. No grant on `faculty` or
`financial_aid` means no access to them at all, with no policy needed to enforce it: the absence
*is* the control.

**How to test:** the notebook asserts it, or query
[`src/pa_a_audit_queries.sql`](src/pa_a_audit_queries.sql) section 1.

**Expected outcome:** `information_schema.table_privileges` shows `account users` with exactly one
table grant, and `schema_privileges` shows it *without* `SELECT`. Assertions fail if schema-wide
`SELECT` ever leaks in, or if a grant appears on `faculty`/`financial_aid` — either would silently
widen access while still looking like a pass.

> Column-name gotcha: `schema_privileges` uses **`schema_name`**; `table_privileges` uses
> **`table_schema`**. Mixing them gives `UNRESOLVED_COLUMN`.


## PA-05 — Permission audit trail

> **Built:** ✅ · **Prompt:** 🟢 tested (`princeton_poc_dev`: Genie space over the audit + lineage tables — both NL prompts generated correct SQL against real data)

### No-code path — audit access in natural language

Genie space **`[<catalog>] Access Audit (PA-05)`**, grounded on `system.access.audit` and
`system.access.table_lineage`, created by the `genie_setup` task of `foundation_build`.

| Prompt | Verified result |
|---|---|
| `Who changed permissions in the last 7 days, and on what object?` | correct SQL — `service_name='unityCatalog'`, `action_name='updatePermissions'`, actor + securable, `event_date` filtered |
| `Who has read the student, faculty or financial_aid tables recently?` | queried `table_lineage`, returned 7 reader/table pairs |
| `Which principals were granted access this week, and by whom?` | — |
| `Show all access denials in the last 7 days` | — |

Both tested prompts produced an **`event_date` partition filter**, which the space's instructions
require — the two tables hold tens of millions of rows a week (21,214 permission changes in the last
day alone here), so an unfiltered query looks broken.

> **Why a PA-specific space rather than reusing DS-08's.** The DS-08 space is grounded on the same
> `system.access.audit` table but instructed toward *notebook* activity. Asked the PA question it
> generated correct SQL and answered *"no permission changes in the last 7 days"* — because it
> filtered `service_name='notebook'`. The data was there: 21,214 rows. Same table, wrong lens.
> Grounding instructions matter as much as table selection, and a plausible wrong answer is worse
> than an error.

Two questions, two tables:

- **Who changed a permission?** `system.access.audit`, `action_name = 'updatePermissions'` — actor,
  securable, and the change itself.
- **Who actually read the sensitive tables?** `system.access.table_lineage`. A grants list says who
  *could*; lineage says who *did*. That distinction is usually the one an auditor cares about.

**⚠️ Always filter on `event_date`** — it is the partition column on both, and they hold tens of
millions of rows per week (53M over 7 days in this workspace). An unfiltered query is slow enough to
look broken.

### An assumed role does not launder your identity

**The question a security reviewer will ask about role switching**, and it deserves a direct answer:
if someone can act as a role, can they hide behind it?

No. `system.access.audit.identity_metadata` is a
`struct<run_by, run_as, acting_resource, run_by_display_name, run_as_display_name>` — `run_by` is the
authenticated human, `run_as` is the role they assumed. Accountability survives the switch, which is
what makes role switching acceptable as a production access pattern rather than a hole in the audit
trail.

```sql
SELECT event_time,
       identity_metadata.run_by  AS run_by,   -- the human
       identity_metadata.run_as  AS run_as,   -- the assumed role
       action_name
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 7 DAYS
  AND identity_metadata.run_as IS NOT NULL
ORDER BY event_time DESC;
```

Returns no rows until someone has actually acted as a role in the window — switch roles, run a
query, wait a few minutes for the audit lag, then re-run.

## PA-06 — Service principals & credential rotation

> **Built:** ✅ · **Prompt:** — n/a

The POC already ships a working example: `engineer/src/apps/grant_app_sp.sh` grants the mock REST
API app's service principal `SELECT` on one table — least privilege for a workload identity, no
human credential involved.

**The rotation argument in one line:** grants attach to the **principal**, not the credential. So
rotating an SP secret is invisible to permissions — exactly what an embedded personal token cannot
offer. Full 5-step procedure, plus the audit query to confirm it, in
[`PA_A_IDENTITY_STRATEGY.md`](PA_A_IDENTITY_STRATEGY.md).

**Expected outcome:** the notebook lists the workspace's service principals and any UC grants held
by a UUID grantee (SP application IDs are UUIDs, so they stand out from user and group grantees).


---

# PA-B / PA-C / PA-D — Data security policies & inventory (PA-07 … PA-12)

**What this group proves:** Oracle FGAC's column- and row-level controls, in Unity Catalog — plus
the ability to inventory every policy and test one *before* rollout.

**Build:** one job, three sequenced tasks — `[<catalog>] PA-B/C/D — Security policies + inventory`.
Masks, then filters, then the inventory that reports on both, so the inventory can never be stale
relative to the policies.

**⚠️ Everything runs on `admin_demo`.** `ALTER TABLE … SET MASK` / `SET ROW FILTER` mutate the
**table object**, so applying either to `silver_dev` would redact and filter for all ~20 session
participants and silently change what the Engineer pipelines read (spec §3.1 rule 4). Every
notebook asserts the foundation stayed clean.

**Prereqs:** `pa_admin_demo_setup` (the copies) and `pa_a_identity_access` (the role → group
mapping the policies branch on).

**Two syntax notes, both verified against the live warehouse** — the plan had the first one wrong:

```sql
ALTER TABLE t ALTER COLUMN c SET MASK fn;        -- correct
ALTER TABLE t SET COLUMN MASK c = fn(c);         -- NOT valid Databricks SQL (the plan's form)
ALTER TABLE t SET ROW FILTER fn ON (c);          -- correct
```

## Generation prompt — PA-07, PA-08

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the mask notebook)

**What it proves:** a masked column is masked for **every** reader through **every** path —
notebook, SQL editor, dashboard, JDBC from a laptop, even `INSERT … SELECT` into another table.
There is no view to bypass and no client setting to change. That is the difference from
application-layer redaction.

**Three graduated treatments**, because "masked" is not one thing:

| Column | Treatment | Faculty sees |
|---|---|---|
| `student.ssn`, `faculty.ssn` | partial | `***-**-6789` — enough to confirm identity |
| `student.dob` | generalisation | `1995-XX-XX` — age analysis still works |
| `financial_aid.amount` | perturbation | rounded to 1,000 — aggregates stay usable |

**PA-08** is the third branch: for any role outside admin/faculty the mask returns **NULL**, not a
`'[REDACTED]'` string. A placeholder still leaks that a value exists and breaks typed clients.

**How to test:** run the job, or `pa_b_column_masking.py` interactively. The PA admin is in the
admin group, so they see **full** values — that is correct, and the reason a naive "did the value
change?" check proves nothing. The role contrast is in PA-D's test harness.

**Expected outcome:** `PASS: PA-B — 3 mask functions, 4 columns masked on admin_demo; admin sees
full values, faculty partial, others NULL; dob parsed across all 3 formats; foundation carries no
policies.`

> **The `dob` trap.** `dob` is a STRING in three mixed formats (`yyyy-MM-dd`, `MM/dd/yyyy`,
> `dd.MM.yyyy`) by design for SE-15. `year(dob)` returns NULL on two of them, so the mask coalesces
> `try_to_date` over all three. Get this wrong and ~67% of "masked" values are silently NULL — which
> looks like a working mask and is actually data loss. An assertion fails on any NULL `dob`.

<details>
<summary><strong>Assistant prompt (generate the masking notebook)</strong> — click to expand</summary>

```text
Write a PySpark notebook that applies Unity Catalog column masks to sensitive columns and proves
they work.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix value ALREADY includes its leading underscore, so concatenate with no separator —
f"{catalog}.silver{suffix}", never f"silver_{suffix}". The bundle passes _dev / _test / "" (empty,
for prod), so an underscore in the f-string breaks qa and prod while passing on dev.

Target <catalog>.admin_demo ONLY — never silver or gold. SET MASK mutates the table object, so
masking the shared foundation would redact for every other user of the workspace.

IMPORTANT — do not collide with the pre-built policies. Name every function you create with a
_prompt suffix (mask_ssn_prompt, filter_by_department_prompt, and so on) and attach nothing to a
table that already has a policy. The pre-built PA-B/PA-C policies are live on admin_demo.student,
admin_demo.faculty and admin_demo.financial_aid, and SET MASK / SET ROW FILTER REPLACE whatever is
there — an unsuffixed generation would silently overwrite the verified baseline we compare against.
If you need a table to attach to, create your own copy first:
CREATE OR REPLACE TABLE admin_demo.student_prompt AS SELECT * FROM <catalog>.silver<suffix>.student


Read widgets "restricted_role" (default "account users") and "admin_group" (default "admins") —
never hardcode either.

Branch on session_user(), NOT is_member(). The restricted identity is reached by RBAC role switching
(workspace menu -> role), and two verified traps make is_member() the wrong predicate — both fail
silently, so the mask looks like it works while proving nothing:
  - a group is not a member of itself: acting as "account users", is_member('account users') is FALSE
  - an assumed role inherits none of the human's memberships: is_member('admins') is FALSE too
session_user() returns the email normally and the role name while a role is assumed. Match the
restricted role FIRST, before any is_member() check can be reached.

1. Capture the unmasked values for a few rows first, so the after-state is a comparison. Read them
   from <catalog>.silver<suffix>.student — the unpolicied foundation — so the cell shows ground truth
   and is safe to re-run after policies are attached.

2. Create three mask functions with graduated treatments — a mask is a FUNCTION applied to a column.
   Each has the same three-branch shape: restricted role -> NULL; admin_group member -> true value;
   everyone else -> partially masked.
   - mask_ssn: NULL for the restricted role; full value for admins; concat('***-**-', right(ssn,4))
     otherwise. Return NULL, not a '[REDACTED]' string — a placeholder still leaks that a value
     exists, and breaks typed columns (financial_aid.amount is a DOUBLE and would error).
   - mask_dob: NULL for the restricted role; full for admins; year only ('YYYY-XX-XX') otherwise.
     dob is a STRING in three formats (yyyy-MM-dd, MM/dd/yyyy, dd.MM.yyyy) and year(dob) returns
     NULL for two of them, so parse with coalesce over try_to_date for all three.
   - mask_amount: NULL for the restricted role; full for admins; round(amount, -3) otherwise.

3. Create your OWN tables to attach to, then mask those — never the live ones:
     CREATE OR REPLACE TABLE <catalog>.admin_demo.student_prompt       AS SELECT * FROM <catalog>.silver<suffix>.student
     CREATE OR REPLACE TABLE <catalog>.admin_demo.faculty_prompt       AS SELECT * FROM <catalog>.silver<suffix>.faculty
     CREATE OR REPLACE TABLE <catalog>.admin_demo.financial_aid_prompt AS SELECT * FROM <catalog>.silver<suffix>.financial_aid
   Attach with ALTER TABLE <t> ALTER COLUMN <c> SET MASK <fn> — that exact form. Do NOT use
   "SET COLUMN MASK c = fn(c)", which is not valid Databricks SQL. DROP MASK first so the notebook
   is re-runnable.
   Mask: student_prompt.ssn, student_prompt.dob, faculty_prompt.ssn, financial_aid_prompt.amount.
   Do NOT touch admin_demo.student / faculty / financial_aid — those carry the verified baseline.

4. Re-run the same query from step 1 against admin_demo.student_prompt to show the governed result.

5. Detect whether the notebook is running AS the restricted role (session_user() == restricted_role)
   and branch: skip policy creation with a clear message, and assert the RESTRICTED outcome instead
   (ssn and dob both NULL). Running as yourself asserts the admin outcome. That makes one notebook
   serve both halves of the demo — apply as admin, then switch roles and re-run to prove enforcement.

6. Assert (admin path): the admin's view is UNCHANGED versus step 1 (if it changed, is_member is
   false and the policy is redacting for everyone); your four masks are attached to the _prompt
   tables, read back from information_schema.column_masks; no mask sits outside admin_demo; and the
   pre-built masks on admin_demo.student / faculty / financial_aid are STILL PRESENT and unchanged
   (4 of them, on student.ssn, student.dob, faculty.ssn, financial_aid.amount) — if any is missing,
   the generation overwrote the verified baseline.

7. For the dob mask, DO NOT test it by counting NULLs in the masked table. As an admin you get the
   unmasked branch, which returns dob untouched, so the coalesce never runs and the check passes even
   when it is broken. Instead evaluate the parse expression directly over every row of
   silver<suffix>.student and assert zero unparseable values:
   sum(CASE WHEN coalesce(try_to_date(dob,'yyyy-MM-dd'), try_to_date(dob,'MM/dd/yyyy'),
   try_to_date(dob,'dd.MM.yyyy')) IS NULL THEN 1 ELSE 0 END) = 0
```

</details>

## PA-07 — Column-level security: masking sensitive fields

> **Built:** ✅ · **Prompt:** 🟡 written (shared prompt above)

**What it proves:** a masked column is masked for **every** reader through **every** path — notebook,
SQL editor, dashboard, JDBC from a laptop, even `INSERT … SELECT` into another table. No view to
bypass, no client setting to change. That is the difference from application-layer redaction.

**Three graduated treatments**, because "masked" is not one thing:

| Column | Treatment | Faculty sees |
|---|---|---|
| `student.ssn`, `faculty.ssn` | partial | `***-**-6789` — enough to confirm identity |
| `student.dob` | generalisation | `1995-XX-XX` — age analysis still works |
| `financial_aid.amount` | perturbation | rounded to 1,000 — aggregates stay usable |

**How to test — both halves, and the second one is the real proof:**

1. **As yourself (admin)** — run the job or the notebook. You see **full** values, which is correct:
   the mask is role-dependent, not blanket redaction. A naive "did the value change?" check proves
   nothing here.
2. **As `account users`** — workspace-name menu → hover the workspace → pick the role, then re-run
   the notebook interactively. It detects the assumed role and switches to its restricted assertions.

**Verified 2026-08-23 in the customer workspace:**

| Run as | `ssn` | `dob` |
|---|---|---|
| `mehak.juneja@databricks.com` (admin) | `565-46-7470` | `03/20/2009` |
| `account users` (assumed role) | **`NULL`** | **`NULL`** |

Admin run printed `PASS: PA-B — 3 mask functions, 4 columns masked on admin_demo; admin sees full
values; all 30,000 dob values parse across the 3 formats; foundation carries no policies.`
Role run printed `PASS (restricted view): acting as 'account users', ssn and dob both return NULL —
PA-08 enforced by Unity Catalog against a real second identity.`

> **The `dob` trap, and a subtler one in how you test it.** `dob` is a STRING in three mixed formats
> (`yyyy-MM-dd`, `MM/dd/yyyy`, `dd.MM.yyyy`) by design for SE-15 — all three are visible in the admin
> row above. `year(dob)` returns NULL on two of them, so the mask coalesces `try_to_date` over all
> three. Get it wrong and ~67% of "masked" values are silently NULL: looks like a working mask, is
> actually data loss.
>
> **Do not test it by counting NULL `dob` in the masked table.** As an admin you get the unmasked
> branch, so the coalesce never runs and the check passes even when completely broken — this was a
> real defect in the first build. Evaluate the parse expression directly over `silver_dev.student`
> instead; the assertion now confirms all **30,000** values parse.

## PA-08 — Column-level security: full column restriction

> **Built:** ✅ · **Prompt:** 🟡 written (shared prompt above)

**What it proves:** restriction is distinct from masking. For any role outside admin/faculty the
mask returns **NULL** — not a `'[REDACTED]'` placeholder.

**Why NULL rather than a string:** a placeholder still leaks that a value *exists*, and it breaks
typed clients — a `DOUBLE` column cannot return `'[REDACTED]'`, so `financial_aid.amount` would
error rather than restrict. NULL is the only treatment that works across types.

**How to test:** the first branch of each mask function, and it is worth testing the real way. The
parameterised twin (`test_mask_ssn_as(ssn, 'account users')` → `NULL`) proves the *branch*; assuming
the role and reading the table proves **enforcement**.

**Verified 2026-08-23 (customer workspace):** acting as `account users`, `admin_demo.student` returned
`ssn = NULL` and `dob = NULL` for every row — no error, and nothing to indicate what was there.

> **This is the assertion that would catch a broken policy.** If the restricted branch were keyed on
> `is_member('account users')` instead of `session_user()`, it would silently never fire — a group is
> not a member of itself, so the check is `false` while acting as the role, and the mask would fall
> through to the *partial* branch. The reader would see `***-**-7470` and the demo would look like it
> worked while PA-08 was not enforced at all.


## Generation prompt — PA-09, PA-10

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the row-filter notebook)

**What it proves:** the same table returns different rows to different readers, enforced at the
table rather than in a WHERE clause someone can forget.

**PA-10 is the one that matters operationally.** A policy with department numbers written into it
needs a code change and a redeploy whenever someone moves department. This one reads a
`department_access` mapping table keyed on **`session_user()`** — so a move is an `INSERT`, and it
takes effect on the next query, for every table the filter is attached to.

> **⚠️ Seed the mapping table with the ROLE NAME, not an email.** While a role is assumed,
> `session_user()` returns `account users`. If the table only holds emails, the filter matches nothing
> and the role sees **zero** rows — which reads as a broken demo rather than a working policy. The
> assertion says so explicitly if it happens.

**How to test — both halves:**

1. **As yourself (admin)** — run the job. Unrestricted (branch 2), and it **inserts one row** into the
   mapping table to show the permitted set widen with no policy edit. That INSERT is PA-10.
2. **As `account users`** — assume the role, re-run the notebook interactively.

**Verified 2026-08-23 (customer workspace):**

| Run as | Rows visible | Departments |
|---|---|---|
| admin | **30,000** of 30,000 | all 40 |
| `account users` | **2,963** (9.9%) | **[5, 12, 24]** only |

2,963 is exactly dept 5 (1,018) + 12 (409) + 24 (1,536) — the mapping table's three rows and nothing
else. Role run printed `PASS (restricted view): acting as 'account users' — 2,963 of 30,000 rows,
departments [5, 12, 24] only (mapped: [5, 12, 24]). PA-09/PA-10 enforced by UC against a real second
identity.`

**Deny by default.** An unmapped principal sees **zero** rows, not everything — asserted, because
"fails open" is the classic row-filter bug.

**Masks and filters compose.** With PA-B and PA-C both applied, the restricted reader saw *fewer rows*
**and** `NULL` columns within them — verified in the same session. Running them in order makes that
stackable behaviour visible.

<details>
<summary><strong>Assistant prompt (generate the row-filter notebook)</strong> — click to expand</summary>

```text
Write a PySpark notebook that applies Unity Catalog row-level security with a policy driven by a
lookup table rather than hardcoded values.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix ALREADY includes its leading underscore — concatenate directly, never f"silver_{suffix}".

Target <catalog>.admin_demo ONLY. SET ROW FILTER mutates the table object, so filtering the shared
foundation would hide rows from every other user — and produce wrong results rather than an error,
which is worse.

IMPORTANT — do not collide with the pre-built policies. Name every function you create with a
_prompt suffix (mask_ssn_prompt, filter_by_department_prompt, and so on) and attach nothing to a
table that already has a policy. The pre-built PA-B/PA-C policies are live on admin_demo.student,
admin_demo.faculty and admin_demo.financial_aid, and SET MASK / SET ROW FILTER REPLACE whatever is
there — an unsuffixed generation would silently overwrite the verified baseline we compare against.
If you need a table to attach to, create your own copy first:
CREATE OR REPLACE TABLE admin_demo.student_prompt AS SELECT * FROM <catalog>.silver<suffix>.student


Read widgets "restricted_role" (default "account users") and "admin_group" (default "admins") —
never hardcode either.

Branch on session_user(), NOT is_member(). The restricted identity is reached by RBAC role switching
(workspace menu -> role), and two verified traps make is_member() wrong here — both fail silently:
  - a group is not a member of itself: acting as "account users", is_member('account users') is FALSE
  - an assumed role inherits none of the human's memberships: is_member('admins') is FALSE too

1. Create a mapping table admin_demo.department_access (principal STRING, dept_id BIGINT,
   granted_by STRING, granted_at TIMESTAMP). This is what makes the policy dynamic — moving someone
   between departments becomes an INSERT, not a policy rewrite.

   Seed the RESTRICTED ROLE (not the current user) to TWO departments, so "filtered" is visibly
   narrower than "all" without being a single row that could be a coincidence. The principal column
   holds whatever session_user() returns, which for an assumed role is the ROLE NAME, not an email.
   Get this wrong and the filter denies every row for the role — which looks like a broken demo
   rather than a working policy.

2. Create a row-filter function returning BOOLEAN, with three branches in precedence order:
   FIRST the restricted role (session_user() = restricted_role) sees only its mapped departments;
   then admin_group members unrestricted; then everyone else sees their own mapped departments, or
   nothing if unmapped. Deny by default — do NOT let an unmapped principal see everything. The
   restricted branch must come first, because is_member() cannot be relied on once a role is assumed.
   A row-filter function MAY contain a subquery against a lookup table.

3. Create your OWN tables to attach to, then filter those — never the live ones:
     CREATE OR REPLACE TABLE <catalog>.admin_demo.student_prompt AS SELECT * FROM <catalog>.silver<suffix>.student
     CREATE OR REPLACE TABLE <catalog>.admin_demo.faculty_prompt AS SELECT * FROM <catalog>.silver<suffix>.faculty
   Attach with ALTER TABLE <t> SET ROW FILTER <fn> ON (dept_id) — that exact form. DROP ROW FILTER
   first so it is re-runnable. Apply to admin_demo.student_prompt and admin_demo.faculty_prompt.
   Do NOT touch admin_demo.student / faculty — those carry the verified baseline.

4. Show what THIS identity sees (count and distinct departments), and print whether the session is
   the admin or the restricted role. Detect the mode with session_user() == restricted_role and skip
   the write cells when acting as the role — it cannot ALTER tables it does not own.

5. Prove the dynamic claim: INSERT one more department into the mapping table and show the row count
   the restricted role may see grow — with the policy function untouched. Evaluate that count as a
   WHERE-clause predicate against the unpolicied foundation, so the number is right regardless of
   which identity runs the cell.

6. Assert, branching on the mode from step 4.
   Admin path: the admin sees ALL rows; the restricted role would see a strict subset (>0 and <all);
   an unmapped principal sees ZERO rows; the INSERT widened access; the filter is attached where
   intended per information_schema.row_filters; and the foundation carries no policies.
   Restricted path: fewer rows than the total, more than zero, and every visible dept_id is one
   mapped to the role. If it sees zero, say in the assertion message that the mapping table probably
   has no row for the role name — that is the failure this design is most likely to hit.
```

</details>

## PA-09 — Row-level security: attribute-based filtering

> **Built:** ✅ · **Prompt:** 🟡 written (shared prompt above)

**What it proves:** the same table returns different rows to different readers, enforced at the
table rather than in a `WHERE` clause someone can forget to add.

The filter is a function returning BOOLEAN, evaluated per row against an attribute — here
`dept_id`. Attached with `ALTER TABLE … SET ROW FILTER fn ON (dept_id)`; the `ON (…)` list supplies
the function's arguments, which is how one function serves several tables.

**How to test:** run the job, or `pa_c_row_filters.py`. Applied to `admin_demo.student` and
`admin_demo.faculty`.

**Expected outcome:** the admin sees all 30,000 rows (unrestricted branch); a mapped identity sees a
strict subset — roughly 1,000 rows across 2 departments.

**Deny by default.** An unmapped principal sees **zero** rows, not everything. Asserted, because
"fails open" is the classic row-filter bug and it is invisible unless you test for it.

## PA-10 — Row-level security: dynamic policy by user identity

> **Built:** ✅ · **Prompt:** 🟡 written (shared prompt above)

**What it proves — and this is the operationally important one.** A policy with department numbers
written into it needs a code change and a redeploy every time someone moves department. This one
reads a `department_access` mapping table keyed on `current_user()`, so a move is an `INSERT` and it
takes effect on the next query, across every table the filter is attached to.

**How to test:** the notebook seeds the running admin to two departments, shows the filtered row
count, then **inserts one row** and shows the visible set widen — with the policy function
untouched. That INSERT is the demonstration; everything else is setup.

**Expected outcome:** `PASS: PA-C — admin unrestricted (30,000 rows); mapped identity sees ~1,000
rows in 2 departments; one INSERT widened that with no policy change; unmapped principals see 0
rows; foundation clean.`

**Grant the mapping table carefully.** Anyone who can write it can widen their own access. It is
readable by the policy and writable only by admins — PA-11 checks exactly that.

**Masks and filters compose.** With PA-07/08 and PA-09/10 both applied, a faculty reader sees
*fewer rows* **and** *masked columns within them*. The job runs them in order so that stacking is
visible rather than accidental.


## Generation prompt — PA-11, PA-12

> **Prompt:** 🟡 written (Assistant — generate the inventory + test notebook)

One notebook covers both scenarios, so one prompt. Each is written up separately below.

**Artifacts:** `pa_d_policy_inventory.py` (asserted) and
[`pa_d_policy_inventory.sql`](src/pa_d_policy_inventory.sql) (reviewable — the form a DBA audits).

<details>
<summary><strong>Assistant prompt (generate the inventory + test notebook)</strong> — click to expand</summary>

```text
Write a PySpark notebook that inventories every Unity Catalog security policy in a catalog and
tests one before rollout.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix ALREADY includes its leading underscore — concatenate directly.

1. Inventory every column mask from <catalog>.information_schema.column_masks (table, column, mask
   function) and every row filter from information_schema.row_filters (table, function,
   target_columns). Use those two views — do NOT loop DESCRIBE EXTENDED over every table, which is
   slow and will miss any table you forgot to list.

2. Show what the policies DO, not just where they are: read routine_name, routine_definition and
   comment from information_schema.routines for the admin_demo schema.

3. The coverage-gap query, which is the one an auditor actually wants: LEFT JOIN
   information_schema.columns to column_masks and list sensitive columns (name matching ssn, dob,
   amount, email) where mask_name IS NULL — i.e. UNPROTECTED. Inventory says what is protected;
   this says what is exposed.

4. Pre-rollout testing, in two mechanisms of increasing strength — label them as such, because
   conflating them overstates what the first one proves.

   (a) Branch logic. There is no impersonation FUNCTION — simulate_principal(), set_session_user()
   and impersonate() all return UNRESOLVED_ROUTINE, and a policy evaluates as the caller. So create a
   test twin of the mask with the identity as a parameter: test_mask_ssn_as(ssn STRING,
   acting_as STRING), same branch logic, and select every treatment side by side. Name it test_* and
   DROP it at the end so it cannot be mistaken for a live policy. For the row filter, count rows for
   three cases: admin (all), the restricted role (subset), an unmapped principal (zero).

   (b) Enforcement. RBAC role switching IS the faux-user mechanism: workspace-name menu -> hover the
   workspace -> pick the role. While assumed, the role is the active SQL identity and UC evaluates
   masks and filters against it. Print session_user() and is_member(admin_group) so the notebook
   records which identity produced its numbers, and document the switch steps in markdown. Do NOT
   claim (a) proves enforcement — it ran as you, with the identity passed in as a string.

5. Check who could REWRITE a policy: query schema_privileges for ALL_PRIVILEGES / CREATE_FUNCTION /
   MODIFY on admin_demo. A principal who can CREATE OR REPLACE the mask function can lift their own
   restriction, and the inventory would still show the policy as attached.

6. Assert: the expected masks and filters are all present; NO policy exists outside admin_demo; no
   sensitive column in admin_demo is unprotected; the three role treatments are genuinely different
   (full value / partial / NULL); an unmapped principal sees zero rows; and the test harness was
   dropped.
```

</details>

## PA-11 — Security policy testing & validation ("faux user")

> **Built:** ✅ · **Prompt:** 🟡 written (shared prompt above)

**What the RFP asks:** before rollout, simulate a Faculty user to confirm they see masked data
correctly — the Oracle "faux user" pattern.

**Databricks has this, and it is RBAC role switching.** There is no impersonation *function* —
`simulate_principal()`, `set_session_user()` and `impersonate()` all return `UNRESOLVED_ROUTINE`
(verified), and a policy evaluates as the caller, so you cannot self-test another identity by calling
something. But you *can* **assume a role**: workspace-name menu → hover the workspace → pick the
role. While assumed, the role is the active SQL identity and UC evaluates grants, masks and row
filters against it.

Two mechanisms, and the distinction matters for what you claim:

| Mechanism | Proves | Needs |
|---|---|---|
| A `test_mask_ssn_as(ssn, acting_as)` twin — same branch logic, identity as an argument | the **branches** are right | nothing; runs alone |
| **Assume the role and re-run PA-B / PA-C** | UC **enforces** it | nothing — no colleague, no service principal |

The first ran as *you*, with the identity passed in as a string — **claiming it proves enforcement
would be overstating it.** The second is the real test, and in this workspace it costs one menu
click.

**How to test:**
1. Run `pa_d_policy_inventory.py` as yourself — mechanism (a), plus the full policy inventory.
2. Switch to the `account users` role and re-run `pa_b_column_masking` and `pa_c_row_filters`. Both
   detect the assumed role and swap to their restricted assertions.
3. Switch back the same way.

**Verified 2026-08-23 (customer workspace) — both mechanisms:**

| | admin | `account users` |
|---|---|---|
| `ssn` | `565-46-7470` | **`NULL`** |
| `dob` | `03/20/2009` | **`NULL`** |
| rows in `student` | 30,000 | **2,963** (depts 5/12/24) |

Enforced by Unity Catalog against a real second identity — not simulated, not a parameterised twin.

> **A third finding worth telling the customer, from the same run.** Reading a table in
> `princeton_poc_prod` — where `account users` holds no `SELECT` at any level — **succeeded** when run
> as the admin. A workspace admin is a metastore admin, and metastore admins **bypass UC grants
> entirely**.
>
> So an admin's own session can never verify a restriction: they are never subject to it. *"I checked
> and it looked restricted"* is not a valid verification, and this is the concrete reason PA-11 needs
> the role switch rather than an admin running the query and eyeballing the result.

The harness is named `test_…` and dropped at the end, so a later inventory cannot mistake it for a
live policy — asserted.

**Also checked: who can *rewrite* a policy.** A restricted principal with `CREATE FUNCTION` or
`MODIFY` on `admin_demo` could `CREATE OR REPLACE` `mask_ssn` and lift its own restriction — and the
inventory would still report the policy as attached. The same argument applies to
`admin_demo.department_access`: write access to the mapping table *is* write access to the row-filter
policy. Expect the owner only.

## PA-12 — Security policy audit & documentation

> **Built:** ✅ · **Prompt:** 🟡 written (shared prompt above)

**What it proves:** the policy catalog is a **table you can query**, not a console screen you
screenshot. Unity Catalog exposes `information_schema.column_masks` and
`information_schema.row_filters`, so an access review is repeatable and cannot miss a table nobody
remembered to check.

**How to test:** run the job, or the queries in
[`src/pa_d_policy_inventory.sql`](src/pa_d_policy_inventory.sql).

**Expected outcome:** 4 masks (`student.ssn`, `student.dob`, `faculty.ssn`,
`financial_aid.amount`) + 2 row filters (`student`, `faculty`), every row in `admin_demo` and none
anywhere else. A row outside `admin_demo` means a policy has leaked onto the shared foundation.

**The query worth showing is not the inventory** — it is the **coverage gap**: sensitive columns
with *no* policy, via a LEFT JOIN from `information_schema.columns`. The usual failure in a
governed estate is not a wrong policy, it is an unprotected table nobody inventoried.

> Read that output honestly: the `silver` rows come back `UNPROTECTED`, and that is **correct**
> here — the shared foundation deliberately carries no policies. In a real deployment those rows
> would be the finding, which is exactly why the check earns its place.

**Expected outcome:** `PASS: PA-D — 4 masks + 2 row filters inventoried, all scoped to admin_demo;
no sensitive column in the sandbox is unprotected; the three role treatments are distinct
(full / partial / NULL); unmapped principals see 0 rows.`


# PA-E — Compute & Capacity Management (PA-13 … PA-18)

**What this group proves:** an administrator can size, isolate, pause, monitor, and prioritize
compute — the operational controls a platform team needs for performance, cost, and availability.

**Build status:** only **PA-17 (capacity dashboard)** is a build object; PA-13/14/15/16/18 are
**admin walkthroughs** (UI / CLI actions, no generated artifact). This runbook gives the RFP ask
+ context for each; the SA fills in the exact click/CLI steps against the target workspace.


**Prereq for PA-17 dashboard:** some query history must exist. Running the E-persona pre-builts
(or any queries) on the workspace populates `system.query.history`, which the dashboard reads.

---

## PA-13 — Scaling compute up/down (manual)


**RFP asks:** *"an administrator manually increases compute capacity to handle a heavy workload,
then scales it back down afterward. Scale operation completes without interrupting active
workloads; new capacity reflected in monitoring; scale-down reclaims resources."*

**Demo flow: - Databricks Demo**
1.  Execute ***SQL Timed Loop Demo*** notebook.  This will execute a 60 sec loop for our testing
2.  Resize the actively running compute to increase cluster capacity while the notebook is running to show no interruption.
3.  View the total running clusters/nodes in the UI
4.  REsize the cluster to reduce the number of clusters/nodes and view the reduction real time in the UI 


**Reference Links:**
***https://docs.databricks.com/api/warehouses/v1/warehouse***
***https://docs.databricks.com/api/clusters/v2/cluster***

**Expected outcome:** warehouse resizes live; the capacity dashboard (PA-17)
reflects the new size / higher throughput; scaling back down reclaims the clusters.



---

## PA-14 — Auto-scaling configuration

**RFP asks:** *"configure the platform to automatically scale compute up when demand exceeds a
threshold and down during idle. Auto-scale triggers under load; scale-down after idle; scaling
events logged with timestamps and trigger reasons."*


**Steps to test:**
1. Open the SQL warehouse ***Serverless Starter Warehouse*** in a tab
2. Open notebook ***PA_14_AUTO_SCALE_UP_DOWN***
3. Execute the notebook
4. Monitor the SQL Warehouse to show clusters scale from 1 to 3 while notebook is running
5. Monitor the SQL Warehouse to show the clusters scale down after about 2-3 mins

**Expected outcome:** under concurrent load the cluster count rises toward max;
after the idle window it drops back toward min; the scaling is visible in the warehouse monitoring
tab.

---

## PA-15 — Compute isolation — workload separation

**RFP asks:** *"different workloads (production pipelines, ad-hoc analyst queries, data science
notebooks) assigned to separate compute pools to prevent contention. Analyst query consuming heavy
resources does not degrade production throughput; assignments visible in admin console."*

**Steps to test:**
1.  This will just be a conversation around how compute works.  

**Expected outcome:** two workloads on two warehouses run without interfering;
warehouse assignment is visible per job/query.


---

## PA-16 — Pause & resume compute resources

**RFP asks:** *"pause a compute resource during a known idle window and resume automatically or on
demand before workloads begin. Paused and resumed without data loss or reconfiguration;
pause/resume events visible in logs."*



**Steps to test:**
1.  Stop warehouse if running
2.  Execute asny query to show that the cluster/warehouse will start automatically.
3.  Highlight the idle timeout on the warehouses and talk about serverless idle time.

**Expected outcome:** warehouse stops and starts cleanly; a query after resume
runs without reconfiguration. 

---

## PA-17 — Capacity dashboard & utilization monitoring  ⭐ BUILD ITEM

**RFP asks:** *"navigate a dashboard showing current compute utilization, historical usage trends,
queue depth, and any throttling events. Displays real-time and historical metrics; admin can
identify peak usage and underutilized windows."*

**Build:** an AI/BI dashboard over **`system.query.history`** (verified table + columns on the POC
workspace). It shows query volume/latency trends, per-user workload, a performance-tier
distribution, and — importantly for the RFP's "queue depth / throttling" ask — the
**`waiting_at_capacity_duration_ms`** and **`waiting_for_compute_duration_ms`** columns, which are
the platform's native queuing/throttling signals.

**Verified dashboard SQL (runs today on princeton_poc — `system.query.history`):**
```sql
-- Daily throughput + latency + queuing by warehouse (last 7 days)
SELECT
  DATE(start_time)                                    AS query_date,
  compute.warehouse_id                                AS warehouse_id,
  COUNT(*)                                            AS query_count,
  ROUND(AVG(total_duration_ms))                       AS avg_total_ms,
  ROUND(percentile(total_duration_ms, 0.95))          AS p95_total_ms,
  ROUND(AVG(waiting_at_capacity_duration_ms))         AS avg_queue_ms,   -- throttling/queue depth
  SUM(CASE WHEN waiting_at_capacity_duration_ms > 0 THEN 1 ELSE 0 END) AS throttled_queries
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 7 DAYS
  AND compute.warehouse_id IS NOT NULL
GROUP BY DATE(start_time), compute.warehouse_id
ORDER BY query_date DESC;

-- Per-user workload (who's driving load)
SELECT executed_by AS user, COUNT(*) query_count,
       ROUND(AVG(total_duration_ms)) avg_ms, SUM(read_rows) total_rows_read
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 7 DAYS
GROUP BY executed_by ORDER BY query_count DESC;

-- Performance-tier distribution (fast / medium / slow)
SELECT CASE WHEN total_duration_ms < 1000 THEN '1 Fast (<1s)'
            WHEN total_duration_ms < 5000 THEN '2 Medium (1-5s)'
            ELSE '3 Slow (>5s)' END AS perf_tier,
       COUNT(*) AS queries
FROM system.query.history
WHERE start_time >= current_timestamp() - INTERVAL 7 DAYS
GROUP BY 1 ORDER BY 1;
```

**Build status:** ✅ **BUILT & deployed** — `admin/src/pa_e_capacity_dashboard.json` +
`admin/resources/pa_e_capacity_dashboard.dashboard.yml` (deploys with the bundle). Verified live
on princeton_poc: dashboard **[princeton_poc] PA-17 Capacity & Utilization**, ACTIVE, all dataset
queries tested against `system.query.history` before deploy.

**Build path:** deploys as an AI/BI dashboard resource with `bundle deploy`, or regenerate via
Genie/Assistant with the prompt below.

<details>
<summary><strong>Genie / Assistant prompt (regenerate the dashboard)</strong></summary>

```text
Build an AI/BI dashboard over system.query.history for the last 30 days showing compute
utilization and capacity: total query count, average + p95 total_duration_ms; hourly query
volume as a line (peaks vs idle windows); a count of throttled queries
(where waiting_at_capacity_duration_ms > 0) as the queue-depth/throttling signal; query count and
avg duration per executed_by user in a table; and a performance-tier bar bucketing total_duration_ms
into Fast (<1s), Medium (1-5s), Slow (>5s).
```
</details>

**Steps to test / demo:**
1. Open the dashboard **[princeton_poc] PA-17 Capacity & Utilization** (Dashboards → search PA-17).
2. Read the four KPIs (total queries, avg + p95 duration, throttled count) and the hourly volume
   line — point out a peak hour vs. an idle window (utilization + historical trend).
3. Show the **Throttled Queries** KPI + per-user table's Throttled column — that's the RFP's
   "queue depth / throttling events." (To make it non-zero, run the PA-14 concurrent-load notebook
   first, then refresh — queued queries appear as throttled.)

**Expected outcome:** dashboard ACTIVE; shows query volume + latency trend, per-user load,
perf-tier split, and the queue/throttle metric; admin can spot peak vs idle windows.

**Notes:** the RFP's "queue depth / throttling events" maps to `waiting_at_capacity_duration_ms`
(time a query waited because the warehouse was at capacity) — a real native signal, no custom
instrumentation.

---

## PA-18 — Workload prioritization & queuing

**RFP asks:** *"configure priority levels for job types or user groups so high-priority workloads
aren't delayed by lower-priority activity during contention. High-priority job runs ahead of
queued lower-priority jobs in a simulated contention scenario; no code change required."*

**Platform capability:** Databricks SQL warehouses queue FIFO per warehouse; prioritization is
achieved by **warehouse separation** (a dedicated higher-capacity warehouse for priority/SLA
workloads) rather than per-query priority hints. Job-level: pin priority jobs to the reserved
warehouse via `warehouse_id`.

---

---

# PA-F — Cost Tracking & Chargeback (PA-19 … PA-25)

**What this group proves:** the platform gives an administrator financial accountability — total
spend, attribution by user/team/pipeline, forecasting, budget alerts, pre-run estimation, and
optimization guidance — all from native cost surfaces (`system.billing.*`, `system.compute.*`).

**Build status:** PA-19/20/21/23 are covered by the stock **Workspace Usage Dashboard V2**
(AI/BI, ships with UC-enabled workspaces). PA-22 is an admin-console **budget** walkthrough.
PA-25 is a built **Genie space** (cost-optimization assistant). PA-24 is an honest **partial**
(native pre-run estimation is limited — EXPLAIN COST + post-run actuals).

> **Attribution depends on tagging.** PA-20/21 slice cost by `custom_tags` / `usage_metadata`.
> The dashboard is fully capable, but the *quality* of user/dept/pipeline attribution depends on
> Princeton applying tags to clusters, warehouses, and jobs. State this plainly — it's a customer
> process input, not a platform gap.

---

## PA-19 / PA-20 / PA-21 / PA-23 — Spend, attribution, forecasting (Usage Dashboard)

**RFP asks:** PA-19 overall spend by cost driver (compute/storage/transfer) over time, exportable ·
PA-20 cost by user/department · PA-21 cost by pipeline/workload · PA-23 spend forecasting (≥30-day horizon).

**Platform capability:** the stock **Workspace Usage Dashboard V2** (AI/BI, over
`system.billing.usage` + `system.billing.list_prices`) covers all four:
- **PA-19** — Usage Overview page: spend over time by product/SKU; compute vs storage vs egress are
  distinct SKUs; export via the dashboard ⋯ menu (CSV/PDF).
- **PA-20** — Tag Matching page: explodes `custom_tags` to attribute cost by department/cost-center.
- **PA-21** — group by `usage_metadata` keys (job/pipeline id) or a `project`/`pipeline` tag.
- **PA-23** — Forecast: uses `AI_FORECAST()` with a configurable horizon (≥30 days) + 90% confidence band.

**Steps to test:**
1. Open **Workspace Usage Dashboard V2** (Dashboards → search "Usage").
2. PA-19: on Usage Overview, show total spend over time and the product/SKU breakdown; export.
3. PA-20: Tag Matching page → pick a tag key (e.g. `department`) → show cost per value.
4. PA-21: group by a pipeline/job tag or `usage_metadata` key.
5. PA-23: show the forecast line + confidence band projecting ≥30 days out.

**Expected outcome:** spend trend + cost-driver breakdown (PA-19), per-tag attribution (PA-20/21),
and a 30-day+ forecast (PA-23) — all from native billing system tables.

**Notes:** PA-20/21 attribution is only as complete as the tags applied to compute/jobs. Verify
compute/storage/transfer appear as separate SKUs when demoing PA-19.

---

## PA-22 — Budget alerts & spending limits

**RFP asks:** *"configure a budget threshold so an alert fires when projected or actual spend
approaches or exceeds a defined limit. Alert fires before the limit is breached; notification
includes current spend, projected spend, and threshold value."*

**Platform capability:** native **Budgets** in the account/usage console — set a spend threshold
with a period + optional filters (workspace, tag, SKU) and email recipients; Databricks alerts on
actual/forecasted spend against the budget.

**Steps to test (walkthrough):**
1. Account console → **Usage → Budgets → Create budget**.
2. Set a period (e.g. monthly), an amount, optional filters (workspace/tag), and alert email(s).
3. Save — show the budget tracking actual vs. threshold; alerts fire as spend approaches the limit.

**Expected outcome:** a budget with an alert threshold; notification includes current + projected
spend vs. the limit. No build — admin-console configuration.

---

## PA-24 — Query & job cost estimation (PARTIAL)

**RFP asks:** *"before executing a large query or pipeline run, show whether the platform can
provide an estimated cost or resource consumption preview. Estimate reasonably aligned with actual
post-run cost."*

**Honest coverage — PARTIAL.** Databricks is primarily a *post-run actuals* platform; there is no
native per-query "this will cost $X" preview. The demonstrable answer:
- **`EXPLAIN COST <query>`** — returns the optimizer's plan **with cost/statistics estimates**
  (estimated row counts + sizes per plan node) *before* execution — the native pre-run resource-shape signal.
- **Query Profile** (post-run) — actual time/rows/memory, which align with the EXPLAIN COST plan.
- **`system.billing.usage`** (post-run) — actual $ cost, closing the estimate-vs-actual loop.

**Steps to test:**
1. Run `EXPLAIN COST <a heavy query>` in the SQL editor → show the estimated statistics per plan node.
2. Execute the query → open **Query Profile** → show actual rows/time/memory align with the estimate.
3. Look the query up in `system.query.history` / `system.billing.usage` → show actual cost.

**Expected outcome:** EXPLAIN COST gives a pre-run resource/statistics estimate; Query Profile +
billing confirm actuals align. Frame PA-24 as **Partial** in the vendor response.

**Note:** for *forward workload* cost planning (size a hypothetical pipeline before writing SQL),
**Lakemeter OSS** (`github.com/databrickslabs/lakemeter-oss`, a Databricks Labs app) provides
pre-run workload estimates with SKU breakdowns. Mentioned as an option; not deployed in this POC.

---

## PA-25 — Cost optimization recommendations (Genie space)  ⭐ BUILD ITEM

**RFP asks:** *"show whether the platform provides automated recommendations for reducing spend —
identifying unused resources, oversized compute, or redundant storage. At least one actionable
recommendation surfaced with an estimated savings value."*

**Build:** a **Genie space** — *[princeton_poc] PA-25 Cost Optimization Assistant*
(`admin/src/pa_f_cost_genie.json`) — grounded on `system.billing.usage`, `system.billing.list_prices`,
and `system.compute.warehouse_events`. Admins ask cost questions in natural language; Genie
generates the SQL, returns spend/attribution, and flags idle/oversized warehouses with savings.
Verified on princeton_poc: "total spend by product last 30 days" → SQL $8.18, JOBS $1.04, DLT
$0.25, APPS $0.10, PredictiveOpt $0.07 (correct USD via the list_prices join).

**Steps to test / demo:**
1. Open the Genie space **[princeton_poc] PA-25 Cost Optimization Assistant**.
2. Ask a starter question: *"What is our total spend in the last 30 days broken down by product?"*
3. Ask an optimization question: *"Which warehouses look idle or underutilized, and what could we save?"* — Genie queries `system.compute.warehouse_events` and surfaces oversized/idle warehouses.
4. Ask an attribution question: *"Break spend down by custom tag."*

**Expected outcome:** Genie answers each in natural language with correct SQL over the billing/compute
system tables, and surfaces at least one actionable optimization with an estimated $ figure.

**Notes:** (1) Also mention **Predictive Optimization** (GA) — automated OPTIMIZE/VACUUM on UC
managed tables — for the RFP's "redundant storage" angle. (2) Honest framing: the Genie space makes
cost analysis *conversational*, but the recommendations are analyst-initiated (AI-mediated query),
not a fully-automated recommendation engine — note as such in the vendor response.
