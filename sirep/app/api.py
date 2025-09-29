"""Expose the FastAPI application instance under ``sirep.app.api``.

Uvicorn commands in deployment scripts still reference this module, so it
simply forwards the actual application object from :mod:`sirep.api`.
"""

from sirep.api import app, create_app

__all__ = ["app", "create_app"]
