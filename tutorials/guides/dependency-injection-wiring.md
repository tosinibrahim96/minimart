# How to Wire Services and Repositories (Class-Level Dependency Injection)

> How a service should *acquire* its repositories — and why "the class builds its own
> dependencies" quietly costs you testability and change-resilience as the graph grows.

**Type:** Guide (cross-cutting how-to — surfaced during Phase 2, when `ProductService`
grew a second repository; applies to every service built after).
**Concept it taught:** Constructor injection vs. self-construction; provider functions as
the *composition root*; FastAPI's per-request dependency cache and the same-session guarantee.
**Why it matters:** The spec teaches DI at the request level (`get_db`, `get_current_user`)
but every service also has a *class-level* wiring question: who builds the repositories?
Getting this right is what makes Phase 15's "unit-test a service with fakes, no DB, no
patching" possible — and it's a standard interview probe ("how do you structure services
for testability?").

## The problem, felt concretely

`ProductService` needed a category check, so its constructor became:

```python
class ProductService:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)          # service BUILDS its dependency
        self.category_repository = CategoryRepository(db)
```

This works, but the service now *knows how to construct* its collaborators — their class
names and their constructor signatures. Two costs follow:

1. **Change ripple.** The day `CategoryRepository.__init__` grows a parameter (e.g. a Redis
   client in Phase 11), every class that constructs one must be edited. The knowledge of
   "how to build a CategoryRepository" is smeared across the codebase.
2. **Untestable without patching.** You cannot hand the service a fake repository in a unit
   test — it manufactures its own. Your only lever is `monkeypatch`, which is fragile.

## The mental model (read this first)

**A class should declare *what* it needs, never *how to build it*.** Someone outside hands
in ready-made collaborators — this is **constructor injection**. The single place that
knows how to assemble the whole object graph is called the **composition root**.

> Analogy: a chef who writes "I need carrots" on the recipe vs. a chef who owns a farm.
> When carrot-growing changes, the first chef's recipe is untouched — only the supplier
> adapts. The supplier is the composition root.

In FastAPI, **the `Depends` chain *is* the composition root**. You don't install a DI
framework; you write small *provider functions* and chain them.

## The target shape

### 1) Services declare their needs

```python
class ProductService:
    def __init__(
        self,
        db: Session,
        repository: ProductRepository,
        category_repository: CategoryRepository,
    ):
        self.db = db
        self.repository = repository
        self.category_repository = category_repository
```

**Why `db` is still a parameter:** the service owns the transaction boundary
(`with self.db.begin():`), so it needs the session itself — not just the repos.

### 2) Provider functions build each piece (the composition root)

```python
def get_product_repository(db: DbSession) -> ProductRepository:
    return ProductRepository(db)

def get_category_repository(db: DbSession) -> CategoryRepository:
    return CategoryRepository(db)

def get_product_service(
    repository: Annotated[ProductRepository, Depends(get_product_repository)],
    category_repository: Annotated[CategoryRepository, Depends(get_category_repository)],
    db: DbSession,
) -> ProductService:
    return ProductService(db, repository, category_repository)
```

**Why:** each class is now buildable in exactly **one place**. When `CategoryRepository`
grows a parameter, you edit `get_category_repository` — and nothing else, anywhere.

**Where these live:** conventionally a `dependencies.py` per domain (the spec's reference
layout ships `auth/dependencies.py`), or at the top of the router module while small.

### 3) Routers stay unchanged

```python
ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]

@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(product: ProductCreate, service: ProductServiceDep):
    ...
```

The router *declares* the top of the tree; FastAPI *resolves* the graph bottom-up on each
request (`get_db` → repos → service → route). Construction logic written inline in a route
body (`ProductService(ProductRepository(db), ...)`) would be wiring leaking into the HTTP
layer — that's the thing this pattern avoids.

## The gotcha that is actually a correctness guarantee: per-request caching

Three nodes in that graph ask for `DbSession`. **`get_db` runs once per request** — FastAPI
caches each dependency's result for the life of the request — so *both repositories and the
service receive the same `Session` object*.

This is not a performance detail. The service's `with self.db.begin():` only governs the
repositories' queries **because they share that one session**. If each repo had its own
session, "one transaction" would silently be three, and the rollback guarantee would be
fiction. (Caching is per-request only — two concurrent requests never share a session.)

## The payoff (Phase 15 preview)

With injection, unit-testing the service needs no FastAPI, no Postgres, no patching:

```python
service = ProductService(
    db=fake_session,
    repository=FakeProductRepo(),
    category_repository=FakeCategoryRepo(),
)
```

The service never knew how to build its collaborators, so handing it fakes is trivial.
This is pillar 3 (testability) growing directly out of pillar 1 (DI).

## When NOT to bother

- A tiny script or a service with one cheap, stateless collaborator: constructing inline is
  fine, and saying so is the senior judgement.
- **Do not** reach for a DI container/auto-wiring library in FastAPI. Provider functions +
  `Depends` are the whole mechanism; a framework on top is over-engineering.

## Interview talking point

"My services take their repositories through the constructor; small provider functions
chained with `Depends` act as the composition root, so each class is constructed in exactly
one place. FastAPI's per-request dependency cache means every repo in a request shares one
session — which is what makes the service-owned transaction boundary real. And because
services never build their own collaborators, I can unit-test them with fakes — no DB, no
monkeypatching."
