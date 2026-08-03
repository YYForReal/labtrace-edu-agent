"""Standalone ASGI entrypoint for the public LabTrace competition edition."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from goaihz.api import router as labtrace_router
from goaihz.model_engine import model_runtime_status

app = FastAPI(
    title="格物智评 LabTrace",
    description="面向高校教师的实验报告证据化批改 Agent",
    version="0.5.0-goaihz",
    docs_url=None,
    redoc_url=None,
)
app.include_router(labtrace_router)


@app.get("/health")
async def health() -> dict[str, str | bool]:
    runtime = model_runtime_status()
    return {
        "status": "ok",
        "product": "labtrace",
        "version": app.version,
        "mode": "model_agent" if runtime["configured"] else "deterministic_demo",
        "model_configured": runtime["configured"],
        "model": runtime["model"] if runtime["configured"] else "none",
    }


_REPO_ROOT = Path(__file__).resolve().parent.parent
_FRONTEND_DIST = _REPO_ROOT / "frontend" / "dist"

if (_FRONTEND_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="labtrace-assets",
    )


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    if not _FRONTEND_DIST.is_dir():
        return HTMLResponse(
            "LabTrace API is running. Build frontend/ before opening the browser demo.",
            status_code=503,
        )

    requested = (_FRONTEND_DIST / full_path).resolve()
    try:
        requested.relative_to(_FRONTEND_DIST.resolve())
    except ValueError:
        requested = _FRONTEND_DIST / "index.html"

    if full_path and requested.is_file():
        return FileResponse(requested)
    return FileResponse(_FRONTEND_DIST / "index.html")


def run() -> None:
    import uvicorn

    uvicorn.run(
        "goaihz.app:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "11315")),
        reload=os.getenv("DEBUG", "").lower() == "true",
    )


if __name__ == "__main__":
    run()
