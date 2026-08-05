"""Princeton POC — Mock Enrollment REST API (SE-08).

A headless FastAPI Databricks App that demonstrates authenticated, paginated REST
ingestion. It serves higher-ed enrollment data queried LIVE from the foundation, behind
its own OAuth 2.0 client-credentials layer with a short token TTL so token refresh is
observable during a demo.

Two auth layers are in play:
  1. Databricks platform OAuth (reverse proxy) — transparent to in-workspace callers.
  2. This app's OWN mock OAuth (what SE-08 demonstrates): POST /oauth/token issues a
     short-lived bearer; protected endpoints require it in the X-API-Token header.

The mock bearer is carried in X-API-Token (not Authorization) so it doesn't collide with
the platform proxy's own Authorization header. The client-credentials flow is otherwise
a faithful OAuth 2.0 demonstration.
"""
import os
import secrets
import time
from functools import lru_cache

from databricks import sql
from databricks.sdk.core import Config
from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query

app = FastAPI(title="Princeton Mock Enrollment API")

TTL = int(os.environ.get("TOKEN_TTL_SECONDS", "300"))
_TOKENS: dict[str, float] = {}  # token -> expiry epoch


# --------------------------------------------------------------------------- health
@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------- OAuth2 (mock) layer
@app.post("/oauth/token")
def issue_token(grant_type: str = Form(...), client_id: str = Form(...),
                client_secret: str = Form(...)):
    """OAuth 2.0 client-credentials grant -> short-lived bearer token."""
    if grant_type != "client_credentials":
        raise HTTPException(400, "unsupported_grant_type")
    if (client_id != os.environ["MOCK_CLIENT_ID"]
            or client_secret != os.environ["MOCK_CLIENT_SECRET"]):
        raise HTTPException(401, "invalid_client")
    tok = secrets.token_urlsafe(32)
    _TOKENS[tok] = time.time() + TTL
    return {"access_token": tok, "token_type": "Bearer", "expires_in": TTL}


def require_token(x_api_token: str = Header(None)):
    """Validate the app's own bearer (carried in X-API-Token). 401 on missing/expired."""
    if not x_api_token:
        raise HTTPException(401, "missing_token")
    exp = _TOKENS.get(x_api_token)
    if exp is None or time.time() > exp:
        raise HTTPException(401, "invalid_or_expired_token")
    return x_api_token


# ------------------------------------------------------------- live foundation query
@lru_cache(maxsize=1)
def _conn():
    cfg = Config()  # auto-injected service-principal auth
    return sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{os.environ['DATABRICKS_WAREHOUSE_ID']}",
        credentials_provider=lambda: cfg.authenticate,
    )


@app.get("/enrollments")
def enrollments(page: int = Query(1, ge=1),
                page_size: int = Query(100, ge=1, le=1000),
                _tok: str = Depends(require_token)):
    """Paginated enrollments from the live foundation. Bearer required (X-API-Token)."""
    cat, sch = os.environ["SRC_CATALOG"], os.environ["SRC_SCHEMA"]
    offset = (page - 1) * page_size
    with _conn().cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {cat}.{sch}.enrollment")
        total = cur.fetchone()[0]
        cur.execute(
            f"SELECT enrollment_id, student_id, course_id, term_id, grade, gpa_points "
            f"FROM {cat}.{sch}.enrollment ORDER BY enrollment_id "
            f"LIMIT {page_size} OFFSET {offset}")
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    has_next = offset + page_size < total
    return {"page": page, "page_size": page_size, "total": total,
            "next": (page + 1) if has_next else None, "data": rows}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("DATABRICKS_APP_PORT", 8000)))
