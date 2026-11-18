"""Document parsing through a model service that holds the OCR model: OCR_SGLang_Model (Baidu's Unlimited OCR 2 on the GPU) or
OCR_Paddle_Model (PaddleOCR-VL on a GPU or PP-OCRv5 on the CPU, whichever the machine can run).

This service holds no model. It turns an upload (image or PDF) into page images. For OCR_SGLang_Model it sends them in one chat
request; OCR_SGLang_Model adds Baidu's no-repeat n-gram logit processor, so no sglang wheel is needed here. For OCR_Paddle_Model it
sends one `POST /v1/ocr` per page. Which one answers is read from the `model` in the service's `/health`. Either way the result is
the parsed text, one entry per page. The address and token are saved on the admin page.

shortcut: no streaming, a long document is one request that returns when the model is done. Upgrade when callers need
partial text."""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Callable
from typing import Any

import httpx

from src.admin_api import ProbeError, check

_log = logging.getLogger(__name__)

MODEL_NAME = "unlimited-ocr-2"  # what a token's "projects" list limits
BACKEND_MODEL = "Unlimited-OCR-2"  # --served-model-name of the SGLang server
PADDLE_MODELS = frozenset({"paddleocr-vl", "pp-ocrv5"})  # what OCR_Paddle_Model reports in /health
PAGE_MARK = "<PAGE>"
PAGE_TOKEN_ID, EOS_TOKEN_ID, MAX_PAGE_TOKENS, NGRAM_SIZE = 128827, 1, 20000, 35  # from the model's README
IMAGE_TYPES = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"RIFF": "image/webp"}


class EngineError(RuntimeError):
    """The file could not be parsed. `status` is the HTTP status the service maps it to."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def sniff(data: bytes) -> str:
    """The kind of an upload from its first bytes: "pdf" or an image MIME type. Other files are refused with 415."""
    if data.startswith(b"%PDF"):
        return "pdf"
    for magic, mime in IMAGE_TYPES.items():
        if data.startswith(magic) and (mime != "image/webp" or data[8:12] == b"WEBP"):  # RIFF also starts WAV and AVI
            return mime
    raise EngineError("Send a PDF, PNG, JPEG or WebP file", 415)


def render_pages(data: bytes, dpi: int, max_pages: int) -> list[tuple[bytes, str]]:
    """Page images (bytes, MIME type) of an upload. A PDF is drawn page by page with PyMuPDF. Blocking: run it in a thread."""
    kind = sniff(data)
    if kind != "pdf":
        return [(data, kind)]
    import fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise EngineError("The PDF could not be read", 422) from None
    with doc:
        if doc.needs_pass:
            raise EngineError("The PDF is password protected", 422)
        if doc.page_count > max_pages:
            raise EngineError(f"The PDF has {doc.page_count} pages; the limit is {max_pages}", 422)
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        return [(page.get_pixmap(matrix=matrix).tobytes("png"), "image/png") for page in doc]


def page_count(data: bytes, max_pages: int) -> int:
    """Pages in an upload (1 for an image). Raises EngineError (415, 422) for a bad file or too many pages. Blocking: run it in a thread."""
    if sniff(data) != "pdf":
        return 1
    import fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise EngineError("The PDF could not be read", 422) from None
    with doc:
        if doc.needs_pass:
            raise EngineError("The PDF is password protected", 422)
        if doc.page_count > max_pages:
            raise EngineError(f"The PDF has {doc.page_count} pages; the limit is {max_pages}", 422)
        return doc.page_count


def split_pages(text: str) -> list[str]:
    """The text between the <PAGE> markers, one entry per page. Text before the first marker is kept as page one."""
    parts = text.split(PAGE_MARK)
    if parts and not parts[0].strip():
        parts = parts[1:]
    return [part.strip() for part in parts] or [""]


class OCREngine:
    """`http` is an httpx client (a test passes a mock transport). `source` returns (url, token) of the model service
    on every call, so the admin page can change it live; without it the constructor's address stays."""

    def __init__(self, backend_url: str = "http://127.0.0.1:29260", token: str = "", *, http: httpx.AsyncClient | None = None,
                 source: Callable[[], tuple[str, str] | None] | None = None) -> None:
        self._source = source or (lambda: (backend_url.rstrip("/"), token))
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(6000, connect=10))
        self.ready = False  # the backend answered its last health probe
        self._backend_model: str | None = None  # the `model` of the last /health answer
        self._probed_url: str | None = None  # the address that answer came from

    @property
    def model(self) -> str:
        """What a kept parse depends on: the model the backend reported, or Unlimited OCR 2 until it has answered."""
        return self._backend_model or MODEL_NAME

    def _target(self) -> tuple[str, dict[str, str]]:
        found = self._source()
        if not found:
            self.ready = False
            raise EngineError("No OCR model service address is set (save a connection on the admin page)", 503)
        url, token = found
        return url, ({"X-Internal-Token": token} if token else {})

    async def close(self) -> None:
        await self._http.aclose()

    async def probe(self) -> bool:
        """Asks the backend if it is up and ready, and updates `ready` and the model it reported."""
        try:
            url, _ = self._target()
            reply = await self._http.get(f"{url}/health", timeout=3)
            body = reply.json()
            self.ready = reply.status_code == 200 and body.get("ready") is True
            self._backend_model, self._probed_url = body.get("model") if isinstance(body.get("model"), str) else None, url
        except (httpx.HTTPError, ValueError, AttributeError, EngineError):
            self.ready = False
        return self.ready

    async def _backend_kind(self) -> None:
        """Learns which model service is behind the address before the first parse, and again when the address changes."""
        if self._probed_url != self._target()[0]:
            await self.probe()

    async def parse(self, data: bytes, *, dpi: int, max_pages: int, tokens_per_page: int, crop_mode: bool) -> dict[str, Any]:
        """The parsed document: {"text", "pages", "page_count"}."""
        await self._backend_kind()
        images = await asyncio.to_thread(render_pages, data, dpi, max_pages)
        if self._backend_model in PADDLE_MODELS:
            return await self._parse_paddle(images)
        content = [{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(raw).decode()}"}}
                   for raw, mime in images]
        content.append({"type": "text", "text": f"{PAGE_MARK}<image>" * len(images) + "Multi page parsing."})
        payload: dict[str, Any] = {
            "model": BACKEND_MODEL, "messages": [{"role": "user", "content": content}],
            "max_tokens": tokens_per_page * len(images), "temperature": 0, "skip_special_tokens": False,
            "images_config": {"crop_mode": crop_mode},
            "custom_params": {"ngram_size": NGRAM_SIZE, "window_size": 1024 if len(images) > 1 else 128,
                              "page_token_id": PAGE_TOKEN_ID, "eos_token_id": EOS_TOKEN_ID, "max_page_tokens": MAX_PAGE_TOKENS},
        }
        reply = await self._send("/v1/chat/completions", json=payload)
        try:
            text = reply.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise EngineError("The OCR model service sent an answer this service cannot read", 502) from None
        return {"text": text, "pages": split_pages(text), "page_count": len(images)}

    async def _parse_paddle(self, images: list[tuple[bytes, str]]) -> dict[str, Any]:
        """OCR_Paddle_Model reads one page image per call. The pages are joined with the same markers Unlimited OCR 2 writes."""
        pages = []
        for raw, mime in images:
            reply = await self._send("/v1/ocr", content=raw, content_type=mime)
            try:
                pages.append(str(reply.json()["text"]).strip())
            except (ValueError, KeyError, TypeError):
                raise EngineError("The OCR model service sent an answer this service cannot read", 502) from None
        return {"text": "".join(f"{PAGE_MARK}{page}" for page in pages), "pages": pages or [""], "page_count": len(images)}

    async def _send(self, path: str, *, content_type: str | None = None, **body: Any) -> httpx.Response:
        """One POST to the model service. A refusal, a dead service or an error status becomes an EngineError (502, or 503 while it loads)."""
        url, headers = self._target()
        if content_type:
            headers = {**headers, "Content-Type": content_type}
        try:
            reply = await self._http.post(f"{url}{path}", headers=headers, **body)
        except httpx.HTTPError as error:
            self.ready = False
            raise EngineError(f"The OCR model service is not reachable ({type(error).__name__})", 503) from None
        if reply.status_code in (401, 403):
            raise EngineError("The OCR model service refused the token (check the token saved on the admin page)", 502)
        if reply.status_code != 200:
            _log.warning("The OCR model service answered %s: %s", reply.status_code, reply.text[:300])
            raise EngineError(f"The OCR model service answered {reply.status_code}", 503 if reply.status_code == 503 else 502)
        self.ready = True
        return reply


async def probe_backend(url: str, token: str) -> str:
    """The admin page's Test button for a model service address: reachable and ready, then the token on a call that needs it
    (the model list of OCR_SGLang_Model, `/v1/device` of OCR_Paddle_Model)."""
    health = await check(url, "", "/health")
    try:
        info = health.json()
    except ValueError:
        info = {}
    paddle = isinstance(info, dict) and info.get("model") in PADDLE_MODELS
    reply = await check(url, token, "/v1/device" if paddle else "/v1/models")
    try:
        if paddle:
            reply.json()["device"]
        else:
            reply.json()["data"]
    except (ValueError, KeyError, TypeError):
        raise ProbeError("That address is not an OCR model service.") from None
    ready = isinstance(info, dict) and info.get("ready") is True
    return "Connected, token accepted." + (f" Model: {info['model']}." if paddle else "") + ("" if ready else " The model is still loading.")
