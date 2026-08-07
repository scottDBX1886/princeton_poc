# Princeton POC — Complete Scenario Tracker

Every individual RFP scenario ID, fanned out (not consolidated), so nothing is missed.
The build *consolidates* many of these into one object (the "Covered by" column), but this
list is the full checklist.

> **Two trackers, two grains — this one is authoritative for _coverage_.**
> - **This file** tracks all 85 RFP **scenario IDs** — what Princeton grades us on (RFP §7).
> - **The [GitHub project board](https://github.com/users/scottDBX1886/projects/2)** tracks
>   the ~33 **build objects** (E1–E11, DS-A…H, BA-A…E, PA-A…F + foundation/apps/#34) — what
>   we actually work on. The "Covered by" column here is the bridge between the two.
> Update both when a build lands: flip the object's board status AND the scenario IDs here.

**Status legend:** ✅ Built & verified · 🟡 Source/prereq built, scenario pending · ⬜ Planned only
**Last updated:** 2026-08-06

**Summary (RFP scenario IDs):** 53 ✅ built-and-verified (E1 SE-04/05/06/07 · E3 SE-08 · E4 SE-10 · E5 SE-11–20 · E6 SE-03/21/22/23 · E7 SE-24/25/26/27 · E8 SE-28/29/30/31/32/33/35 · E9 SE-34 · E10 SE-36/37/38/39 · E11 SE-40/41/42/43 · SE-09 · BA-01…08 · DS-01/02/04/05) · 1 🟡 (DS-03, needs classic compute) · 32 ⬜ planned. **Entire Engineer persona (except parked E2) + entire Business Analyst persona built; Data Scientist in progress (DS-A, DS-B).**
**Total = 86 rows** = 85 RFP IDs + 1 for the split DS-06(a/b). See the per-persona tally at the bottom.

> ⚠️ **Count correction:** we've been loosely calling this "~60 scenarios" — the actual
> RFP catalogue is **85 distinct scenario IDs** (SE 43 + DS 9 + BA 8 + PA 25). The "~30
> built objects" consolidation target still holds; there are just more underlying IDs
> than the round number implied. This tracker is the authoritative full list.

---

## Persona 1 — Software / Data Engineer (SE-01 … SE-43)

### 3.1 Data Source Connectivity & Ingestion
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| SE-01 | Relational DB ingestion — full extract | E2 | ⬜ (BYO-DB parked) |
| SE-02 | Relational DB ingestion — custom SQL (joins/agg/window/proc) | E2 | ⬜ (BYO-DB parked) |
| SE-03 | Incremental / CDC ingestion from a DB source | E6 | ✅ built & verified |
| SE-04 | Flat-file ingestion — CSV & delimited text | E1 | ✅ built & verified |
| SE-05 | Excel workbook ingestion (named sheet) | E1 | ✅ built & verified |
| SE-06 | Semi-structured — JSON (nested) | E1 | ✅ built & verified |
| SE-07 | Semi-structured — XML (repeating/optional nodes) | E1 | ✅ built & verified |
| SE-08 | REST API ingestion — authenticated + paginated | E3 | ✅ built & verified (60k rows, SP-M2M + API OAuth + refresh) |
| SE-09 | SFTP file retrieval and ingestion | (own job) | ✅ built & verified (600 rows) |
| SE-10 | Multi-source pipeline on a single canvas | E4 | ✅ built & verified |

### 3.2 Data Transformation
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| SE-11 | Lookup / reference data enrichment | E5 | ✅ built & verified |
| SE-12 | Join — multiple dataset merge (inner/left/full) | E5 | ✅ built & verified |
| SE-13 | String manipulation functions | E5 | ✅ built & verified |
| SE-14 | Null detection & conditional logic | E5 | ✅ built & verified |
| SE-15 | Date & time handling | E5 | ✅ built & verified |
| SE-16 | Data type casting & validation (reject path) | E5 | ✅ built & verified |
| SE-17 | Aggregation & running totals (control-break) | E5 | ✅ built & verified |
| SE-18 | Pivot — rows↔columns | E5 | ✅ built & verified |
| SE-19 | Last-record-in-group identification | E5 | ✅ built & verified |
| SE-20 | Record loop / iteration over grouped records | E5 | ✅ built & verified |

### 3.3 Slowly Changing Dimensions & Change Capture
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| SE-21 | Type 1 SCD — overwrite | E6 | ✅ built & verified |
| SE-22 | Type 2 SCD — history preservation | E6 | ✅ built & verified |
| SE-23 | Change capture — new/changed/deleted detection | E6 | ✅ built & verified |

### 3.4 Target Loading
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| SE-24 | Insert/update/delete to a DB target (UPSERT) | E7 | ✅ built & verified |
| SE-25 | Flat-file output — CSV / delimited | E7 | ✅ built & verified |
| SE-26 | Excel workbook output | E7 | ✅ built & verified |
| SE-27 | JSON file output | E7 | ✅ built & verified |

### 3.5 Orchestration & Job Management
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| SE-28 | Sequential job chaining (+ variable passing) | E8 | ✅ built & verified |
| SE-29 | Parallel job execution | E8 | ✅ built & verified |
| SE-30 | Scheduled execution (daily/weekly/cron) | E8 | ✅ built & verified |
| SE-31 | Bulk disable / pause of workloads | E8 | ✅ built & verified |
| SE-32 | Automated retry on failure | E8 | ✅ built & verified |
| SE-33 | Failure & completion alerting | E8 | ✅ built & verified |
| SE-34 | Job monitoring dashboard | E9 | ✅ built & verified |
| SE-35 | Calling external processes | E8 | ✅ built & verified |

### 3.6 DevOps, CI/CD & Environment Promotion
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| SE-36 | Source control integration | E10 | ✅ built & verified |
| SE-37 | Promotion across environments | E10 | ✅ built & verified (dev/qa/prod all validate) |
| SE-38 | CI/CD pipeline integration | E10 | ✅ built & verified (GitHub Actions workflow) |
| SE-39 | Rollback of a failed deployment | E10 | ✅ built & verified (git revert / tag redeploy) |

### 3.7 Data Observability & Governance
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| SE-40 | Data lineage — end-to-end tracing | E11 | ✅ built & verified (system.access.table_lineage) |
| SE-41 | Schema drift detection | E11 | ✅ built & verified (Delta DESCRIBE HISTORY, wksp-safe) |
| SE-42 | Data drift / anomaly detection | E11 | ✅ built & verified (Lakehouse Monitoring on the fact) |
| SE-43 | Automated documentation | E11 | ✅ built & verified (Catalog discovery + AI comments) |

---

## Persona 2 — Data Scientist / Advanced Analyst (DS-01 … DS-09)
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| DS-01 | SQL-based data exploration | DS-A | ✅ built & verified |
| DS-02 | Notebook environment — Python | DS-B | ✅ built & verified (pandas round-trip, 9711 rows) |
| DS-03 | Notebook environment — R | DS-B | 🟡 built (sparklyr); needs a classic cluster to run — not yet executed |
| DS-04 | Bring your own data — ad-hoc file upload | DS-B | ✅ built & verified (40 depts, 5 matched, per-user upload path) |
| DS-05 | Large dataset handling | DS-C | ✅ built & verified (5M rows -> 960 groups in 1.93s on Photon) |
| DS-06(a) | Connectivity from local environment (Python/R/SAS/SPSS) | DS-D | ⬜ |
| DS-06(b) | In-platform ML model training | DS-E | ⬜ |
| DS-07 | Scheduling/operationalizing a notebook or script | DS-F | ⬜ |
| DS-08 | Version control for analytical code | DS-G | ⬜ |
| DS-09 | Visualization & charting within the platform | DS-H | ⬜ |

> **RFP anomaly:** DS-06 is duplicated in the RFP (used for both "local connectivity" and
> "in-platform ML"). Split here as DS-06(a)/(b); flag to Princeton in the read-out.

---

## Persona 3 — Business Analyst (BA-01 … BA-08)
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| BA-01 | No-code / low-code data browsing | BA-A | ✅ built & verified |
| BA-02 | Pre-built report or dataset subscription | BA-B | ✅ built & verified |
| BA-03 | Ad-hoc data extract to flat file or Excel | BA-C | ✅ built & verified |
| BA-04 | Upload and join a spreadsheet to platform data | BA-D | ✅ built & verified |
| BA-05 | Light transformation — rename/filter/derived field | BA-D | ✅ built & verified |
| BA-06 | Output to Excel workbook with formatting | BA-C | ✅ built & verified |
| BA-07 | Output to flat file for external distribution | BA-C | ✅ built & verified |
| BA-08 | Reuse and save a self-service workflow | BA-E | ✅ built & verified |

---

## Persona 4 — Platform Administrator (PA-01 … PA-25)

### 6.1 User & Group Access Management
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| PA-01 | User provisioning & role assignment | PA-A | ⬜ |
| PA-02 | Group-based access control | PA-A | ⬜ |
| PA-03 | Environment-level access segregation | PA-A | ⬜ |
| PA-04 | Source & target object-level permissions | PA-A | ⬜ |
| PA-05 | Permission audit trail | PA-A | ⬜ |
| PA-06 | Service account & API credential management | PA-A | ⬜ (grant_app_sp.sh pattern ✅ exists) |

### 6.2 Row-Level & Column-Level Security
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| PA-07 | Column-level security — masking sensitive fields | PA-B | ⬜ (runs on admin_demo copies) |
| PA-08 | Column-level security — full column restriction | PA-B | ⬜ (runs on admin_demo copies) |
| PA-09 | Row-level security — attribute-based filtering | PA-C | ⬜ (runs on admin_demo copies) |
| PA-10 | Row-level security — dynamic policy by user identity | PA-C | ⬜ (runs on admin_demo copies) |
| PA-11 | Security policy testing & validation ("faux user") | PA-D | ⬜ |
| PA-12 | Security policy audit & documentation | PA-D | ⬜ |

### 6.3 Compute & Capacity Management
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| PA-13 | Scaling compute up/down — manual | PA-E | ⬜ |
| PA-14 | Auto-scaling configuration | PA-E | ⬜ |
| PA-15 | Compute isolation — workload separation | PA-E | ⬜ |
| PA-16 | Pause & resume compute resources | PA-E | ⬜ |
| PA-17 | Capacity dashboard & utilization monitoring | PA-E | ⬜ |
| PA-18 | Workload prioritization & queuing | PA-E | ⬜ |

### 6.4 Cost Tracking & Chargeback
| ID | Scenario | Covered by | Status |
|----|----------|-----------|--------|
| PA-19 | Spend dashboard — overall platform cost | PA-F | ⬜ |
| PA-20 | Cost distribution by user or department | PA-F | ⬜ |
| PA-21 | Cost distribution by pipeline or workload | PA-F | ⬜ |
| PA-22 | Budget alerts & spending limits | PA-F | ⬜ |
| PA-23 | Spend forecasting | PA-F | ⬜ |
| PA-24 | Query & job cost estimation | PA-F | ⬜ |
| PA-25 | Cost optimization recommendations | PA-F | ⬜ |

---

## Cross-cutting
| Item | Status |
|------|--------|
| Shared data foundation (all layers + source files) | ✅ built & verified |
| Mock REST API app (SE-08 source) | ✅ deployed & running (E3 verified against it, 60k rows) |
| SFTP server + retrieval (SE-09) | ✅ built & verified |
| Multi-user isolation (issue #34) | 🟡 designed; code retrofit pending |
| Demonstration runbook | 🟡 in progress — Engineer persona fully testable (Phase 0 + E1/E3/E4/E5/E6/E7/SE-09 entries done, copy-paste prompts + coverage map); DS/BA/PA entries pending |

---

## Tally by persona
| Persona | Total IDs | ✅ | 🟡 | ⬜ |
|---------|-----------|----|----|----|
| Engineer (SE) | 43 | 41 (SE-03…43 except SE-01/02) | 0 | 2 (SE-01/02, E2 parked) |
| Data Scientist (DS) | 10* | 4 (DS-01/02/04/05) | 1 (DS-03) | 5 |
| Business Analyst (BA) | 8 | 8 (BA-01…08) | 0 | 0 |
| Admin (PA) | 25 | 0 | 0 | 25 |
| **Total** | **86** | **53** | **1** | **32** |

*DS counts the duplicated DS-06 as two (a/b). SE total 43, DS 10, BA 8, PA 25 = 86 rows here
(the RFP's ~60 headline counts DS-06 once and reflects the catalogue's own numbering).
