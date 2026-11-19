"""Lightweight ASGI entrypoint for Render.

Binds the HTTP port before importing the full application. The main API imports
pandas and other optional research modules; loading those at process startup can
delay Render's port detection. The first non-health request loads the full app.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
from typing import Any

_inner_app: Any | None = None
_load_lock = asyncio.Lock()
_HEALTH_BODY = json.dumps(
    {"estado": "ok", "aplicacion": "AppApuestas"},
    separators=(",", ":"),
).encode("utf-8")


async def _load_inner_app() -> Any:
    global _inner_app

    if _inner_app is not None:
        return _inner_app

    async with _load_lock:
        if _inner_app is None:
            try:
                module = await asyncio.to_thread(importlib.import_module, "api_servidor")
                _inner_app = module.app
            except Exception:
                logging.exception("No se pudo cargar la aplicación principal AppApuestas.")
                raise

    return _inner_app


async def app(scope, receive, send):
    """ASGI application that exposes health immediately and lazy-loads the API."""
    scope_type = scope.get("type")

    if scope_type == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
        return

    if scope_type != "http":
        return

    if scope.get("path") == "/health":
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": _HEALTH_BODY,
        })
        return

    try:
        inner_app = await _load_inner_app()
    except Exception:
        body = b'{"detail":"La API principal no pudo iniciar."}'
        await send({
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})
        return

    await inner_app(scope, receive, send)
