"""Reader settings, read from the environment (and a local .env, never committed)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8092
    internal_token: str = ""
    data_dir: Path = PROJECT_DIR / ".data"
    # SGLangModel (AI/ModelServices/SGLangModel), which holds the model on the GPU.
    backend_url: str = "http://127.0.0.1:9210"
    backend_token: str = ""
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
    def docs_dir(self) -> Path:
        return self.data_dir / "docs"

    @property
    def exposed_without_token(self) -> bool:
        """Listening beyond loopback with no token lets anything that can reach the port call every tool."""
        return not self.internal_token and self.host not in LOOPBACK_HOSTS


def load_settings() -> Settings:
    load_dotenv(PROJECT_DIR / ".env")
    env = os.environ.get
    return Settings(
        host=env("READER_HOST", "127.0.0.1"),
        port=int(env("READER_PORT", "8092")),
        internal_token=env("INTERNAL_API_TOKEN", ""),
        data_dir=Path(env("READER_DATA_DIR") or PROJECT_DIR / ".data"),
        backend_url=env("READER_BACKEND_URL", "http://127.0.0.1:9210"),
        backend_token=env("READER_BACKEND_TOKEN", ""),
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
