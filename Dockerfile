# syntax=docker/dockerfile:1

# ---- base: shared foundation for every stage ----
    FROM python:3.12-slim AS base
    ENV UV_COMPILE_BYTECODE=1 \
        UV_LINK_MODE=copy \
        UV_PROJECT_ENVIRONMENT=/opt/venv \
        PYTHONUNBUFFERED=1 \
        PATH="/opt/venv/bin:$PATH"
    COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
    WORKDIR /app
    
    # ---- deps: only dependency metadata, so this layer caches ----
    FROM base AS deps
    COPY pyproject.toml uv.lock ./
    
    # ---- dev: includes dev tools; source is bind-mounted at runtime, not copied ----
    FROM deps AS dev
    RUN --mount=type=cache,target=/root/.cache/uv \
        uv sync --frozen --no-install-project
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    
    # ---- prod: lean, no dev deps, source copied in, non-root, no reload ----
    FROM deps AS prod
    RUN --mount=type=cache,target=/root/.cache/uv \
        uv sync --frozen --no-dev --no-install-project
    COPY app ./app
    RUN useradd --create-home appuser && chown -R appuser /app /opt/venv
    USER appuser
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
