# How to Refactor Working Code to Constructor Injection (the Composition Root)

> Take two working domains whose services build their own repositories, and rewire them —
> without changing a single response — so that every class *receives* its collaborators and
> exactly one provider function constructs each one.

**Phase:** 4 — ♻️ Refactor: dependency wiring (the composition root)
**Concept it taught:** Constructor injection and the composition root — plus the *discipline*
of refactoring working code: define the end state first, verify behaviour before touching
anything, change one domain at a time, verify again.
**Why it matters:** A service that constructs its own repositories can't be unit-tested
without monkeypatching, and every repository signature change ripples through the codebase.
This refactor is also the practice run for Phase 24 (rewriting the whole data layer behind a
test suite) — same skill, tiny blast radius. The theory and origin story live in
[`../guides/dependency-injection-wiring.md`](../guides/dependency-injection-wiring.md); this
tutorial is the record of actually *doing* it.

## Prerequisites

- Phases 1–3: the `categories` and `products` domains, both working.
- Read the DI wiring guide first — this tutorial assumes its mental model (declare vs
  construct, provider functions, per-request caching).

## The starting point (what was wrong)

Both services took a `Session` and built their own repositories:

```python
# categories/service.py — BEFORE
class CategoryService:
    def __init__(self, db: Session):
        self.repository = CategoryRepository(db)      # service BUILDS its collaborator

# products/service.py — BEFORE
class ProductService:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)        # two construction sites
        self.category_repository = CategoryRepository(db)  # for CategoryRepository...
        self.db = db
```

Two smells: (1) services know their repositories' constructor signatures — add a parameter
to `CategoryRepository.__init__` and *two* service files change; (2) unit-testing either
service with a fake repository requires monkeypatching the import, because the real class
is hardwired inside `__init__`.

## Steps

### 0) Record behaviour BEFORE touching anything

This is a ♻️ refactor phase: the deliverable is *unchanged behaviour*, and with no test
suite yet (Phase 19), the baseline is manual. Hit every endpoint of both domains —
**including the error paths** — and note status codes and bodies:

```bash
curl -s -w " [%{http_code}]\n" http://localhost:8000/categories
curl -s -w " [%{http_code}]\n" http://localhost:8000/categories/1
curl -s -w " [%{http_code}]\n" http://localhost:8000/categories/999999   # must stay 404
# ...same for /products: list, get, get-missing, POST valid, POST bad category, PATCH...
```

**Why:** "it still works" means nothing without a before-picture. The error paths matter
most — they're the ones a refactor silently breaks (an exception mapping lost in the move).

### 1) Categories first — the smaller blast radius

Order of attack was deliberate: categories has one repo, no writes, no transaction. Learn
the move where a mistake is cheap, then repeat it where it isn't.

**Service: receive, don't build — and inject only what you use.**

```python
# categories/service.py — AFTER
class CategoryService:
    def __init__(self, category_repository: CategoryRepository):
        self.category_repository = category_repository
```

**Why no `Session` parameter:** `CategoryService` has no transaction boundary — it never
used `self.db`. Constructor injection makes the dependency list a *document* of what the
class actually needs; carrying an unused `Session` "just in case" would make that document
lie. If a write path arrives later, the parameter gets added then — visibly.

### 2) Create the composition root: `categories/dependencies.py`

New file — the **only** place category classes are constructed:

```python
from typing import Annotated

from fastapi import Depends

from app.categories.repository import CategoryRepository
from app.categories.service import CategoryService
from app.common.dependencies import DbSession


def get_category_repository(db: DbSession) -> CategoryRepository:
    return CategoryRepository(db)


CategoryRepositoryDep = Annotated[CategoryRepository, Depends(get_category_repository)]


def get_category_service(repository: CategoryRepositoryDep) -> CategoryService:
    return CategoryService(repository)


CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]
```

**Why a dedicated `dependencies.py` and not the top of `router.py`** (where
`get_category_service` used to live): `ProductService` *also* needs a `CategoryRepository`.
If the provider stayed in `categories/router.py`, the products composition root would have
to import another domain's **HTTP module** just to get wiring — smelly, and an invitation
to circular imports. A domain whose pieces are consumed across domains earns its own
wiring module.

Note the providers **chain**: `get_category_service` doesn't take `db` and thread it
through — it declares the *repository* (via `Depends`), which itself declares `db`. FastAPI
resolves the graph; no human plumbing.

### 3) Slim the router

`categories/router.py` now imports one thing from the wiring world:

```python
from app.categories.dependencies import CategoryServiceDep
```

The provider function, the `DbSession` import, and `Depends` all left the file. A router
that no longer even imports `Depends` for wiring is the proof that it "never sees
repositories."

### 4) Verify categories, then — and only then — products

Re-ran the step-0 curls for categories: `200`, `200`, `404` with identical bodies. Only
after that did products begin. One domain at a time means a breakage points at exactly one
change.

### 5) Products — the domain that keeps its `Session`

```python
# products/service.py — AFTER
class ProductService:
    def __init__(
        self,
        db: Session,
        product_repository: ProductRepository,
        category_repository: CategoryRepository,
    ):
        self.db = db
        self.product_repository = product_repository
        self.category_repository = category_repository
```

**Why `db` stays here:** `create_product`/`update_product` open `with self.db.begin():` —
the service *owns the transaction boundary* (architecture rule), so the `Session` is a real
collaborator, not plumbing. The contrast with `CategoryService` is the lesson: after this
refactor, you can read any service's constructor and know whether it has a transaction.

Also renamed `self.repository` → `self.product_repository` — with two repositories in one
class, the unqualified name was ambiguity waiting to happen.

### 6) Products composition root — REUSE, don't reconstruct

```python
# products/dependencies.py
from app.categories.dependencies import CategoryRepositoryDep
from app.common.dependencies import DbSession
from app.products.repository import ProductRepository
from app.products.service import ProductService


def get_product_repository(db: DbSession) -> ProductRepository:
    return ProductRepository(db)


ProductRepositoryDep = Annotated[ProductRepository, Depends(get_product_repository)]


def get_product_service(
    db: DbSession,
    product_repository: ProductRepositoryDep,
    category_repository: CategoryRepositoryDep,   # ← categories' provider, reused
) -> ProductService:
    return ProductService(db, product_repository, category_repository)
```

**The trap this dodges:** writing `CategoryRepository(db)` inside `get_product_service`
would have "relocated" the problem — two construction sites, just in different files. The
acceptance criterion is each class constructed in exactly **one** provider; sharing
`CategoryRepositoryDep` is what satisfies it.

**Why this sharing is *safe* (the interview-gold part):** FastAPI caches each dependency
per request. When one request resolves `get_product_service`, the `get_db` inside
`DbSession` runs **once** — so `db`, the session inside `product_repository`, and the
session inside `category_repository` are all the *same object*. That's not an optimisation;
it's what makes `with self.db.begin():` actually cover the category lookup *and* the
product insert in one transaction. Two sessions would silently split "one transaction"
into two.

## Run & verify

Three checks, matching the acceptance criteria:

```bash
# 1) Services receive, never build:
grep -rn "Repository(" app/*/service.py          # → no output (exit 1)

# 2) Exactly one construction site per class:
grep -rn "Repository(db)" app/ | grep -v __pycache__
#   app/products/dependencies.py:12:    return ProductRepository(db)
#   app/categories/dependencies.py:11:    return CategoryRepository(db)

# 3) Behaviour unchanged — full endpoint sweep vs the step-0 baseline:
#   GET  /categories, /categories/1 → 200 ; /categories/999999 → 404
#   GET  /products (+filters+pagination), /products/1 → 200 ; /products/999999 → 404
#   POST /products valid → 201 ; bad category_id → 422 ; negative price → 422
#   PATCH /products/{id} → 200 ; missing id → 404 ; bad category_id → 422,
#         and a re-fetch shows the failed PATCH left no partial state
```

Thought experiment (criterion 3): add a parameter to `CategoryRepository.__init__` —
which files change? Only `categories/dependencies.py`. Passes.

## Troubleshooting (real issues we hit)

- **Dead imports left behind by the refactor** — `ruff check` flagged `F401` twice:
  `Session` in `categories/service.py` (constructor no longer takes it) and `Depends` in
  `categories/router.py` (wiring moved out). A refactor that removes responsibilities from
  a file almost always strands imports; run ruff *after* the move, not just at the end.
- **`I001` un-sorted import block** — the new `app.categories.dependencies` import was
  appended after `app.common.pagination` instead of sorted within the `app.` group. Fixed
  with `ruff check --fix`.
- **`W292` no newline at end of file** on the new `dependencies.py` — plus `ruff format`
  wants two blank lines between each provider and its `Annotated` alias.
- **A 422 where we expected a 404 (false alarm, but the diagnosis is the lesson).** During
  verification, `POST /products` with a nonexistent `category_id` returned `422`, not the
  predicted `404`. Before calling it a regression: `git show HEAD:app/products/router.py`
  — the pre-refactor code had the *same* mapping (`CategoryNotFoundError → 422` on writes).
  Behaviour unchanged = refactor correct; the surprise was in the baseline, not the change.
  When verifying a refactor, always compare against *what the code did*, not *what you
  assumed it did*.

## Concepts that confused me (and the plain-English answer)

### "Same session" — fine, but why is per-request caching a CORRECTNESS requirement?

My first answer to the self-check was "every repository in the request wraps the same
`Session`, so `db.begin()` uses the same session, not a new one." True — but that's the
*mechanism*, and the interviewer's guaranteed follow-up is: **"and what would go wrong if
it were two?"** The answer needs the failure, traced:

Start from what you know: each provider is just a function FastAPI calls, and `get_db` is
declared by both `get_product_repository` and `get_product_service`. If FastAPI *didn't*
cache per request, `get_db` would run twice — two sessions. Now trace `create_product`:

1. `with self.db.begin():` opens a transaction on **session A**.
2. `self.product_repository.create_product(...)` executes its INSERT on **session B** —
   a different connection, inside B's own separate transaction.
3. Session A's transaction contains *nothing*. A rollback on A rolls back nothing; B's
   INSERT commits (or evaporates) on its own schedule.

"The whole thing is one transaction" would silently be a lie — every request still returns
200, no error ever appears, the atomicity guarantee just quietly doesn't exist. That's the
difference between an optimisation (things get slower without it) and a correctness
requirement (things get *wrong* without it, invisibly).

### What does constructor injection actually buy in Phase 19?

One line. With self-construction, the real `CategoryRepository` is hardwired inside
`__init__`, so keeping Postgres out of a unit test means monkeypatching the import. With
injection, the test is:

```python
service = CategoryService(FakeCategoryRepository())
```

No DB, no patching, no FastAPI running. "I can hand the service a fake in one line" is the
whole payoff, collected in Phase 19.

### When is inline construction the RIGHT call — and why never a DI container?

This was the self-check I couldn't answer. Two questions hiding in one:

**Inline construction is right for values; injection is for collaborators.** We already
constructed things inline all over this codebase — `Page.create(...)` in the router,
`CategoryNotFoundError(...)` in the service, every Pydantic schema — and that was correct.
The rule that separates them from `CategoryRepository(db)`:

- A **collaborator** does I/O or holds a managed resource, and you'd want to *substitute*
  it in a test (a repository talking to Postgres, holding a session). → Inject it.
- A **value** is deterministic data — no I/O, no state, nothing you'd ever fake. Faking a
  `Page` in a test would be absurd; you'd just build a real one. → Construct it inline.

Analogy: the composition root is the kitchen's supplier delivering the oven and the
walk-in fridge — big, shared, swappable equipment. You don't ask the supplier to courier
each pinch of salt; you grab it. Cargo-culting fails in *both* directions: constructing
collaborators inline (what this phase fixed), and injecting values "because DI is good"
(ceremony that makes code harder to read).

**A DI container is never the answer in FastAPI because `Depends` already IS one.** A DI
container (auto-wiring library — `dependency-injector`, `injector`, Java's Spring) is a
framework you *register* classes with, and it builds the object graph automatically from
type hints, assigning each object a **lifetime** (singleton vs per-request). But look at
what ~15 lines of providers already gave us: graph resolution (providers chain), lifetime
management (per-request caching), resource cleanup (`get_db`'s `finally`), and test
substitution (`app.dependency_overrides`). That's a container's entire feature list.
Adding one on top costs three concrete things:

1. **Explicitness.** "Who constructs `CategoryRepository`?" currently has a one-line,
   greppable answer. Auto-wiring replaces it with resolution magic debugged via the
   container's docs, not your code.
2. **Lifetime conflicts — real bugs.** Containers default to singletons. A singleton
   `ProductService` captures *one* `Session` at startup, shared across all requests
   forever: transactions interleave across users — the exact bug class this phase
   eliminated, reintroduced.
3. **Testability.** `dependency_overrides` hooks FastAPI's resolution; objects built by an
   external container are invisible to it.

The senior one-liner: *"FastAPI's `Depends` already is the container — request-scoped,
explicit, test-overridable. My composition root is thirty greppable lines; an auto-wiring
library would replace them with magic, risk singleton-captured sessions, and break
`dependency_overrides`. Containers earn their keep in frameworks without built-in DI —
not here."*

## Interview talking point

"I refactored working services from self-constructed repositories to constructor injection
behind provider functions — a composition root per domain. The subtle part was a repository
shared across domains: it must keep a single construction site, and FastAPI's per-request
dependency caching is what makes sharing it *correct*, not just convenient — every
repository in a request wraps the same session, which is what keeps the service-owned
transaction boundary real. I verified behaviour was unchanged with a before/after sweep of
every endpoint, error paths included."
