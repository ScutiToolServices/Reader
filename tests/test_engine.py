import asyncio

import pytest

from src.engine import EngineError, page_count, render_pages, sniff, split_pages
from tests.conftest import backend_engine, pdf, png

OPTIONS = {"dpi": 72, "max_pages": 10, "tokens_per_page": 100, "crop_mode": True}


def test_split_pages_uses_the_markers():
    assert split_pages("<PAGE>a<PAGE> b ") == ["a", "b"]
    assert split_pages("no marker") == ["no marker"]
    assert split_pages("") == [""]


def test_uploads_are_told_apart_by_their_first_bytes():
    assert sniff(b"%PDF-1.7") == "pdf" and sniff(png()) == "image/png" and sniff(b"\xff\xd8\xffx") == "image/jpeg"
    assert sniff(b"RIFF    WEBPVP8 ") == "image/webp"
    for other in (b"hello", b"RIFF    WAVEfmt "):
        with pytest.raises(EngineError) as error:
            sniff(other)
        assert error.value.status == 415


def test_a_pdf_gives_one_image_per_page_and_the_limit_applies():
    assert [mime for _, mime in render_pages(pdf(3), 72, 10)] == ["image/png"] * 3
    assert page_count(pdf(3), 10) == 3 and page_count(png(), 10) == 1
    for call in (lambda: render_pages(pdf(3), 72, 2), lambda: page_count(pdf(3), 2)):
        with pytest.raises(EngineError) as error:
            call()
        assert error.value.status == 422


def test_a_broken_pdf_is_refused():
    for call in (lambda: render_pages(b"%PDF-1.7 not really", 72, 10), lambda: page_count(b"%PDF-1.7 not really", 10)):
        with pytest.raises(EngineError) as error:
            call()
        assert error.value.status == 422


def test_parse_sends_the_pages_in_one_request_like_the_readme():
    engine = backend_engine()
    result = asyncio.run(engine.parse(pdf(2), **OPTIONS))
    body = engine.requests[0]
    content = body["messages"][0]["content"]
    assert result == {"text": "<PAGE>first page<PAGE>second page", "pages": ["first page", "second page"], "page_count": 2}
    assert [item["type"] for item in content] == ["image_url", "image_url", "text"]
    assert content[-1]["text"] == "<PAGE><image><PAGE><image>Multi page parsing."
    assert body["model"] == "Unlimited-OCR-2" and body["max_tokens"] == 200 and body["temperature"] == 0
    assert body["images_config"] == {"crop_mode": True} and body["custom_params"]["window_size"] == 1024
    assert body["custom_params"]["page_token_id"] == 128827 and "custom_logit_processor" not in body


def test_a_single_page_uses_the_narrow_window():
    engine = backend_engine(text="<PAGE>only")
    asyncio.run(engine.parse(png(), **OPTIONS))
    assert engine.requests[0]["custom_params"]["window_size"] == 128


def test_the_token_is_sent_and_a_refusal_is_reported():
    engine = backend_engine(token="sglm_abc")
    asyncio.run(engine.parse(png(), **OPTIONS))
    assert engine.headers[-1]["x-internal-token"] == "sglm_abc"
    with pytest.raises(EngineError) as error:
        asyncio.run(backend_engine(status=401).parse(png(), **OPTIONS))
    assert error.value.status == 502 and "admin page" in str(error.value)


def test_a_backend_error_becomes_502_a_loading_backend_503_and_a_dead_one_503():
    for status, expected in ((500, 502), (503, 503)):
        with pytest.raises(EngineError) as error:
            asyncio.run(backend_engine(status=status).parse(png(), **OPTIONS))
        assert error.value.status == expected
    dead = backend_engine(up=False)
    with pytest.raises(EngineError) as error:
        asyncio.run(dead.parse(png(), **OPTIONS))
    assert error.value.status == 503 and not dead.ready


def test_probe_tracks_the_backend():
    assert asyncio.run(backend_engine().probe()) is True
    assert asyncio.run(backend_engine(backend_ready=False).probe()) is False
    assert asyncio.run(backend_engine(up=False).probe()) is False


def test_the_address_is_read_on_every_call_and_an_empty_one_is_a_clear_error():
    import httpx

    from src.engine import OCREngine

    target = {"now": ("http://a:29260", "t1")}
    engine = OCREngine(source=lambda: target["now"])
    assert engine._target() == ("http://a:29260", {"X-Internal-Token": "t1"})
    target["now"] = ("http://b:29260", "")
    assert engine._target() == ("http://b:29260", {})
    target["now"] = None
    with pytest.raises(EngineError, match="No OCR model service address") as raised:
        engine._target()
    assert raised.value.status == 503
    assert asyncio.run(engine.probe()) is False  # probing with no address is not ready, not a crash


async def test_probe_backend_checks_health_then_the_token_on_the_model_list(monkeypatch):
    import httpx

    from src.engine import probe_backend

    real, seen = httpx.AsyncClient, []

    def handler(request):
        seen.append((request.url.path, request.headers.get("X-Internal-Token")))
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True, "ready": False})
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    assert await probe_backend("http://s:29260", "tok") == "Connected, token accepted. The model is still loading."
    assert seen == [("/health", None), ("/v1/models", "tok")]


def paddle_engine(model="pp-ocrv5", status=200, token="paddle_abc"):
    """A real OCREngine talking to a fake OCR_Paddle_Model: /health names the model, /v1/ocr answers "page N" per call."""
    import httpx

    from src.engine import OCREngine

    seen = []

    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "model": model, "ready": True})
        seen.append((request.url.path, request.headers.get("content-type"), request.headers.get("x-internal-token"), request.content))
        if status != 200:
            return httpx.Response(status, text="boom")
        return httpx.Response(200, json={"text": f" page {len(seen)} ", "format": "text", "model": model, "device": "cpu", "duration_ms": 1})

    engine = OCREngine("http://paddle:29262", token, http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    engine.requests = seen
    return engine


def test_paddle_backend_gets_one_image_per_call_and_the_pages_are_marked_like_unlimited_ocr():
    engine = paddle_engine()
    assert engine.model == "unlimited-ocr-2"  # until the backend has answered
    result = asyncio.run(engine.parse(pdf(2), **OPTIONS))
    assert result == {"text": "<PAGE>page 1<PAGE>page 2", "pages": ["page 1", "page 2"], "page_count": 2}
    assert [(path, kind, token) for path, kind, token, _ in engine.requests] == [("/v1/ocr", "image/png", "paddle_abc")] * 2
    assert all(body[1:4] == b"PNG" for *_, body in engine.requests)
    assert engine.model == "pp-ocrv5"  # a kept parse is keyed by the model that made it


def test_paddle_backend_errors_map_like_the_other_backend():
    for status, expected in ((401, 502), (500, 502), (503, 503)):
        with pytest.raises(EngineError) as error:
            asyncio.run(paddle_engine(status=status).parse(png(), **OPTIONS))
        assert error.value.status == expected


def test_the_backend_is_asked_again_when_the_address_changes():
    import httpx

    from src.engine import OCREngine

    models = {"http://a:29260": "unlimited-ocr-2", "http://b:29262": "paddleocr-vl"}
    target = {"now": "http://a:29260"}

    def handler(request):
        base = f"{request.url.scheme}://{request.url.host}:{request.url.port}"
        if request.url.path == "/health":
            return httpx.Response(200, json={"ready": True, "model": models[base]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "<PAGE>x"}}], "text": "y"})

    engine = OCREngine(source=lambda: (target["now"], ""), http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    asyncio.run(engine.parse(png(), **OPTIONS))
    assert engine.model == "unlimited-ocr-2"
    target["now"] = "http://b:29262"
    asyncio.run(engine.parse(png(), **OPTIONS))
    assert engine.model == "paddleocr-vl"


async def test_probe_backend_uses_the_device_call_for_ocr_paddle_model(monkeypatch):
    import httpx

    from src.engine import probe_backend

    real, seen = httpx.AsyncClient, []

    def handler(request):
        seen.append((request.url.path, request.headers.get("X-Internal-Token")))
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "model": "pp-ocrv5", "ready": True})
        return httpx.Response(200, json={"device": "cpu", "model": "pp-ocrv5"})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    assert await probe_backend("http://p:29262", "tok") == "Connected, token accepted. Model: pp-ocrv5."
    assert seen == [("/health", None), ("/v1/device", "tok")]
