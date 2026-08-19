# Databricks notebook source
# MAGIC %md
# MAGIC # 60 — Genie space setup (runs AFTER the data load)
# MAGIC Creates the POC Genie spaces from their committed `.geniespace.json` bodies, via the Genie
# MAGIC REST API. This is the LAST task of `foundation_build` — it runs only after the silver/gold
# MAGIC tables exist, which is exactly what the Genie API requires (it validates the grounding
# MAGIC tables at create time).
# MAGIC
# MAGIC **Why this is a job task, not a DAB `genie_spaces` resource:** DAB resolves resources at
# MAGIC `bundle deploy`, before any data exists, so a genie_spaces resource forces a
# MAGIC deploy→run→re-deploy dance and a mid-deploy "table does not exist" failure. As a post-load
# MAGIC job step, deploy stays clean and the whole bring-up is one deploy + one run.
# MAGIC
# MAGIC Idempotent: a space with the same title is deleted, then re-created (predictable rebuild).

# COMMAND ----------
import json, re, pathlib
from databricks.sdk import WorkspaceClient

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("schema_suffix", "_dev")
dbutils.widgets.text("warehouse_id", "")
CATALOG = dbutils.widgets.get("catalog")
SUFFIX = dbutils.widgets.get("schema_suffix")
WAREHOUSE = dbutils.widgets.get("warehouse_id")

w = WorkspaceClient()

# Repo files are synced under the bundle workspace path; resolve relative to this notebook.
NB_DIR = "/Workspace" + "/".join(
    dbutils.notebook.entry_point.getDbutils().notebook().getContext()
    .notebookPath().get().split("/")[:-2])   # .../files/foundation/src -> .../files/foundation
REPO_ROOT = str(pathlib.Path(NB_DIR).parent)  # .../files

# Manifest: which spaces to build, their committed body, and display metadata.
SPACES = [
    {
        "title": f"[{CATALOG}] Enrollment Explorer (BA-01)",
        "description": "No-code NL exploration of enrollments, departments, terms, GPAs (BA-01).",
        "body": f"{REPO_ROOT}/businessanalyst/src/genie/enrollment_explorer.geniespace.json",
    },
    {
        "title": f"[{CATALOG}] Data Foundation",
        "description": "NL exploration over the shared higher-ed data foundation (DS-01).",
        "body": f"{REPO_ROOT}/datascientist/src/genie_foundation.geniespace.json",
    },
    {
        "title": f"[{CATALOG}] Analytical Code Audit (DS-08)",
        "description": "NL audit trail over notebook activity — who changed which notebook, when (DS-08).",
        "body": f"{REPO_ROOT}/datascientist/src/genie_code_audit.geniespace.json",
    },
]

# COMMAND ----------
# Retarget table identifiers in the serialized body to THIS run's catalog + schema_suffix, so the
# same committed JSON (authored against princeton_poc_dev / _dev) works for any target. The
# `data_sources.tables[].identifier` values are catalog.schema.table where schema = base + '_dev'.
def retarget(body: dict) -> dict:
    for t in body.get("data_sources", {}).get("tables", []):
        parts = t["identifier"].split(".")
        # Leave system tables alone — system.access.audit is not a per-target catalog and
        # retargeting it would produce <catalog>.access<suffix>.audit, which does not exist.
        if parts[0] == "system":
            continue
        if len(parts) == 3:
            _, schema, table = parts
            base = schema[:-4] if schema.endswith("_dev") else schema  # silver_dev -> silver
            t["identifier"] = f"{CATALOG}.{base}{SUFFIX}.{table}"
    # tables MUST be sorted by identifier or create fails INVALID_PARAMETER_VALUE
    body["data_sources"]["tables"] = sorted(
        body["data_sources"]["tables"], key=lambda x: x["identifier"])
    return body


def list_spaces():
    spaces, token = [], None
    while True:
        q = {"page_size": 100}
        if token:
            q["page_token"] = token
        resp = w.api_client.do("GET", "/api/2.0/genie/spaces", query=q)
        spaces += resp.get("spaces", [])
        token = resp.get("next_page_token")
        if not token:
            break
    return spaces


# COMMAND ----------
existing = {s.get("title"): s.get("space_id") for s in list_spaces()}
created_ids = []

for spec in SPACES:
    body = retarget(json.loads(pathlib.Path(spec["body"]).read_text()))
    # Idempotent: delete a same-titled space first, then create fresh.
    if spec["title"] in existing:
        sid = existing[spec["title"]]
        try:
            w.api_client.do("DELETE", f"/api/2.0/genie/spaces/{sid}")
            print(f"deleted existing '{spec['title']}' ({sid})")
        except Exception as e:
            print(f"warn: could not delete '{spec['title']}': {e}")
    payload = {
        "title": spec["title"],
        "description": spec["description"],
        "warehouse_id": WAREHOUSE,
        "serialized_space": json.dumps(body),
    }
    created = w.api_client.do("POST", "/api/2.0/genie/spaces", body=payload)
    sid = created.get("space_id")
    created_ids.append((spec["title"], sid))
    print(f"created '{spec['title']}' -> space_id={sid}")

# COMMAND ----------
# Verify by GET on each returned space_id (immediately consistent — the list API lags a few
# seconds after create, so scanning the list here would give false negatives).
for title, sid in created_ids:
    assert sid, f"no space_id returned for {title}"
    got = w.api_client.do("GET", f"/api/2.0/genie/spaces/{sid}")
    assert got.get("space_id") == sid, f"GET did not confirm space {title} ({sid})"
    print(f"verified: {title} -> {sid}")
print("PASS: Genie spaces created & verified:", [t for t, _ in created_ids])
