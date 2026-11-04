"""ASGI entry point for uvicorn: ``uvicorn mlforge_api.asgi:app``."""

from .main import create_app

app = create_app()
