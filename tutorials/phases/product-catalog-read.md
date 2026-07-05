# How to Build the Product Catalog Read Path (Layers, DI & Pagination)

> Turn an empty FastAPI app into a database-backed catalog: a `GET /products` list that's
> paginated with metadata and a `GET /products/{id}` that returns one product or a real 404 —
> built through clean layers (router → service → repository) with the DB session injected as a
> dependency.

**Phase:** 1 — Product catalog (read path)
**Concept it taught:** The three **data shapes** (DB model ≠ input schema ≠ output schema), the
`get_db` **yield dependency** (dependency injection), the **layered architecture** (router
decides nothing, service decides *what*, repository *does* it), and **offset pagination** with a
page-metadata envelope.
**Why it matters:** Beginners merge the DB model and the API schema into one class and regret it
the first time the shapes diverge (or a password hash leaks). The `get_db` dependency is *the*
canonical reason DI exists — it's what makes the session swappable in tests later. This phase is
the foundation every other phase builds on.

> Built first for **categories** as a walkthrough, then replicated for **products** (which adds
> `Decimal` money, timestamps, and pagination). The code below uses products as the worked
> example; categories is the same pattern, minus pagination.

## Prerequisites

- Phase 0 complete (Docker-first FastAPI app that boots and serves `/health`).
- Docker + Compose. **PostgreSQL, never SQLite** (row locking and full-text search need a real DB later).
- Decision made up front: **sync SQLAlchemy** (not async) — see *Concepts* below for why.

---

## Part A — Foundation (build once, reused by every domain)

### 1) Add the dependencies

```bash
docker compose run --rm api uv add sqlalchemy "psycopg[binary]" pydantic-settings
docker compose build
```

**Why:** These are baked into the *image*, so after changing dependencies you must rebuild
(`docker compose build`). Editing Python code later does **not** need a rebuild — the source is
bind-mounted. `psycopg[binary]` is **psycopg 3** (the modern driver), which matters in step 2.

### 2) Add Postgres to `docker-compose.yml`

```yaml
services:
  api:
    # ...existing...
    environment:
      - DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/minimart
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16
    container_name: minimart-db
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=minimart
    volumes:
      - minimart-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  minimart-db-data:
```

**Why the exact `DATABASE_URL`:** the scheme selects the driver. Bare `postgresql://` defaults to
**psycopg2** (the *old* driver, not installed) — you must write `postgresql+psycopg://` to use
psycopg 3. The host is **`db`** (the Compose service name), not `localhost`, because inside the
Compose network Docker's DNS resolves service names.
**Why the top-level `volumes:` block:** a *named* volume must be declared at the file root, or
Compose errors with "refers to undefined volume." (A bind mount like `.:/app` doesn't need this;
a named volume does — it's how Postgres data survives `docker compose down`.)

### 3) `app/core/config.py` — settings from the environment

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str  # populated from the DATABASE_URL env var


settings = Settings()
```

**Why:** `BaseSettings` reads fields from environment variables automatically (`database_url` ←
`DATABASE_URL`, case-insensitive). No default on `database_url` makes it **required** — the app
refuses to boot if it's missing, which is the fail-loud behaviour you want. No secrets in code.

### 4) `app/core/database.py` — pure connection infrastructure

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    echo=False,          # set True in Phase 8 to SEE the N+1 query storm
    pool_pre_ping=True,  # check a pooled connection is alive before using it
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
```

**Why:** `engine` is one connection pool for the whole process (created lazily — a bad URL fails
on first query, not here). `SessionLocal()` produces a fresh `Session` (unit of work) per
request. `Base` is the one declarative base every model inherits — `Base.metadata` collects all
tables for `create_all`. **This file imports no FastAPI** — it's framework-agnostic infrastructure
(see step 5 for why that matters).

### 5) `app/common/dependencies.py` — the `get_db` dependency + `DbSession` alias

```python
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
```

**Why `get_db` lives here, not in `database.py`:** the `DbSession` alias uses `Depends` — a
FastAPI construct. Keeping it out of `database.py` means the infrastructure stays framework-free
("if I swapped FastAPI for a CLI, `database.py` wouldn't change a line"). Dependencies point
*inward*: `common/dependencies.py` imports from `core/database.py`, never the reverse.
**Why the `yield`/`finally`:** FastAPI runs everything before `yield` at setup, hands the session
to the route, and runs the `finally` **after the response is sent — even if the route raised.**
That guaranteed cleanup is the whole reason DI exists for sessions.
**Why no `db.commit()` here:** the transaction boundary belongs in the *service* (a business unit
of work), not in infrastructure. `get_db` only manages lifecycle.

---

## Part B — The domain feature (repeat this 5-file pattern per domain)

### 6) The model — `app/products/models.py`

```python
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, Text, Integer, ForeignKey, Boolean, DateTime, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    stock: Mapped[int] = mapped_column(Integer)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
```

**Why these choices:**
- **`price` is `Decimal`/`Numeric(10, 2)`, never `float`** — floats can't represent decimal money
  exactly and the error compounds across an order. See
  [Storing money: Decimal vs float](../guides/storing-money-decimal-vs-float.md).
- **`Mapped[str | None]` = nullable; `Mapped[str]` = `NOT NULL`.** The `| None` is how SQLAlchemy
  2.0 marks a nullable column. (`nullable=True` on `description` is redundant with `| None`.)
- **`category_id` FK is `NOT NULL`** — a product must belong to a category (a conscious rule).
- **Timestamps use `server_default=func.now()`** — the *database* sets them, so they hold no
  matter who inserts (app, raw SQL, migration). `DateTime(timezone=True)` stores `TIMESTAMPTZ` and
  gives timezone-**aware** datetimes (avoids the naive-datetime "was that UTC?" bug). `updated_at`
  adds `onupdate=func.now()` — but that only fires on SQLAlchemy-issued UPDATEs (a raw SQL update
  wouldn't refresh it; true DB-level auto-update needs a trigger).
- **`is_active` uses `server_default=text("true")`** — a Boolean needs a SQL expression, not a
  bare `True`; this guarantees the default at the DB (unlike Python-side `default=True`).
- **`name` is NOT `unique`.** Categories are unique (a taxonomy), but two products *can* share a
  name. To genuinely prevent duplicates you'd use a DB `UNIQUE` constraint (an app-level check is
  race-prone) — but for products we don't want that rule.

**Create the table** in `main.py`'s `lifespan` with `Base.metadata.create_all(bind=engine)` (see
step 12). The model's module must be **imported** before that runs, or `Base` won't know the table
exists.

### 7) The output schema — `app/products/schemas.py`

```python
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = Field(..., examples=["Product 1"])
    description: str | None = Field(None, examples=["A description"])
    price: Decimal = Field(..., examples=[10.0])
    stock: int = Field(..., examples=[10])
    category_id: int = Field(..., examples=[1])
    created_at: datetime = Field(..., examples=["2026-01-01T12:00:00Z"])
```

**Why a separate class from the model:** this is the phase's headline lesson. `ProductRead`
exposes `created_at` but **omits `updated_at` and `is_active`** — you added internal columns to
the model and *chose* what the outside world sees. That divergence is the whole point: a merged
class would leak internals (imagine a `User` model's `password_hash`), couple your storage to your
public contract, and force every DB change to be an API change.
**Why `from_attributes=True`:** it lets Pydantic build the schema by reading *attributes* off a
SQLAlchemy object (`product.price`) instead of a dict — the bridge that lets a route return an ORM
object and have `response_model` serialize it. (It was `orm_mode` in Pydantic v1.)
**Why no length constraints here:** validation (`min_length`, etc.) belongs on the *input* schema
(untrusted client data → 422). An output schema *serializes trusted DB data* — a constraint here
could turn a read into a 500.

### 8) The repository — `app/products/repository.py`

```python
from sqlalchemy import select, func
from collections.abc import Sequence
from sqlalchemy.orm import Session
from app.products.models import Product


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_products(self, limit: int = 10, offset: int = 0) -> Sequence[Product]:
        result = self.db.execute(select(Product).limit(limit).offset(offset))
        return result.scalars().all()

    def count_products(self) -> int:
        result = self.db.execute(select(func.count()).select_from(Product))
        return result.scalar_one()

    def get_product(self, product_id: int) -> Product | None:
        return self.db.get(Product, product_id)
```

**Why the session is injected (`__init__(self, db)`), never created here:** if the repo called
`SessionLocal()` itself, that session would leak (nothing closes it), couldn't be swapped in tests,
and couldn't share a transaction with other repos. The session is created in **one place**
(`get_db`) and flows down. This is the "no route creates its own DB session" rule, extended to
every layer.
**Why it returns ORM `Product`, not `ProductRead`:** the repo speaks *database*, not *API*. It knows
nothing about schemas. Converting to `ProductRead` happens at the router edge.
**Why `Sequence`, not `list`:** `.scalars().all()` is *typed* to return `Sequence[Product]`
(list, tuple, etc. are all Sequences). Annotating `list` makes mypy complain that you over-promised.
**Why `db.get(...)` for by-id:** it's the primary-key shortcut and checks the session's identity map
first (may skip a round-trip). It returns `None` when missing — it does **not** raise. Deciding what
to *do* about `None` (the 404) is a business decision, so it happens upstairs.

### 9) The domain exception — `app/products/exceptions.py`

```python
class ProductNotFoundError(Exception):
    """Raised when a product lookup finds nothing."""
```

**Why:** services raise **domain** exceptions, never `HTTPException`. A `ProductNotFoundError`
makes sense whether called from a web route, a CLI, or a job; an `HTTPException(404)` only makes
sense on the web. The router translates the domain error to a status code (step 11).

### 10) The service — `app/products/service.py`

```python
from collections.abc import Sequence
from sqlalchemy.orm import Session
from app.common.pagination import PaginationParams
from app.products.repository import ProductRepository
from app.products.exceptions import ProductNotFoundError
from app.products.models import Product


class ProductService:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)

    def list_products(self, params: PaginationParams) -> tuple[Sequence[Product], int]:
        offset = (params.page - 1) * params.per_page
        products = self.repository.list_products(limit=params.per_page, offset=offset)
        product_count = self.repository.count_products()
        return products, product_count

    def get_product(self, product_id: int) -> Product:
        product = self.repository.get_product(product_id)
        if product is None:
            raise ProductNotFoundError(f"Product with id {product_id} not found")
        return product
```

**Why the offset math lives here:** `offset = (page - 1) * per_page` converts the *user's* world
(page numbers) into the *database's* world (rows to skip) — an orchestration rule, so it belongs in
the service, not the router (HTTP only) or the repo (dumb data access).
**Why `get_product` returns `Product`, not `Product | None`:** it either returns a product or
raises. Annotating `-> Product` tells the caller the truth ("you get a product or an exception,
never None"), so the router doesn't need a redundant null-check. The repo returns the *maybe-absent*
`Product | None`; the service *narrows* it — that narrowing is the value the service adds.
**Why it returns `(items, total)` (ORM objects), not a `Page`:** the service hands back domain data;
building the API envelope is the router's job (keeps the service HTTP-agnostic). The service is
deliberately *thin* on the read path — that's expected; the seam is there for when Phase 7 makes it
heavy.

### 11) Reusable pagination — `app/common/pagination.py`

```python
import math
from typing import Generic, TypeVar
from collections.abc import Sequence
from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int

    @classmethod
    def create(cls, items: Sequence[T], total: int, params: PaginationParams) -> "Page[T]":
        pages = math.ceil(total / params.per_page) if total else 0
        return cls(items=items, total=total, page=params.page, per_page=params.per_page, pages=pages)
```

**Why a generic `Page[T]`:** one envelope works for any item type — `Page[ProductRead]`,
`Page[CategoryRead]`, later `Page[OrderRead]`. Write it once, parameterize everywhere.
**Why `create` is a `@classmethod`:** it's a **factory** — it builds a *new* `Page` before one
exists. An instance method needs an existing object (chicken-and-egg for a constructor); a
classmethod is called on the class (`Page.create(...)`) and uses `cls(...)` to make the instance.
**Why the `per_page: Field(..., le=100)` cap:** an unbounded page size re-introduces the "return
50,000 rows" problem. The `ge`/`le` constraints give you a `422` for free — you never hand-write
the check.
**Why `create` accepts `Sequence` but the field is `list`:** be liberal in what you accept (the
service hands you a `Sequence`), precise in what you store (Pydantic coerces it into the `list`
field on construction).

### 12) The router — `app/products/router.py`

```python
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query

from app.common.pagination import Page, PaginationParams
from app.common.dependencies import DbSession
from app.products.service import ProductService
from app.products.schemas import ProductRead
from app.products.exceptions import ProductNotFoundError


def get_product_service(db: DbSession) -> ProductService:
    return ProductService(db)


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=Page[ProductRead])
def list_products(service: ProductServiceDep, params: Annotated[PaginationParams, Query()]):
    products, total = service.list_products(params)
    return Page.create(items=products, total=total, params=params)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, service: ProductServiceDep):
    try:
        return service.get_product(product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

**Why the `get_product_service` provider function:** you can't do `Depends(ProductService)`
directly — FastAPI would try to resolve the service's `db: Session` parameter as a request param
and fail. The provider is the one place FastAPI's DI (`get_db` → `DbSession`) meets your
framework-agnostic service. It's also the seam tests override.
**Why `Annotated[..., Depends(...)]` (not `= Depends(...)`):** `Annotated` lets you *alias* the
dependency (`ProductServiceDep`), keeps the parameter default-free (callable as a normal function
in tests, no parameter-ordering issues), and is FastAPI's one uniform injection syntax.
**Why `Annotated[PaginationParams, Query()]`:** FastAPI 0.115+ reads a Pydantic model straight from
query params. No provider function, and the `page`/`per_page` constraints stay defined once in the
model — DRY.
**Why `Page.create(...)` in the router:** the service returned `(items, total)`; the router builds
the envelope. The `items` are still ORM objects — `response_model=Page[ProductRead]` coerces each
into `ProductRead` via `from_attributes`. Envelope built here, serialization at the edge.
**Why the `try/except` → `HTTPException(404)`:** this is the **only** place `HTTPException` may
appear. The service raised the domain error; the router maps it to a status code.

### 13) Wire it into `app/main.py`

```python
from app.categories import models  # noqa: F401  (import so the table registers on Base)
from app.core.database import Base, engine
from app.categories.router import router as categories_router
from app.products.router import router as products_router

# inside lifespan, before `yield`:
Base.metadata.create_all(bind=engine)

# after app = FastAPI(...):
app.include_router(categories_router)
app.include_router(products_router)
```

**Why `create_all` lives in `lifespan`:** it runs once at startup, before traffic. It's a
blocking call, but that's fine at startup (see *Concepts* — same call would be a disaster inside an
async route). **This is temporary — Phase 3 replaces it with Alembic migrations.**
**Why the "unused" `models` import matters:** importing the module is what registers the table on
`Base.metadata`; without it, `create_all` builds nothing. `# noqa: F401` stops ruff from deleting
it. (Importing the routers pulls the models in transitively too.)

### 14) Seed realistic data

Run in TablePlus / `psql` (categories first — the FK needs them to exist):

```sql
INSERT INTO categories (name)
VALUES ('Electronics'), ('Books'), ('Clothing'), ('Home & Kitchen'), ('Toys')
ON CONFLICT (name) DO NOTHING;

INSERT INTO products (name, description, price, stock, category_id)
SELECT v.name, v.description, v.price, v.stock, c.id
FROM (VALUES
    ('Wireless Mouse', 'Ergonomic wireless mouse', 24.99, 120, 'Electronics'),
    ('Clean Code', 'A handbook of agile craftsmanship', 38.99, 90, 'Books')
    -- ...more rows...
) AS v(name, description, price, stock, category_name)
JOIN categories c ON c.name = v.category_name;
```

**Why the `VALUES ... JOIN categories`:** it resolves each product's `category_id` by joining on
the category *name*, so you never hardcode ids, and a misspelled category simply won't insert
(inner join). For bulk *fake* data, `generate_series(1, 50)` + `CROSS JOIN LATERAL (SELECT id FROM
categories ORDER BY random() LIMIT 1)` creates N products with a valid random category each
(`LATERAL` re-runs the subquery per row; a plain subquery would pick one category for all rows).

## Run & verify

```bash
docker compose up
```

- `GET /products?page=1&per_page=20` → `200`, envelope with `items`, `total`, `page`, `per_page`,
  `pages`. Note `price` comes back as a **string** (`"79.99"`) and `created_at` is populated by the
  DB; `updated_at`/`is_active` are absent (schema divergence).
- `GET /products?page=2&per_page=20` → the next slice; `GET ...?page=3` → the remainder.
- `GET /products/999999` → `404` with `{"detail": "Product with id 999999 not found"}`.
- `GET /products?page=0` and `?per_page=500` → `422` (validation you didn't hand-write).
- Green tooling: `docker compose exec api sh -c "ruff check . && mypy ."`

## Troubleshooting (real issues we hit)

- **`ModuleNotFoundError: No module named 'psycopg2'`** → the `DATABASE_URL` scheme was
  `postgresql://`, which SQLAlchemy maps to the old psycopg2 driver. Use
  `postgresql+psycopg://` to select psycopg 3.
- **`docker compose up` errors: "service db refers to undefined volume"** → a named volume needs a
  top-level `volumes:` block at the file root, not just the reference under the service.
- **App changed the model but the table didn't change** → `create_all` only *creates missing*
  tables; it never `ALTER`s an existing one. In dev, `DROP TABLE products;` and let it rebuild.
  (This annoyance is exactly why Phase 3 introduces Alembic.)
- **`Depends(CategoryService)` / `Depends(ProductService)` fails at startup** → FastAPI can't
  resolve the service's `db: Session` parameter. Use a provider function
  (`def get_product_service(db: DbSession) -> ProductService`) and depend on *that*.
- **`TypeError` on `Sequence[Product]` at import** → `from sqlalchemy import Sequence` imports the
  *SQL sequence generator*, a different thing. Import `from collections.abc import Sequence`.
- **mypy: `Missing named argument "database_url" for "Settings"`** → mypy doesn't know
  pydantic-settings fills fields from env. Enable the plugin in `pyproject.toml`:
  `[tool.mypy]` → `plugins = ["pydantic.mypy"]`.
- **mypy: `Incompatible return value type (got Sequence, expected list)`** → once the repo honestly
  returns `Sequence`, every layer that passes it up must annotate `Sequence` too. The type
  propagates through repo → service.
- **Router returns the raw `(items, total)` tuple** → it won't match `response_model=Page[...]`.
  Build the envelope with `Page.create(...)`.
- **Importing `Depends`/`HTTPException` from `fastapi.params`/`fastapi.exceptions`** → those are
  internal paths. Import from the top level: `from fastapi import Depends, HTTPException`.

## Concepts that confused me (and the plain-English answer)

### "Is a model the same as a schema? And what about a migration?"

**Start from a house.** The **model** is the *blueprint* of the table — what columns exist, what
type each is. The **schema** is the *form* the outside world fills in and reads back — what the API
accepts and returns. The **migration** is the *construction crew* that actually builds or renovates
the real building to match the blueprint.

They're three separate things:
- **Model** (SQLAlchemy) → describes the DB table.
- **Schema** (Pydantic) → describes the JSON at the API boundary.
- **Migration** (Alembic, Phase 3) → the versioned script that makes the *real database* match the
  model.

Concrete example of why model ≠ schema: a `User` model has a `password_hash` column (blueprint), but
the `UserRead` schema deliberately omits it (the form you hand back to the world), so the hash can't
leak. **Tie-back:** Phase 1 skips migrations and creates tables with `create_all`; Phase 3 swaps to
Alembic once you feel `create_all`'s limits.

### "Why is `lifespan` async but `create_all` has no `await`?"

**Start from what `async def` really means:** it marks a function that's *allowed* to use `await` —
it does **not** mean every line inside must be awaited. You freely call normal functions with no
`await`:

```python
async def lifespan(app):
    print("starting up")             # normal function, no await — totally fine
    Base.metadata.create_all(engine) # also a normal (sync) function — just call it
    yield
    # await some_async_thing()       # await appears ONLY for async functions
```

`await` is only for *awaitables* (things an `async def` returns). `create_all` is a plain sync
function, so there's nothing to await. **Tie-back:** `lifespan` itself is `async` only because
FastAPI *requires* that shape — unrelated to our sync database.

### "sync vs async DB — and how does it relate to sync/async routes?"

**Think of two knobs**, and they should be set to match. A **`def` route** gets handed to a
*threadpool* — its own worker — so it's allowed to sit and block on a slow DB call without holding
anyone else up. An **`async def` route** runs on the single shared *event loop* — one lane everyone
uses — so it must never sit and block; it may only `await` non-blocking IO. A blocking call in an
`async def` route freezes the whole server for every user (the classic FastAPI performance bug).

**The rule:** match the colors — sync DB → `def` routes; async DB → `async def` routes.
**Tie-back:** we chose **sync** (simpler, and the whole curriculum's `get_db` / N+1 / transaction
lessons are written sync), so we write `def` routes. Async is planned as its own later exercise.

### "What is `Depends`, and does it resolve all the way down?"

**Start from ordering at a restaurant:** you ask for "a burger," and the kitchen quietly sources the
bun, patty, and lettuce for you — you don't assemble it yourself. `Depends(x)` is the same: you
declare "I need `x`," and FastAPI builds `x` *and* whatever `x` itself needs, recursively, down to
leaves that need nothing (like `get_db`).

Your chain: you ask for a `ProductService`; FastAPI sees it needs a session, runs `get_db` first,
then builds the service, then hands it to your route. **The clever part:** within one request, each
distinct dependency runs **once and is cached** — so if two things both need `get_db`, they share
*one* session. **Tie-back:** that shared single session is exactly what lets a checkout decrement
stock and create an order in one atomic transaction in Phase 7.

### "Why `@classmethod` when the method is already inside the class?"

**The chicken-and-egg:** a normal method (with `self`) can only be called *on an object that already
exists* — `some_page.method()`. But `Page.create()`'s whole job is to *make* a new `Page`. If it
needed an existing `Page` to run, you could never make the first one.

`@classmethod` fixes that: its first argument is `cls` (the class itself), and you call it on the
class — `Page.create(...)` — no existing instance required. `cls(...)` then builds a fresh one.
**Tie-back:** you've already used this pattern — Pydantic's `Model.model_validate(data)` is a
classmethod factory too.

### "Offset vs cursor pagination — which and why?"

**Start from two apps you've used.** Google results have *numbered pages* (jump to page 7) — that's
**offset** (`LIMIT`/`OFFSET`): simple, gives "page X of Y", perfect for a small, mostly-static
catalog. A Twitter/Instagram feed has *"load more"* forever — that's **cursor** (keyset): it
remembers the last item you saw and fetches after it; stable under new inserts and fast at any
depth, but can't jump to a page or show a total.

**Offset's failure mode, concretely:** you read page 1 (rows 1–20); someone inserts a new product at
the top; you read page 2 (`OFFSET 20`) — but everything shifted down one, so the old row 20 is now at
21 and you see it **twice**. **Tie-back:** we picked offset because the catalog is small and users
want page numbers; you'd switch to cursor for a large, high-write feed to avoid those skips/duplicates
and keep constant-time paging.

## Interview talking points

- "I keep the DB model, input schema, and output schema as three separate classes. In this catalog
  the product model has `is_active` and `updated_at` that the `ProductRead` schema deliberately
  doesn't expose — a merged class would leak internals and weld my storage to my public contract."
- "The DB session arrives via a `get_db` yield-dependency, so its `finally: db.close()` runs even if
  the route raises — and because it's a dependency, tests swap it for a test DB with one line."
- "Business logic raises domain exceptions like `ProductNotFoundError`; only the router maps them to
  HTTP status codes — the service never imports `HTTPException`, so it'd work behind a CLI too."
- "I used offset pagination with a size cap for the catalog because it's small and users want page
  numbers; I'd move to cursor pagination for a large, high-write feed to avoid skip/duplicate and
  keep constant-time paging."
