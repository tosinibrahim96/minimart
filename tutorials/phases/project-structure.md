# How to Lay Out a FastAPI Project the Senior Way

> Establish a domain-based folder structure on day one — before writing a single endpoint —
> so the codebase stays changeable as it grows.

**Phase:** 0 — Foundation & setup
**Concept it taught:** Domain-based (feature-first) layout and the four-layer rule —
*the router decides nothing, the service decides what, the repository does it.*
**Why it matters:** "Seniors have opinions about layout before writing an endpoint, because
structure is what keeps a codebase changeable." Picking domain-based over layer-based — and
being able to justify it — is a direct interview signal.

## Prerequisites

- The project boots in Docker already (see `project-setup.md` in this folder).
- Nothing else — this phase is *only* about where files go. The folders can be near-empty.

## Steps

### 1) Choose domain-based over layer-based

We organise `app/` by **feature** (each owns its router/service/repository/schemas/models),
not by **role** (a global `routers/`, `services/`, `models/`).

```
app/
├── core/         config, security, database, cache  (cross-cutting infra)
├── common/       shared dependencies, pagination, base exceptions
├── products/     router.py service.py repository.py schemas.py models.py
├── auth/         (added in Phase 4 — same shape)
├── cart/         (Phase 6)
├── orders/       (Phase 7)
├── payments/     (Phase 10)
└── main.py       creates the app, includes each domain's router
```

**Why:** Layer-based folders smear one feature across five directories — to change "products"
you touch `routers/products.py`, `services/products.py`, `models/products.py`… and so on.
Domain-based keeps everything for one feature in one folder, which scales far better. This is
the community-standard structure (popularised by *fastapi-best-practices*, modelled on
Netflix's open-source Dispatch app). There's no single "official" FastAPI layout — the docs
are deliberately light — but this is the convergent professional answer, and that's what makes
it defensible.

### 2) Scaffold a few folders now, even mostly empty

For Phase 0 we created `core/`, `common/`, and **one** fully-laid-out domain, `products/`, as
the template to clone later. Each layer file carries a one-line role docstring so the structure
documents its own intent:

```python
# app/products/router.py
"""HTTP layer: parses requests, declares dependencies, calls the service, maps
results/domain errors to status codes. Decides nothing on its own."""

# app/products/service.py
"""Business logic: decides *what* should happen, owns the transaction boundary,
raises domain exceptions (never HTTPException)."""

# app/products/repository.py
"""Data-access layer: *does* the DB work (queries, writes). Knows nothing about
HTTP; makes no business decisions; never owns the transaction."""
```

**Why:** "Adopt the domain-based structure now, even with near-empty folders." Establishing the
skeleton before writing endpoints means logic has a correct home from the start, instead of
piling into the route and being refactored out later. We scaffolded just `products/` (not all
five domains) to prove the shape without busywork — the rest get cloned as their phases land.

### 3) Internalise the four-layer rule

| Layer | Responsibility | Must NOT |
|-------|----------------|----------|
| **Router** | HTTP only: parse, depend, call one service, map result/error to status | contain business logic |
| **Service** | the use case, orchestration, **the transaction boundary** | raise `HTTPException`; know HTTP exists |
| **Repository** | *do* the DB work (queries, atomic updates, locks) | make business decisions; own the transaction |
| **Models vs schemas** | DB model, input schema, output schema = **three separate classes** | be merged into one |

**Why:** The test for "where does this code go?" — *would it still be true if I swapped FastAPI
for a CLI, or Postgres for MongoDB?* Business rules survive both swaps (service, centre); HTTP
parsing dies with the framework (router, edge); queries die with the database (repository,
bottom). Keeping DB model and API schema separate matters because the two shapes *will* diverge
(e.g. the create-input has no `id`; the response hides the password hash) — merge them and you
regret the coupling the first time they need to differ.

## Run & verify

- `find app -type f -not -path "*/__pycache__/*"` shows `core/`, `common/`, and `products/`
  with its five layer files plus `main.py`.
- The app still boots unchanged — these folders aren't imported yet:
  `curl -s localhost:8000/health` → `{"status":"ok"}`.
- Acceptance criterion met: folders separate routing, models, schemas, services, data access.

## Troubleshooting (real issues we hit)

- **"Cannot find module fastapi" red squiggle in the editor while building this** → not a
  structure problem at all; the IDE was resolving the wrong Python interpreter. See
  `../guides/dependency-management.md` — the fix is a host `.venv` via `uv sync`, then selecting it.
- **Tempted to scaffold all five domains at once** → don't. Empty folders you aren't using yet
  are noise. Clone `products/` into a new domain only when that phase starts.

## Interview talking point

"I went domain-based rather than layer-based — each feature owns its router, service,
repository, and schemas — because layer-based folders smear one feature across five
directories. And I enforce a strict rule: the router decides nothing, the service decides what
(and owns the transaction boundary), the repository just does the DB work. The service raises
domain exceptions like `OutOfStockError`; the router maps them to status codes — services never
know HTTP exists."
