from src.config import Settings, load_settings


def test_loopback_without_token_is_fine():
    assert not Settings(host="127.0.0.1", internal_token="").exposed_without_token


def test_exposed_without_token_is_flagged():
    assert Settings(host="0.0.0.0", internal_token="").exposed_without_token
    assert not Settings(host="0.0.0.0", internal_token="x").exposed_without_token


def test_defaults_fit_armory_call_budget():
    settings = Settings()
    assert settings.port == 8092 and settings.timeout_s < 120


def test_environment_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("READER_PORT", "9001")
    monkeypatch.setenv("READER_MAX_PAGES", "5")
    monkeypatch.setenv("READER_TTL_HOURS", "2")
    monkeypatch.setenv("READER_CROP_MODE", "0")
    monkeypatch.setenv("READER_BACKEND_URL", "http://gpu:9210")
    monkeypatch.setenv("READER_DATA_DIR", str(tmp_path))
    settings = load_settings()
    assert settings.port == 9001 and settings.max_pages == 5 and settings.crop_mode is False
    assert settings.ttl_seconds == 7200 and settings.docs_dir == tmp_path / "docs" and settings.backend_url == "http://gpu:9210"
