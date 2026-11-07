"""The Reader server: one MCP tool, a document upload route and a health check."""

from __future__ import annotations

import asyncio
import hmac
import os
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from src.config import PROJECT_DIR, Settings
from src.contract import ParseResult
from src.admin_api import Backends, Slot, Usage, register
from src.engine import OCREngine, probe_sglang
from src.errors import DocumentRejected, EngineFailed, FileNotFound, IdentityRequired, OCRError, QuotaExceeded
from src.identity import owner_from_context
from src.middleware import InternalTokenMiddleware
from src.options import live, make_config
from src.runtime import Config
from src.service import OCRService
from src.store import DocumentStore

WEB_DIR = Path(os.environ.get("READER_WEB_DIR") or PROJECT_DIR / "web")

PLAYGROUND = {"operations": [{
    "label": "Read document", "route": "/api/files", "method": "POST", "encoding": "raw", "response": "json",
    "fields": [
        {"key": "X-Requester-Username", "label": "Requester username", "type": "text", "location": "header",
         "required": True, "default": "playground"},
        {"key": "file", "label": "Document", "type": "file", "required": True,
         "accept": "application/pdf,image/png,image/jpeg,image/webp"},
    ],
    "followup": {"route": "/api/parse", "method": "POST", "bodyKeys": ["file_id"], "response": "json"},
}]}


class ParseIn(BaseModel):
    """An owned upload identifier; identity always comes from the public request header."""

    model_config = ConfigDict(strict=True, extra="forbid")
    file_id: str = Field(pattern=r"^[a-f0-9]{32}$")

INSTRUCTIONS = (
    "Document OCR (PDFs, PNG, JPEG, WebP). The user attaches a document in chat; the question then contains a line "
    "'[Document file_id: ...]'. Call tool_ocr_parse with that file_id to get the text of every page."
)


CONNECT = {
    "host": "ocr",
    "port": 29402,
    "paths": [
        {
            "label": "MCP, for Armory",
            "method": "POST",
            "path": "/mcp"
        },
        {
            "label": "Upload document",
            "method": "POST",
            "path": "/api/files"
        },
        {
            "label": "Parse",
            "method": "POST",
            "path": "/api/parse"
        },
        {
            "label": "Health, no token",
            "method": "GET",
            "path": "/health"
        }
    ]
}


def build_app(settings: Settings, engine: OCREngine | None = None, config: Config | None = None) -> Starlette:
    """`config` (default: from READER_ADMIN_PASSWORD, see options.make_config) makes the options in options.py
    changeable on /admin/ while running; without it they stay as the environment set them."""
    config = config if config is not None else make_config(settings)
    base, settings = settings, live(settings, config)
    backends = Backends(base.state_dir / "backends.json")
    usage = Usage()
    engine = engine or OCREngine(source=lambda: backends.get("ocr"))
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
            owner = owner_from_context(ctx)
            async with usage.track(owner, "parse"):
                return await service.parse(owner, file_id)
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

    @mcp.custom_route("/api/parse", methods=["POST"])
    async def parse(request: Request) -> Response:
        """Expose the MCP parse path to HTTP clients, retaining ownership, quotas, cache and inference limits."""
        owner = request.headers.get("x-requester-username", "").strip()
        if not owner:
            return JSONResponse({"error": "identity_required"}, status_code=401)
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 4096:
                return JSONResponse({"error": "too_large"}, status_code=413)
        try:
            body = ParseIn.model_validate_json(data)
        except (ValueError, ValidationError):
            return JSONResponse({"error": "invalid_request", "message": "Send an uploaded file_id."}, status_code=422)
        try:
            async with usage.track(owner, "parse"):
                result = await service.parse(owner, body.file_id)
        except OCRError as error:
            code = (401 if isinstance(error, IdentityRequired) else 404 if isinstance(error, FileNotFound)
                    else 413 if isinstance(error, QuotaExceeded) else 503 if isinstance(error, EngineFailed) else 400)
            # DocumentRejected may wrap a backend rejection; keep backend text out of this public adapter.
            message = "That document cannot be parsed. Try another document." if isinstance(error, DocumentRejected) else str(error)
            return JSONResponse({"error": error.code, "message": message}, status_code=code)
        return JSONResponse(result.model_dump())

    async def status() -> list[dict[str, str]]:
        ready = await engine.probe()
        return [{"label": "Model", "value": engine.model}, {"label": "OCR_SGLang_Model", "value": "ready" if ready else "not ready"}]

    if config is not None:
        register(mcp, connect=CONNECT, service="Reader", admin_password=base.admin_password, usage=usage, backends=backends, status=status,
                 playground=PLAYGROUND, slots=[
            Slot("ocr", "Document OCR", "The OCR_SGLang_Model service that holds Baidu's Unlimited OCR 2 on the GPU. This service holds no model, "
                 "so it always needs an address.", probe_sglang, "http://127.0.0.1:29260", local=False),
        ])

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
            return JSONResponse({"service": "Reader", "settings": config.describe()})

    app = mcp.streamable_http_app()
    if config is not None and WEB_DIR.is_dir():
        app.router.routes.append(Mount("/admin", StaticFiles(directory=WEB_DIR, html=True)))
    app.add_middleware(InternalTokenMiddleware, token=settings.internal_token)
    return app
