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
   Only **account-level** groups (`type=Group`) can hold UC privileges. With no account-admin
   rights here, PA-A maps each RFP role onto an account group that already exists.
2. **Grants need MANAGE on the securable.** `princeton_poc_dev` is owned by another user, so
   catalog-scoped grants return `PERMISSION_DENIED`. PA-A therefore grants at **`admin_demo`
   scope**, which the PA admin owns — and which is where spec §3.1 requires PA security scenarios
   to operate anyway. The constraint and the design agree.

**Policy checks use `is_member()`, not `is_account_group_member()`.** The account-level function
cannot see workspace groups, so a mask written against it redacts for *everyone including the
admin* while appearing to work. `is_member()` resolves both group types.

## Role → group mapping

| RFP role | Account group used | PA admin a member? |
|---|---|---|
| admin | `dbx_demo_shared_admins` | **yes** |
| faculty | `data_engineers_demo_group` | no |
| student | `dbx_demo_shared_dev_group` | no |

**Say this mapping out loud in the demo.** The group names are inherited from the shared workspace,
not chosen. In Princeton's own tenancy these would be `princeton_admins` / `_faculty` / `_students`,
provisioned by SCIM from their IdP — the pattern is identical, only the names and the group-check
function change.

The membership column is what makes PA-B's masking demo real: the admin sees unmasked `ssn`, the
other two roles demonstrably do not. Nothing is staged.

## PA-01 / PA-02 / PA-04 — provisioning, group-based access, object-level permissions

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the grants notebook)

<details>
<summary><strong>Assistant prompt (generate the identity & access notebook)</strong> — click to expand</summary>

```text
Write a PySpark notebook that sets up role-based access control in Unity Catalog and proves it works.

Read two widgets: "catalog" (default princeton_poc_dev) and "schema_suffix" (default _dev). The
suffix value ALREADY includes its leading underscore, so concatenate with no separator —
f"{catalog}.silver{suffix}", never f"silver_{suffix}". The bundle passes _dev / _test / "" (empty,
for prod), so an underscore in the f-string breaks qa and prod while passing on dev.

Two hard constraints — get these wrong and it fails at runtime in ways that look like other things:

1. Unity Catalog will NOT grant to a workspace-local group. Groups created in a workspace are SCIM
   type=WorkspaceGroup and GRANT returns PRINCIPAL_DOES_NOT_EXIST. Only ACCOUNT-level groups
   (type=Group) can hold UC privileges. So do NOT create groups — discover the existing
   account-level ones with the SDK (w.groups.list(), keep those where meta.resource_type == "Group")
   and map the three RFP roles onto them.
2. GRANT needs MANAGE on the securable. Grant at <catalog>.admin_demo scope, NOT catalog scope —
   the admin owns admin_demo but not the catalog, and catalog-scoped grants return
   PERMISSION_DENIED.

GRANT is additive, so re-granting what the pre-built already applied is a harmless no-op — but do
NOT issue any REVOKE, which would tear down the verified baseline we compare against.

GRANT is additive, so re-granting what the pre-built already applied is a harmless no-op — but do
NOT issue any REVOKE, which would tear down the verified baseline.

Steps:
1. Map three roles — admin, faculty, student — onto account-level groups. For each, print whether
   it is UC-grantable and whether is_member('<group>') is true for the caller. Use is_member(), NOT
   is_account_group_member(): the account-level function cannot see workspace groups and would make
   every downstream mask redact for everyone including the admin.
2. Grant on <catalog>.admin_demo: ALL PRIVILEGES to admin; USE SCHEMA + SELECT to faculty; and for
   student, USE SCHEMA on the schema plus SELECT on ONLY the admin_demo.student table — no
   schema-wide SELECT. That narrower grant IS the object-level-permissions scenario.
3. Read the effective grants back from information_schema. Note the column names differ:
   schema_privileges uses schema_name, table_privileges uses table_schema. Mixing them gives
   UNRESOLVED_COLUMN.
4. Assert: every role maps to a UC-grantable group; is_member() is true for the admin role (else the
   masking demo has no authorised reader); is_member() is FALSE for at least one other role (else
   there is no contrast to demonstrate); each role holds a privilege on admin_demo; and the student
   role does NOT hold schema-wide SELECT.
```

</details>

### PA-01 — provisioning

**How to test:** run the job, or the notebook interactively. It reports, per role, whether the group
is UC-grantable and whether `is_member()` resolves for the caller.

Provisioning a person is then a **membership change only** — no grants are edited:
**Settings → Identity and access → Groups** → add the user. Verify as them:
`SELECT is_member('data_engineers_demo_group')` → `true`.

**⚠️ Membership is cached.** After a group change, `is_member()` kept returning the old answer for
30+ seconds. Make membership changes a few minutes before you need them on screen — do not remove
someone from a group live and expect the next query to redact.

## PA-02 — Group-based access control

> **Built:** ✅ · **Prompt:** — n/a

**What it proves:** every grant targets a group. Onboarding is a membership change; offboarding
revokes everything at once, because nothing was ever granted to an individual.

**Expected outcome:** `admin_demo` shows `ALL PRIVILEGES` for the admin group, `USE_SCHEMA` +
`SELECT` for faculty, and `USE_SCHEMA` only for the student group.

## PA-03 — Environment-level access segregation

> **Built:** 🟡 model demonstrated, not applied · **Prompt:** — n/a

Environments are separate **catalogs** — `princeton_poc_dev`, `_test`, `_qa`, `princeton_poc` — in
one workspace. `USE CATALOG` gates everything beneath it, so withholding it is absolute: there is
no schema-level way around a missing catalog grant.

**Why 🟡:** applying catalog-scoped grants needs MANAGE on the catalog, which the PA admin does not
hold here. The notebook demonstrates the model by reading the live catalog grant state; applying it
per environment is a one-line `GRANT` for the catalog owner.

## PA-04 — Object-level permissions

> **Built:** ✅ · **Prompt:** — n/a

**The demonstration is the student role.** It gets `USE_SCHEMA` on `admin_demo` but **no
schema-wide `SELECT`** — just `SELECT` on `admin_demo.student`. No grant on `faculty` or
`financial_aid` means no access to them at all. An assertion fails if schema-wide SELECT ever leaks
in, because that would silently widen access and still look like a pass.

**Expected outcome:** `information_schema.table_privileges` shows the student group with exactly one
table grant.

> Column name gotcha: `schema_privileges` uses **`schema_name`**; `table_privileges` uses
> **`table_schema`**. Mixing them up gives `UNRESOLVED_COLUMN`.

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

## PA-07 / PA-08 — Column masking and full column restriction

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


Use is_member('<group>') for the role checks, NOT is_account_group_member(). The account-level
function cannot see workspace groups and would make every branch fall through to the ELSE —
redacting for everyone including the admin, which looks like it works and proves nothing.
Groups: admin = dbx_demo_shared_admins, faculty = data_engineers_demo_group.

1. Capture the unmasked values for a few rows first, so the after-state is a comparison.

2. Create three mask functions with graduated treatments — a mask is a FUNCTION applied to a column:
   - mask_ssn: full value for admin; concat('***-**-', right(ssn,4)) for faculty; NULL otherwise.
     Return NULL, not a '[REDACTED]' string — a placeholder still leaks that a value exists and
     breaks typed clients.
   - mask_dob: full for admin; year only ('YYYY-XX-XX') for faculty; NULL otherwise. dob is a STRING
     in three formats (yyyy-MM-dd, MM/dd/yyyy, dd.MM.yyyy) and year(dob) returns NULL for two of
     them, so parse with coalesce over try_to_date for all three.
   - mask_amount: full for admin; round(amount, -3) for faculty; NULL otherwise.

3. Attach them with ALTER TABLE <t> ALTER COLUMN <c> SET MASK <fn> — that exact form. Do NOT use
   "SET COLUMN MASK c = fn(c)", which is not valid Databricks SQL. DROP MASK first so the notebook
   is re-runnable.
   Mask: student.ssn, student.dob, faculty.ssn, financial_aid.amount.

4. Re-run the same query from step 1 to show the governed result.

5. Assert: the admin's view is UNCHANGED (if it changed, is_member is false and the policy is
   redacting for everyone); every intended mask is actually attached, read back from
   information_schema.column_masks; zero rows have NULL dob after masking; and the shared foundation
   carries no masks or row filters at all.
```

</details>

## PA-09 / PA-10 — Row-level security, static and dynamic

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the row-filter notebook)

**What it proves:** the same table returns different rows to different readers, enforced at the
table rather than in a WHERE clause someone can forget.

**PA-10 is the one that matters operationally.** A policy with department numbers written into it
needs a code change and a redeploy whenever someone moves department. This one reads a
`department_access` mapping table keyed on `current_user()` — so a move is an `INSERT`, and it takes
effect on the next query, for every table the filter is attached to.

**How to test:** run the job, or `pa_c_row_filters.py`. It seeds the running admin to two
departments, shows the filtered row count, then **inserts one row** and shows the visible set widen
— with no policy edit. That INSERT is the demonstration.

**Expected outcome:** `PASS: PA-C — admin unrestricted (30,000 rows); mapped identity sees ~1,000
rows in 2 departments; one INSERT widened that with no policy change (PA-10); unmapped principals
see 0 rows; foundation clean.`

**Deny by default.** An unmapped principal sees **zero** rows, not everything — asserted, because
"fails open" is the classic row-filter bug.

**Masks and filters compose.** With PA-B and PA-C both applied, a faculty reader sees *fewer rows*
**and** *masked columns within them*. Running them in order makes that stackable behaviour visible.

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


Use is_member(), not is_account_group_member(). Admin group = dbx_demo_shared_admins.

1. Create a mapping table admin_demo.department_access (principal STRING, dept_id BIGINT,
   granted_by STRING, granted_at TIMESTAMP). This is what makes the policy dynamic — moving someone
   between departments becomes an INSERT, not a policy rewrite. Seed the current user to TWO
   departments, so "filtered" is visibly narrower than "all" without being a single row that could
   be a coincidence.

2. Create a row-filter function returning BOOLEAN, with three branches in precedence order:
   admins unrestricted; anyone whose principal matches current_user() in department_access sees
   their mapped departments; everyone else sees nothing. Deny by default — do NOT let an unmapped
   principal see everything. A row-filter function MAY contain a subquery against a lookup table.
   Also match on is_member(principal), so the mapping table can name a GROUP as well as a user.

3. Attach it with ALTER TABLE <t> SET ROW FILTER <fn> ON (dept_id) — that exact form. DROP ROW
   FILTER first so it is re-runnable. Apply to admin_demo.student and admin_demo.faculty.

4. Show the admin's row count (unrestricted), then evaluate what a mapped non-admin would see by
   applying the same predicate as a WHERE clause. You cannot become another user mid-notebook, so
   evaluate the predicate rather than pretending to impersonate.

5. Prove the dynamic claim: INSERT one more department into the mapping table and show the visible
   row count grow — with the policy function untouched.

6. Assert: the admin sees ALL rows; a mapped identity sees a strict subset; the department count
   matches the mapping table; the INSERT widened access; an unmapped principal sees ZERO rows; the
   filter is attached where intended per information_schema.row_filters; and the foundation carries
   no policies.
```

</details>

## PA-11 / PA-12 — Policy testing & inventory

> **Built:** ✅ · **Prompt:** 🟡 written (Assistant — generate the inventory notebook)

**Artifacts:** `pa_d_policy_inventory.py` (asserted) and
[`pa_d_policy_inventory.sql`](src/pa_d_policy_inventory.sql) (reviewable — the form a DBA audits).

### PA-12 — the inventory is a table, not a console screen

Unity Catalog exposes `information_schema.column_masks` and `information_schema.row_filters`. That
*is* the scenario: policy coverage is queryable, so an access review is repeatable and cannot miss a
table nobody remembered.

**Expected:** 4 masks + 2 row filters, every row in `admin_demo` and none anywhere else.

**The query worth showing** is not the inventory but the **coverage gap** — sensitive columns with
*no* policy. The usual failure in a governed estate isn't a wrong policy, it's an unprotected table
nobody inventoried.

> Read that output honestly: the `silver` rows come back `UNPROTECTED`, and that is **correct here**
> — the shared foundation deliberately carries no policies. In a real deployment those rows would
> be the finding, which is why the check earns its place.

### PA-11 — there is no impersonation function

The plan suggested `simulate_principal()` via UCX. **It does not exist** — verified, along with
`set_session_user()` and `impersonate()`; all return `UNRESOLVED_ROUTINE`. A UC policy is evaluated
as the **caller**, so no single session can self-test another identity.

Two honest mechanisms, and the distinction matters for what you claim:

1. **Evaluate the policy logic** — a `test_mask_ssn_as(ssn, role)` twin with the role
   parameterised instead of an `is_member()` call. Same branch logic, all three treatments in one
   query, runnable before anything is attached. **Proves the branches are right.**
2. **Have a second real principal run the query** and confirm the audit trail records their read.
   **Proves UC enforces it.**

(1) is in the notebook and is what you can do alone. (2) is stronger, needs a colleague, and is
documented in the SQL file as a pre-session checklist item. Claiming (1) proves enforcement would
be overstating it — worth saying plainly in the read-out.

The harness is named `test_…` and dropped at the end, so it can never be mistaken for a live policy.

**Also checked:** who can *rewrite* a policy. A faculty principal with `CREATE FUNCTION` on
`admin_demo` could replace `mask_ssn` and lift their own restriction — the policy would still show
as "attached" while doing nothing. Expect the admin group only.

**Expected outcome:** `PASS: PA-D — 4 masks + 2 row filters inventoried, all scoped to admin_demo;
no sensitive column in the sandbox is unprotected; the three role treatments are distinct
(full / partial / NULL); unmapped principals see 0 rows.`

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

4. Pre-rollout testing. There is NO impersonation function in Databricks — simulate_principal(),
   set_session_user() and impersonate() do not exist, and a policy is evaluated as the caller. So
   instead create a test twin of the mask with the role as a parameter:
   test_mask_ssn_as(ssn STRING, role STRING), same branch logic, and select all three treatments
   side by side. Name it test_* and DROP it at the end so it cannot be mistaken for a live policy.
   For the row filter, count rows for three cases: admin (all), a mapped identity (subset), and an
   unmapped principal (zero).

5. Check who could REWRITE a policy: query schema_privileges for ALL_PRIVILEGES / CREATE_FUNCTION /
   MODIFY on admin_demo. A principal who can CREATE OR REPLACE the mask function can lift their own
   restriction, and the inventory would still show the policy as attached.

6. Assert: the expected masks and filters are all present; NO policy exists outside admin_demo; no
   sensitive column in admin_demo is unprotected; the three role treatments are genuinely different
   (full value / partial / NULL); an unmapped principal sees zero rows; and the test harness was
   dropped.
```

</details>

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
