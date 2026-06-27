# How to Add & Remove Dependencies in a Docker-First uv Project

> The full round-trip for changing dependencies when your app runs in Docker but your editor
> runs on the host — and the mental model that makes it make sense.

**Type:** Guide (cross-cutting how-to — surfaced during Phase 0, used in every phase after).
**Concept it taught:** One source of truth (`pyproject.toml` + `uv.lock`) feeding two *derived*
environments (the container image and the host `.venv`); Docker image layers vs. the container's
ephemeral writable layer.
**Why it matters:** Knowing *why* a package you installed "disappeared" after recreating a
container — and being able to explain build-time vs. runtime state — is exactly the kind of
Docker fluency that separates "I followed a tutorial" from "I understand the model."

## The mental model (read this first — everything below is just applying it)

There is **one source of truth** and **two things derived from it**:

```
        SOURCE OF TRUTH                    DERIVED (must be refreshed)
   ┌────────────────────┐
   │  pyproject.toml     │  ──build──▶  container image  (/opt/venv)   ← runtime
   │  uv.lock            │  ──sync───▶  host .venv                       ← your IDE
   └────────────────────┘
```

- **`pyproject.toml`** = your *declared intent* (loose constraints, e.g. `fastapi>=0.115`).
- **`uv.lock`** = the *resolved, pinned* full dependency tree (exact versions + hashes) that
  makes installs reproducible. **Both are committed to git.**
- The **container image** (`/opt/venv`) and the **host `.venv`** are *caches* of the lock. They
  do **not** update themselves — you rebuild / resync them.

> **Adding a package = change the lockfile, then refresh the two things derived from it.**
> Every command below is one of those boxes.

## Prerequisites

- The Docker-first stack from `../phases/project-setup.md` (image at the `dev` target, venv at
  `/opt/venv`, source bind-mounted).
- `uv` on the host is *optional* but makes this smoother (see the two paths below).

## Steps

### 1) Create the host `.venv` (one-time — this is what your IDE resolves against)

```bash
uv sync                    # creates ./.venv with Python 3.12 + everything in uv.lock
```

Then point your editor at it: **Cmd+Shift+P → "Python: Select Interpreter" → `./.venv/bin/python`**.

**Why:** In a Docker-first project the dependencies are installed *in the container*, so the
host has nothing for the editor's type-checker to resolve — hence the dreaded
`Cannot find module fastapi`. The `.venv` is a host-side copy that exists **purely for the
IDE**; the app never runs from it. `uv sync` means "make this venv match the lockfile exactly."

### 2) Add a package — the recommended (host-driven) path

```bash
uv add <pkg>                                   # 1. lockfile + host .venv, in one shot
docker compose build api && docker compose up -d api   # 2. rebuild the container from the new lock
```

**Why:** Running `uv add` *on the host* does two of our three boxes at once — it edits
`pyproject.toml` + `uv.lock` **and** installs into `./.venv` (so the IDE resolves the import
immediately). The rebuild is the only remaining box: it re-runs the Dockerfile's `uv sync`
against the new lock, baking the package into the image's `/opt/venv`.

### 2b) Alternative — container-driven (when you have NO host uv)

```bash
docker compose run --rm api uv add <pkg>       # edits pyproject + lock (lands on host via the mount)
uv sync                                         # refresh the host .venv (IDE)
docker compose build api && docker compose up -d api    # refresh the container
```

**Why:** Same three boxes, just split apart. `uv add` runs inside a *throwaway* container; the
`--rm` discards that container, but the lockfile edits persist because `/app` is bind-mounted to
your host. Because the install happened somewhere that *isn't* your host `.venv`, you need a
separate `uv sync` to update the IDE's view.

**Does the host `.venv` auto-update when you add via the container? No.** This is the key gotcha:

| You ran… | `pyproject` + `uv.lock` | host `.venv` (IDE) | container `/opt/venv` (runtime) |
|---|---|---|---|
| `uv add` **on host** | ✅ | ✅ automatically | ❌ until `docker compose build` |
| `uv add` **via container** | ✅ | ❌ stale — needs `uv sync` | ❌ until `docker compose build` |

### 3) Use it, then verify both environments

Add the import in `app/main.py`, then check each derived env independently:

```bash
.venv/bin/python -c "import <pkg>; print('host OK')"   # IDE/type-checker view
curl -s localhost:8000/<route-that-uses-it>             # container runtime view
```

### 4) Remove a package — the reverse, in the right order

```bash
# 1. remove the CODE that uses it first (so you never import a package that's gone)
# 2. then remove the package:
uv remove <pkg>                                # lockfile + host .venv
docker compose build api && docker compose up -d api    # refresh the container
```

**Why the order:** if you `uv remove` while code still imports the package, the app breaks until
you also edit the code. Remove the usage first, then the dependency. Removal is the same three
boxes as adding, run in reverse: change the lock → refresh host venv → refresh container.

## Concepts that confused me (and the plain-English answer)

**"Why did `cowsay` vanish after I recreated the container, but `fastapi` survived?"**
Because they got in two completely different ways:

- A Docker **image** is a stack of **read-only layers**, built once by the Dockerfile. A running
  **container** adds a thin **writable layer** on top.
- **`fastapi` went in at *build time*.** The Dockerfile copies `pyproject.toml` + `uv.lock`, then
  `RUN ... uv sync` installs into `/opt/venv` — *baked into a read-only image layer*. Every
  container started from that image has it, forever.
- **`cowsay` went in at *runtime*.** Installing it from the Docker Desktop **Exec** shell (i.e.
  inside the *live* container) wrote into that container's **writable layer**. Recreate the
  container and that layer is thrown away — back to the pristine image, which never had `cowsay`.

> **Mental model: the running container is scratch paper; the image is the printed book.**
> A runtime `uv add` writes on the scratch paper. To change the book, re-run the press (`build`).

**"But the container `uv add` *did* update `pyproject.toml` and `uv.lock` on my host — why
didn't that help?"** Because those files are only read **at build time**. Your current image was
built earlier, from the *old* lock; editing the lock afterwards doesn't reach into a finished
image. You have to rebuild for the change to take effect in `/opt/venv`.

**"Can't I just copy the container's venv to the host and bind-mount it, so there's only one?"**
No — a venv is **platform-specific compiled binaries**, not portable data. The container is
Linux (ELF `.so` files, e.g. `pydantic-core`); your Mac needs Mach-O. It also hard-codes
absolute paths (`/opt/venv/...`) and points at a Linux interpreter that doesn't exist on the
host. The portable thing is the **lockfile**, not the venv — that's exactly why the pattern is
"one lock → two native builds." If you genuinely want a single environment, point the IDE at the
*container's* interpreter (VS Code Dev Containers), don't copy files across the OS boundary.

## Troubleshooting (real issues we hit)

- **`Cannot find module fastapi` in the editor (but the app runs fine in Docker)** → the IDE
  resolved the wrong interpreter (e.g. a global pyenv 3.9 with no project deps) because no host
  `.venv` existed. Fix: `uv sync` to create `./.venv`, then select `./.venv/bin/python` as the
  interpreter. It's an *editor* problem, not an app problem — the package is installed where it
  actually runs (the container).
- **Installed a package via Docker Desktop's Exec tab; it vanished after `down`/rebuild** →
  you installed into the container's ephemeral writable layer. Don't use Exec to manage
  dependencies; use the `uv add` + `docker compose build` flow so it's baked into the image.
- **Added a dep but the IDE still red-squiggles the import** → you added it via the container,
  so the host `.venv` is stale. Run `uv sync`.
- **Added a dep but the running app still `ModuleNotFoundError`s** → you didn't rebuild. The
  container's `/opt/venv` only changes on `docker compose build`.
- **Build fails with a frozen-lockfile error after editing deps** → `uv.lock` is stale relative
  to `pyproject.toml`. Re-lock (`uv lock`, or it happens as part of `uv add`).

## Interview talking point

"My project runs in Docker but I edit on the host, so I treat `uv.lock` as the single source of
truth feeding two derived environments — the image's `/opt/venv` (refreshed by `docker compose
build`) and a host `.venv` (refreshed by `uv sync`, purely for the IDE). I learned the build-time
vs. runtime distinction the hard way: a package I installed inside a live container disappeared on
recreate because it lived in the writable layer, not a baked image layer. The fix — and the rule —
is that dependencies belong in the lockfile and get built into the image, never poked into a
running container."
