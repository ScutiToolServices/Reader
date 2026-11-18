"""The Reader options the admin page can change. The default shown is the value at start (.env or built in), which
load_settings already read; a saved value wins over it."""

from __future__ import annotations

from src.config import Settings
from src.runtime import Config, LiveSettings, Setting

MB = 1024 * 1024

# attribute of Settings -> (setting key, conversion to the attribute's unit)
FIELDS = {
    "max_pages": ("max_pages", int),
    "timeout_s": ("timeout_s", int),
    "dpi": ("dpi", int),
    "tokens_per_page": ("tokens_per_page", int),
    "crop_mode": ("crop_mode", bool),
    "max_bytes": ("max_upload_mb", lambda mb: int(mb * MB)),
    "ttl_seconds": ("ttl_hours", lambda hours: hours * 3600),
    "quota_bytes": ("quota_mb", lambda mb: mb * MB),
    "concurrency": ("concurrency", int),
}

_TUNED = "Armory cancels a call after 120 s: raise only after measuring on the real GPU host"


def schema(base: Settings) -> list[Setting]:
    return [
        Setting("max_pages", "Most pages per document", "int", base.max_pages, minimum=1, maximum=5000,
                help="A PDF with more pages is refused at upload. " + _TUNED),
        Setting("timeout_s", "Parse time limit (seconds)", "int", base.timeout_s, minimum=1, maximum=600, help=_TUNED),
        Setting("dpi", "PDF render resolution (DPI)", "int", base.dpi, minimum=72, maximum=600,
                help="Baidu's README uses 300. Lower is faster and uses less GPU memory"),
        Setting("tokens_per_page", "Output tokens per page", "int", base.tokens_per_page, minimum=1, maximum=20000,
                help="The whole document gets this many times its page count; the model stops earlier when it is done"),
        Setting("crop_mode", "Tile pages (gundam mode)", "bool", base.crop_mode,
                help="On = tiles, better on dense pages. Off = one view per page (base mode), faster"),
        Setting("max_upload_mb", "Largest upload (MB)", "float", base.max_bytes / MB, minimum=0.1, maximum=1024),
        Setting("ttl_hours", "Keep uploads for (hours)", "int", base.ttl_seconds // 3600, minimum=1, maximum=8760),
        Setting("quota_mb", "Document storage per user (MB)", "int", base.quota_bytes // MB, minimum=1, maximum=100000),
        Setting("concurrency", "Parses at once", "int", base.concurrency, minimum=1, maximum=16, restart=True,
                help="OCR_SGLang_Model batches the work itself, so one is usually enough"),
        Setting("data_path", "Data folder", "text", "", restart=True,
                help=f"Where stored data (documents) goes. Empty = {base.state_dir}. Applies after a restart; files already stored are not moved. "
                     f"Settings and saved model connections stay in the standard folder."),
    ]


def make_config(base: Settings) -> Config | None:
    """None, so nothing is changeable at run time, unless SERVICE_ADMIN_PASSWORD is set."""
    return Config(base.state_dir / "settings.json", schema(base)) if base.admin_password else None


def live(base: Settings, config: Config | None):
    return LiveSettings(base, config, FIELDS) if config else base
