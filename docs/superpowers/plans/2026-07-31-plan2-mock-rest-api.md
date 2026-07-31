# Princeton POC — Plan 2: Mock REST API App (SE-08) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Deploy an in-workspace FastAPI Databricks App that serves paginated higher-ed enrollment data behind OAuth 2.0 client-credentials auth, so the SE-08 ingestion scenario (authenticated + paginated + token-refresh) has a real endpoint to consume — reconciling with the foundation for SE-10.

**Architecture:** Headless FastAPI app (not AppKit — no UI). Exposes `POST /oauth/token` (client-credentials grant → short-TTL bearer) and `GET /enrollments?page=N` (bearer-protected, paginated). Queries the foundation live via databricks-sql-connector using the app's auto-injected service-principal auth against a SQL warehouse. Deployed as an app resource in the existing `princeton_poc` bundle; deployed/started with `databricks apps deploy`.

**Tech Stack:** FastAPI + uvicorn, databricks-sql-connector, Databricks Apps (FastAPI/other-frameworks path), DABs.

## Global Constraints

- **Profile:** `dbx_shared_demo` (dev target). Never auto-select; pass `--profile dbx_shared_demo`.
- **App name:** `princeton-mock-api` (≤26 chars, lowercase/hyphens; no underscores).
- **Bind:** host `0.0.0.0`, port `int(os.environ["DATABRICKS_APP_PORT"])` (fallback 8000 local). Hardcoding a port = 502.
- **No workspace-specific IDs in code** — inject via env (`valueFrom: sql-warehouse`, catalog/schema as env values).
- **Two auth layers:** platform OAuth (reverse proxy, transparent to workspace callers) + the app's OWN mock client-credentials OAuth (what SE-08 demonstrates). Keep them distinct.
- **Data source:** live query of `${catalog}.silver_dev.enrollment` (dev). App SP needs UC `SELECT`.
- **Short token TTL:** 300s, so token refresh is observable mid-ingestion (SE-08 outcome).
- **Deps:** `requirements.txt` only, pinned. No system packages (no root).
- **Deploy:** `databricks apps deploy` (validates + uploads + starts). A bare `bundle deploy` leaves it stopped.
- **Verification model:** build → deploy → hit the live endpoints with curl/python → assert token + pagination + 401-on-expiry → commit.
- **Mock credentials:** `MOCK_CLIENT_ID`/`MOCK_CLIENT_SECRET` as app env values for the POC (the OAuth *flow* is the demo, not secret hardening). Note inline: production would use a UC secret scope (`valueFrom: secret`).

---

### Task 1: FastAPI app skeleton + health endpoint

**Files:**
- Create: `src/apps/mock_api/app.py`
- Create: `src/apps/mock_api/requirements.txt`
- Create: `src/apps/mock_api/app.yaml`

**Interfaces:**
- Produces: a runnable FastAPI app binding `0.0.0.0:$DATABRICKS_APP_PORT` with `GET /health` → `{"status":"ok"}`.

- [ ] **Step 1: Write `requirements.txt`**

```
fastapi==0.115.6
uvicorn==0.34.0
databricks-sql-connector==4.0.3
```

- [ ] **Step 2: Write `app.py` skeleton (health + bind)**

```python
import os
from fastapi import FastAPI

app = FastAPI(title="Princeton Mock Enrollment API")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("DATABRICKS_APP_PORT", 8000)))
```

- [ ] **Step 3: Write `app.yaml`**

```yaml
command:
  - uvicorn
  - app:app
  - --host
  - "0.0.0.0"
  - --port
  - "${DATABRICKS_APP_PORT:-8000}"
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: SRC_CATALOG
    value: "princeton_poc_dev"
  - name: SRC_SCHEMA
    value: "silver_dev"
  - name: MOCK_CLIENT_ID
    value: "princeton_poc_client"
  - name: MOCK_CLIENT_SECRET
    value: "poc_secret_change_me"
  - name: TOKEN_TTL_SECONDS
    value: "300"
```

- [ ] **Step 4: Commit**

```bash
git add src/apps/mock_api && git commit -m "feat(api): FastAPI mock API skeleton + health endpoint"
```

---

### Task 2: OAuth 2.0 client-credentials token endpoint

**Files:**
- Modify: `src/apps/mock_api/app.py`

**Interfaces:**
- Consumes: `MOCK_CLIENT_ID`, `MOCK_CLIENT_SECRET`, `TOKEN_TTL_SECONDS` env.
- Produces: `POST /oauth/token` accepting `grant_type=client_credentials&client_id=..&client_secret=..` (form), returning `{access_token, token_type: "Bearer", expires_in}`. A `require_token` dependency validates `Authorization: Bearer <t>` and returns 401 on missing/expired/invalid.

- [ ] **Step 1: Add token issue + validation**

```python
import time, secrets
from fastapi import Depends, Form, HTTPException, Header

_TOKENS: dict[str, float] = {}  # token -> expiry epoch
TTL = int(os.environ.get("TOKEN_TTL_SECONDS", "300"))

@app.post("/oauth/token")
def issue_token(grant_type: str = Form(...), client_id: str = Form(...),
                client_secret: str = Form(...)):
    if grant_type != "client_credentials":
        raise HTTPException(400, "unsupported_grant_type")
    if (client_id != os.environ["MOCK_CLIENT_ID"]
            or client_secret != os.environ["MOCK_CLIENT_SECRET"]):
        raise HTTPException(401, "invalid_client")
    tok = secrets.token_urlsafe(32)
    _TOKENS[tok] = time.time() + TTL
    return {"access_token": tok, "token_type": "Bearer", "expires_in": TTL}

def require_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing_bearer")
    tok = authorization.split(" ", 1)[1]
    exp = _TOKENS.get(tok)
    if exp is None or time.time() > exp:
        raise HTTPException(401, "invalid_or_expired_token")
    return tok
```

- [ ] **Step 2: Commit**

```bash
git add src/apps/mock_api/app.py && git commit -m "feat(api): OAuth2 client-credentials token endpoint + bearer validation"
```

---

### Task 3: Paginated, bearer-protected /enrollments (live foundation query)

**Files:**
- Modify: `src/apps/mock_api/app.py`

**Interfaces:**
- Consumes: `require_token`, `DATABRICKS_WAREHOUSE_ID`, `SRC_CATALOG`, `SRC_SCHEMA`; auto-injected `DATABRICKS_CLIENT_ID`/`SECRET`/`HOST` (SP auth).
- Produces: `GET /enrollments?page=N&page_size=100` (default 100), bearer-required, returning `{page, page_size, total, next, data: [...]}`. Queries `${SRC_CATALOG}.${SRC_SCHEMA}.enrollment` with `LIMIT/OFFSET` ordered by `enrollment_id`.

- [ ] **Step 1: Add a pooled SQL connection helper**

```python
from functools import lru_cache
from databricks import sql
from databricks.sdk.core import Config

@lru_cache(maxsize=1)
def _conn():
    cfg = Config()  # picks up injected SP env
    return sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{os.environ['DATABRICKS_WAREHOUSE_ID']}",
        credentials_provider=lambda: cfg.authenticate,
    )
```

- [ ] **Step 2: Add the paginated endpoint**

```python
from fastapi import Query

@app.get("/enrollments")
def enrollments(page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=1000),
                _tok: str = Depends(require_token)):
    cat, sch = os.environ["SRC_CATALOG"], os.environ["SRC_SCHEMA"]
    offset = (page - 1) * page_size
    with _conn().cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {cat}.{sch}.enrollment")
        total = cur.fetchone()[0]
        cur.execute(
            f"SELECT enrollment_id, student_id, course_id, term_id, grade, gpa_points "
            f"FROM {cat}.{sch}.enrollment ORDER BY enrollment_id LIMIT {page_size} OFFSET {offset}")
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    has_next = offset + page_size < total
    return {"page": page, "page_size": page_size, "total": total,
            "next": (page + 1) if has_next else None, "data": rows}
```

- [ ] **Step 3: Commit**

```bash
git add src/apps/mock_api/app.py && git commit -m "feat(api): paginated bearer-protected /enrollments over live foundation"
```

---

### Task 4: Bundle app resource + warehouse grant + deploy

**Files:**
- Create: `resources/mock_api.app.yml`

**Interfaces:**
- Consumes: `${var.warehouse_id}` (must be set now — see below).
- Produces: app `princeton-mock-api` deployed and RUNNING with a URL; SP granted CAN_USE on the warehouse.

- [ ] **Step 1: Set `warehouse_id` for dev** in `databricks.yml` (was empty). Pick a warehouse ID from `databricks warehouses list --profile dbx_shared_demo`; set it on the dev target `variables:`.

- [ ] **Step 2: Write `resources/mock_api.app.yml`**

```yaml
resources:
  apps:
    mock_api:
      name: princeton-mock-api
      source_code_path: ../src/apps/mock_api
      resources:
        - name: sql-warehouse
          sql_warehouse:
            id: ${var.warehouse_id}
            permission: CAN_USE
```

- [ ] **Step 3: Validate + deploy the app**

Run: `databricks bundle validate -t dev --profile dbx_shared_demo`
then: `databricks apps deploy princeton-mock-api -t dev --profile dbx_shared_demo`
Expected: app builds, starts, returns a URL.

- [ ] **Step 4: Grant the app SP `SELECT` on the foundation**

The app SP (name shown in `databricks apps get princeton-mock-api`) needs UC read. Run:
```sql
GRANT USE CATALOG ON CATALOG princeton_poc_dev TO `<app_sp>`;
GRANT USE SCHEMA ON SCHEMA princeton_poc_dev.silver_dev TO `<app_sp>`;
GRANT SELECT ON TABLE princeton_poc_dev.silver_dev.enrollment TO `<app_sp>`;
```
(Resolve `<app_sp>` from `databricks apps get princeton-mock-api --profile dbx_shared_demo -o json` → `service_principal_client_id`/`name`.)

- [ ] **Step 5: Verify RUNNING**

Run: `databricks apps get princeton-mock-api --profile dbx_shared_demo -o json` → `app_status.state == RUNNING`; capture the `url`.

- [ ] **Step 6: Commit**

```bash
git add resources/mock_api.app.yml databricks.yml && git commit -m "feat(api): bundle app resource + warehouse grant; deploy princeton-mock-api"
```

---

### Task 5: End-to-end verification (the SE-08 dance)

**Files:**
- Create: `src/apps/mock_api/verify.py` (a throwaway client that mimics what the SE-08 pipeline will do)

**Interfaces:**
- Consumes: the deployed app URL; workspace auth (for the platform proxy) + mock client creds (for the app's OAuth).

- [ ] **Step 1: Write `verify.py`** — fetch a token, page through, assert.

```python
# Run locally against the deployed app. Uses the databricks CLI's OAuth for the
# platform proxy (via the SDK) and the mock client-credentials for the app's own auth.
import os, requests
from databricks.sdk import WorkspaceClient

APP_URL = os.environ["APP_URL"]            # from `databricks apps get`
w = WorkspaceClient(profile="dbx_shared_demo")
platform_headers = w.config.authenticate()  # {'Authorization': 'Bearer <platform oauth>'}

# 1. get mock OAuth token
r = requests.post(f"{APP_URL}/oauth/token", headers=platform_headers,
                  data={"grant_type": "client_credentials",
                        "client_id": "princeton_poc_client",
                        "client_secret": "poc_secret_change_me"})
r.raise_for_status(); tok = r.json()["access_token"]
print("token acquired, expires_in:", r.json()["expires_in"])

# 2. paginate
h = dict(platform_headers); h["Authorization"] = f"Bearer {tok}"  # NOTE: app bearer replaces here
# (platform proxy needs its own header; see verification note below on dual-header handling)
page, seen = 1, 0
while page and page <= 3:
    resp = requests.get(f"{APP_URL}/enrollments", params={"page": page, "page_size": 100}, headers=h)
    resp.raise_for_status(); body = resp.json(); seen += len(body["data"]); page = body["next"]
print("rows across pages:", seen, "total:", body["total"])
```

> **Dual-header note:** the platform proxy and the app both read `Authorization`. If they collide, the resolution (documented at execution) is to send the **platform** token in `Authorization` and the **mock** token in a custom header (e.g. `X-API-Token`), and have `require_token` read that custom header. Adjust Task 2/3 to read `X-API-Token` if the collision occurs during Step 2 verification. This is the one integration risk to resolve live.

- [ ] **Step 2: Run verification**

Run: `APP_URL=<url> python src/apps/mock_api/verify.py`
Expected: token acquired; ≥300 rows across 3 pages; `total` = foundation enrollment count.

- [ ] **Step 3: Assert 401 on bad/expired token**

Manually call `/enrollments` with a garbage bearer; expect HTTP 401.

- [ ] **Step 4: Commit**

```bash
git add src/apps/mock_api/verify.py && git commit -m "test(api): end-to-end SE-08 verification (token + pagination + 401)"
```

---

## Deliverable: runbook entry

- [ ] **Final step:** Append an SE-08 entry to `docs/runbook/README.md`: the app URL, the OAuth token curl, the paginated call, the expected outcome (all pages retrieved, token refresh at 300s), and the pre-built fallback (the app itself + `verify.py`). Commit.

---

## Self-Review

**Spec coverage:** SE-08 (auth + pagination + refresh) → Tasks 2,3,5 ✓. Foundation-live data for SE-10 reconciliation → Task 3 ✓. In-workspace app (spec §4.3) → Task 4 ✓. OAuth 2.0 client-credentials (chosen earlier) → Task 2 ✓. Short TTL for observable refresh → Global Constraints + Task 2 ✓.

**Placeholder scan:** `<app_sp>` and `<url>` are operator-resolved at execution (documented). Mock creds are intentionally literal POC values with a production-secret note. No TODO/TBD.

**Type consistency:** `require_token` defined Task 2, consumed Task 3. `/oauth/token` form fields match `verify.py` POST body. `SRC_CATALOG`/`SRC_SCHEMA` env names consistent across app.yaml, app.py, and the grant.

**Open risk (flagged, not hidden):** the dual-`Authorization`-header collision between the platform proxy and the app's own auth (Task 5 note). Resolution path documented (move mock token to `X-API-Token`); confirmed live during Task 5.
