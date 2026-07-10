# How to Build the Catalog Write Path (Create, Partial Update & Filtering)

> Add `POST /products` and `PATCH /products/{id}` behind real validation, a service-owned
> transaction boundary, and merge-patch semantics — then compose filtering with pagination.

**Phase:** 2 — Catalog write path + filtering
**Concept it taught:** The **input-vs-output schema split** (a third schema per resource:
create-input, update-input, read-output); the **transaction boundary in the service**
(`with db.begin()`, and what `flush`/`commit`/`refresh` each actually do); **merge-patch
semantics** for PATCH (`exclude_unset` and the absent-vs-null tri-state); check-then-act
**TOCTOU** and the constraint-as-backstop pattern; and what a linter's "all checks passed"
actually promises.
**Why it matters:** Write endpoints are where data integrity is won or lost. Every lesson here
(transactions, races, constraint discrimination, partial updates) is a direct rehearsal for
Phase 9's checkout and Phase 5's SKU work — and each one is a standard interview probe.

## Prerequisites

- Phase 1's read path (`tutorials/phases/product-catalog-read.md`) — layers, `get_db`, pagination.
- The Docker-first stack running: `docker compose up`.

## Steps

### 1) Design the input schemas — three shapes per resource, now for real

```python
class ProductCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    description: str | None = Field(None, max_length=255)
    price: Decimal = Field(..., ge=Decimal("50"), max_digits=10, decimal_places=2)
    stock: int = Field(..., ge=0)          # 0 = legitimate "not yet in stock"
    category_id: int = Field(..., gt=0)
```

**Why:** No client-supplied `id`, `created_at`, or `is_active` — the input schema is a
**whitelist**, which is also what makes `Product(**data.model_dump())` safe against
mass-assignment. `max_digits=10, decimal_places=2` mirrors the DB's `Numeric(10, 2)` so the API
rejects what the DB would silently round. `ge=Decimal("50")` is a *business* rule (₦50 minimum
price — Nigerian market), distinct from the *integrity* rule "price can't be negative"; business
rules may move to config/service later, integrity rules live in the schema forever.

### 2) Create: repository flushes, service owns the transaction

```python
# repository.py — does the work, never commits
def create_product(self, data: ProductCreate) -> Product:
    new_product = Product(**data.model_dump())
    self.db.add(new_product)
    self.db.flush()          # send INSERT (id + server defaults come back) — still uncommitted
    return new_product
```

```python
# service.py — decides the boundary
def create_product(self, data: ProductCreate) -> Product:
    with self.db.begin():    # commits on clean exit, rolls back on ANY exception
        category = self.category_repository.get_category(data.category_id)
        if category is None:
            raise CategoryNotFoundError(f"Category with id {data.category_id} not found")
        try:
            new_product = self.repository.create_product(data)
        except IntegrityError as e:   # backstop: category deleted in the race window
            raise CategoryNotFoundError(
                f"Category with id {data.category_id} not found"
            ) from e
    self.db.refresh(new_product)     # commit expired attributes; reload explicitly
    return new_product
```

**Why — the mental model (flush vs commit vs refresh):**
- `add()` → notebook entry in the session; **nothing** has touched the DB.
- `flush()` → the SQL is **sent and executed** inside the open transaction. The row exists in
  Postgres — visible to *your* connection only (MVCC). `INSERT ... RETURNING` brings back the
  DB-generated `id`/`created_at`.
- `commit()` → seals the envelope: permanent, visible to everyone. By default it also **expires**
  every loaded attribute (`expire_on_commit=True`) — hence the explicit `refresh` after the block.
- `with db.begin()` is "begin-once" style: never call `commit()` inside it (the context manager
  owns the transaction; a manual commit inside makes the next statement raise
  `InvalidRequestError`). All the use case's work — reads included — goes inside the block.

**Why the check *and* the backstop:** the existence check is check-then-act — between the check
and the flush, another request can delete the category (**TOCTOU**). The FK constraint is the
true guardian (data can never go wrong); the app-level check exists for a friendly error, and
the `except IntegrityError` turns the rare race from a `500` into the same domain error.
`from e` chains the exceptions so the traceback keeps the real cause.
*(Reproduced for real with two connections: check passed → other connection deleted the category
→ flush raised `IntegrityError` wrapping `ForeignKeyViolation`, constraint name
`products_category_id_fkey`. The blanket catch is acceptable only while a single constraint can
fire on this insert — Phase 5's SKU uniqueness makes constraint-name discrimination mandatory.)*

### 3) Route it — deliberate status codes

```python
@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, service: ProductServiceDep):
    try:
        return service.create_product(data)
    except CategoryNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)
        ) from e
```

**Why:** FastAPI defaults every route to `200`; create must say `201`. The `422` choice for a
dangling `category_id` (vs `404`/`400`) is deliberate: `404` on POST is ambiguous ("is the
endpoint missing?"). Known cost, accepted consciously: our string `detail` differs from
Pydantic's list-shaped `422` detail — two shapes under one status code. Phase 20's exception
handlers unify them into one error envelope (machine-readable codes, RFC 9457 style); until
then, per-route `try/except` is the pattern. `HTTP_422_UNPROCESSABLE_CONTENT` is the
non-deprecated constant (the IETF renamed the phrase).

### 4) PATCH: choose merge-patch semantics, then earn them

**Decision — PATCH over PUT:** PUT means "replace with this complete resource," so every client
must know *every* field; an old client's PUT silently nulls columns added after it shipped
(imagine Phase 5's `sku`). PATCH decouples client knowledge from schema evolution — right for
"any kind of frontend." (Third option, field masks à la Google AIP-134: explicit `update_mask`
listing fields to apply. Exists because proto3 can't represent "field absent"; Pydantic can, so
masks would be redundant ceremony here.)

The update schema needs the **absent / value / null tri-state**:

```python
class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=50)
    description: str | None = Field(None, max_length=255)   # nullable column: null = clear
    price: Decimal | None = Field(None, ge=Decimal("50"), max_digits=10, decimal_places=2)
    stock: int | None = Field(None, ge=0)
    category_id: int | None = Field(None, gt=0)

    @field_validator("name", "price", "stock", "category_id")
    @classmethod
    def reject_explicit_null(cls, v: Any, info: ValidationInfo) -> Any:
        if v is None:
            raise ValueError(f"Field {info.field_name} cannot be null")
        return v
```

**Why each piece (the 2×2 that took three attempts):** the **type** `X | None` controls whether
`null` passes validation; the **default** `None` controls whether the field may be *omitted* —
two independent axes. `Optional[str]` does NOT mean "optional to send"; omittability comes only
from the default. The validator produces the cell no annotation can: *omittable but not
nullable* — it runs only on values the client actually sent, so absent fields sail through and
explicit `null` gets a `422` naming the field. `description` stays out of the list: it's the one
nullable column, and merge-patch's convention is `null` = clear.

### 5) Apply the update — mutate the tracked object, never `add()`

```python
# repository.py
def update_product(self, product: Product, data: ProductUpdate) -> Product:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    self.db.flush()
    return product
```

```python
# service.py — resource first, then referenced entities, then act
def update_product(self, product_id: int, data: ProductUpdate) -> Product:
    with self.db.begin():
        product = self.get_product(product_id)                  # 404 first
        if data.category_id is not None:                        # check only if being changed
            category = self.category_repository.get_category(data.category_id)
            if category is None:
                raise CategoryNotFoundError(f"Category with id {data.category_id} not found")
        try:
            product = self.repository.update_product(product, data)
        except IntegrityError as e:                              # same race backstop as create
            raise CategoryNotFoundError(
                f"Category with id {data.category_id} not found"
            ) from e
    self.db.refresh(product)
    return product
```

**Why:** an object loaded through the session is **persistent** — the session watches it, and
plain attribute assignment *is* the update; at flush, the unit of work diffs against its
snapshot and emits `UPDATE ... SET <changed cols> WHERE id = ...`. `db.add()` means "INSERT this
new object" and is never how you modify a row. `exclude_unset=True` is the merge-patch engine:
only fields the client actually sent get applied. Check order matters: the URL's resource is
validated before the body's references (`PATCH /products/999999` → `404` regardless of body).
**Decision:** empty body `{}` → `200` no-op — "you asked me to update nothing; done." (Valid
merge patch; consistent with idempotent reading. The `422` alternative was considered and
rejected.)

### 6) Configure ruff so "passing" means something

```toml
[tool.ruff]
target-version = "py312"

[tool.ruff.lint]
extend-select = [
    "W",   # pycodestyle warnings — trailing whitespace, newline-at-EOF
    "I",   # isort — deterministic import ordering
    "B",   # flake8-bugbear — real bug patterns (B904: raise ... from)
    "UP",  # pyupgrade — modern syntax (flags Optional[X] → X | None)
    "SIM", # flake8-simplify — needless complexity
]
```

**Why:** ruff's default ruleset is tiny (pyflakes + a sliver of pycodestyle) — "All checks
passed" only ever means "for the rules you enabled." The same tree failed 10 checks the moment
`W`+`I` were enabled. `--fix` applies only *safe* fixes; findings without the `[*]` marker are
either **unsafe** (behavior could change — `UP046`'s `class Page[T](BaseModel)` rewrite: applied
manually, then verified the endpoint still serializes) or **no-fix-by-design** (`B904`: only a
human knows whether `from e` — keep the cause — or `from None` — suppress it — is intended; we
chose `from e` everywhere we translate domain errors to HTTP). The config is a committed team
contract: CI (Phase 23) runs exactly this.

### 7) Pagination is a lie without ORDER BY (and how we proved it)

Preparing for filtering, we paginated `GET /categories` (same `Page[T]` + `PaginationParams`
pattern as products) — and walked into the classic offset-pagination bug both endpoints had
been carrying: **no `ORDER BY`**.

```python
# before (categories AND products): order left to chance
select(Category).limit(limit).offset(offset)
# after: deterministic, unique sort key
select(Category).order_by(Category.id).limit(limit).offset(offset)
```

**The witness (run this yourself):** with `per_page=2`, page 1 returned ids `[1, 3]`. Then, in
`psql`, a **no-op update** — `UPDATE categories SET name = name WHERE id = 1;` — changes zero
data. Page 1 immediately became `[3, 4]` and id 1 moved to the *last* page. A row that didn't
change teleported across pages.

**Why:** SQL's contract is that row order without `ORDER BY` is **undefined**; Postgres returns
heap order (physical position on disk). Under MVCC an `UPDATE` never modifies a tuple in place —
it writes a *new* tuple version at the end of the heap and marks the old one dead. So any update,
even a no-op, physically relocates the row and reshuffles your "pages." It looks ordered in dev
only because freshly-seeded rows sit in insertion order — which is why this ships to production
undetected. (After the fix, the heap is still shuffled; `ORDER BY` is what protects the API.)

**The rule:** the sort key must be **deterministic and unique**. Sorting by a non-unique column
alone (e.g. `name`) still leaves ties in undefined order — the bug survives at tie boundaries.
Sort by a unique column, or end the key with one as a tiebreaker (`ORDER BY name, id`).

**Two-level interview answer:** without `ORDER BY`, offset pagination is broken even on an idle
database (undefined order); *with* it, it's still fragile under concurrent writes (inserts/deletes
shift what each offset points at — rows skip or repeat between page requests); cursor/keyset
pagination fixes the latter. Phase 1 chose offset consciously; this is the full cost sheet.

### 8) Derived data belongs to the owner of its inputs (`params.offset`)

Both services computed `offset = (params.page - 1) * params.per_page` — the same formula, twice,
waiting to diverge. `offset` is derived *entirely* from `page` and `per_page`, which live on
`PaginationParams` — so the formula belongs there, as a **property** (a method that presents
itself as an attribute):

```python
class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page
```

Services now pass `params.offset` through; the formula exists once in the codebase.

**Why `@property`, not `@computed_field`:** a plain property is invisible to Pydantic — not in
`model_dump()`, not in the OpenAPI schema. `@computed_field` would make it part of the model's
*serialized shape*. `offset` is internal plumbing (clients speak `page`/`per_page`), so it stays
invisible. Contrast: `Page.pages` is a derived *output* value — that's what `@computed_field` is
for. Annotate the return type (`-> int`) or mypy loses the plot at every call site.

### 9) Filtering composed with pagination — the categories rehearsal

Strategy: build the pattern once on the smallest possible canvas (categories: one filter,
`name`) before doing products (three filters) from memory.

*(Design context — why structured params and not a Stripe-style query string: researched
Stripe/GitHub/Google before building; the answer is a whole design lesson of its own →
`tutorials/guides/filtering-vs-search-api-design.md`.)*

**The filter schema** — a Pydantic model per domain, so filters travel as one named object:

```python
class CategoryFilter(BaseModel):
    name: str | None = Field(None, min_length=1)
```

The `None` **default** makes it omittable (the PATCH lesson, third appearance: `X | None` is
the *type*, omittability comes only from the *default*). `min_length=1` answers the
empty-string question: `?name=` sends `""` (present-but-empty ≠ absent — the tri-state again,
now on query params), and an empty pattern would silently match everything; reject it with a
field-level `422` instead.

**Discovery — FastAPI allows only ONE `Query()` model per route.** Declaring both
`params: Annotated[PaginationParams, Query()]` and `filters: Annotated[CategoryFilter, Query()]`
silently breaks BOTH: neither explodes into fields; each becomes a required scalar query param
named after the argument (`?params=...&filters=...`). Verified empirically on FastAPI 0.138.1
with a minimal repro. The fix that keeps two separate objects:

```python
filters: Annotated[CategoryFilter, Depends()],   # model class as a dependency
```

`Depends()` on the model class makes FastAPI introspect its fields into query params, and it
coexists with the one `Query()` model. (Alternative: one merged model inheriting
`PaginationParams`; rejected to keep cross-cutting pagination separate from domain filters.)

**The repository pattern — conditions built once, applied to BOTH queries:**

```python
def list_categories(
    self, limit: int, offset: int, filters: CategoryFilter
) -> tuple[Sequence[Category], int]:
    conditions = self._filter_conditions(filters)
    items_stmt = (
        select(Category)
        .where(*conditions)          # empty list unpacks to zero args = valid no-op
        .order_by(Category.id)
        .limit(limit)
        .offset(offset)
    )
    count_stmt = select(func.count()).select_from(Category).where(*conditions)
    return (
        self.db.execute(items_stmt).scalars().all(),
        self.db.execute(count_stmt).scalar_one(),
    )

def _filter_conditions(self, filters: CategoryFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.name is not None:
        conditions.append(Category.name.icontains(filters.name, autoescape=True))
    return conditions
```

**Why each piece:**
- **Condition vs statement:** `Category.name.icontains(...)` is a `ColumnElement[bool]` — a
  free-standing SQL fragment ("name matches X") attached to no query; `query.where(cond)`
  returns a whole new `Select`. The helper builds *fragments*, independent of any statement —
  that independence is what lets the same list feed two different queries.
- **The `total` lie, structurally prevented:** if items filter and the count doesn't, the API
  reports `total: 5, pages: 3` while matching one row. One method builds conditions once and
  returns `(items, total)` — the two queries *cannot* drift because there's one source.
- **`icontains(term, autoescape=True)` over `ilike(f"%{term}%")`:** hand-rolled patterns splice
  user input into the pattern, so `?name=%` (a LIKE metacharacter) matches every row — wildcard
  injection (not SQL injection: still a bound parameter; just wrong results). `autoescape`
  escapes `%`/`_` and adds the `ESCAPE` clause: `?name=%25` returns zero rows, not all.
- **`.where(*conditions)`:** `*` unpacks the list into separate arguments (`.where()` is
  variadic and ANDs them); passing the bare list hands it one non-SQL argument. `*[]` = zero
  args, so "no filters" needs no special case.
- The underscore on `_filter_conditions` marks it internal — not part of the repository's
  public contract, free to change without rippling.
- The **service stays a passthrough** — no business rule exists for a filtered read; an empty
  result is a valid answer. (The layer earns its keep in Phase 5 when soft-delete filtering
  lands exactly there.)

**Verify:**

```bash
curl -s 'localhost:8000/categories?name=elec'          # substring, case-insensitive → total: 1
curl -s 'localhost:8000/categories?name=o&per_page=1'  # composed: total = filtered count
curl -si 'localhost:8000/categories?name=' | head -1   # → 422 (empty ≠ absent)
curl -s 'localhost:8000/categories?name=%25'           # URL-encoded '%' → zero rows (escaped)
```

### 10) Products filtering — the rep from memory, and what it taught

Built without looking at the categories files: `name`, `category_id`, `in_stock`,
`min_price`/`max_price`, `min_created_at`/`max_created_at` — same conditions-list pattern,
same one-method `(items, total)` return. The pattern reproduced cleanly; the new lessons came
from the cross-field validation and three self-inflicted bugs (see Troubleshooting).

**Decision — `min > max` is a `422`, not an empty result:** a contradictory range is a client
error, not a query with no matches; reject it at the edge with a message naming the fields.
(Valid-but-empty is defensible too — "no product satisfies an impossible predicate" — but then
a client bug looks identical to a legitimately empty page.)

**Cross-field validation needs `@model_validator`, not `@field_validator`:**

```python
@model_validator(mode="after")
def reject_min_is_greater_than_max(self) -> Self:
    pairs = [("min_price", "max_price"), ("min_created_at", "max_created_at")]
    for min_field, max_field in pairs:
        min_value, max_value = getattr(self, min_field), getattr(self, max_field)
        if min_value is not None and max_value is not None and min_value > max_value:
            raise ValueError(f"{min_field} cannot be greater than {max_field}")
    return self
```

A `field_validator` runs per field with `info.data` holding only *previously validated* fields —
a pair rule riding on it fires on the wrong field, multiple times, or not at all.
`model_validator(mode="after")` runs once with the complete model (`self`). Return `Self`.

**Discovery — `Depends()` models can't produce a 422 from model-level validation.** FastAPI
translates `ValidationError` into a 422 only when *it* runs the validation (body, or a `Query()`
model). A model injected via `Annotated[Model, Depends()]` is constructed as dependency code —
a `model_validator` raising there is just an exception from a dependency → **500**. (Field-level
constraints like `min_length` still 422, because those are validated per-param before
construction.) Verified both paths with a minimal `TestClient` repro. Consequence: cross-field
validation forces the single-`Query()`-model design.

**The merged model — multiple inheritance + Liskov substitution:**

```python
class ProductListParams(PaginationParams, ProductFilter):
    pass
```

One `Query()` model per route (step 9's limit), so pagination and filters merge by inheriting
both. The payoff is that an instance **is** a `PaginationParams` *and* **is** a `ProductFilter`:
the router passes one object; `Page.create(params=...)` accepts it (it's a `PaginationParams`);
the service reads `per_page`/`offset` and hands *the same object* to the repository as
`filters=params` (it's a `ProductFilter`). One object, three layers, each seeing the type it
needs. It lives in `schemas.py` — it's a request *shape*; `dependencies.py` is reserved for
provider *functions* (Phase 4).

**`in_stock: bool | None` over `min_stock`/`max_stock`:** the first draft exposed raw inventory
bounds on a public endpoint — admin-shaped (and a competitor's scraper's dream). Customers ask
one question: is it available? Tri-state: absent = don't care, `true` → `stock > 0`,
`false` → `stock == 0`. Saying no to your own extra feature is part of the exercise.

**Verify:**

```bash
curl -s 'localhost:8000/products?category_id=1&min_price=100&max_price=500&per_page=2'
                                       # composed: total = filtered count, page respects it
curl -si 'localhost:8000/products?min_price=500&max_price=100' | head -1    # 422, names fields
curl -s 'localhost:8000/products?in_stock=false'      # only stock == 0 rows
curl -s 'localhost:8000/products?name=%25'            # zero rows (autoescape)
curl -si 'localhost:8000/products?min_price=abc' | head -1                  # 422 type error
```

## Run & verify

```bash
# create → 201 with DB-generated id/created_at
curl -i -X POST localhost:8000/products -H 'Content-Type: application/json' \
  -d '{"name": "Keyboard", "price": "500.00", "stock": 10, "category_id": 1}'

# validation → 422 with Pydantic field detail (negative price, 3 decimal places, short name)
curl -i -X POST localhost:8000/products -H 'Content-Type: application/json' \
  -d '{"name": "Bad", "price": "-5", "stock": 1, "category_id": 1}'

# dangling category → 422 domain message; verify NO row leaked (transaction rolled back)
curl -i -X POST localhost:8000/products -H 'Content-Type: application/json' \
  -d '{"name": "Ghost", "price": "500.00", "stock": 1, "category_id": 999}'

# partial update → 200, ONLY price changes (check the row in psql)
curl -i -X PATCH localhost:8000/products/<id> -H 'Content-Type: application/json' \
  -d '{"price": "750.00"}'

# explicit null on non-nullable → 422 naming the field; on description → 200 (clears it)
curl -i -X PATCH localhost:8000/products/<id> -H 'Content-Type: application/json' -d '{"name": null}'

# unknown product → 404 (checked before the body's category)
curl -i -X PATCH localhost:8000/products/999999 -H 'Content-Type: application/json' -d '{"price": "750.00"}'

docker compose exec api sh -c "ruff check . && mypy ."   # with the real ruleset

# filtering & pagination verifies live inline in steps 7, 9 and 10 — the full battery:
#   composed filter+page, min>max → 422, in_stock partition, %25 wildcard, ?name= → 422,
#   bad type → 422, and the ordering witness (no-op UPDATE, re-fetch, nothing moves)
```

Bonus proof (flush vs commit, in two `psql` terminals): `BEGIN; INSERT ... RETURNING id;` in A is
visible to A but invisible to B until `COMMIT` — that's exactly what `flush` does vs `commit`.

## Concepts that confused me (and the plain-English answer)

- **Why does a method name start with `_`?** Python has no `private` keyword; the leading
  underscore is a convention meaning "internal — not part of this class's public contract."
  Think of the repository as offering a menu (`list_products`, `get_product`): the service
  depends on those signatures, so changing them ripples outward. `_filter_conditions` is
  kitchen staff — rename or delete it freely, because the underscore told everyone not to
  build on it. The smaller a class's public surface, the cheaper it is to change.

- **Why `icontains` over `ilike`?** Same SQL family, different builder. Hand-rolled
  `ilike(f"%{term}%")` splices user input *into the pattern*, so LIKE metacharacters keep
  their powers: a user sending `%` produces pattern `'%%%'` — matches every row (wildcard
  injection: still a bound parameter, so not SQL injection — just wrong results).
  `icontains(term, autoescape=True)` wraps the `%...%`, lowercases both sides, escapes the
  user's `%`/`_`, and adds the `ESCAPE` clause. Proof: `?name=%25` returns zero rows, not all.

- **Does `.where()` before `.order_by()` matter?** No — a `select()` isn't a string being
  appended to; it's a **structured description with named slots** (a WHERE slot, an ORDER BY
  slot…). Each method fills its slot and returns a new object; compilation emits clauses in
  the order SQL grammar demands regardless of fill order. Prove it:
  `str(select(X).where(c).order_by(o)) == str(select(X).order_by(o).where(c))` → `True`.
  The one place call order matters: calling the *same* method twice —
  `.order_by(a).order_by(b)` appends, so the sequence of sort keys is the call sequence.

- **Why `.where(*conditions)` and not `.where(conditions)`?** `*` unpacks a list into
  separate arguments: `f(*[1,2,3])` is `f(1,2,3)`. `.where()` is variadic ("zero or more SQL
  expressions, I'll AND them"); without `*` you hand it one argument that's a Python `list`,
  not a SQL expression. Bonus: `*[]` unpacks to zero arguments, so an empty conditions list
  is a legal no-op — "no filters" needs no special case.

- **What is `list[ColumnElement[bool]]`?** Read inside-out from `list[int]`: a list of
  `ColumnElement[bool]`. The mind-bender: in SQLAlchemy, comparing a column doesn't produce
  a `bool` — it produces an *object*. `Category.name == "Books"` returns a
  `BinaryExpression` because SQLAlchemy overrides `__eq__` to **build a description of a SQL
  comparison** (`categories.name = :name_1`) instead of comparing anything; the comparison
  happens later, inside Postgres. `ColumnElement` is the base class of all such fragments,
  and `[bool]` is the SQL type the fragment evaluates to *in the database*
  (`Product.price` is a `ColumnElement[Decimal]`; `price >= 50` is a `ColumnElement[bool]`).
  So the annotation says: "a list of SQL fragments, each evaluating to true/false in the DB"
  — precisely `.where()`'s food. This is also how mypy caught appending `query.where(cond)`
  (a `Select`, a whole statement) where a fragment belonged.

- **What do `curl -si` and `| head -1` actually do?** `-si` = `-s` (silence the progress
  meter) + `-i` (include the response *headers* — an HTTP response is status line + headers
  + blank line + body; without `-i` you see only the body, and the whole point of an error
  test is the status). `head` is a separate Unix program printing the first N lines of its
  input; the `|` pipe feeds curl's output into it. So `curl -si URL | head -1` reads: fetch
  quietly, include headers, show only the first line — which is the status line. It's the
  quick "just tell me the status code" idiom; the precise form is
  `curl -s -o /dev/null -w '%{http_code}'`, and the Phase 19 form is
  `assert response.status_code == 422`. Quote URLs in zsh — unquoted `?` and `&` are shell
  metacharacters.

- **How can one object be both pagination AND filters?** (step 10's merged model) — because
  `ProductListParams` *inherits* from both, an instance **is a** `PaginationParams` and
  **is a** `ProductFilter` — not "contains one," *is one* (Liskov substitution). Any code
  expecting either parent type accepts it: `Page.create(params=...)` sees a
  `PaginationParams`; the repo's `filters: ProductFilter` parameter sees a `ProductFilter`.
  A parameter name describes the *role* the object plays there, not its full identity —
  which is why `filters=params` is correct and only *reads* strangely.

## Troubleshooting (real issues we hit)

- **`commit()` lived in the repository** → violates "transaction boundary in the service": repo
  methods that commit can never compose into one atomic use case (checkout!). Repo flushes;
  service owns `with db.begin()`.
- **`InvalidRequestError: Can't operate on closed transaction inside context manager`** → called
  `db.commit()` (and then `refresh`) *inside* `with db.begin():`. Begin-once means the context
  manager commits; manual commit closes its transaction and the next statement dies. Pick one
  style; keep refresh after the block.
- **PATCH "worked" but INSERTed a new row** (`Product(**data.model_dump(exclude_unset=True))` +
  `db.add()`) → full-field patch returned `200` and silently duplicated the product; partial
  patch 500'd on NOT NULL. Updates = mutate the session-tracked object; `add()` is INSERT-only.
- **Partial PATCH → `422` "Field required"** → fields declared `Optional[X] = Field(...)` with no
  default. `Optional` ≠ omittable; the **default** makes a field omittable. Restore `= Field(None, ...)`.
- **Explicit `{"name": null}` → 500** (NOT NULL violation) → `X | None` accepts null; added the
  `reject_explicit_null` field validator (runs only on sent values).
- **API lied: null-name violation reported as "Category with id 1 not found"** → the blanket
  `except IntegrityError → CategoryNotFoundError` caught a *different* constraint's violation.
  Blanket translation is only safe while exactly one constraint can fire; discriminate by
  `e.orig.diag.constraint_name` when that stops being true (Phase 5).
- **Validator message said "Field ProductUpdate is required"** → `cls.__name__` in a
  `field_validator` is the *model*; the field name comes from `info.field_name`
  (`ValidationInfo`). And the claim was wrong: the field wasn't missing, it was null.
- **`ruff` said "All checks passed" while files had trailing whitespace, unsorted imports, no
  EOF newlines** → no `[tool.ruff]` config existed; defaults check almost nothing. Enable rule
  families explicitly (see step 6).
- **`StarletteDeprecationWarning: HTTP_422_UNPROCESSABLE_ENTITY is deprecated`** → renamed
  upstream; use `HTTP_422_UNPROCESSABLE_CONTENT`.
- **`NoReferencedTableError` in a standalone script importing only `Product`** → the FK target
  (`Category`) was never imported, so SQLAlchemy couldn't resolve `categories.id`. Import all
  related models (the app does this at startup).
- **Paginated lists had no `ORDER BY`** — looked correctly ordered in dev (fresh seed = insertion
  order), but a no-op `UPDATE ... SET name = name` relocated the row's tuple in the heap and it
  jumped to the last page. Undefined order + MVCC = pages reshuffle on any update. Fix: a
  deterministic, *unique* sort key on every paginated query (see step 7).
- **The bug came straight back through the tie hole** — products switched to
  `order_by(created_at)` and 42 of 44 rows had the *identical* timestamp: Postgres `now()` is
  frozen at **transaction start**, so a one-transaction seed stamps every row the same. `ORDER BY`
  holds between distinct values; within a tie it's heap order again — the same no-op UPDATE moved
  a product to the end of its 42-row tie group. Fix: `order_by(Product.id.desc())` (unique by
  itself, newest-first, and walks the PK index backwards — no sort step). The compound alternative
  is `created_at DESC, id DESC` (needs a composite index to avoid a sort). Caveat worth knowing:
  `id DESC` ≈ newest-first relies on sequence ids; sequence order is allocation order, not commit
  order, and the trick dies with random UUIDs.
- **The witness test for any ordering change:** no-op `UPDATE` a mid-list row in `psql`, re-fetch
  all pages, assert nothing moved. Becomes a real test in Phase 19.
- **Two `Annotated[Model, Query()]` params on one route → both silently break** — FastAPI
  (0.138.1) supports exactly one Pydantic query model per route; with two, neither explodes into
  fields and the endpoint demands `?params=...&filters=...` as required scalars. Fix: the second
  model goes in via `Annotated[Model, Depends()]`. Found via minimal repro with `TestClient`
  inside the container — reproduce framework weirdness in isolation before blaming your code.
- **Appended `query.where(cond)` into `list[ColumnElement[bool]]`** — mixed up a *statement*
  (`Select`) with a *condition* (a bare SQL boolean fragment). The type annotation was right and
  the code wrong — `mypy` flags exactly this mismatch; run it, not just ruff.
- **Filter field declared `Field(min_length=1)` with no default → required** → every unfiltered
  list request 422'd. Same rule as the PATCH schemas: the default, not the type, makes a field
  omittable. `Field(None, min_length=1)`.
- **`?max_stock=0` silently ignored — returned all 44 products** → repo guards used truthiness
  (`if filters.max_stock:`) and `0` is falsy. The tri-state lesson leaking into the repository:
  absent is `None`; `0` is a value the client sent. Guard with `is not None`, always.
- **Cross-field `field_validator` → 500 with errors on the wrong fields** → logs showed
  "min_price cannot be greater than max_price" attached to `min_created_at`/`max_created_at`
  (`input_value=None`), duplicated, as a raw `pydantic_core.ValidationError` through uvicorn.
  Two stacked causes: wrong validator type (per-field + `info.data` for a whole-model rule), and
  `Depends()` construction errors not being FastAPI-managed. Fix: `model_validator(mode="after")`
  on a merged single `Query()` model (see step 10).
- **`.order_by(Product.id)` regression** — the rewrite silently dropped the previous session's
  deliberate `.desc()`. Manual rewrites revert decisions tests would have pinned; the Phase 19
  ordering assertion exists for exactly this.
- **`SyntaxError`-driven design: `filters: ProductFilter | None = None`** → required param after
  `limit: int = 10` is illegal ("parameter without a default follows parameter with a default"),
  so the new param got a default to appease the parser — making the signature lie and forcing
  `if filters:` guards. Real fix: interrogate the *first* default — the repo had its own page-size
  default (10) disagreeing with `PaginationParams` (20), two sources of truth. Repos don't decide
  policy: all three params required, no defaults, no `None`.
- **The same ruff `I001` (unsorted imports) came back in new files** → the gate only means
  something if you run it: `ruff check .` before calling any chunk done — CI (Phase 23) will run
  exactly this.

## Interview talking points

- "The transaction boundary lives in my **service** (`with db.begin()`); repositories **flush,
  never commit** — flush executes SQL inside the open transaction (that's how I get the
  DB-generated id mid-transaction), commit makes it durable and visible to other connections.
  A mid-transaction failure — I forced one with a dangling FK — leaves zero partial state."
- "My category check is **check-then-act**, so it races (TOCTOU): I reproduced it with two
  connections — check passed, another transaction deleted the category, my flush hit the FK.
  The **constraint is the guarantee; the check is UX**; I catch `IntegrityError` as a backstop
  and chain it with `from e`. I also saw why blanket IntegrityError translation mislabels errors
  once two constraints can fire — that's why you discriminate by constraint name."
- "I chose **PATCH with merge-patch semantics** over PUT because full replacement couples every
  client to the complete schema — an old client's PUT nulls columns it never knew about. The
  cost is the **absent/value/null tri-state**, which I handle with Pydantic's `exclude_unset`
  plus a validator that rejects explicit null on non-nullable fields. Field masks (Google) solve
  the same problem for proto3, which can't represent absence."
- "A linter passing only means the **enabled rules** pass — ruff's defaults are minimal, so I
  commit an explicit ruleset as a team contract, and I know why some findings have no autofix:
  `raise ... from e` vs `from None` is a semantic decision a tool shouldn't guess."
- "I shipped the classic offset-pagination bug — no `ORDER BY` — and **proved** it: a no-op
  `UPDATE` moved a row to the last page, because Postgres MVCC writes a new tuple at the end of
  the heap and undefined order is heap order. My rule now: every paginated query gets a
  deterministic sort key ending in a unique column. And I can go a level deeper: even with
  `ORDER BY`, offset pagination skips/repeats rows under concurrent writes — that's the case for
  cursor pagination."
- "My filters are built as a list of SQL fragments (`ColumnElement[bool]`) **independent of any
  statement**, then applied to both the page query and the count query — so `total` structurally
  can't disagree with the filter. I also know the difference between *filtering* (structured
  params on known fields — what Stripe and GitHub list endpoints do) and *search* (a `q=` string
  through a text pipeline — their dedicated search endpoints); Phase 16 builds the second one.
  And I escape LIKE metacharacters (`icontains(..., autoescape=True)`) because `?name=%` matching
  every row is wildcard injection — wrong results through a bound parameter, not SQL injection."
