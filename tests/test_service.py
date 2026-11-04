import asyncio

import pytest

from src.errors import DocumentRejected, EngineFailed, FileNotFound, IdentityRequired
from src.service import OCRService
from src.store import DocumentStore
from tests.conftest import FakeEngine, pdf, png


def make(settings, engine=None):
    engine = engine or FakeEngine()
    store = DocumentStore(settings.docs_dir, settings.ttl_seconds, settings.quota_bytes)
    return OCRService(engine, store, settings), engine


async def test_upload_then_parse_returns_the_pages(settings):
    service, engine = make(settings)
    stored, expires = await service.upload("ann", "a.pdf", pdf(2))
    assert stored.page_count == 2 and expires > 0
    result = await service.parse("ann", stored.file_id)
    assert result.pages == ["first page", "second page"] and result.page_count == 2 and result.cached is False
    assert "Parsed 2 page(s)" in result.message and engine.parse_calls == 1


async def test_the_second_parse_comes_from_the_cache(settings):
    service, engine = make(settings)
    stored, _ = await service.upload("ann", "a.png", png())
    await service.parse("ann", stored.file_id)
    again = await service.parse("ann", stored.file_id)
    assert again.cached is True and engine.parse_calls == 1


async def test_a_changed_option_parses_again(settings):
    from dataclasses import replace

    service, engine = make(settings)
    stored, _ = await service.upload("ann", "a.png", png())
    await service.parse("ann", stored.file_id)
    service._settings = replace(settings, dpi=150)
    assert (await service.parse("ann", stored.file_id)).cached is False and engine.parse_calls == 2


async def test_upload_refuses_bad_files_and_too_many_pages(settings):
    service, _ = make(settings)
    with pytest.raises(DocumentRejected):
        await service.upload("ann", "a.txt", b"hello")
    with pytest.raises(DocumentRejected):
        await service.upload("ann", "a.pdf", pdf(11))


async def test_identity_is_required(settings):
    service, _ = make(settings)
    with pytest.raises(IdentityRequired):
        await service.upload("", "a.png", png())
    with pytest.raises(IdentityRequired):
        await service.parse("", "a" * 32)


async def test_a_missing_or_foreign_document_is_not_found(settings):
    service, _ = make(settings)
    stored, _ = await service.upload("ann", "a.png", png())
    with pytest.raises(FileNotFound):
        await service.parse("bob", stored.file_id)
    with pytest.raises(FileNotFound):
        await service.parse("ann", "b" * 32)


async def test_a_backend_that_is_down_is_a_clean_failure(settings):
    service, _ = make(settings, FakeEngine(status=503))
    stored, _ = await service.upload("ann", "a.png", png())
    with pytest.raises(EngineFailed) as error:
        await service.parse("ann", stored.file_id)
    assert "backend said no" not in str(error.value)


async def test_a_file_the_model_side_calls_bad_is_rejected(settings):
    service, _ = make(settings, FakeEngine(status=422))
    stored, _ = await service.upload("ann", "a.png", png())
    with pytest.raises(DocumentRejected):
        await service.parse("ann", stored.file_id)


async def test_a_slow_parse_times_out(settings):
    from dataclasses import replace

    service, _ = make(replace(settings, timeout_s=0.05), FakeEngine(delay=1))
    stored, _ = await service.upload("ann", "a.png", png())
    with pytest.raises(EngineFailed) as error:
        await service.parse("ann", stored.file_id)
    assert "too long" in str(error.value)


async def test_parsing_the_same_document_twice_at_once_runs_the_model_once(settings):
    service, engine = make(settings, FakeEngine(delay=0.1))
    stored, _ = await service.upload("ann", "a.png", png())
    first, second = await asyncio.gather(service.parse("ann", stored.file_id), service.parse("ann", stored.file_id))
    assert engine.parse_calls == 1 and {first.cached, second.cached} == {False, True}
