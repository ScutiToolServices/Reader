# Purpose

**Kind:** PDF or image → text

**Group:** OCR

**Tags:** `cpu`, `mcp`, `http`

| | |
|---|---|
| Input | An uploaded PDF or image (PNG, JPEG or WebP) through `POST /api/files`, then `tool_ocr_parse(file_id)`. The user comes from `X-Requester-Username` or `_meta.requester`. |
| Output | `{text, pages, page_count, cached, message}`: `text` has a `<PAGE>` marker per page and `pages` is the same text split at the markers. |
| Needs | `SGLangModel` (NVIDIA GPU, Linux), one connection on the admin page. Without it a parse fails with "The OCR model is not available right now." |
| Runs on | CPU. Holds no model; PyMuPDF draws PDF pages and sends them to SGLangModel. |

**Use for:** reading whole documents and multi-page PDFs.
**Not for:** cutting regions from an image or choosing a speed or accuracy mode (see `Lens`).
