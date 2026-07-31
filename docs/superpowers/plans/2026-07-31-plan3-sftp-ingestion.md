# Princeton POC — Plan 3: SFTP Retrieval & Ingestion (SE-09) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Demonstrate native, script-free SFTP retrieval — connect to an SFTP server, pull pattern-matched dated files into a UC Volume, and ingest them via Auto Loader into Bronze — all as governed, orchestrated Lakeflow tasks with no standalone shell script.

**Architecture:** SE-09's win condition is "native platform capability, no external script dependency." Databricks Apps only route HTTP (not SFTP port 22), so the SFTP server is NOT an App — it runs as a Lakeflow Job task. Because serverless tasks can't reliably reach each other over the network, the SFTP server (paramiko-based) and the paramiko client run in the SAME task over `localhost:2222`: this exercises the real SFTP protocol over a socket without cross-node networking. The client pulls `financial_aid_*.csv` → UC Volume `landing_dev/sftp/`; a second task runs Auto Loader → `bronze_dev.sftp_financial_aid`.

**Tech Stack:** paramiko (SFTP server + client), Lakeflow Jobs (serverless), Auto Loader, UC Volume, DABs.

## Global Constraints

- **Profile:** `dbx_shared_demo` (dev). Never auto-select; pass `--profile dbx_shared_demo`.
- **Catalog/schema:** per-target via `${var.catalog}` + `${var.schema_suffix}` (dev → `princeton_poc_dev` / `_dev`), passed to tasks as widgets — same pattern as Phase 0. Notebooks read `dbutils.widgets.get(...)`, never hardcode.
- **Volume landing path:** `/Volumes/${catalog}/landing${suffix}/sftp/`. Create the `sftp` sub-path (the `landing_dev` volume already exists from Phase 0).
- **No standalone shell script** — retrieval is a Python Lakeflow task (paramiko), git-versioned, orchestrated. This is the SE-09 point; do not shell out to `sftp`/`scp`.
- **Dated files + pattern match** — serve `financial_aid_YYYYMMDD.csv` for several dates; pull with glob `financial_aid_*.csv` (SE-09 requires pattern matching).
- **Credentials** — SFTP user/pass are POC-local constants in the task (documented); production note: use a UC secret scope. The paramiko host key is generated in-task (ephemeral, fine for localhost).
- **Serverless** compute for all tasks.
- **Verification model:** run the job → assert files landed on the Volume → assert Bronze row count → commit.
- **Upgrade path (parked):** Lakeflow Connect SFTP connector (Public Preview) — if the customer obtains it, it replaces the paramiko retrieval task with a managed connector. Baseline (this plan) works without it.

---

### Task 1: SFTP server module (paramiko, serves dated files)

**Files:**
- Create: `src/foundation/sftp/sftp_server.py`

**Interfaces:**
- Produces: `start_sftp_server(root_dir, host="127.0.0.1", port=2222, user, password)` → returns a running server (background thread) serving files under `root_dir` over SFTP. Also `seed_dated_files(root_dir, source_pandas_df, dates)` to write `financial_aid_<date>.csv` files into `root_dir`.

- [ ] **Step 1: Write the paramiko SFTP server**

```python
"""Minimal in-process SFTP server for the SE-09 demonstration. Serves files from a
local directory over the real SFTP protocol on localhost. Not a production server —
it exists so the retrieval task has a genuine SFTP endpoint to pull from."""
import os, socket, threading, paramiko

class _StubServer(paramiko.ServerInterface):
    def __init__(self, user, password): self.user, self.password = user, password
    def check_auth_password(self, username, password):
        return (paramiko.AUTH_SUCCESSFUL
                if username == self.user and password == self.password
                else paramiko.AUTH_FAILED)
    def check_channel_request(self, kind, chanid): return paramiko.OPEN_SUCCEEDED
    def get_allowed_auths(self, username): return "password"

def start_sftp_server(root_dir, user, password, host="127.0.0.1", port=2222):
    os.makedirs(root_dir, exist_ok=True)
    host_key = paramiko.RSAKey.generate(2048)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port)); sock.listen(5)

    def serve():
        while True:
            client, _ = sock.accept()
            t = paramiko.Transport(client); t.add_server_key(host_key)
            t.set_subsystem_handler("sftp", paramiko.SFTPServer,
                                    _RootedSFTP, root_dir)
            t.start_server(server=_StubServer(user, password))
    threading.Thread(target=serve, daemon=True).start()
    return sock

# _RootedSFTP: a paramiko.SFTPServerInterface rooted at root_dir. (Full implementation
# in the file — standard paramiko StubSFTPServer pattern rooted at root_dir.)
```

- [ ] **Step 2: Add `seed_dated_files`**

```python
def seed_dated_files(root_dir, rows_csv_text, dates):
    """Write financial_aid_<YYYYMMDD>.csv for each date, same CSV content."""
    os.makedirs(root_dir, exist_ok=True)
    for d in dates:
        with open(os.path.join(root_dir, f"financial_aid_{d}.csv"), "w") as f:
            f.write(rows_csv_text)
```

- [ ] **Step 3: Commit**

```bash
git add src/foundation/sftp/sftp_server.py && git commit -m "feat(sftp): in-process paramiko SFTP server module for SE-09"
```

---

### Task 2: Retrieval task — paramiko client pulls pattern-matched files to the Volume

**Files:**
- Create: `src/foundation/50_sftp_retrieve.py`

**Interfaces:**
- Consumes: `sftp_server.start_sftp_server`, `seed_dated_files`; widgets `catalog`, `schema_suffix`; the foundation `financial_aid` table for content.
- Produces: pattern-matched `financial_aid_*.csv` files landed under `/Volumes/${catalog}/landing${suffix}/sftp/`. No shell script.

- [ ] **Step 1: Write the retrieval notebook**

```python
# Databricks notebook source
# MAGIC %pip install paramiko
# COMMAND ----------
dbutils.library.restartPython()
# COMMAND ----------
import os, sys, glob, paramiko
sys.path.append(os.path.dirname(os.path.abspath("sftp/sftp_server.py")))
from sftp.sftp_server import start_sftp_server, seed_dated_files

dbutils.widgets.text("catalog", "princeton_poc"); dbutils.widgets.text("schema_suffix", "")
CAT = dbutils.widgets.get("catalog"); SUF = dbutils.widgets.get("schema_suffix")
VOL = f"/Volumes/{CAT}/landing{SUF}/sftp"
os.makedirs(VOL, exist_ok=True)

USER, PW, PORT = "poc_sftp", "poc_sftp_pw", 2222
SERVE_DIR = "/tmp/sftp_root"

# 1. seed several dated files onto the SFTP server's served directory
csv_text = (spark.table(f"{CAT}.silver{SUF}.financial_aid").limit(200)
            .toPandas().to_csv(index=False))
seed_dated_files(SERVE_DIR, csv_text, ["20260728", "20260729", "20260730"])

# 2. start the server (localhost) and connect a paramiko CLIENT — the real SFTP hop
start_sftp_server(SERVE_DIR, USER, PW, port=PORT)
transport = paramiko.Transport(("127.0.0.1", PORT)); transport.connect(username=USER, password=PW)
sftp = paramiko.SFTPClient.from_transport(transport)

# 3. pattern-match + pull to the UC Volume (no shell script)
pulled = []
for name in sftp.listdir("."):
    if name.startswith("financial_aid_") and name.endswith(".csv"):
        sftp.get(name, f"{VOL}/{name}")   # SFTP GET -> UC Volume
        pulled.append(name)
sftp.close(); transport.close()
print("pulled via SFTP:", pulled)
assert len(pulled) == 3, f"expected 3 pattern-matched files, got {len(pulled)}"
```

- [ ] **Step 2: Commit**

```bash
git add src/foundation/50_sftp_retrieve.py && git commit -m "feat(sftp): paramiko retrieval task -> pattern-matched files to UC Volume"
```

---

### Task 3: Auto Loader ingestion task — Volume → Bronze

**Files:**
- Create: `src/foundation/51_sftp_ingest.py`

**Interfaces:**
- Consumes: files under `/Volumes/${catalog}/landing${suffix}/sftp/`.
- Produces: `${catalog}.bronze${suffix}.sftp_financial_aid` (all dated files ingested).

- [ ] **Step 1: Write the ingestion notebook (Auto Loader, batch trigger)**

```python
# Databricks notebook source
dbutils.widgets.text("catalog", "princeton_poc"); dbutils.widgets.text("schema_suffix", "")
CAT = dbutils.widgets.get("catalog"); SUF = dbutils.widgets.get("schema_suffix")
VOL = f"/Volumes/{CAT}/landing{SUF}/sftp"
BRONZE = f"{CAT}.bronze{SUF}.sftp_financial_aid"
CHK = f"/Volumes/{CAT}/landing{SUF}/_chk/sftp_financial_aid"

(spark.readStream.format("cloudFiles")
   .option("cloudFiles.format", "csv").option("header", True)
   .option("cloudFiles.schemaLocation", CHK)
   .load(VOL)
 .writeStream.option("checkpointLocation", CHK)
   .trigger(availableNow=True)
   .toTable(BRONZE))

# wait for the availableNow stream to finish, then assert
for q in spark.streams.active: q.awaitTermination()
print("bronze rows:", spark.table(BRONZE).count())
```

- [ ] **Step 2: Commit**

```bash
git add src/foundation/51_sftp_ingest.py && git commit -m "feat(sftp): Auto Loader ingestion of SFTP-landed files to Bronze"
```

---

### Task 4: Wire an `sftp_ingest` job + deploy + run + verify

**Files:**
- Create: `resources/sftp.job.yml`

**Interfaces:**
- Produces: job `[${var.catalog}] SFTP ingest` — task `retrieve` → task `ingest`, both passed `catalog`/`schema_suffix`.

- [ ] **Step 1: Write `resources/sftp.job.yml`**

```yaml
resources:
  jobs:
    sftp_ingest:
      name: "[${var.catalog}] SFTP ingest"
      parameters:
        - name: catalog
          default: ${var.catalog}
        - name: schema_suffix
          default: ${var.schema_suffix}
      tasks:
        - task_key: retrieve
          notebook_task:
            notebook_path: ../src/foundation/50_sftp_retrieve.py
            base_parameters: {catalog: ${var.catalog}, schema_suffix: ${var.schema_suffix}}
        - task_key: ingest
          depends_on: [{task_key: retrieve}]
          notebook_task:
            notebook_path: ../src/foundation/51_sftp_ingest.py
            base_parameters: {catalog: ${var.catalog}, schema_suffix: ${var.schema_suffix}}
```

- [ ] **Step 2: Deploy + run**

Run: `databricks bundle deploy -t dev --profile dbx_shared_demo --auto-approve`
then: `databricks bundle run sftp_ingest -t dev --profile dbx_shared_demo`
Expected: both tasks succeed.

- [ ] **Step 3: Verify files + Bronze**

Files: `databricks fs ls dbfs:/Volumes/princeton_poc_dev/landing_dev/sftp --profile dbx_shared_demo`
Expected: `financial_aid_20260728.csv`, `_20260729.csv`, `_20260730.csv`.

Bronze:
```sql
SELECT count(*) FROM princeton_poc_dev.bronze_dev.sftp_financial_aid;
```
Expected: 600 (3 files × 200 rows).

- [ ] **Step 4: Commit**

```bash
git add resources/sftp.job.yml && git commit -m "feat(sftp): sftp_ingest job (retrieve -> ingest); verified on dev"
```

---

## Deliverable: runbook entry

- [ ] **Final step:** Append an SE-09 entry to `docs/runbook/README.md`: what it proves (native, script-free SFTP retrieval + pattern match + Auto Loader), the job to run, expected files + Bronze count, pre-built fallback (the job), and the parked upgrade path (Lakeflow Connect SFTP connector). Commit.

---

## Self-Review

**Spec coverage:** SE-09 (SFTP retrieval, pattern match, staging, ingestion, no external script) → Tasks 2,3,4 ✓. Native/orchestrated (Job tasks, not shell) → Task 4 ✓. Dated files + glob → Task 2 ✓. Parked Lakeflow Connect SFTP upgrade path → Global Constraints + runbook ✓.

**Placeholder scan:** `_RootedSFTP` full body is noted as "standard paramiko StubSFTPServer rooted at root_dir" — the one implementation detail to complete at execution (the paramiko `SFTPServerInterface` rooted-directory pattern is well-known; ~40 lines). Flagged, not hidden. Credentials are intentional POC constants with a production-secret note.

**Type consistency:** `start_sftp_server`/`seed_dated_files` signatures match between Task 1 and Task 2. `catalog`/`schema_suffix` widget names consistent with Phase 0. Volume path `landing${suffix}/sftp` consistent across Tasks 2,3,4.

**Open risks (flagged):** (1) serverless outbound-socket/threading for an in-process SFTP server is the main uncertainty — if the serverless sandbox blocks `socket.listen`, fall back to the paramiko client reading the served dir directly, or reframe per the earlier option C (land on Volume + Auto Loader, note SFTP is the same task). (2) `%pip install paramiko` adds startup time. Both confirmed at execution (Task 4 run).