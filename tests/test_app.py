from dataclasses import replace

import pytest
from starlette.testclient import TestClient

from src.app import build_app
from tests.conftest import FakeEngine, pdf, png

ANN = {"X-Requester-Username": "ann"}


def make(settings, **changes):
    return TestClient(build_app(replace(settings, **changes), FakeEngine()))


def test_health(settings):
    assert make(settings).get("/health").json() == {"ok": True, "ready": True}


def test_upload_requires_identity(settings):
    assert make(settings).post("/api/files", content=png()).status_code == 401


def test_upload_ok(settings):
    response = make(settings).post("/api/files", content=pdf(3), headers={**ANN, "X-Filename": "../../a.pdf"})
    body = response.json()
    assert response.status_code == 200 and len(body["file_id"]) == 32
    assert body["page_count"] == 3 and body["size_bytes"] > 0 and body["expires_at"] > 0


def test_upload_rejects_bad_files_and_too_many_pages(settings):
    c = make(settings)
    assert c.post("/api/files", content=b"hello", headers=ANN).status_code == 400
    assert c.post("/api/files", content=pdf(11), headers=ANN).status_code == 400


def test_upload_over_byte_cap_is_413(settings):
    assert make(settings, max_bytes=10).post("/api/files", content=png(), headers=ANN).status_code == 413


def test_upload_over_quota_is_413(settings):
    response = make(settings, quota_bytes=10).post("/api/files", content=png(), headers=ANN)
    assert response.status_code == 413 and response.json()["error"] == "quota_exceeded"


def test_upload_needs_token_when_configured(settings):
    c = make(settings, internal_token="secret")
    assert c.post("/api/files", content=png(), headers=ANN).status_code == 401
    assert c.post("/api/files", content=png(), headers={**ANN, "X-Internal-Token": "secret"}).status_code == 200
    assert c.get("/health").status_code == 200


def test_parse_enforces_public_token_and_requester_identity(settings):
    c = make(settings, internal_token="secret")
    body = {"file_id": "a" * 32}
    assert c.post("/api/parse", json=body, headers=ANN).status_code == 401
    assert c.post("/api/parse", json=body, headers={"X-Internal-Token": "secret"}).status_code == 401


def test_parse_reuses_owned_document_cache_and_counts_usage(settings):
    engine = FakeEngine()
    c = TestClient(build_app(replace(settings, admin_password="pw"), engine))
    file_id = c.post("/api/files", content=png(), headers=ANN).json()["file_id"]
    first = c.post("/api/parse", json={"file_id": file_id}, headers=ANN)
    assert first.status_code == 200
    assert first.json()["text"] == "<PAGE>first page<PAGE>second page"
    assert first.json()["pages"] == ["first page", "second page"]
    assert first.json()["cached"] is False
    assert c.post("/api/parse", json={"file_id": file_id}, headers=ANN).json()["cached"] is True
    assert engine.parse_calls == 1
    wrong_owner = c.post("/api/parse", json={"file_id": file_id}, headers={"X-Requester-Username": "bob"})
    assert wrong_owner.status_code == 404 and wrong_owner.json()["error"] == "file_not_found"
    status = c.get("/admin/status", headers={"X-Admin-Password": "pw"}).json()
    assert status["usage"]["calls"] == 3
    assert status["usage"]["errors"] == 1
    assert status["usage"]["tools"] == {"parse": 3}


@pytest.mark.parametrize("body", [{}, {"file_id": 1}, {"file_id": "../x"}, {"file_id": "a" * 32, "owner": "bob"}])
def test_parse_rejects_invalid_body(settings, body):
    assert make(settings).post("/api/parse", json=body, headers=ANN).status_code == 422


def test_parse_rejects_invalid_json_and_oversize_body(settings):
    c = make(settings)
    assert c.post("/api/parse", content=b"invalid", headers=ANN).status_code == 422
    assert c.post("/api/parse", content=b" " * 4097, headers=ANN).status_code == 413


@pytest.mark.parametrize("engine_status,expected", [(503, 503), (422, 400)])
def test_parse_maps_service_failures_without_backend_text(settings, engine_status, expected):
    c = TestClient(build_app(settings, FakeEngine(status=engine_status)))
    file_id = c.post("/api/files", content=png(), headers=ANN).json()["file_id"]
    response = c.post("/api/parse", json={"file_id": file_id}, headers=ANN)
    assert response.status_code == expected
    assert "backend said no" not in response.text


def test_the_admin_page_is_off_without_a_password(settings):
    assert make(settings).get("/admin/settings").status_code in (404, 405)


def test_the_admin_settings_need_the_password_and_can_be_changed(settings):
    c = make(settings, admin_password="pw")
    assert c.get("/admin/settings").status_code == 401
    shown = c.get("/admin/settings", headers={"X-Admin-Password": "pw"}).json()
    assert shown["service"] == "Reader" and {row["key"] for row in shown["settings"]} >= {"max_pages", "dpi", "crop_mode"}
    saved = c.put("/admin/settings", json={"values": {"max_pages": 2}}, headers={"X-Admin-Password": "pw"})
    assert saved.status_code == 200
    assert c.post("/api/files", content=pdf(3), headers=ANN).status_code == 400  # the new limit applies at once
    assert c.put("/admin/settings", json={"values": {"max_pages": 0}}, headers={"X-Admin-Password": "pw"}).status_code == 422


def test_the_admin_page_shows_status_usage_and_the_ocr_slot(settings):
    c = make(settings, admin_password="pw")
    pw = {"X-Admin-Password": "pw"}
    assert c.get("/admin/status").status_code == 401
    body = c.get("/admin/status", headers=pw).json()
    assert body["service"] == "Reader" and {"label": "SGLangModel", "value": "ready"} in body["items"]
    slot = c.get("/admin/backends", headers=pw).json()["backends"][0]
    assert (slot["key"], slot["url"], slot["local"], slot["source"]) == ("ocr", "", False, "environment")
    assert c.put("/admin/backends/ocr", headers=pw, json={"url": ""}).status_code == 422  # there is no local OCR engine
    moved = c.put("/admin/backends/ocr", headers=pw, json={"url": "http://gpu:9210", "token": "t"}).json()["backends"][0]
    assert moved["url"] == "http://gpu:9210" and moved["token_set"] is True and moved["source"] == "saved"
