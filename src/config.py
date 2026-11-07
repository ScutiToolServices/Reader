"""Reader settings, read from the environment (and a local .env, never committed)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, replace
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8092
    internal_token: str = ""
    data_dir: Path = PROJECT_DIR / ".data"
    config_dir: Path | None = None  # set when the data folder was moved: the folder that keeps settings.json
    # OCR_SGLang_Model (AI/ModelServices/OCR_SGLang_Model), which holds the model on the GPU.
    max_bytes: int = 50 * 1024 * 1024
    # Armory cancels a tool call after 120 s, so the page limit and the time limit are tuned together. Measure on the real
    # GPU host (nothing has run against the model yet) and raise both after that.
    max_pages: int = 30
    timeout_s: int = 110
    dpi: int = 300
    tokens_per_page: int = 8000
    crop_mode: bool = True
    ttl_seconds: int = 24 * 3600
    quota_bytes: int = 200 * 1024 * 1024
    concurrency: int = 1
    # Unlocks /admin/ (settings page). Empty = the page is off and settings stay as the environment set them.
    admin_password: str = ""

    @property
    def state_dir(self) -> Path:
        """Where settings.json and backends.json live: the first data folder, even after the data folder was moved."""
        return self.config_dir or self.data_dir

    @property
    def docs_dir(self) -> Path:
        return self.data_dir / "docs"

    @property
    def exposed_without_token(self) -> bool:
        """Listening beyond loopback with no token lets anything that can reach the port call every tool."""
        return not self.internal_token and self.host not in LOOPBACK_HOSTS


def _from_environment() -> Settings:
    env = os.environ.get
    return Settings(
        host=env("READER_HOST", "127.0.0.1"),
        port=int(env("READER_PORT", "8092")),
        internal_token=env("INTERNAL_API_TOKEN", ""),
        data_dir=Path(env("READER_DATA_DIR") or PROJECT_DIR / ".data"),
        max_bytes=int(env("READER_MAX_UPLOAD_MB", "50")) * 1024 * 1024,
        max_pages=int(env("READER_MAX_PAGES", "30")),
        timeout_s=int(env("READER_TIMEOUT_S", "110")),
        dpi=int(env("READER_DPI", "300")),
        tokens_per_page=int(env("READER_TOKENS_PER_PAGE", "8000")),
        crop_mode=env("READER_CROP_MODE", "1").strip().lower() in ("1", "true", "yes", "on"),
        ttl_seconds=int(env("READER_TTL_HOURS", "24")) * 3600,
        quota_bytes=int(env("READER_QUOTA_MB", "200")) * 1024 * 1024,
        concurrency=int(env("READER_CONCURRENCY", "1")),
        admin_password=env("READER_ADMIN_PASSWORD", ""),
    )


def with_saved_data_path(settings: Settings) -> Settings:
    """The admin page's "Data folder" setting moves stored data (audio, uploads, voices, results) to another folder.
    It is read once, here at start. Settings and saved model connections stay in the first folder, which is where this
    value is saved. A folder that cannot be written is ignored."""
    try:
        saved = json.loads((settings.data_dir / "settings.json").read_text("utf-8")).get("data_path")
    except (OSError, ValueError, AttributeError):
        return settings
    if not isinstance(saved, str) or not saved.strip():
        return settings
    target = Path(saved.strip()).expanduser()
    if not target.is_absolute():
        target = PROJECT_DIR / target
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".write-test"
        probe.write_text("x")
        probe.unlink()
    except OSError:
        logging.getLogger(__name__).warning("Data folder %s cannot be written; using %s", target, settings.data_dir)
        return settings
    return replace(settings, data_dir=target, config_dir=settings.data_dir)


def load_settings() -> Settings:
    return with_saved_data_path(_from_environment())
