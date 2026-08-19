# Princeton POC — Demonstration Runbook (index)

Hand-to-the-DMIA-team playbook for running each RFP scenario live. **The runbook is split per
persona** — each lives in its own folder next to that persona's code:

| Runbook | Covers | Prereq |
|---------|--------|--------|
| [`foundation/RUNBOOK.md`](../../foundation/RUNBOOK.md) | Phase 0 — build & verify the shared dataset; new-workspace deploy; day-2 CDC/drift demo | — (build first) |
| [`engineer/RUNBOOK.md`](../../engineer/RUNBOOK.md) | Software/Data Engineer: E1–E11 + SE-09 + SA pre-flight & checklist | foundation |
| [`businessanalyst/RUNBOOK.md`](../../businessanalyst/RUNBOOK.md) | Business Analyst: BA-01…08 (Genie, AI/BI, Designer) | foundation |
| [`datascientist/RUNBOOK.md`](../../datascientist/RUNBOOK.md) | Data Scientist: DS-01…09 (owned by DS team) | foundation |
| [`admin/RUNBOOK.md`](../../admin/RUNBOOK.md) | Platform Administrator: PA-01…25 (runs on `admin_demo`) | foundation |

> **New here?** Build [`foundation/RUNBOOK.md`](../../foundation/RUNBOOK.md) first, then open the
> persona runbook you're testing. Per-scenario status (built + prompt-tested) lives in
> [`docs/SCENARIO_TRACKER.md`](../SCENARIO_TRACKER.md).

---

## Build-item → scenario coverage map

Each runbook entry (build object) covers several RFP scenario IDs. This is the bridge from
"what you run" to "what Princeton grades" (RFP §7). The authoritative per-ID checklist lives
in [`docs/SCENARIO_TRACKER.md`](../SCENARIO_TRACKER.md); this table is the runbook-facing
summary. **Status:** ✅ built & verified · 🟡 partial/prereq only · ⬜ planned.

| Build item | RFP scenario IDs | Capability | Status |
|-----------|------------------|-----------|--------|
| **Foundation** | — (shared dataset) | Higher-ed data across bronze/silver/gold + 5 source files | ✅ |
| **E1** — Multi-format file ingestion | SE-04, SE-05, SE-06, SE-07 | CSV/delimited, Excel (named sheet), nested JSON, XML | ✅ |
| **E3** — REST API ingestion | SE-08 | OAuth 2.0 + pagination + token refresh | ✅ |
| **E4** — Multi-source merge | SE-10 | Reconcile file + API + DB on one key | ✅ |
| **E5** — Transformation kitchen-sink | SE-11 … SE-20 | Lookup, joins, strings, nulls, dates, cast/reject, running totals, pivot, last-in-group, iteration | ✅ |
| **E6** — CDC + SCD | SE-03, SE-21, SE-22, SE-23 | Change capture + SCD Type 1 & Type 2 (snapshot diff) | ✅ |
| **E7** — Target loading | SE-24, SE-25, SE-26, SE-27 | UPSERT + hard-delete; CSV/pipe/JSON/Excel export | ✅ |
| **SE-09** — SFTP retrieval & ingestion | SE-09 | Pattern-matched SFTP pull → Volume → Auto Loader (no shell script) | ✅ |
| **E2** — Relational DB ingestion | SE-01, SE-02 | Full extract + custom SQL (BYO-DB) | ⬜ parked |
| **E8** — Orchestration | SE-28, SE-29, SE-30, SE-31, SE-32, SE-33, SE-35 | Sequential/parallel/scheduled jobs, retry, alerting, external calls | ✅ |
| **E9** — Workload monitoring | SE-34 | AI/BI dashboard over jobs + pipelines + notebook runs (system tables) | ✅ |
| **E10** — DevOps / CI-CD | SE-36, SE-37, SE-38, SE-39 | Source control, env promotion, CI/CD, rollback | ✅ |
| **E11** — Observability & governance | SE-40, SE-41, SE-42, SE-43 | Lineage, schema drift, data drift, auto-docs | ✅ |
| **DS-A … DS-H** — Data Scientist | DS-01 … DS-09 | SQL/NL exploration, notebooks (Py/R), BYO-data, large data, local connect, ML, scheduling, version control, viz | ✅ (DS-03 🟡 needs classic R cluster) |
| **BA-A … BA-E** — Business Analyst | BA-01 … BA-08 | No-code browse (Genie), subscriptions (AI/BI), Designer + Genie-agent flows for extract/upload+join/transform, saved workflow | ✅ |
| **PA-A … PA-F** — Platform Admin | PA-01 … PA-25 | Access mgmt, column/row security, compute/capacity, cost/chargeback | ⬜ |

**Coverage so far: 49 of 85 RFP scenario IDs ✅ built & verified** — the **entire Engineer
persona except the parked E2 (BYO-DB, SE-01/02)** (ingestion, transformation, CDC/SCD,
target-loading, orchestration, monitoring, DevOps, governance) **plus the entire Business
Analyst persona (BA-01…08)** (no-code browse, subscriptions, extracts, upload+join+transform,
saved workflow). Remaining work is E2 (parked) plus the Data Scientist and Admin personas.

---

## Running this with a group (multi-user sessions)

These runbooks are run by **~20+ participants concurrently, per-person**. To avoid
collisions:
- The **foundation is read-only** — nobody writes to `silver_dev` / `gold_dev` or the
  landing source files. Browse/query/Genie/AI-BI/REST are all safe to run concurrently.
- **Scenarios that create objects write to your own per-person schema**
  `princeton_poc_dev.wksp_<your_user>` (notebooks derive it automatically from
  `current_user()`), so your outputs never clash with anyone else's.
- **Admin (PA) scenarios are performed by one designated person for the whole group**,
  against a dedicated `admin_demo` schema (copies of the sensitive tables) — so masking/
  RLS demos don't change what everyone else sees.
- **Compute:** the session uses an autoscaling SQL warehouse (or serverless) sized for
  concurrency; heavy scenarios (DS-05, PA-13…18) route through it.

> **Status of already-built items** (safe for a group session unless noted): E1, E3, E5,
> and SE-09 are all built and write to per-person `wksp_<user>` schemas — except the SE-09
> job, which currently writes a shared `bronze_dev.sftp_financial_aid` table and will get
> the `wksp_<user>` retrofit before a concurrent group session (fine as-is for a solo/paired
> walkthrough).

---
