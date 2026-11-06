"""Upload and parse: validate, store, cache lookup, parse under a semaphore."""

from __future__ import annotations

import asyncio

from src.config import Settings
from src.contract import ParseResult
from src.engine import EngineError, OCREngine, page_count
from src.errors import DocumentRejected, EngineFailed, FileNotFound, IdentityRequired
from src.store import DocumentStore, StoredDoc


class OCRService:
    def __init__(self, engine: OCREngine, store: DocumentStore, settings: Settings) -> None:
        self._engine, self._store, self._settings = engine, store, settings
        self._slots = asyncio.Semaphore(settings.concurrency)
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._quota_lock = asyncio.Lock()

    def _signature(self) -> str:
        """What a kept parse depends on besides the file: the model and the options that change its output."""
        s = self._settings
        return f"{self._engine.model}|{s.dpi}|{s.tokens_per_page}|{int(s.crop_mode)}"

    async def upload(self, owner: str, filename: str, data: bytes) -> tuple[StoredDoc, float]:
        if not owner:
            raise IdentityRequired("Reader needs to know who is asking.")
        try:
            pages = await asyncio.to_thread(page_count, data, self._settings.max_pages)
        except EngineError as error:
            raise DocumentRejected(str(error)) from None
        file_id = DocumentStore.file_id(owner, data)
        async with self._quota_lock:
            stored = await asyncio.to_thread(self._store.put, owner, file_id, data, filename, pages)
        return stored, self._store.expires_at(stored)

    async def parse(self, owner: str, file_id: str) -> ParseResult:
        if not owner:
            raise IdentityRequired("Reader needs to know who is asking.")
        key = (owner, file_id)
        lock = self._locks.setdefault(key, asyncio.Lock())
        try:
            async with lock:
                stored = await asyncio.to_thread(self._store.get, owner, file_id)
                if stored is None:
                    raise FileNotFound("That document expired or does not exist. Attach it again.")
                signature = self._signature()
                payload = await asyncio.to_thread(self._store.get_result, owner, file_id, signature)
                cached = payload is not None
                if payload is None:
                    payload = await self._run(stored)
                    await asyncio.to_thread(self._store.put_result, owner, file_id, signature, payload)
        finally:
            if not lock.locked() and not getattr(lock, "_waiters", None):
                self._locks.pop(key, None)
        return ParseResult(
            text=payload["text"], pages=payload["pages"], page_count=payload["page_count"], cached=cached,
            message=f"Parsed {payload['page_count']} page(s) ({len(payload['text'].split())} words).",
        )

    async def _run(self, stored: StoredDoc) -> dict:
        s = self._settings
        data = await asyncio.to_thread(stored.path.read_bytes)
        try:
            async with self._slots:
                return await asyncio.wait_for(
                    self._engine.parse(data, dpi=s.dpi, max_pages=s.max_pages, tokens_per_page=s.tokens_per_page, crop_mode=s.crop_mode),
                    s.timeout_s,
                )
        except TimeoutError:
            raise EngineFailed("Parsing took too long. Try a shorter document.") from None
        except EngineError as error:
            # 422 and 415 mean the file itself is wrong; 5xx means the model side is not available.
            if error.status in (415, 422):
                raise DocumentRejected(str(error)) from None
            raise EngineFailed("The OCR model is not available right now. Try again.") from None
