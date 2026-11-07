# Changelog

## Unreleased

- Admin page: **Connect to this service** card with the addresses other services can use (this page's address, same PC, Docker network, `host.docker.internal`) and every endpoint, each with a Copy button.
- `POST /api/parse` accepts an owned `file_id` with the existing public token and requester headers and returns the same parse result as the MCP tool.

- Admin **Try it** panel sends real public API requests with a requester username, readable status/errors, latency, cancellation, media/text results and redacted curl. Auth choice (b): the public token stays in memory, separate from admin auth; existing quotas, ownership and caches apply.

- Admin page: status, usage per user, and the SGLangModel address and token (changeable live, with a Test connection button), next to the settings.

## 0.1.0

- First version: MCP server `ocr` with one tool, `tool_ocr_parse(file_id)`, and a document upload route (`POST /api/files`), like Scribe for audio.
- Reads PDFs and images with Baidu Unlimited OCR 2 through SGLangModel; holds no model and needs no GPU.
- Results are kept per document and options; uploads expire after 24 hours; per-user quota; optional settings page at `/admin/`.
- Not yet run against the real model, and not yet registered in Armory.
