FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /usr/local/bin/uv

# Harden apt against ISP/proxy "Hash Sum mismatch" (common on some Indian networks).
RUN printf '%s\n' \
      'Acquire::http::Pipeline-Depth "0";' \
      'Acquire::http::No-Cache "true";' \
      'Acquire::BrokenProxy "true";' \
      > /etc/apt/apt.conf.d/99fix-proxy \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic.ini ./
COPY database ./database
COPY scripts ./scripts

RUN uv sync --frozen --no-dev

COPY docker/api-entrypoint.sh /api-entrypoint.sh
COPY docker/worker-entrypoint.sh /worker-entrypoint.sh
COPY docker/migrate-entrypoint.sh /migrate-entrypoint.sh
RUN sed -i 's/\r$//' /api-entrypoint.sh /worker-entrypoint.sh /migrate-entrypoint.sh \
    && chmod +x /api-entrypoint.sh /worker-entrypoint.sh /migrate-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["/api-entrypoint.sh"]
