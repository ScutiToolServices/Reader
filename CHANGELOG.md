# Changelog

## Unreleased

### Model connections page redesign

Each model slot now shows its state first (saved connection, direct address, runs in this service, or not connected) with the address and whether a token is saved. Editing opens in place: pick a source (saved connection, direct address or in this service) and only the fields for that source appear. A slot that has not been connected opens its editor. Test connection also updates the slot's state. Saved connections are a table with credentials and the slots using them; Add connection opens the form only on request, and a connection in use has its Delete button disabled. The admin API is unchanged.

- Document OCR can use OCR_Paddle_Model (port 29262) as well as OCR_SGLang_Model. The engine reads the backend's `model` from `/health`: `paddleocr-vl` or `pp-ocrv5` gets one `POST /v1/ocr` per page (pages joined with `<PAGE>` like Unlimited OCR 2's), anything else keeps the single chat request. A kept parse is keyed by the model that made it, and the backend is asked again when the saved address changes. The Test connection button checks `/v1/device` for OCR_Paddle_Model. Not run against a real OCR_Paddle_Model yet.

### Admin navigation

The admin page now has seven sidebar pages: Overview, Playground, Access tokens, Model connections, Runtime & settings, Usage and Connect & API. Overview reads live health and service status; links and browser history select pages. The sidebar collapses to an icon rail and remembers its display preference. Existing connections, tokens, settings and public Playground authentication keep their behavior.

### Docs: Citadel's upload route exists

The README no longer says the ember_api upload route is unwritten: `POST /api/attachments/document` forwards PDFs and images to `/api/files`, and ember_web adds the `[Document file_id: ...]` line. No behaviour change in this service.

### Breaking: callers use admin-page tokens, not `INTERNAL_API_TOKEN`

`INTERNAL_API_TOKEN` is no longer read. Set `SERVICE_ADMIN_PASSWORD`, open `/admin/`, make one token per caller on the new **Tokens** card (stored hashed in `tokens.json` in the data folder; sent in `X-Internal-Token`) and put it in the caller's configuration (Armory: the extension's `headers`). A token can carry a calls-per-minute limit and an expiry, and **Revoke** cuts a caller off at once. Without an admin password there are no checks, and the service refuses to start on a non-loopback host.

### Breaking: common service environment variables

Service-owned environment variables now use `SERVICE_*`. Old names are no longer read.
Rename old names once in your real `.env`, Compose `environment:` block, and CI/secret settings.

| Old name | New name |
|---|---|
| `READER_ADMIN_PASSWORD` | `SERVICE_ADMIN_PASSWORD` |
| `READER_BIND` | `SERVICE_BIND` |
| `READER_CONCURRENCY` | `SERVICE_CONCURRENCY` |
| `READER_CROP_MODE` | `SERVICE_CROP_MODE` |
| `READER_DATA_DIR` | `SERVICE_DATA_DIR` |
| `READER_DPI` | `SERVICE_DPI` |
| `READER_HOST` | `SERVICE_HOST` |
| `READER_MAX_PAGES` | `SERVICE_MAX_PAGES` |
| `READER_MAX_UPLOAD_MB` | `SERVICE_MAX_UPLOAD_MB` |
| `READER_PORT` | `SERVICE_PORT` |
| `READER_QUOTA_MB` | `SERVICE_QUOTA_MB` |
| `READER_TIMEOUT_S` | `SERVICE_TIMEOUT_S` |
| `READER_TOKENS_PER_PAGE` | `SERVICE_TOKENS_PER_PAGE` |
| `READER_TTL_HOURS` | `SERVICE_TTL_HOURS` |
| `READER_WEB_DIR` | `SERVICE_WEB_DIR` |

- Default service port moves from 8092 to 29402. Update any explicit port in your real `.env`, saved model-service connections in `backends.json`, and browser or MCP client configurations once; model-service connection ports also move to the new model port blocks. Docker users who used the Compose default receive the new host and container ports together; explicit host-port overrides remain in effect until changed.
- Model connection labels, Docker CONNECT hosts and documentation use the purpose-prefixed model-service names. Update saved model-service connections to the renamed load balancer hosts using the current connection defaults.

- `run.bat` loads `.env` from the service folder for a local run: it passes `--dotenv`, the service prints which variable names it loaded (never the values), and a real environment variable still wins. A plain `uv run python -m src.run`, Docker and the tests never read `.env`.
- Untracked folders now start with `.` or `_`: `zip_versions/` is `_zip_versions/`. A local `voices`, `tem_code` or `zip_versions` folder from an older checkout needs renaming by hand.
- `run.bat` is now a menu (run the service, deploy, build the release ZIP) and `run.bat run|deploy|zip` skips it. `tools/deploy.bat`, `tools/make_zip.bat` and `tools/deploy.local.example.bat` are gone; the local deploy target is `tools/deploy.local.ini` (copy `tools/deploy.local.example.ini`).
- Admin page: **Connect to this service** card with the addresses other services can use (this page's address, same PC, Docker network, `host.docker.internal`) and every endpoint, each with a Copy button.
- `POST /api/parse` accepts an owned `file_id` with the existing public token and requester headers and returns the same parse result as the MCP tool.

- Admin **Try it** panel sends real public API requests with a requester username, readable status/errors, latency, cancellation, media/text results and redacted curl. Auth choice (b): the public token stays in memory, separate from admin auth; existing quotas, ownership and caches apply.

- Admin page: status, usage per user, and the OCR_SGLang_Model address and token (changeable live, with a Test connection button), next to the settings.

## 0.1.0

- First version: MCP server `ocr` with one tool, `tool_ocr_parse(file_id)`, and a document upload route (`POST /api/files`), like Scribe for audio.
- Reads PDFs and images with Baidu Unlimited OCR 2 through OCR_SGLang_Model; holds no model and needs no GPU.
- Results are kept per document and options; uploads expire after 24 hours; per-user quota; optional settings page at `/admin/`.
- Not yet run against the real model, and not yet registered in Armory.
