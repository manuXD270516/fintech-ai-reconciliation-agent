# Build context: repository root (see compose.yaml).
# Base images are pinned by multi-arch index digest; bump tag and digest together.
ARG PYTHON_IMAGE=python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.20@sha256:100047e74f30778ab704942321a09750d6158739573ff58bf3924085cc6cd2d8

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12
WORKDIR /app

FROM base AS builder
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock .python-version ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY packages/domain/pyproject.toml packages/domain/pyproject.toml
COPY packages/knowledge/pyproject.toml packages/knowledge/pyproject.toml
COPY apps/mcp-server/pyproject.toml apps/mcp-server/pyproject.toml
COPY packages/store/pyproject.toml packages/store/pyproject.toml
RUN uv sync --locked --no-dev --no-install-workspace
COPY apps/api/src apps/api/src
COPY apps/worker/src apps/worker/src
COPY packages/domain/src packages/domain/src
COPY packages/knowledge/src packages/knowledge/src
COPY apps/mcp-server/src apps/mcp-server/src
COPY packages/store/src packages/store/src
RUN uv sync --locked --no-dev --no-editable

FROM base AS runtime
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /app/.venv /app/.venv
# Synthetic knowledge corpus for the one-shot knowledge-ingest job (read-only data).
COPY datasets/synthetic/knowledge-v1 /app/datasets/synthetic/knowledge-v1
COPY datasets/synthetic/provider-status-v1 /app/datasets/synthetic/provider-status-v1
ENV PATH=/app/.venv/bin:$PATH
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "recon_api"]

# Test tooling image for the Compose smoke: dev group + integration tests.
FROM builder AS smoke
RUN uv sync --locked --no-editable
COPY tests tests
COPY datasets datasets
ENV PATH=/app/.venv/bin:$PATH
USER 10001:10001
CMD ["pytest", "-p", "no:cacheprovider", "-m", "integration", "tests/integration"]
