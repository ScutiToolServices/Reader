# Changelog

## 0.1.0

- First version: MCP server `ocr` with one tool, `tool_ocr_parse(file_id)`, and a document upload route (`POST /api/files`), like Scribe for audio.
- Reads PDFs and images with Baidu Unlimited OCR 2 through SGLangModel; holds no model and needs no GPU.
- Results are kept per document and options; uploads expire after 24 hours; per-user quota; optional settings page at `/admin/`.
- Not yet run against the real model, and not yet registered in Armory.
