# syntax=docker/dockerfile:1
# No model and no GPU here: this image calls SGLangModel (AI/ModelServices/SGLangModel) over HTTP.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" OCR_DATA_DIR=/data OCR_HOST=0.0.0.0 OCR_WEB_DIR=/app/web
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY web ./web
RUN uv sync --frozen --no-dev --no-editable

EXPOSE 8092
CMD ["python", "-m", "src.run"]
