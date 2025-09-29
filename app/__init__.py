"""Compatibility package exposing the FastAPI application entrypoint.

This module re-exports the lazily created FastAPI application used by
``uvicorn``. Historically the project exposed the app under
``sirep.app.api``; keeping this import path available avoids breaking
existing commands or deployment scripts.
"""

from api import app, create_app

__all__ = ["app", "create_app"]
