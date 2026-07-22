# How to Add Data Lifecycle Columns: Soft Deletes & SKUs

> Columns that carry business meaning — and the constraints that guard them at the only
> layer no write path can bypass: the database itself.

**Phase:** 5 — Catalog data lifecycle: soft deletes & SKUs
**Concept it taught:** Edge validation vs data invariants; data migrations
(deterministic, reversible-or-honest); the `NOT VALID`/`VALIDATE` two-phase constraint
pattern and the lock mechanics underneath it; lifecycle columns (`deleted_at`) vs
business-state columns (`is_active`) and *which layer owns each filter*; staged
migrations on populated tables; partial unique indexes; constraint-name discrimination
with provenance-aware retries.
**Why it matters:** "Where do you enforce a business rule?" is a modelling question every
production system answers. Pydantic guards one door; a `CHECK` constraint guards the
building. And "how do you add a constraint to a huge live table without downtime?" is a
real interview question — the warm-up builds that answer at 43-row scale.

## Prerequisites

- Phases 3–4: Alembic running, DI wiring done.
- The naming convention in `app/core/database.py` (`ck_%(table_name)s_%(constraint_name)s`) —
  it plays a starring role in two bugs below.

## Part 1 — Warm-up: constraints as guards

### The problem, discovered not invented

During Phase 4's verification we noticed `ProductCreate` enforced `price >= 50` (₦50 floor —
we sell in naira) and required `brand`, while the database held **32 products under ₦50 and
43 without brands**. Both rules were deliberate — but they lived only in Pydantic.

**Edge validation vs data invariant (the concept):** a Pydantic rule is a *doorman* — it
checks people entering from tonight onward, at one door. A business rule like "no product
under ₦50" is a claim about *everyone already inside*, and there are doors the doorman
never sees: a bulk-import script, a psql session, future admin tooling. If the rule is
real, the database must enforce it — a `CHECK` constraint — and the existing violators
must be dealt with first, because Postgres validates a new CHECK against every existing
row and refuses if any violate:

```
ERROR:  check constraint "ck_products_price_floor" of relation "products" is violated by some row
```

### 1) Decide the data rules (before any code)

Two real decisions, made consciously:

- **Price:** re-price violators with `GREATEST(price * 5, 50)` — deterministic, and the
  `GREATEST` makes "cannot produce a violator" self-evident (bare `* 5` only worked because
  the accidental minimum was ₦11.99).
- **Brand:** backfill `'Unbranded'` and complete the stage to `NOT NULL` (the alternative —
  documented permanent nullability — was rejected; we wanted the invariant, accepting that
  a placeholder invents data).

**Wrong turn we made first:** `price * FLOOR((RANDOM() * 4) + 2)`. Two sins: (a)
**non-determinism** — a migration must produce the same database on dev, CI, and prod;
`RANDOM()` gives three different catalogs; (b) **it didn't even guarantee the floor** —
the multiplier could draw 2 against an ₦11.99 product → ₦23.98, still violating → a
*flaky migration*. Rules in migrations must be deterministic and provably sufficient.

**How to populate data in a migration (the question we asked):** first ask *"is the new
value derivable from the row by a rule, or does it need outside knowledge?"* Derivable →
one set-based `UPDATE` (no JSON, no per-row lists — if a rule exists, SQL evaluates it).
Not derivable (real brands per product) → a mapping **embedded in the migration file**
(a `VALUES` join), never an external file: migrations must be self-contained and frozen.
And never import app models into a migration — models evolve; migrations are frozen history.

### 2) The migration, big-table style (deliberately)

We wrote it as if products had 100M rows, to learn the production pattern. Final form in
`alembic/versions/2026_07_14_1509-00304c736732_...py`. The shape:

```python
op.execute("SET lock_timeout = '5s'")                     # fail fast, don't dam the queue

# Data fixes — transactional, idempotent by shape (WHERE matches nothing on re-run)
op.execute("UPDATE products SET price = GREATEST(price * 5, 50) WHERE price < 50")
op.execute("UPDATE products SET brand = 'Unbranded' WHERE brand IS NULL")

# Guards: register instantly (no scan)...
op.execute("ALTER TABLE products ADD CONSTRAINT ck_products_minimum_price "
           "CHECK (price >= 50) NOT VALID")
op.execute("ALTER TABLE products ADD CONSTRAINT ck_products_brand_not_null "
           "CHECK (brand IS NOT NULL) NOT VALID")

# ...then validate in SEPARATE transactions (this is the whole point — see below)
with op.get_context().autocommit_block():
    op.execute("ALTER TABLE products VALIDATE CONSTRAINT ck_products_minimum_price")
    op.execute("ALTER TABLE products VALIDATE CONSTRAINT ck_products_brand_not_null")

# PG12+: SET NOT NULL skips its scan because the validated CHECK proves no NULLs
op.alter_column("products", "brand", nullable=False)
op.drop_constraint(op.f("ck_products_brand_not_null"), "products", type_="check")
```

**Why `NOT VALID` + `VALIDATE` (the lock model):** danger = **lock weight × hold
duration**. A plain `ADD CONSTRAINT CHECK` takes the heaviest lock (`ACCESS EXCLUSIVE` —
no reads, no writes) and holds it *while scanning every row* — minutes of frozen table at
scale. `NOT VALID` takes the same heavy lock for a millisecond (no scan, rule applies to
new writes only); `VALIDATE` does the scan under a weak lock that lets traffic flow.

**Why the `autocommit_block` (locks release at COMMIT, not statement end):** Alembic runs
a migration in one transaction, and a transaction holds every lock it has taken until
COMMIT. Back-to-back `NOT VALID; VALIDATE;` in one transaction means the heavy lock from
the ADD is *still held* during the "gentle" scan — identical blocking to the plain form,
pure ceremony. The pattern only works if the two statements **commit separately** —
`autocommit_block()` is Alembic's API for exactly that. Analogy: close the road for one
minute to bolt up the "new rules" sign, *reopen it*, then inspect existing cars from the
shoulder. Keeping the road closed for the inspection anyway makes the sign trick pointless.

**The price of the pattern — atomicity is spent, deliberately:** once you commit
mid-migration, a later failure leaves earlier work applied (we hit this — see
Troubleshooting). Everything before the commit point must tolerate re-running; our UPDATEs
are idempotent by shape (`WHERE price < 50` matches nothing the second time).

**The PG12 bridge (`SET NOT NULL` for free):** `ALTER COLUMN ... SET NOT NULL` normally
does its own full-table scan under the heavy lock. Postgres 12+ skips the scan if a
*validated* CHECK already proves `col IS NOT NULL`. So the zero-downtime NOT NULL recipe
is: CHECK `NOT VALID` → `VALIDATE` (weak lock) → `SET NOT NULL` (instant, rides the
check) → drop the now-redundant scaffold CHECK.

**`SET lock_timeout` (from cargo-cult to load-bearing):** even an instant DDL statement
must *queue* for its heavy lock behind every in-flight query — and while it queues, all new
queries queue behind *it*. One forgotten idle-in-transaction session turns a millisecond
`DROP CONSTRAINT` into minutes of dammed traffic. `lock_timeout` makes the migration give
up cleanly instead of plugging the table.

### 3) The downgrade — honest, not magical

```python
op.alter_column("products", "brand", nullable=True)     # loosen NOT NULL FIRST...
op.execute("UPDATE products SET brand = NULL WHERE brand = 'Unbranded'")  # ...then null
op.drop_constraint(op.f("ck_products_minimum_price"), "products", type_="check")
# Prices are NOT restored: the original sub-50 values were overwritten and
# no longer exist. Recovering them requires a backup taken before this ran.
```

**Why:** after `GREATEST(price*5, 50)`, the value ₦11.99 exists nowhere — no SQL recovers
destroyed information. The two honest postures: (a) reverse what's reversible and *say
loudly* what isn't (chosen — production teams treat pre-deploy backups, not `downgrade()`,
as the undo for data migrations); (b) make it reversible by design — snapshot doomed rows
to a side table in `upgrade()`, restore from it in `downgrade()` (rejected here as extra
ceremony, but know the pattern). Also: downgrades are mirrors — reverse the steps in
reverse order, or the brand UPDATE violates the NOT NULL you haven't dropped yet.

### 4) Keep the model truthful

The DB changed; `app/products/models.py` must tell the same story or the next
`--autogenerate` emits spurious diffs: `brand` becomes non-nullable in the model, and the
price CHECK is declared in `__table_args__` (autogenerate doesn't track CHECKs, but fresh
`create_all` databases — Phase 19's test DBs — must get the same constraints). Two traps
here — see Troubleshooting entries 3 and 4.

### 5) Prove it (the acceptance criteria)

```
-- raw insert under the floor: rejected BY THE DATABASE, not the API
INSERT ... VALUES ('cheap', 49.99, ...);
ERROR:  new row ... violates check constraint "ck_products_minimum_price"

-- raw insert with NULL brand:
ERROR:  null value in column "brand" ... violates not-null constraint

-- round trip: alembic downgrade -1 (constraint gone, brand nullable, 43 NULLs back)
--             alembic upgrade head (full state restored)
-- API still serves: GET /products → 200
```

## Troubleshooting (real issues we hit)

- **`ERROR: check constraint ... is violated by some row` when adding a CHECK** → Postgres
  validates existing rows at ADD time. Not a bug — it's the feature: fix the data first
  (same migration, data-then-constraint order), and it forces you to confront violators
  honestly.
- **Raw `op.execute("COMMIT;")` to split transactions → NEVER.** It yanks the transaction
  out from under Alembic: everything before the COMMIT is permanently committed even if a
  later statement fails (half-applied migration, `alembic_version` not bumped, re-run
  crashes on "already exists"), and SQLAlchemy's connection bookkeeping no longer matches
  reality. The instinct (separate commits) was *right* — the tool is
  `op.get_context().autocommit_block()`.
- **`constraint "ck_products_ck_products_brand_not_null" does not exist` — the doubled
  prefix.** `op.drop_constraint("ck_products_brand_not_null", ...)` ran the name through
  the naming convention template `ck_%(table_name)s_%(constraint_name)s` — Alembic treated
  the full name as the `%(constraint_name)s` token and wrapped it again. **`op.f()`** marks
  a name as final ("hands off") — that's what it's been doing in every autogenerated
  migration since Phase 3. Root cause of the mix-up: constraints *created* via raw SQL
  (conventions never see it) but *dropped* via Alembic ops (conventions apply) — two APIs,
  two naming behaviours. This failure struck *after* the autocommit block → the
  half-applied state above, recovered by manually dropping the two constraints in psql and
  re-running (the UPDATEs no-op'd — idempotency paying off).
- **The same doubled-prefix bug, model-side:** `CheckConstraint("price >= 50",
  name="ck_products_minimum_price")` in `__table_args__` ALSO gets template-wrapped —
  proven by printing `Product.__table__.constraints` → `ck_products_ck_products_minimum_price`.
  A Phase 19 test DB built via `create_all` would get the wrong constraint name, silently
  breaking the constraint-name discrimination the SKU work depends on. Fix: give the
  *short* name (`name="minimum_price"`) and let the convention expand it — the convention
  is the single source of naming truth, in both the model and hand-written migrations.

- **`__table_args__ value must be a tuple, dict, or None` after deleting a constraint** →
  Python gotcha: parentheses don't make tuples, **commas** do. With two constraints the
  separating comma made the tuple; deleting one left `(CheckConstraint(...))` — a bare
  parenthesized expression. Fix: trailing comma. Habit: always keep the trailing comma in
  one-element tuples so removing elements can't silently change the type.
- **The definitive "model matches DB" check:** `alembic check` — reports whether
  autogenerate would emit anything. "No new upgrade operations detected" = no drift.
- **Ran the `deleted_at` migration → every row instantly soft-deleted.** Root cause:
  `server_default=func.now()` copy-pasted from `created_at`. `ADD COLUMN` with a
  `server_default` **backfills every existing row** with it (the exact behaviour we
  *wanted* for `is_active`), and every future INSERT gets stamped too — products born
  dead. Fix: lifecycle columns get NO default. Asymmetry worth knowing: only `ADD COLUMN`
  backfills; `ALTER COLUMN ... SET DEFAULT` affects future inserts only, never existing
  rows.
- **Autogenerate blind spot #3, confirmed empirically:** after fixing the model (default
  removed) the DB still had the default, yet `--autogenerate` drafted *nothing* —
  `server_default` drift is invisible unless `compare_server_default=True` is set in
  `env.py` (off by default; textual comparison is unreliable). Confirmed blind-spot list,
  each met personally: data migrations, CHECK constraints, server defaults. That list is
  the real answer to "why review autogenerated migrations?"
- **App down: `PydanticUserError: Decorators defined with incorrect fields` on import** →
  a `@field_validator("sku")` was placed on `ProductUpdate`, which has no `sku` field.
  Pydantic verifies decorator targets at class-definition time and refuses — the import
  crashed, taking the whole (reloading) server with it. Fix: validators live on the class
  that owns the field (`ProductCreate`). Details in Part 3 §4.
- **`alembic check`: `Detected changed index ... unique=True to unique=False`** → the
  model's copy of the partial index was transcribed without `unique=True` while the DB's
  (from the migration) had it. Autogenerate renders any index difference as a
  drop-and-recreate pair (Postgres can't `ALTER` an index's uniqueness) — read it as "if
  I trusted your model, I'd replace your unique index with a non-unique one." One
  argument fixed it. Details in Part 3 §2.
- **mypy/Pyrefly: `Object of class BaseException has no attribute "diag"`** →
  `IntegrityError.orig` is typed `BaseException | None`; only psycopg errors carry
  `.diag`. Dotting through fails type-checking. Fix: probe with
  `getattr(e.orig, "diag", None)` in a small `_constraint_name` helper.
- **Attribute docstrings attached to the wrong columns** → Python's convention (PEP 258,
  honored by Sphinx/IDEs) puts an attribute's docstring *after* the attribute, not
  before. Strings written above `deleted_at`/`is_active` were silently read as docs for
  the *previous* column. Fix: move each string directly below the line it documents.

## Concepts that confused me (and the plain-English answer)

- **Edge validation vs data invariant:** the doorman vs the building (Part 1).
- **How data migrations populate values:** rule → one UPDATE; outside knowledge → embedded
  mapping; never external files, never app-model imports.
- **Locks:** danger = weight × duration; catalog-only DDL (DROP CONSTRAINT, RENAME, add
  nullable column) is heavy-but-instant vs scan/rewrite DDL (plain ADD CHECK, SET NOT NULL
  pre-bridge, ALTER TYPE) which is heavy-and-long; the queue amplifier and `lock_timeout`.
- **Locks release at COMMIT, not statement end** — why the two-phase pattern needs two
  transactions.

- **What is a SKU, really? (vs the database id, vs a barcode.)** Start from the `id`
  column: it identifies a row perfectly but means nothing to a human, changes if you
  reload the catalog, and nobody outside your database knows it. A **SKU** (Stock Keeping
  Unit) is the *seller's* code for each distinct thing they stock — "distinct thing" at
  the granularity stock is counted (red-medium and red-large shirts = two SKUs). A
  **UPC/EAN** (barcode) is the *manufacturer's* code, global, same in every store.
  One product → one UPC → many SKUs (one per seller). Analogy: UPC = fingerprint
  (issued by nature, same everywhere); SKU = employee ID (each company that "stocks" you
  issues its own); `id` = the row number in one HR spreadsheet. That's also why `id`
  stays the primary key: SKUs are *natural keys* with business meaning, and business
  meaning invites business change — `id` is a *surrogate key*, meaningless and therefore
  stable. Amazon adds its own layer (ASIN) on top of seller SKUs for the same reason.

- **Opaque vs meaningful SKUs — and why generated ones must be opaque.** A human-minted
  `TSHIRT-RED-M` is readable but rots if the product changes (SKUs are immutable; their
  inputs aren't). Machine-generated "meaningful" codes are worse: derived from mutable
  fields, plus ugly collision suffixes. The hybrid model dissolves the dilemma: merchants
  who want meaning supply it; the platform's fallback generator mints opaque codes —
  exactly what real platforms do (ASIN `B08N5WRWNW`, Stripe `prod_...`).

- **Crockford base32, from first principles.** A number base is just "how many symbols
  per position": base 10 uses `0–9`, hex uses sixteen (`FF` = 15×16+15 = 255). Base 32
  uses thirty-two — the question is *which* thirty-two characters. Douglas Crockford's
  2008 answer: take `0–9A–Z` (36) and drop `I`, `L`, `O` (misread as `1`, `1`, `0` on
  labels and over the phone) and `U` (profanity guard) → 32 symbols, which is neatly 2⁵ —
  each character carries exactly 5 bits. Proof it's a real base:
  `ALPHABET.index("Z")*32 + ALPHABET.index("8")` = `31*32+8` = `1000` — "Z8" *is* 1000.
  Analogy: it's a phonetic alphabet for codes — "Alfa, Bravo, Charlie" exists because
  B/D/E *sound* alike over radio; Crockford's set exists because 0/O and 1/I/L *look*
  alike. Nuance: Crockford base32 proper is an *encoding* (decodable back to a number);
  our generator only borrows the curated **alphabet** as a pool for random draws — renting
  the typeface, not the arithmetic. ULID uses the same alphabet for the same reason.
  The transferable rule: any identifier humans will read, type, or say aloud gets an
  alphabet designed for humans.

- **The generator one-liner, decomposed.**
  `"".join(secrets.choice(_SKU_ALPHABET) for _ in range(_SKU_LENGTH))` is a compressed
  loop: `secrets.choice(s)` picks one random character; `for _ in range(8)` repeats it
  8 times (`_` = "I never use this variable"); the whole `x for _ in range(n)` is a
  generator expression (a comprehension without the brackets); `"".join(...)` glues the
  pieces with nothing between them. Loop form:
  ```python
  chars = []
  for _ in range(8):
      chars.append(secrets.choice(_SKU_ALPHABET))
  code = "".join(chars)
  ```
  Analogy: a Scrabble bag with 32 tiles — draw, write the letter down, *put it back*,
  eight times. (Put-it-back means repeats are legal; whole-SKU uniqueness is the
  database's job, not the generator's.) `"".join(<piece> for _ in range(n))` is *the*
  standard Python idiom for "build a string from n generated pieces."

- **What the partial unique index actually promises.** Only rows `WHERE deleted_at IS
  NULL` exist to the index, so the invariant is: *among alive products a SKU appears at
  most once; among dead ones, anything goes.* Two dead rows + one alive row may all share
  `SKU-X`; a second alive holder is rejected. Two consequences traced through time:
  (a) a SKU identifies one *alive* row at a moment, not one row across history — which is
  why order lines must reference `id`, never `sku` (the surrogate-key decision and the
  partial index are two halves of one design); (b) a future "restore" feature can fail:
  un-deleting moves a row back into the index's view, and if its SKU was reused
  meanwhile, the restore hits the unique violation — "can you undelete?" is honestly
  "yes, with a possible SKU conflict to resolve."

- **Universal invariant vs audience-dependent filter (why `deleted_at` is central and
  `is_active` must not be).** `deleted_at IS NULL` is true for *every* caller in *every*
  context → it belongs in the repository's one central helper. `is_active` filtering
  depends on *who's asking*: shoppers mustn't see hidden products, but the merchant must
  (Shopify: draft products invisible on the storefront, fully editable in admin) — and if
  the central helper filtered them, `update_product`'s fetch would break and the flag
  would become a one-way trap (hide a product, never able to un-hide it). So visibility
  is a per-query *service* condition for the right audience. Decision recorded: since the
  API has only one audience until Phase 7 (no auth yet), filtering is **deferred** — all
  reads return inactive products with the flag exposed; Phase 7's public read paths add
  `is_active == True` while admin paths don't. Related display nuance: the "blurred
  product" pattern in real stores is *out-of-stock* (deliberately shown — SEO, demand
  signals, "notify me"), not inactive; stock is data the client renders, needing no
  filter at all.

- **Why the SKU-collision retry needs a *fresh transaction* (the poisoned transaction).**
  When any statement in a Postgres transaction fails, the whole transaction aborts —
  every later statement answers `current transaction is aborted` until ROLLBACK. So
  "catch the IntegrityError and just insert again" cannot work inside the same
  `with db.begin():`. The loop must wrap the transaction (one attempt = one transaction),
  and the `except` sits *outside* the `with`, because the `with`-exit performs the
  rollback as the exception passes through, handing the next iteration a clean session.
  Full code and the two companion shape-rules ("handlers decide and raise; loops retry";
  "never swallow unknown constraints — `case _: raise`") in Part 3 §6.

- **Deleting by object vs by id (repository signatures).** The service must fetch anyway
  to decide the 404, so `soft_delete(product)` receives *proof of existence, not a claim
  of it* — an id-based method would either re-fetch or blind-update and smuggle the
  not-found decision into its return value. The id-based signature wins in the other
  regime: atomic conditional updates (`UPDATE ... WHERE id = :id AND deleted_at IS NULL`)
  that need no prior read — Phase 9's tool. Rule: fetched-for-a-decision → pass the
  object; no decision needs the row → pass the id, let rows-affected report.

- **Why ids have gaps (48, 49, then 51).** Sequences are non-transactional: a failed
  INSERT consumes its number and a rollback doesn't refund it — if it did, concurrent
  transactions would have to serialize on id handout. Gaps are normal, harmless, and a
  nice thing to say calmly in an interview when someone points at them.

## Part 2 — Soft delete (`deleted_at`)

### Design decision: explicit repository filtering, no ORM magic

SQLAlchemy can enforce `deleted_at IS NULL` globally — a `do_orm_execute` event listener +
`with_loader_criteria` on a mixin filters every SELECT (and even relationship lazy-loads)
automatically. Django managers, Rails `default_scope`, Hibernate `@Where` are the same
idea. We considered it and **chose explicit repository-layer filtering instead**: a
private helper every read starts from — one enforcement point, visible at the call site,
greppable in both directions ("where's the filter?" → one method; "does this query
filter?" → read its first line).

**Why:** the global filter trades "can't forget" for "can't see" — the `default_scope`
lesson: a WHERE clause appears in your SQL that exists nowhere near any query you can
read, and debugging "why can't I see this row" means discovering an event listener you've
never opened (cf. Laravel observers: things just happen and you don't know why). The
explicit version's weaker guarantee is owned honestly: convention makes the helper the
easy path, and Phase 19's soft-delete behaviour test is the tripwire if anyone bypasses it.
Knowing *both* options and articulating the choice is the interview-worthy part.

### 1) The column — and the bug that soft-deleted the whole catalog

`deleted_at` is a nullable timestamptz with **no default** (NULL = alive). The first
attempt copy-pasted the neighbouring `created_at` pattern — dragging
`server_default=func.now()` along — and the migration promptly stamped **all 43 rows** as
deleted. See Troubleshooting; the three-timestamps distinction is the concept:

- `created_at` / `updated_at`: "stamp me at birth" — a `now()` default is the point.
- `deleted_at`: **NULL is the meaningful state**; only the explicit delete action may ever
  set it. A lifecycle column with a birth-time default answers "when were you deleted?"
  with "the moment you were created."

### 2) The fix-forward exercise (done deliberately)

Instead of delete-and-regenerate (the dev-only luxury), we kept the bad migration applied
and practised the production move: **history is immutable once merged — fix by adding,
never editing.** Why editing can't work: `alembic upgrade` never re-runs a revision
recorded in `alembic_version`, so deployed DBs ignore your edit while fresh DBs run it —
two populations, same revision id, different histories. Leave the bad file alone and add a
fix on top, and every database *converges*: deployed ones run just the fix; fresh ones
replay bug-then-fix and land in the same state.

The fix migration (`2612b7564f77`) has two jobs mirroring the two damages:

```python
def upgrade() -> None:
    # Damage 1: every INSERT was getting deleted_at = now() (born dead).
    op.alter_column('products', 'deleted_at', server_default=None)
    # Damage 2: the ADD COLUMN backfill stamped every existing row.
    # Blanket NULL is safe HERE ONLY because soft delete isn't built yet.
    op.execute("UPDATE products SET deleted_at = NULL WHERE deleted_at IS NOT NULL")
```

**Identifying wrongly-stamped rows (the production version):** Postgres freezes `now()`
at transaction start, so the migration's backfill gave every row an *identical*
timestamp — verified in our data: `count(DISTINCT deleted_at)` = 1. That spike is the
discriminator a real fix would key on (`WHERE deleted_at = '<signature>'`), plus
`WHERE deleted_at = created_at` for born-dead inserts. The discriminators exist because
the bug is young — which is why data bugs get fixed forward *fast*.

**The downgrade near-miss:** the first draft's `downgrade()` re-stamped rows with
`UPDATE ... SET deleted_at = NOW() WHERE deleted_at IS NULL` — symmetry instinct, but it
*fabricates* data (the original stamps are destroyed; `NOW()` at downgrade time is a
plausible-looking lie) and it's a landmine: run months later, after real deletes exist, it
would mark **every alive product deleted**. Honest downgrade restores the schema default
only and states in a comment that the data cannot come back.

### 3) Repository filtering — one helper, every read starts from it

The design decision above (explicit over magic) became a private builder in
`ProductRepository`:

```python
def _select_products(self, include_deleted: bool = False) -> Select[tuple[Product]]:
    query = select(Product)
    if not include_deleted:
        query = query.where(Product.deleted_at.is_(None))
    return query
```

Every read path composes from it — `list_products` builds items *and* count from the same
filtered base (count must respect the filter too, or page metadata counts ghosts), and
`get_product` gained an `include_deleted: bool = False` escape hatch (default safe;
bypassing the filter is a visible, greppable decision at the call site). One consequence
worth noticing: `db.get(Product, id)` had to go — the identity-map shortcut can't carry a
WHERE clause, so the fetch became `execute(select...).scalar_one_or_none()`. The
soft-delete write is `soft_delete(product)`: stamp `deleted_at = now(UTC)`, flush; commit
stays with the service.

### 4) The DELETE endpoint — each layer's one job

- **Repository** `soft_delete(product)` *does* it (stamp + flush, no decisions).
- **Service** `delete_product(id)` decides *what*: open the transaction, fetch via
  `get_product` (raises `ProductNotFoundError` — the 404 decision is business logic),
  then hand the verified object to the repo.
- **Router** maps: `204` on success, `ProductNotFoundError → 404`. Nothing else.

**Why the repo takes the object, not the id (asked and answered):** the service must fetch
anyway to decide the 404, so `soft_delete(product)` receives **proof of existence, not a
claim of it** — an id-based repo method would either re-fetch (duplicate query) or
blind-update and smuggle the not-found decision into its return value. Matches
`update_product(product, data)` and the DDD repository-as-collection metaphor
(`list.remove(obj)`, not remove-by-description). The id-based signature wins in the *other*
regime: an atomic conditional update (`UPDATE ... SET deleted_at = now() WHERE id = :id AND
deleted_at IS NULL`) needs no prior SELECT and closes the race window entirely.

**Two decisions made consciously:**
- **Repeat DELETE → `404`, not `204`.** `get_product` filters deleted rows, so a second
  delete naturally 404s — consistent with "behaves deleted." The alternative reading
  (HTTP DELETE as idempotent → repeat `204`) is defensible; we chose consistency with the
  fetch semantics and can argue it.
- **The check-then-act window, seen and deliberately deferred.** Fetch-then-stamp means two
  racing DELETEs can both pass the fetch and both 204 (second overwrites the timestamp).
  Harmless here — but it is Phase 9's oversell window in miniature, and
  `WHERE deleted_at IS NULL` is the same closing move as `WHERE stock >= q`. Named now,
  closed there.

### 5) Verified (the acceptance criteria, live)

```
DELETE /products/42        → 204
GET    /products/42        → 404 {"detail":"Product with id 42 not found"}
DELETE /products/42 again  → 404   (chosen repeat-delete semantics)
DELETE /products/9999      → 404
GET /products?per_page=100 → id 42 absent from items

-- and the row is still there (psql):
 id |       name       |          deleted_at           | is_active
----+------------------+-------------------------------+-----------
 42 | LEGO Classic Set | 2026-07-18 10:49:17.707991+00 | t
```

Note `is_active` stayed `t` while `deleted_at` got stamped — the two columns moving
independently is the distinction, demonstrated in data.

### 6) Documenting the two columns (the last criterion)

The distinction lives as **attribute docstrings on the model** (placed *after* each
column — PEP 258; a string above the attribute silently documents the *previous* one,
a mistake we made first). `deleted_at` = lifecycle, gone-for-everyone, filtered
centrally in the repository (universal invariant). `is_active` = reversible business
state, audience-dependent visibility, filtered per-query in the service — **deferred
until Phase 7 brings audiences**; until then all reads return inactive products with the
flag exposed. One-liner: *`is_active` is a light switch the merchant flips; `deleted_at`
is a death certificate with a date on it.* Full reasoning in "Concepts that confused me."
Content lesson from review: an early draft documented a SKU-uniqueness consequence under
`is_active` — true but misleading, since `deleted_at` (the partial index), not
`is_active`, governs SKU uniqueness; each column's doc states what *it* governs.

## Part 3 — SKU: staged migration, partial unique index, 409 discrimination

### Design decisions (made before code)

- **Opaque generated SKUs** over meaningful ones: the hybrid model means merchants who
  want `TSHIRT-RED-M` supply it; the generator only fires when the client didn't care.
  Machine-derived "meaningful" codes are built from mutable fields (name/category) and rot
  against SKU immutability; collisions need ugly suffix counters. Platforms mint opaque
  (Amazon ASIN, Stripe `prod_...`); humans mint meaningful.
- **SKU vs id vs UPC:** the SKU is the *seller's* identifier (per-catalog, business
  domain); `id` stays the surrogate PK/FK target (natural keys make terrible PKs — business
  meaning invites business change); a UPC/EAN would be the *manufacturer's* global code.
- **Immutable after creation** (published identifier — labels, order history reference it);
  fix a wrong SKU by making a new product, like fixing migration history: add, never edit.

### 1) The staged migration (`26cbd8a980dc`) — four moves, one file

```python
op.execute("SET lock_timeout = '5s'")
# 1. add NULLABLE — instant (no scan, no default, no rewrite)
op.add_column("products", sa.Column("sku", sa.String(length=100), nullable=True))
# 2. backfill — deterministic (derived from id), idempotent by shape;
#    soft-deleted rows included (NOT NULL binds them too)
op.execute("UPDATE products SET sku = CONCAT('SKU-', id) WHERE sku IS NULL")
# 3. enforce required (plain form scans; at scale: the NOT VALID/VALIDATE bridge)
op.alter_column("products", "sku", nullable=False)
# 4. partial unique — deleted products free their SKU
op.create_index("uq_products_sku", "products", ["sku"], unique=True,
                postgresql_where=sa.text("deleted_at IS NULL"))
```

Downgrade: explicit mirror (`drop_index`, `drop_column`). The round trip is **lossless
because the backfill is deterministic** — downgrade destroys the SKUs, upgrade regenerates
the identical values. Register note: written in the small-table form deliberately; the
big-table narration is `CREATE UNIQUE INDEX CONCURRENTLY` (outside the transaction) and
the CHECK-bridge for NOT NULL.

### 2) Wrong turns on the way (all instructive)

- **`ALTER TABLE ... ADD CONSTRAINT ... UNIQUE (sku) WHERE deleted_at IS NULL` → syntax
  error at `WHERE`.** A UNIQUE *constraint* is SQL-standard and the standard has no partial
  uniqueness — the grammar has no slot for it. Postgres's partiality extension lives at the
  *index* level: `CREATE UNIQUE INDEX ... WHERE ...` is the only spelling. (Postgres backs
  every unique constraint with a unique index anyway; the constraint object is just the
  standard's face on it.)
- **Same mistake, model-side:** `UniqueConstraint("sku", postgresql_where=...)` →
  SQLAlchemy `ArgumentError` — the ORM mirrors the grammar. Model spelling:
  `Index("uq_products_sku", "sku", unique=True, postgresql_where=text(...))`.
- **`unique=True` left on the `mapped_column`** — the sneaky one: it *works*, by creating
  a SECOND, total unique constraint alongside the partial index — the dead-SKU-hostage bug
  smuggled back in through a column flag. Uniqueness lives in exactly one place.
- **`op.alter_column(..., unique=True)` (first draft) — silently ignored.** Uniqueness is
  a database *object*, not a column property; there's no `ALTER COLUMN ... SET UNIQUE` for
  Alembic to translate to, and it drops the kwarg without error. NOT NULL + zero
  uniqueness enforcement would have shipped.
- **`alembic check` caught real drift:** the model's Index was transcribed missing
  `unique=True` → `Detected changed index ... unique=True to unique=False`. Autogenerate
  renders any index change as a drop/recreate pair (Postgres can't ALTER uniqueness) — it
  was proposing to replace the unique index with a non-unique one. One argument fixed it;
  check now clean. Two copies of one index (migration = what prod runs, model = what
  Phase 19 `create_all` test DBs get) is exactly what the check exists to keep honest.

### 3) Verified

```
uq_products_sku | CREATE UNIQUE INDEX uq_products_sku ON public.products
                  USING btree (sku) WHERE (deleted_at IS NULL)
downgrade -1  → sku column gone;  upgrade head → back, identical values (SKU-1 ... SKU-42)
alembic check → "No new upgrade operations detected"
```

Discrimination note for the service step: violating a plain unique *index* still raises
`duplicate key value violates unique constraint "uq_products_sku"` — Postgres reports the
index name in the constraint slot (`e.orig.diag.constraint_name`), so constraint-name
discrimination works identically.

### 4) Schemas — immutability and normalization live at the edge

- `ProductCreate`: optional `sku` (`min_length=3` — NOT 8: the backfilled `SKU-1`…`SKU-43`
  are 5–6 chars, and the first draft's `min_length=8` would have 422'd our own
  reuse-after-delete acceptance test), with a validator that strips, **uppercases**
  (case-insensitivity by normalization, not an expression index) and enforces
  `^[A-Z0-9-]+$`.
- `ProductUpdate`: **no `sku` field at all**, plus `model_config = ConfigDict(extra="forbid")`
  — PATCH with `sku` → loud `422 extra_forbidden` naming the field. Immutability enforced
  by the schema's *shape* (strict-reader choice, made consciously over silent-ignore).
- **Wrong turn:** the sku validator was first placed on `ProductUpdate` — which has no
  `sku` field. Pydantic refuses at class-definition time (`PydanticUserError: Decorators
  defined with incorrect fields`) — the import crashed, taking the whole app down.
  Ironically the crash *proved* the immutability design: ProductUpdate really doesn't know
  sku exists. Validators must live on the class that owns the field.

### 5) Generation — opaque, in the service, `secrets` over `uuid`

```python
_SKU_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # Crockford base32: no I, L, O, U
_SKU_LENGTH = 8                                       # 32^8 ≈ 1.1e12 values
_SKU_PREFIX = "SKU-"
_SKU_MAX_ATTEMPTS = 5

def _generate_sku(self) -> str:
    code = "".join(secrets.choice(_SKU_ALPHABET) for _ in range(_SKU_LENGTH))
    return f"{_SKU_PREFIX}{code}"
```

Placement rationale: generation is a business policy ("we assign identity when the client
doesn't") *and* the retry fork needs **provenance** — only the service knows whether the
SKU came from the client (→ 409) or from us (→ regenerate). A Pydantic `default_factory`
would generate before the service ever saw the request, erasing that distinction. Crockford
alphabet = transcription-safe (drops `I/L/O/U`, the lookalikes + the profanity vowel; same
alphabet ULID uses). `secrets` over `random` (no predictable sequence) and over truncated
`uuid` (worse alphabet, same entropy job).

### 6) 409 discrimination + bounded retry — and the transaction lesson inside it

Seen live before fixing (build-it-wrong-first, on schedule): duplicate SKU returned
`422 "Category with id 5 not found"` — a lie; the blanket `except IntegrityError →
CategoryNotFoundError` mislabeled the unique-index violation. The fix has three load-bearing
parts:

```python
for _ in range(_SKU_MAX_ATTEMPTS):
    if not has_sku_from_customer:
        data.sku = self._generate_sku()
    try:
        with self.db.begin():
            ...category check...
            new_product = self.product_repository.create_product(data)
    except IntegrityError as e:
        match self._constraint_name(e):
            case "uq_products_sku" if has_sku_from_customer:
                raise DuplicateSKUError(f"SKU {data.sku} already exists") from e
            case "uq_products_sku":
                continue          # generated collision — fresh code, fresh transaction
            case "fk_products_category_id_categories":
                raise CategoryNotFoundError(...) from e
            case _:
                raise             # never swallow unknown constraints
    else:
        self.db.refresh(new_product)
        return new_product
raise RuntimeError(f"Could not generate a unique SKU after {_SKU_MAX_ATTEMPTS} attempts")
```

- **The loop wraps the transaction, not vice versa.** A failed INSERT *poisons* the whole
  Postgres transaction (`current transaction is aborted`); nothing can run on it until
  rollback. The first draft retried *inside* the same `with self.db.begin()` — structurally
  impossible. The `except` sits **outside** the `with` because the `with`-exit performs the
  rollback as the exception passes through, leaving the session clean for the next attempt.
- **Handlers decide and raise; loops retry.** The first draft's error-handler method also
  performed the retry insert and discarded the result (→ `UnboundLocalError` far from the
  cause). Restructured: the match only *classifies and raises/continues*.
- **Provenance fork via a match guard:** `case "uq_products_sku" if has_sku_from_customer:`
  — client duplicates 409 immediately (their conflict to resolve, never retried); only our
  generated collisions regenerate, bounded at 5 (hitting the bound in a 10^12 keyspace
  means something is *broken* — hence honest `RuntimeError`/500, not a domain error).
- Constraint name read via a `getattr` helper (`e.orig` is typed `BaseException | None`;
  dotting `.diag` directly fails mypy/Pyrefly). Unique-*index* violations report the index
  name in the constraint slot — discrimination works identically to a named constraint.

### 7) Verified (acceptance criteria, live)

```
POST no sku                  → 201, sku SKU-MJM3DF4W (generated, Crockford)
POST sku "dup-test-1"        → 201, stored as DUP-TEST-1 (edge normalization)
POST duplicate sku           → 409 "SKU DUP-TEST-1 already exists"   (was: lying 422)
POST bad category            → 422 "Category with id 9999 not found" (both constraints, distinct answers)
PATCH {"sku": ...}           → 422 extra_forbidden naming the field
DELETE then recreate same sku→ 201 (partial index proven through the API)
ruff + mypy                  → clean
```

Bonus observation: the failed duplicate insert consumed an id (48, 49, then 51) —
sequences are non-transactional (a rollback doesn't refund the number, or concurrent
transactions would serialize on id handout). Gaps in ids are normal.

## Interview talking point (SKU)

"SKUs are hybrid: merchants supply their own, the service generates an opaque Crockford
base32 code when they don't — generation lives in the service because only it knows the
SKU's provenance, and provenance decides collision handling: a client duplicate is a 409,
our own generated collision retries with a fresh code in a *fresh transaction*, because a
failed INSERT aborts the whole Postgres transaction. Uniqueness is a partial unique index
(`WHERE deleted_at IS NULL`) so a soft-deleted product frees its SKU, and the service
discriminates IntegrityErrors by constraint name — with two constraints able to fire on one
insert, a blanket catch mislabels errors, which I reproduced live before fixing."

## Interview talking point (warm-up)

"I found business rules that existed only as API validation while the database held
violating rows. I fixed the data and added the constraints in one reviewed migration — and
did it the zero-downtime way: `CHECK ... NOT VALID`, then `VALIDATE` in a separate
transaction under the weak lock, then `SET NOT NULL` riding Postgres 12's validated-check
bridge so it skipped its scan. I can explain why the pattern is pointless inside a single
transaction — locks release at COMMIT — and what it costs: atomicity, which is why every
step before the mid-migration commit is idempotent."
