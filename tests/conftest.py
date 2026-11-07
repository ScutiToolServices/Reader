import asyncio
import io

import httpx
import pytest
from PIL import Image

from src.config import Settings
from src.engine import EngineError, OCREngine

TEXT = "<PAGE>first page<PAGE>second page"


def png(shade: int = 0) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (shade, shade, shade)).save(buf, "PNG")
    return buf.getvalue()


def pdf(pages: int = 2) -> bytes:
    import fitz

    doc = fitz.open()
    for number in range(pages):
        doc.new_page().insert_text((72, 72), f"page {number + 1}")
    return doc.tobytes()


class FakeEngine:
    """Stands in for OCREngine: `parse` answers two pages (or fails with `status`) and counts its calls."""

    model = "fake-ocr"

    def __init__(self, delay: float = 0.0, status: int | None = None):
        self.parse_calls = 0
        self.delay, self.status = delay, status

    async def probe(self) -> bool:
        return True

    async def parse(self, data: bytes, **options) -> dict:
        self.parse_calls += 1
        await asyncio.sleep(self.delay)
        if self.status:
            raise EngineError("backend said no", self.status)
        return {"text": TEXT, "pages": ["first page", "second page"], "page_count": 2}


def backend_engine(text: str = TEXT, status: int = 200, up: bool = True, backend_ready: bool = True, token: str = "") -> OCREngine:
    """A real OCREngine talking to a fake OCR_SGLang_Model; `engine.requests` lists the JSON bodies, `engine.headers` the headers."""
    seen, seen_headers = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        if not up:
            raise httpx.ConnectError("refused")
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "ready": backend_ready})
        import json

        seen.append(json.loads(request.content))
        seen_headers.append(dict(request.headers))
        if status != 200:
            return httpx.Response(status, text="boom")
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    engine = OCREngine("http://sglm:9210", token, http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    engine.requests, engine.headers = seen, seen_headers
    return engine


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, max_pages=10, max_bytes=1_000_000, timeout_s=2)


@pytest.fixture
def engine() -> FakeEngine:
    return FakeEngine()
