# Databricks notebook source
# MAGIC %md
# MAGIC # E3 — REST API ingestion (SE-08): OAuth 2.0 + pagination + token refresh
# MAGIC Ingests paginated enrollment data from the in-workspace mock REST API into a
# MAGIC per-person Bronze table. Demonstrates client-credentials OAuth, automatic
# MAGIC pagination, and token refresh on expiry.
# MAGIC
# MAGIC **Two auth layers (faithful enterprise "API behind a gateway"):**
# MAGIC 1. **Databricks Apps SSO proxy** — the notebook authenticates as a *service
# MAGIC    principal* via OAuth M2M (workspace token endpoint, client-credentials). The
# MAGIC    SP has CAN_USE on the app, so the proxy admits it. Token → `Authorization`.
# MAGIC 2. **The mock API's own OAuth** — client-credentials bearer in `X-API-Token`.
# MAGIC
# MAGIC SP credentials live in the UC secret scope `princeton_poc_e3` (never in code).
# MAGIC Foundation is read-only; output goes to your own `wksp_<you>` schema.

# COMMAND ----------
import re
import requests
from datetime import datetime

dbutils.widgets.text("catalog", "princeton_poc_dev")
dbutils.widgets.text("app_url",
    "https://princeton-mock-api-3438839487639471.11.azure.databricksapps.com")
dbutils.widgets.text("secret_scope", "princeton_poc_e3")
CATALOG = dbutils.widgets.get("catalog")
APP_URL = dbutils.widgets.get("app_url").rstrip("/")
SCOPE = dbutils.widgets.get("secret_scope")

# Workspace host for the OIDC token endpoint.
HOST = ("https://" + spark.conf.get("spark.databricks.workspaceUrl")).rstrip("/")

user = spark.sql("SELECT current_user()").first()[0]
USER_SCHEMA = "wksp_" + re.sub(r"[^a-zA-Z0-9]", "_", user)
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{USER_SCHEMA}")
OUT = f"{CATALOG}.{USER_SCHEMA}.e3_enrollments_from_api"

# COMMAND ----------
# MAGIC %md ## Layer 1 — SP OAuth M2M token for the Apps proxy
# MAGIC Client-credentials grant against the workspace OIDC endpoint, scope=all-apis.
# COMMAND ----------
sp_client_id = dbutils.secrets.get(SCOPE, "client_id")
sp_client_secret = dbutils.secrets.get(SCOPE, "client_secret")

def get_platform_token():
    r = requests.post(
        f"{HOST}/oidc/v1/token",
        auth=(sp_client_id, sp_client_secret),
        data={"grant_type": "client_credentials", "scope": "all-apis"})
    r.raise_for_status()
    return r.json()["access_token"]

platform_token = get_platform_token()
PLATFORM = {"Authorization": f"Bearer {platform_token}"}

# proxy reachability probe
_h = requests.get(f"{APP_URL}/health", headers=PLATFORM)
print(f"/health via SP token -> HTTP {_h.status_code}, body[:80]={_h.text[:80]!r}")
assert _h.status_code == 200 and _h.text.strip().startswith("{"), \
    "SP token not admitted by the Apps proxy — check SP CAN_USE grant + scope"

# COMMAND ----------
# MAGIC %md ## Layer 2 — the mock API's own client-credentials OAuth (SE-08)
# COMMAND ----------
CLIENT_ID = "princeton_poc_client"
CLIENT_SECRET = "poc_secret_change_me"   # the API's demo creds (not the SP's)

def get_mock_token():
    r = requests.post(f"{APP_URL}/oauth/token", headers=PLATFORM,
                      data={"grant_type": "client_credentials",
                            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
    r.raise_for_status()
    body = r.json()
    print(f"mock token acquired at {datetime.now().isoformat()}, expires_in={body['expires_in']}s")
    return body["access_token"]

mock_token = get_mock_token()

# COMMAND ----------
# MAGIC %md ## Paginated pull with token-refresh on 401
# COMMAND ----------
def headers():
    h = dict(PLATFORM)
    h["X-API-Token"] = mock_token
    return h

rows, page, total, pages, refreshes = [], 1, None, 0, 0
while page:
    resp = requests.get(f"{APP_URL}/enrollments",
                        params={"page": page, "page_size": 100}, headers=headers())
    if resp.status_code == 401:                 # mock token expired -> refresh (SE-08)
        refreshes += 1
        print(f"401 at page {page}; refreshing mock token...")
        mock_token = get_mock_token()
        continue
    resp.raise_for_status()
    body = resp.json()
    total = body["total"]
    rows.extend(body["data"])
    pages += 1
    page = body["next"]

print(f"pages={pages}  rows={len(rows)}  total_reported={total}  token_refreshes={refreshes}")

# COMMAND ----------
# MAGIC %md ## Write to per-person Bronze + assert completeness
# COMMAND ----------
df = spark.createDataFrame(rows)
df.write.mode("overwrite").saveAsTable(OUT)
cnt = spark.table(OUT).count()
print(f"wrote {cnt} rows to {OUT}")
assert cnt == total, f"pagination incomplete: got {cnt}, API total {total}"
print("PASS: OAuth2 (SP proxy auth + API client-credentials) + pagination; count matches API total.")
