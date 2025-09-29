from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from services.orchestrator import PipelineOrchestrator

from .routers import auth, pipeline


def create_app() -> FastAPI:
    """Configure the FastAPI application with routes and static assets."""

    app = FastAPI(title="SIREP API", version="0.1.0")

    app.include_router(auth.router, prefix="/api")
    app.include_router(pipeline.router, prefix="/api")

    app.state.pipeline_orchestrator = PipelineOrchestrator()

    static_dir = Path(__file__).resolve().parents[1] / "ui"
    app.mount("/app", StaticFiles(directory=static_dir, html=True), name="app")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/app/")

    return app


__all__ = ["create_app"]
