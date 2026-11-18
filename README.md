# Reader

Document OCR for Citadel and Ember. A user attaches a PDF or image (PNG, JPEG, WebP) in chat; the agent calls `ocr__tool_ocr_parse` and answers from the text. It does not run a model here: this MCP server draws PDF pages with PyMuPDF and sends them to a model service, which you pick on the admin page. **OCR_Paddle_Model** (`AI/ModelServices/OCR_Paddle_Model`, port 29262) uses PaddleOCR-VL on a capable GPU and PP-OCRv5 on the CPU otherwise, one call per page. **OCR_SGLang_Model** (`AI/ModelServices/OCR_SGLang_Model`, port 29260) holds Baidu's [Unlimited OCR 2](https://github.com/baidu/Unlimited-OCR) (MIT license) on the GPU and gets all pages in one request. Reader reads which one answers from its `/health`. The CPU model returns plain text lines; the GPU models return Markdown with layout.

## Tools and API

- Upload: `POST /api/files` (raw bytes, `X-Requester-Username`, `X-Filename`), meant to be used by ember_api and the authenticated admin playground. Returns `{file_id, page_count, size_bytes, expires_at}`.
- Tool: `tool_ocr_parse(file_id)` over MCP at `/mcp`. Returns `{text, pages, page_count, cached, message}`; `text` has a `<PAGE>` marker per page and `pages` is the same text split at the markers.

## Setup

- Run: `run.bat run` (loads `.env`) or `uv run python -m src.run --dotenv` (first `uv sync`). Docker: `docker compose up -d --build` (the Citadel network must exist).
- Needs OCR_Paddle_Model or OCR_SGLang_Model running and a token for it (save a connection on the admin page). `/health` returns `{"ok": true, "ready": ...}`; `ready` is true when the model service answers and its model is loaded. Without it, a parse fails with "The OCR model is not available right now."

## Registering in Armory

Not done yet. Add this next to `scribe` in `Python/Citadel/apps/armory/configs/config_extensions.json`:

```json
"ocr": {
  "label": "Reader",
  "description": "OCR: reads an attached PDF or image and returns the text of every page.",
  "url": "http://127.0.0.1:29402/mcp",
  "headers": {"X-Internal-Token": "${READER_TOKEN}"},
  "forward_requester": true
}
```

Citadel's ember_api has that route: `POST /api/attachments/document` forwards a PDF or image (20 MB cap) to `/api/files` with the requester and this service's token (`READER_TOKEN` in ember_api's `.env`). ember_web adds the `[Document file_id: ...]` line next to its pdf_merger line, and skips it when Reader is off or refuses the file.

## Limits worth knowing

- Limits: 50 MB, 30 pages (`SERVICE_MAX_PAGES`), 200 MB per user. Uploads and results are deleted after 24 hours.
- Privacy: user documents sit on this machine for 24 hours, and their page images go to the model service.
- Settings: with `SERVICE_ADMIN_PASSWORD` set, `/admin/` edits the options (pages, time limit, DPI, tokens per page, tiling, upload size, retention, quota); saved values win over `.env`.

- No streaming and no partial results: a parse is one call that ends when the model is done. Armory cancels a call after 120 s, so large documents must be cut by `SERVICE_MAX_PAGES` until the speed is measured. Nothing has run against the real model yet.
- A long document returns all its text in one tool result, which can be large for the agent's context.
- The `<PAGE>` marker position is taken from Baidu's README wording; check it against real output.
- Supported languages and the model size are not stated in Baidu's README.

### Releasing

A plain publish (`run.bat`, Deploy, option 1) only updates the `live` branch, so it is fine for test deploys. A release is a separate step: set `VERSION` (and `pyproject.toml`, to the same number), commit, then run `run.bat`, Deploy, option R or `py tools\publish_live.py --release`. That publishes to `live` and tags the `main` commit `vX.Y.Z` and the live commit `live-vX.Y.Z`. `run.bat`, Build the release ZIP, then builds `_zip_versions\Reader-<VERSION>.zip` and opens GitHub's new-release page for the tag.

## Admin page

With `SERVICE_ADMIN_PASSWORD` set, open `/admin/` and sign in. The shared sidebar has **Overview**, **Playground**, **Access tokens**, **Model connections**, **Runtime & settings**, **Usage** and **Connect & API**. Each page has a direct URL hash. The sidebar collapses to an icon rail and remembers its display preference in this browser.

The Document OCR slot calls the model service (OCR_Paddle_Model or OCR_SGLang_Model). Overview reports the model and remote readiness. Reader has no local OCR engine.

Overview reads `/health` and the service status. Usage shows calls, errors and average time per requester, and resets on restart. Model connections keeps slot test/save/reset and reusable named connections. Runtime & settings saves options and marks those needing a restart. Access tokens creates and revokes caller tokens; Connect & API lists addresses and endpoints with Copy buttons. Admin authentication remains separate from public request tokens. See [the web UI guide](docs/guide-web-ui.md).

## Tests

```bash
uv sync
uv run pytest -q
```

## Try it from the admin page

Open `/admin/#playground` and use **Playground** with a token from **Access tokens** and a requester username. The token is held only in memory, separate from admin sign-in. Requests use the ordinary public API, quotas and cache; the panel shows HTTP status, latency, output, cancellation and curl with a token placeholder. See [the web UI guide](docs/guide-web-ui.md).

Enter the requester username and upload a PDF, PNG, JPEG or WebP. The panel first posts bytes to `POST /api/files` with `X-Requester-Username` and `X-Filename`, then sends `{file_id}` to `POST /api/parse` using the same username and public token. The parse route calls the same owned-document service, cache, quota and inference path as `tool_ocr_parse`; it returns `{text, pages, page_count, cached, message}`. Uploaded documents and results follow the normal retention policy. OCR_SGLang_Model must be reachable for inference.

## Documentation

- [Purpose: input, output and what it is for](docs/purpose.md)
- [Deployment](deployment.md)
- [Changelog](CHANGELOG.md)
- [Docker on this PC](docs/guide-docker-same-device.md)
- [Docker on another machine](docs/guide-docker-deployment-device.md)
- [Run without Docker](docs/guide-no-docker-same-device.md)
