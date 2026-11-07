# Changelog

## Unreleased

- `run.bat` loads `.env` from the service folder for a local run: it passes `--dotenv`, the service prints which variable names it loaded (never the values), and a real environment variable still wins. A plain `uv run python -m src.run`, Docker and the tests never read `.env`.
- Untracked folders now start with `.` or `_`: `zip_versions/` is `_zip_versions/`. A local `voices`, `tem_code` or `zip_versions` folder from an older checkout needs renaming by hand.
- `run.bat` is now a menu (run the service, deploy, build the release ZIP) and `run.bat run|deploy|zip` skips it. `tools/deploy.bat`, `tools/make_zip.bat` and `tools/deploy.local.example.bat` are gone; the local deploy target is `tools/deploy.local.ini` (copy `tools/deploy.local.example.ini`).
- Admin page: **Connect to this service** card with the addresses other services can use (this page's address, same PC, Docker network, `host.docker.internal`) and every endpoint, each with a Copy button.
- `POST /api/parse` accepts an owned `file_id` with the existing public token and requester headers and returns the same parse result as the MCP tool.

- Admin **Try it** panel sends real public API requests with a requester username, readable status/errors, latency, cancellation, media/text results and redacted curl. Auth choice (b): the public token stays in memory, separate from admin auth; existing quotas, ownership and caches apply.

- Admin page: status, usage per user, and the SGLangModel address and token (changeable live, with a Test connection button), next to the settings.

## 0.1.0

- First version: MCP server `ocr` with one tool, `tool_ocr_parse(file_id)`, and a document upload route (`POST /api/files`), like Scribe for audio.
- Reads PDFs and images with Baidu Unlimited OCR 2 through SGLangModel; holds no model and needs no GPU.
- Results are kept per document and options; uploads expire after 24 hours; per-user quota; optional settings page at `/admin/`.
- Not yet run against the real model, and not yet registered in Armory.
