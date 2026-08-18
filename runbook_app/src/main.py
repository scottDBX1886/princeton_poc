"""Princeton POC — interactive runbook app.

Read-only static content site (no database, no warehouse). Serves a single-page
app whose content is driven by static/data.json, so updating the runbook means
editing data — not markup. Binds to 0.0.0.0 on the platform-assigned port.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Princeton POC Runbook")

# health check for quick sanity / uptime probes
@app.get("/healthz")
def healthz():
    return {"status": "ok"}

# Mount the SPA at root. html=True serves index.html for "/" and lets the
# browser fetch data.json + assets from the same origin (no CORS concerns).
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
