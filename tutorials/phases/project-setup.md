# How to Set Up MiniMart: A Docker-First FastAPI Project with uv

> Stand up a FastAPI service that runs entirely in Docker — interactive docs, live reload,
> and a proper app lifecycle — where the only tool you need on your machine is Docker.

**Phase:** 0 — Foundation & setup
**Concept it taught:** A *Docker-first* dev environment (only Docker required on the host),
multi-stage images (one `dev` image with tooling, one lean `prod` image), live reload via a
bind mount, and the FastAPI application lifecycle (`lifespan`).
**Why it matters:** "Works on my machine" dies here. A teammate clones the repo, runs one
command, and has the exact same environment — no Python, no virtualenv, no version drift.
Multi-stage builds give you dev ergonomics *and* a small, secure production image from a
single Dockerfile, and `lifespan` is where you'll open/close the DB pool and Redis later.

## Prerequisites

- **Docker** with Compose v2 (`docker compose`, not `docker-compose`).
- **uv** on the host — the default path uses it to scaffold and to lock dependencies.
  Don't have it? Every uv step below includes a **Docker-only equivalent**, so Docker alone
  is enough to build the project.
- **Python is NOT required on the host.** That's the whole point.

## Steps

### 1) Scaffold the project

```bash
mkdir minimart && cd minimart
uv init .            # creates pyproject.toml, .python-version, README.md, and a sample main.py
rm -f main.py hello.py   # delete the sample entrypoint uv created at the root; ours lives in app/
mkdir -p app tests
touch app/__init__.py
```

**Without uv** (Docker-only) — create the same files by hand:

```bash
mkdir minimart && cd minimart
mkdir -p app tests
touch app/__init__.py README.md
printf '3.12\n' > .python-version
# pyproject.toml is written in step 2 below — that's all uv init would have given you here.
```

**Why:** `uv init` only writes project metadata files — it does **not** create a virtualenv
(that's `uv sync`), so nothing gets installed on your host either way. We keep our code in a
real package (`app/`) from day one rather than a loose `main.py`, matching the layout the
rest of the project expects. Since step 2 replaces the generated `pyproject.toml` regardless,
the manual path loses nothing.

### 2) Declare dependencies in `pyproject.toml`

Replace the generated file with:

```toml
[project]
name = "minimart"
version = "0.1.0"
description = "MiniMart — a Docker-first FastAPI learning project"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi[standard]>=0.115",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "httpx>=0.27",
    "ruff>=0.6",
    "mypy>=1.11",
]
```

And pin the interpreter in `.python-version`:

```text
3.12
```

**Why:** `fastapi[standard]` pulls in uvicorn and the FastAPI CLI, so we don't list a server
separately. Runtime deps and **dev-only** tools (pytest/ruff/mypy) are kept in separate
groups — the `prod` image will install with `--no-dev` to stay lean, while the `dev` image
installs everything. No `[build-system]` means uv treats this as an *application*, not a
library, so it won't try to build/package our code during install.

### 3) Create the app with a lifespan + health check

`app/main.py`:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup: runs once before the app serves traffic ---
    # Later phases initialize shared resources here, e.g.:
    #   app.state.db = await create_db_pool(settings.database_url)
    #   app.state.redis = await create_redis(settings.redis_url)
    print("MiniMart API starting up")
    try:
        yield
        # The app serves requests during the yield.
    finally:
        # --- Shutdown: runs once on a clean stop ---
        #   await app.state.db.close()
        #   await app.state.redis.aclose()
        print("MiniMart API shutting down")


app = FastAPI(title="MiniMart API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

**Why:** Code before `yield` runs at startup, the `yield` hands control to FastAPI to serve
requests, and the `finally` block runs at shutdown — the right place to release the DB and
Redis connections you'll add later. Wiring `lifespan` now means there's a correct home for
those resources from the start instead of bolting it on. `title`/`version` shape the
generated docs.

### 4) Write the multi-stage `Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1

# ---- base: shared foundation for every stage ----
FROM python:3.12-slim AS base
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
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
```

**Why each piece:**
- **`UV_PROJECT_ENVIRONMENT=/opt/venv`** — the single most important line. It puts the
  virtualenv *outside* `/app`. In dev we bind-mount our source over `/app`, and if the venv
  lived at the default `/app/.venv` the mount would hide it, leaving the container with no
  installed packages. Putting it at `/opt/venv` makes the mount harmless. Adding it to
  `PATH` means `uvicorn`, `pytest`, etc. are callable directly — no `uv run` needed.
- **`deps` stage copies only `pyproject.toml` + `uv.lock`** — so Docker reuses the cached
  dependency layer on every rebuild *unless your dependencies actually change*. Editing app
  code no longer triggers a reinstall.
- **Cache mount (`--mount=type=cache`)** — keeps uv's download cache across builds, so even
  a real dependency change is fast.
- **`--no-install-project`** — install dependencies but not our own app package; the code is
  provided by the mount (dev) or the `COPY app` (prod) and imported from the working dir.
- **`dev` vs `prod` targets** — same file, two images: dev has tooling and reload; prod is
  lean, `--no-dev`, and runs as a **non-root** user (a baseline security practice).

### 5) Add `.dockerignore`

```text
.git
__pycache__/
*.pyc
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.env
```

**Why:** Keeps the build context small and prevents a stray host `.venv` or caches from
leaking into the image and busting layer caching.

### 6) Write `docker-compose.yml`

```yaml
services:
  api:
    build:
      context: .
      target: dev          # build the dev image (with tooling + reload)
    container_name: minimart-api
    ports:
      - "8000:8000"        # host:container
    volumes:
      - .:/app             # mount the whole project: app/ AND tests/
```

**Why:** `target: dev` ensures the running container has pytest/ruff/mypy available.
Mounting the **whole project** (`.`), not just `./app`, means live reload works *and* the
container can see `tests/`. This full mount is only safe because the venv lives at
`/opt/venv` (step 4) — otherwise it would clobber the packages. The dev stage's `CMD`
already runs uvicorn with `--reload`, so Compose doesn't need a `command:` override.

### 7) Generate the lockfile

Default (uv on host):

```bash
uv lock
```

**Without uv** (Docker-only):

```bash
docker run --rm -v "$PWD":/app -w /app ghcr.io/astral-sh/uv:latest uv lock
```

**Why:** `uv.lock` pins exact, resolved versions. The Dockerfile installs with `--frozen`,
which *fails the build* if the lockfile is missing or out of date — guaranteeing the image
matches the lock. Note `uv lock` only writes the lockfile; it does **not** create a host
virtualenv, so the "only Docker required" property holds.

### 8) Build and run

```bash
docker compose up --build
```

## Run & verify

With the stack up, confirm:

- Health: `http://localhost:8000/health` → `{"status": "ok"}`
- Swagger docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI schema: `http://localhost:8000/openapi.json`

**Live reload:** edit `app/main.py` (e.g. change the health payload) and save — the logs
should show `WatchFiles detected changes ... Reloading...` and the new response appears
without a rebuild.

**Lifecycle:** the startup log line ("MiniMart API starting up") prints when the container
comes up; `docker compose down` prints the shutdown line. That proves `lifespan` is wired.

Run the tooling inside the container to prove the dev image is complete:

```bash
docker compose exec api pytest          # collects 0 tests for now, but proves pytest exists
docker compose exec api sh -c "ruff check . && mypy ."
```

## Troubleshooting (real issues to expect)

- **Container has no installed packages / `ModuleNotFoundError` after adding the mount** →
  the source mount hid the venv. Ensure `UV_PROJECT_ENVIRONMENT=/opt/venv` (outside `/app`)
  and that `PATH` includes `/opt/venv/bin`. This is the #1 Docker-first Python gotcha.
- **`uvicorn: command not found` / `pytest: command not found`** → you're on the wrong build
  target (`prod` has `--no-dev`) or `/opt/venv/bin` isn't on `PATH`. Build the `dev` target.
- **`tests/` not found when running pytest in the container** → the mount only covers `app/`.
  Mount the whole project (`.:/app`), as in step 6.
- **Can't reach the app from the browser** → uvicorn must bind `--host 0.0.0.0` inside the
  container. `127.0.0.1` only listens inside the container and won't be reachable via the
  published port.
- **`port is already allocated`** → something else uses 8000. Change the host side of the
  mapping, e.g. `"8001:8000"`.
- **Build fails with a frozen-lockfile error** → `uv.lock` is missing or stale. Re-run
  `uv lock` (step 7) after any `pyproject.toml` change.
- **Python version mismatch** → keep `.python-version` and the `python:3.12-slim` base image
  in agreement.

## Interview talking point

"I set the project up Docker-first so the only host requirement is Docker. A single
multi-stage Dockerfile produces a `dev` image with the test/lint tooling and a lean,
non-root `prod` image, and I put the uv virtualenv at `/opt/venv` so the dev source
bind-mount doesn't shadow the installed packages — which is the classic trap with
live-reload Python containers."
