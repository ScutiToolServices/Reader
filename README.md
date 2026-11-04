# UnlimitedOCR

Document OCR for Citadel and Ember. A user attaches a PDF or image (PNG, JPEG, WebP) in chat; the agent calls `ocr__tool_ocr_parse` and answers from the text. The model is Baidu's [Unlimited OCR 2](https://github.com/baidu/Unlimited-OCR) (MIT license). It does not run here: this MCP server draws PDF pages with PyMuPDF and sends them in one request to **SGLangModel** (`AI/ModelServices/SGLangModel`, port 9210), which holds the model on the GPU.

- Upload: `POST /api/files` (raw bytes, `X-Requester-Username`, `X-Filename`), meant to be reached only through ember_api. Returns `{file_id, page_count, size_bytes, expires_at}`.
- Tool: `tool_ocr_parse(file_id)` over MCP at `/mcp`. Returns `{text, pages, page_count, cached, message}`; `text` has a `<PAGE>` marker per page and `pages` is the same text split at the markers.
- Limits: 50 MB, 30 pages (`OCR_MAX_PAGES`), 200 MB per user. Uploads and results are deleted after 24 hours.
- Run: `uv run python -m src.run` (first `uv sync`). Docker: `docker compose up -d --build` (the Citadel network must exist).
- Needs SGLangModel running and a token for it (`OCR_BACKEND_URL`, `OCR_BACKEND_TOKEN`). `/health` returns `{"ok": true, "ready": ...}`; `ready` is true when SGLangModel answers and its model is loaded. Without it, a parse fails with "The OCR model is not available right now."
- Privacy: user documents sit on this machine for 24 hours, and their page images go to SGLangModel.
- Settings: with `OCR_ADMIN_PASSWORD` set, `/admin/` edits the options (pages, time limit, DPI, tokens per page, tiling, upload size, retention, quota); saved values win over `.env`.

## Registering in Armory

Not done yet. Add this next to `scribe` in `Python/Citadel/apps/armory/configs/config_extensions.json`:

```json
"ocr": {
  "label": "UnlimitedOCR",
  "description": "OCR: reads an attached PDF or image and returns the text of every page.",
  "url": "http://127.0.0.1:8092/mcp",
  "headers": {"X-Internal-Token": "${INTERNAL_API_TOKEN}"},
  "forward_requester": true
}
```

Ember also needs an upload route like Scribe's (`POST /api/attachments/audio`) that forwards a document to `/api/files` and adds a `[Document file_id: ...]` line to the question. That lives in ember_api and is not written.

## Limits worth knowing

- No streaming and no partial results: a parse is one call that ends when the model is done. Armory cancels a call after 120 s, so large documents must be cut by `OCR_MAX_PAGES` until the speed is measured. Nothing has run against the real model yet.
- A long document returns all its text in one tool result, which can be large for the agent's context.
- The `<PAGE>` marker position is taken from Baidu's README wording; check it against real output.
- Supported languages and the model size are not stated in Baidu's README.

### Releasing

A plain publish (`tools\deploy.bat` option 1) only updates the `live` branch, so it is fine for test deploys. A release is a separate step: set `VERSION` (and `pyproject.toml`, to the same number), commit, then run `tools\deploy.bat` option R or `py tools\publish_live.py --release`. That publishes to `live` and tags the `main` commit `vX.Y.Z` and the live commit `live-vX.Y.Z`. `tools\make_zip.bat` then builds `zip_versions\UnlimitedOCR-<VERSION>.zip` and opens GitHub's new-release page for the tag.

## Admin page

With `OCR_ADMIN_PASSWORD` set, `/admin/` (header `X-Admin-Password`) has four parts:

- **Status**: what the service runs and for how long, plus the model and whether SGLangModel is ready.
- **Usage**: calls, errors and average time per user since the service started (kept in memory, so a restart clears it).
- **Model services**: the `SGLangModel` address and token (`OCR_BACKEND_URL`, `OCR_BACKEND_TOKEN` are only the starting values). This service holds no model, so it has no local option. Pick **In this service** or **A model service**, set the address and token, press **Test connection** (it calls the other service with that token), then **Save**. A change applies to the next call; the token is stored in `.data/backends.json`, never shown again, and `Use the environment value` drops the saved one.
- **Settings**: the options saved in `.data/settings.json`.
