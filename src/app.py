"""The UnlimitedOCR server: one MCP tool, a document upload route and a health check."""

from __future__ import annotations

import asyncio
import hmac
import os
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from src.config import PROJECT_DIR, Settings
from src.contract import ParseResult
from src.engine import OCREngine
from src.errors import DocumentRejected, EngineFailed, IdentityRequired, OCRError, QuotaExceeded
from src.identity import owner_from_context
from src.middleware import InternalTokenMiddleware
from src.options import live, make_config
from src.runtime import Config
from src.service import OCRService
from src.store import DocumentStore

WEB_DIR = Path(os.environ.get("OCR_WEB_DIR") or PROJECT_DIR / "web")

INSTRUCTIONS = (
    "Document OCR (PDFs, PNG, JPEG, WebP). The user attaches a document in chat; the question then contains a line "
    "'[Document file_id: ...]'. Call tool_ocr_parse with that file_id to get the text of every page."
)


def build_app(settings: Settings, engine: OCREngine | None = None, config: Config | None = None) -> Starlette:
    """`config` (default: from OCR_ADMIN_PASSWORD, see options.make_config) makes the options in options.py
    changeable on /admin/ while running; without it they stay as the environment set them."""
    config = config if config is not None else make_config(settings)
    base, settings = settings, live(settings, config)
    engine = engine or OCREngine(base.backend_url, base.backend_token)
    store = DocumentStore(base.docs_dir, lambda: settings.ttl_seconds, lambda: settings.quota_bytes)
    store.sweep()
    service = OCRService(engine, store, settings)
    mcp = FastMCP(name="ocr", instructions=INSTRUCTIONS, host=settings.host, port=settings.port)

    @mcp.tool(
        meta={"keywords": ["ocr", "pdf", "scan", "document", "image to text", "extract text"], "display_label": "Reading document"},
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
    )
    async def tool_ocr_parse(
        file_id: Annotated[str, Field(description="The file_id from the '[Document file_id: ...]' line of the user's attachment.")],
        ctx: Context = None,
    ) -> ParseResult:
        """Read an attached PDF or image with OCR and return the text of every page. The file belongs to the asking user
        and expires after 24 hours. Returns the full text, the text per page, the page count and a summary."""
        try:
            return await service.parse(owner_from_context(ctx), file_id)
        except OCRError as error:
            raise ToolError(str(error)) from error

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> Response:
        return JSONResponse({"ok": True, "ready": await engine.probe()})

    @mcp.custom_route("/api/files", methods=["POST"])
    async def upload(request: Request) -> Response:
        owner = request.headers.get("x-requester-username", "").strip()
        if not owner:
            return JSONResponse({"error": "identity_required"}, status_code=401)
        # shortcut: the whole body is read before the size check; fine behind ember_api's own cap, add streaming if exposed.
        data = await request.body()
        if len(data) > settings.max_bytes:
            return JSONResponse({"error": "too_large"}, status_code=413)
        # Only a display name: last path part, bounded; it never becomes a path.
        filename = request.headers.get("x-filename", "document").replace("\\", "/").rsplit("/", 1)[-1][:255] or "document"
        try:
            stored, expires_at = await service.upload(owner, filename, data)
        except QuotaExceeded as error:
            return JSONResponse({"error": error.code, "message": str(error)}, status_code=413)
        except DocumentRejected as error:
            return JSONResponse({"error": error.code, "message": str(error)}, status_code=400)
        except EngineFailed as error:
            return JSONResponse({"error": error.code, "message": str(error)}, status_code=503)
        except IdentityRequired:
            return JSONResponse({"error": "identity_required"}, status_code=401)
        return JSONResponse({
            "file_id": stored.file_id, "page_count": stored.page_count,
            "size_bytes": stored.size_bytes, "expires_at": expires_at,
        })

    if config is not None:
        @mcp.custom_route("/admin/settings", methods=["GET", "PUT"])
        async def admin_settings(request: Request) -> Response:
            given = request.headers.get("x-admin-password", "").encode("utf-8")
            if not hmac.compare_digest(given, base.admin_password.encode("utf-8")):
                return JSONResponse({"detail": "Wrong admin password."}, status_code=401)
            if request.method == "PUT":
                try:
                    values = (await request.json())["values"]
                    if not isinstance(values, dict):
                        raise TypeError
                except (ValueError, KeyError, TypeError):
                    return JSONResponse({"detail": "Send {\"values\": {...}}."}, status_code=422)
                try:
                    await asyncio.to_thread(config.set, values)
                except ValueError as error:
                    return JSONResponse({"detail": str(error)}, status_code=422)
            return JSONResponse({"service": "UnlimitedOCR", "settings": config.describe()})

    app = mcp.streamable_http_app()
    if config is not None and WEB_DIR.is_dir():
        app.router.routes.append(Mount("/admin", StaticFiles(directory=WEB_DIR, html=True)))
    app.add_middleware(InternalTokenMiddleware, token=settings.internal_token)
    return app
