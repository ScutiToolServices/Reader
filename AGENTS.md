# UnlimitedOCR

Document OCR MCP server for Citadel and Ember. A standalone service on port 8092, to be registered in Armory as the `ocr` extension (not done yet; the entry is in `README.md`). Counterpart of Scribe (`../Scribe`, speech to text) and Bard (`../Bard`). It holds no model: it calls `AI/ModelServices/SGLangModel`, which runs Baidu's Unlimited OCR 2 on the GPU.

## Agent instructions
This file is the one instruction file for every coding agent; `CLAUDE.md` only imports it (`@AGENTS.md`). Edit this file, never `CLAUDE.md`.

## Commands (from this folder, managed by uv)
- Install: `uv sync` (on this machine set `UV_CACHE_DIR=.uv_cache UV_LINK_MODE=copy`; the default cache is on another drive. An old `.venv` here is stale since the folder moved; use `UV_PROJECT_ENVIRONMENT=.venv_ocr` or delete it)
- Test: `uv run pytest -q` (no GPU needed; SGLangModel is faked)
- Run: `uv run python -m src.run`, or `docker compose up -d --build`

## Rules
- Never read or print `.env`.
- Logic lives in `service.py`, `engine.py`, `store.py`; `app.py` is glue. Tools never call an AI.
- `engine.py` is the only code that talks to SGLangModel (httpx async). Blocking work (PDF page counting and drawing, file IO) runs through `asyncio.to_thread`.
- `INTERNAL_API_TOKEN` guards `/mcp` and `/api/*`; an exposed bind without it must refuse to start.
- Result models end with `message`. Error messages never contain paths or backend text.
- The owner key is the username (`_meta.requester` for tools, `X-Requester-Username` for HTTP).
- `src/runtime.py` is shared with Bard and Scribe and copies Laya's `settings.py`: keep the copies in step. `web/index.html` is the same file as in Scribe and Bard (the service name comes from the API).
- SGLangModel adds Baidu's no-repeat n-gram logit processor; do not add an sglang dependency here.
- Defaults are tuned to the Armory call timeout (120 s): 30 pages, 110 s parse timeout. Nothing has been measured on the real GPU host; raise pages and timeout together only after timing a real document.
- Uploaded documents and their parse results are kept 24 hours on this machine, then deleted.
- Admin page (`web/index.html`, `src/admin_api.py`, `tests/test_admin_api.py`): the same three files in Bard, Scribe and UnlimitedOCR; change one, copy it to the other two. With `OCR_ADMIN_PASSWORD` set, `/admin/` shows status and usage per user (`GET /admin/status`, in-memory `Usage`, reset on restart), the model-service slots (`/admin/backends`: where OCR (`ocr` slot, always remote: `local=False`, `OCREngine(source=...)`) runs, address + token saved in `.data/backends.json`, never sent back, read on every call) and the settings. Header `X-Admin-Password`. Each service passes its own slots, `status` items and probes to `register(...)` in `app.py`. Parse calls are counted through `usage.track` in `tool_ocr_parse`.
