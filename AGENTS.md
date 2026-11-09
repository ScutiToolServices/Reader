# Reader

Document OCR MCP server for Citadel and Ember. A standalone service on port 29402, registered in Citadel's Armory as the `ocr` extension (`READER_TOKEN` in Armory's `.env`; ember_api uploads through `POST /api/attachments/document`). Counterpart of Scribe (`../Scribe`, speech to text) and Bard (`../Bard`). It holds no model: it calls `AI/ModelServices/OCR_Paddle_Model` (PaddleOCR-VL on a GPU, PP-OCRv5 on the CPU) or `AI/ModelServices/OCR_SGLang_Model` (Baidu's Unlimited OCR 2 on the GPU), whichever the `ocr` slot points at.

## Agent instructions
This file is the one instruction file for every coding agent; `CLAUDE.md` only imports it (`@AGENTS.md`). Edit this file, never `CLAUDE.md`.

## Commands (from this folder, managed by uv)
- Install: `uv sync` (on this machine set `UV_CACHE_DIR=.uv_cache UV_LINK_MODE=copy`; the default cache is on another drive. An old `.venv` here is stale since the folder moved; use `UV_PROJECT_ENVIRONMENT=.venv_ocr` or delete it)
- Test: `uv run pytest -q` (no GPU needed; both model services are faked)
- Run: `run.bat run`, or `uv run python -m src.run` (add `--dotenv` to load `.env`), or `docker compose up -d --build`

## Rules
- Follow the `tool-service-parity` skill and `AI/ToolServices/_docs/SHARED-FEATURES.md` (what must match in every tool service) and `AI/ToolServices/_docs/SERVICE-SPECIFIC.md` (what differs on purpose). A change to a shared feature goes to every tool service; a new difference goes into `SERVICE-SPECIFIC.md` in the same change.
- Data folder: `Settings.data_dir` holds documents; the admin setting `data_path` (restart, `src/config.py` `with_saved_data_path`) moves it at the next start and keeps `settings.json` and `backends.json` in `Settings.state_dir` (the first folder). No `.env` variable; `SERVICE_DATA_DIR` is read only as the base folder (Docker).
- Never read or print `.env`.
- Logic lives in `service.py`, `engine.py`, `store.py`; `app.py` is glue. Tools never call an AI.
- `engine.py` is the only code that talks to the model services (httpx async). It learns which one answers from `model` in `/health` (`paddleocr-vl` or `pp-ocrv5` = OCR_Paddle_Model: one `POST /v1/ocr` per page, pages joined with `<PAGE>`; anything else = OCR_SGLang_Model's chat request) and asks again when the address changes. Blocking work (PDF page counting and drawing, file IO) runs through `asyncio.to_thread`.
- Tokens guard `/mcp` and `/api/*` (header `X-Internal-Token`). With `SERVICE_ADMIN_PASSWORD` set, each caller gets its own token from the admin page (`GET/POST /admin/tokens`, `DELETE /admin/tokens/{id}`; `src/tokens.py` keeps them hashed in `tokens.json` in the state folder; `src/middleware.py` checks them and answers 401, or 429 over a token's calls-per-minute). No admin password = no checks, so an exposed bind without one must refuse to start. `src/tokens.py`, `src/middleware.py`, `tests/test_tokens.py` and `tests/seed.py` are the same in all five tool services.
- Result models end with `message`. Error messages never contain paths or backend text.
- The owner key is the username (`_meta.requester` for tools, `X-Requester-Username` for HTTP).
- `src/runtime.py` is shared with Bard and Scribe and copies Laya's `settings.py`: keep the copies in step. `web/index.html` is the same file as in Scribe and Bard (the service name comes from the API).
- OCR_SGLang_Model adds Baidu's no-repeat n-gram logit processor; do not add an sglang dependency here.
- Defaults are tuned to the Armory call timeout (120 s): 30 pages, 110 s parse timeout. Nothing has been measured on the real GPU host; raise pages and timeout together only after timing a real document.
- Uploaded documents and their parse results are kept 24 hours on this machine, then deleted.
- Admin page (`web/index.html`, `src/admin_api.py`, `tests/test_admin_api.py`): the same three files in Bard, Scribe and Reader; change one, copy it to the other two. With `SERVICE_ADMIN_PASSWORD` set, `/admin/` shows status and usage per user (`GET /admin/status`, in-memory `Usage`, reset on restart), the model-service slots (`/admin/backends`: where OCR (`ocr` slot, always remote: `local=False`, `OCREngine(source=...)`) runs, address + token saved in `.data/backends.json`, never sent back, read on every call) and the settings. Header `X-Admin-Password`. Each service passes its own slots, `status` items and probes to `register(...)` in `app.py`. Parse calls are counted through `usage.track` in `tool_ocr_parse`.
- Saved connections: the admin page also keeps a shared list of named model-service addresses (`/admin/connections/{name}`, under the reserved `_connections` key of `backends.json`, token never sent back). A slot picks one with `PUT /admin/backends/{key}` `{"connection": name}`, so editing a connection updates every slot using it; a connection a slot uses cannot be deleted (409). Addresses and tokens are saved only on the admin page (there are no environment variables for them); a slot with no address runs in this service, or fails when it has no local engine.
- Behaviour changes update `README.md`, `deployment.md`, the guides in `docs/`, `.env.example`, `AGENTS.md` and `CHANGELOG.md` in the same commit.
- Commit with the noreply author email `214214011+scutiii2@users.noreply.github.com` (another address is rejected on push). Push `main`, then run `python tools/publish_live.py`. Build Docker only when the Dockerfile or the dependencies changed.
- Shared admin files (`web/index.html`, `web/playground.js`, `src/admin_api.py`, `src/tokens.py`, `src/middleware.py`, `tests/test_admin_api.py`, `tests/test_tokens.py`, `tests/seed.py`, `tools/check_sync.py`) are byte-identical in the five tool services. Run `python tools/check_sync.py` after changing one; it must exit 0.
