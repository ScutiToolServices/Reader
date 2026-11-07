# Reader

Document OCR for Citadel and Ember. A user attaches a PDF or image (PNG, JPEG, WebP) in chat; the agent calls `ocr__tool_ocr_parse` and answers from the text. The model is Baidu's [Unlimited OCR 2](https://github.com/baidu/Unlimited-OCR) (MIT license). It does not run here: this MCP server draws PDF pages with PyMuPDF and sends them in one request to **SGLangModel** (`AI/ModelServices/SGLangModel`, port 9210), which holds the model on the GPU.

## Tools and API

- Upload: `POST /api/files` (raw bytes, `X-Requester-Username`, `X-Filename`), meant to be used by ember_api and the authenticated admin playground. Returns `{file_id, page_count, size_bytes, expires_at}`.
- Tool: `tool_ocr_parse(file_id)` over MCP at `/mcp`. Returns `{text, pages, page_count, cached, message}`; `text` has a `<PAGE>` marker per page and `pages` is the same text split at the markers.

## Setup

- Run: `uv run python -m src.run` (first `uv sync`). Docker: `docker compose up -d --build` (the Citadel network must exist).
- Needs SGLangModel running and a token for it (save a connection on the admin page). `/health` returns `{"ok": true, "ready": ...}`; `ready` is true when SGLangModel answers and its model is loaded. Without it, a parse fails with "The OCR model is not available right now."

## Registering in Armory

Not done yet. Add this next to `scribe` in `Python/Citadel/apps/armory/configs/config_extensions.json`:

```json
"ocr": {
  "label": "Reader",
  "description": "OCR: reads an attached PDF or image and returns the text of every page.",
  "url": "http://127.0.0.1:8092/mcp",
  "headers": {"X-Internal-Token": "${INTERNAL_API_TOKEN}"},
  "forward_requester": true
}
```

Ember also needs an upload route like Scribe's (`POST /api/attachments/audio`) that forwards a document to `/api/files` and adds a `[Document file_id: ...]` line to the question. That lives in ember_api and is not written.

## Limits worth knowing

- Limits: 50 MB, 30 pages (`READER_MAX_PAGES`), 200 MB per user. Uploads and results are deleted after 24 hours.
- Privacy: user documents sit on this machine for 24 hours, and their page images go to SGLangModel.
- Settings: with `READER_ADMIN_PASSWORD` set, `/admin/` edits the options (pages, time limit, DPI, tokens per page, tiling, upload size, retention, quota); saved values win over `.env`.

- No streaming and no partial results: a parse is one call that ends when the model is done. Armory cancels a call after 120 s, so large documents must be cut by `READER_MAX_PAGES` until the speed is measured. Nothing has run against the real model yet.
- A long document returns all its text in one tool result, which can be large for the agent's context.
- The `<PAGE>` marker position is taken from Baidu's README wording; check it against real output.
- Supported languages and the model size are not stated in Baidu's README.

### Releasing

A plain publish (`run.bat`, Deploy, option 1) only updates the `live` branch, so it is fine for test deploys. A release is a separate step: set `VERSION` (and `pyproject.toml`, to the same number), commit, then run `run.bat`, Deploy, option R or `py tools\publish_live.py --release`. That publishes to `live` and tags the `main` commit `vX.Y.Z` and the live commit `live-vX.Y.Z`. `run.bat`, Build the release ZIP, then builds `_zip_versions\Reader-<VERSION>.zip` and opens GitHub's new-release page for the tag.

## Admin page

With `READER_ADMIN_PASSWORD` set, `/admin/` (header `X-Admin-Password`) has four parts:

- **Status**: what the service runs and for how long, plus the model and whether SGLangModel is ready.
- **Usage**: calls, errors and average time per user since the service started (kept in memory, so a restart clears it).
- **Model services**: the `SGLangModel` address and token (saved on the admin page only). This service holds no model, so it has no local option. Pick **In this service** or **A model service**, set the address and token, press **Test connection** (it calls the other service with that token), then **Save**. A change applies to the next call; the token is stored in `.data/backends.json`, never shown again, and `Use the environment value` drops the saved one.
- **Settings**: the options saved in `.data/settings.json`.

## Tests

```bash
uv sync
uv run pytest -q
```

## Try it from the admin page

Open `/admin/` and use **Try it** with the service's internal API token and a requester username. The token is held only in memory, separate from admin sign-in. Requests use the ordinary public API, quotas and cache; the panel shows HTTP status, latency, output, cancellation and curl with a token placeholder. See [the web UI guide](docs/guide-web-ui.md).

Enter the requester username and upload a PDF, PNG, JPEG or WebP. The panel first posts bytes to `POST /api/files` with `X-Requester-Username` and `X-Filename`, then sends `{file_id}` to `POST /api/parse` using the same username and public token. The parse route calls the same owned-document service, cache, quota and inference path as `tool_ocr_parse`; it returns `{text, pages, page_count, cached, message}`. Uploaded documents and results follow the normal retention policy. SGLangModel must be reachable for inference.

## Documentation

- [Purpose: input, output and what it is for](docs/purpose.md)
- [Deployment](deployment.md)
- [Changelog](CHANGELOG.md)
- [Docker on this PC](docs/guide-docker-same-device.md)
- [Docker on another machine](docs/guide-docker-deployment-device.md)
- [Run without Docker](docs/guide-no-docker-same-device.md)
