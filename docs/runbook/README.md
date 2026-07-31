# Princeton POC — Demonstration Runbook

Hand-to-the-DMIA-team playbook for running each RFP scenario live. Grows one entry per
scenario/combination as each build phase completes. Each entry gives the no-code path
(Lakeflow Designer / Genie prompt), the code path (Databricks Assistant prompt), the
pre-built fallback object, and the expected outcome.

---

## Phase 0 — Stand up the shared data foundation

Every scenario runs against this one dataset. Build it once per workspace.

**Prerequisites:** `docs/CONFIG.md` values filled in (`storage_root`, `warehouse_id`);
`--profile` chosen.

**Build:**
```bash
databricks bundle validate --strict -t dev --profile <PROFILE>
databricks bundle deploy  -t dev --profile <PROFILE>   # creates catalog/schemas/volume + the job
databricks bundle run foundation_build -t dev --profile <PROFILE>   # generates all data + files
```

**Verify (assert query):**
```sql
SELECT
  (SELECT count(*) FROM princeton_poc.silver.student)            AS students,       -- ~30000
  (SELECT count(*) FROM princeton_poc.gold.enrollment_history)   AS fact_rows,      -- = row_count
  (SELECT count(*) FROM princeton_poc.silver.financial_aid)      AS aid_rows;       -- ~50000
```
And confirm the five source files landed:
```bash
databricks fs ls dbfs:/Volumes/princeton_poc/landing/files --profile <PROFILE>
# expect: students.csv, enrollments.pipe.txt, financial_aid.xlsx, course_catalog.json, faculty.xml
```

---

## Demo-time: CDC / SCD / schema-drift (SE-03, SE-21, SE-22, SE-23, SE-41)

These are triggered by the **standalone day-2 change script** — run it live during the
session, then show the platform detecting exactly the planted changes.

**Step 1 — note the current table version (the CDF floor):**
```sql
DESCRIBE HISTORY princeton_poc.silver.student LIMIT 1;   -- note the version number
```

**Step 2 — apply the day-2 changes** (`src/foundation/40_day2_changes.sql`): run the
script. It plants **10 inserts, 20 updates, 5 deletes, and adds one column.**

**Step 3 — show the platform detected them (CDF):**
```sql
SELECT _change_type, count(*)
FROM table_changes('princeton_poc.silver.student', <version_from_step_1>)
GROUP BY _change_type;
-- Expect: insert=10, update_preimage=20, update_postimage=20, delete=5
```
The known counts ARE the proof: "the platform detected exactly the changes we planted."

**Schema drift (SE-41):** the `ALTER TABLE ... ADD COLUMN citizenship` in the same script
is the drift event — show it surfaced in Catalog Explorer / the pipeline's schema view.

---

## Persona scenario entries

_Appended as Phases 1–4 are built. Each entry:_
- **Scenario ID(s) + title**
- **What it proves**
- **No-code path** (Lakeflow Designer / Genie prompt to paste)
- **Code path** (Databricks Assistant prompt to paste)
- **Pre-built fallback** (object to run if a prompt drifts)
- **Expected outcome** (from the RFP) + how to verify

_(Phase 1 Engineer, Phase 2 Data Scientist, Phase 3 Business Analyst, Phase 4 Admin — TBD as built.)_
