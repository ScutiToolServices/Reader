"""python -m src.run"""

from __future__ import annotations

import sys

import uvicorn

from src.app import build_app
from src.config import load_settings
from src.options import make_config


def main() -> None:
    settings = load_settings()
    if settings.exposed_without_token:
        sys.exit("UnlimitedOCR refuses to start: OCR_HOST is not a loopback address and INTERNAL_API_TOKEN is empty.")
    uvicorn.run(build_app(settings, config=make_config(settings)), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
