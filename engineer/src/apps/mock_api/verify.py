"""SE-08 end-to-end verification / pre-built fallback for the mock REST API.

Mimics what an ingestion pipeline does: obtain a client-credentials token, page through
/enrollments (bearer in X-API-Token), follow `next` until null, and assert the total.

Run locally against the deployed app:
    APP_URL=https://princeton-mock-api-...azure.databricksapps.com \
    PROFILE=dbx_shared_demo \
    python engineer/src/apps/mock_api/verify.py
"""
import os
import requests
from databricks.sdk import WorkspaceClient

APP_URL = os.environ["APP_URL"].rstrip("/")
PROFILE = os.environ.get("PROFILE", "dbx_shared_demo")

# Platform OAuth token for the Databricks Apps reverse proxy.
w = WorkspaceClient(profile=PROFILE)
platform_token = w.config.oauth_token().access_token
base_headers = {"Authorization": f"Bearer {platform_token}"}

# 1. client-credentials grant against the app's own OAuth layer
r = requests.post(f"{APP_URL}/oauth/token", headers=base_headers,
                  data={"grant_type": "client_credentials",
                        "client_id": "princeton_poc_client",
                        "client_secret": "poc_secret_change_me"})
r.raise_for_status()
mock_token = r.json()["access_token"]
print("token acquired, expires_in:", r.json()["expires_in"])

# 2. paginate, carrying the mock bearer in X-API-Token
h = dict(base_headers)
h["X-API-Token"] = mock_token
page, seen, total = 1, 0, None
while page:
    resp = requests.get(f"{APP_URL}/enrollments",
                        params={"page": page, "page_size": 1000}, headers=h)
    if resp.status_code == 401:   # token expired mid-run -> refresh (SE-08 outcome)
        print("401 received; refreshing token...")
        mock_token = requests.post(
            f"{APP_URL}/oauth/token", headers=base_headers,
            data={"grant_type": "client_credentials", "client_id": "princeton_poc_client",
                  "client_secret": "poc_secret_change_me"}).json()["access_token"]
        h["X-API-Token"] = mock_token
        continue
    resp.raise_for_status()
    body = resp.json()
    total = body["total"]
    seen += len(body["data"])
    page = body["next"]

print(f"rows retrieved: {seen} | total reported: {total}")
assert seen == total, f"page total mismatch: got {seen}, expected {total}"
print("PASS: all pages retrieved, count matches.")
