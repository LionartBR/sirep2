from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.types import Scope

from infra.config import settings
from services.orchestrator import PipelineOrchestrator

from .routers import auth, pipeline, plans, treatment


class NoCacheStaticFiles(StaticFiles):
    """Serve arquivos estáticos sempre ignorando cache do navegador."""

    def is_not_modified(
        self, response_headers: Headers, request_headers: Headers
    ) -> bool:  # pragma: no cover - comportamento fixo
        return False

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response


def create_app() -> FastAPI:
    """Configure the FastAPI application with routes and static assets."""

    app = FastAPI(title="SIREP API", version="0.1.0")

    app.include_router(auth.router, prefix="/api")
    app.include_router(pipeline.router, prefix="/api")
    app.include_router(plans.router, prefix="/api")
    app.include_router(treatment.router, prefix="/api")

    app.state.pipeline_orchestrator = PipelineOrchestrator()

    @app.get("/app", include_in_schema=False)
    async def app_redirect() -> RedirectResponse:
        """Ensure `/app` always resolves to the static app index with trailing slash."""

        return RedirectResponse(url="/app/")

    static_dir = Path(__file__).resolve().parents[1] / "ui"
    static_handler = (
        NoCacheStaticFiles(directory=static_dir, html=True)
        if settings.debug
        else StaticFiles(directory=static_dir, html=True)
    )
    app.mount("/app", static_handler, name="app")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/app/login.html")

    return app


__all__ = ["create_app"]
