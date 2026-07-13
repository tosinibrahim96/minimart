# MiniMart API — Learning Requirements & Progress Tracker

A behaviour-driven spec for becoming **interview-ready** on FastAPI and backend engineering by building a deliberately lean online store. This is **not** a feature wishlist — it's a sequence of *concepts* disguised as features. Every phase exists to force one idea you can't fake your way around, so that in an interview you're speaking from things you actually built, not things you read.

> **How to use this document**
> - Work the phases in order. The order *is* the curriculum.
> - For each phase: read the *Learning objective* and *Why it matters* first, then build until the *Acceptance criteria* pass, then answer the *Self-check / interview questions* out loud before moving on.
> - A phase is "done" only when the acceptance criteria pass **and** you can answer the self-check questions without notes. Working code you can't explain is not done — an interviewer will find the gap in two sentences.
> - Update each phase's *Status* and tick the dashboard. Watching it fill up is the point.
> - No code lives in this doc on purpose. The behaviour is specified; the implementation — and the struggle — is yours. That struggle is the learning.
> - A few phases (marked 🔬) use a **build-it-wrong-first** plan: you deliberately build the naive version, reproduce the failure (oversell, N+1 query storm, a frozen event loop, stale cache), *then* fix it. Don't skip the wrong version — feeling the bug is what makes the fix and the interview story stick.
> - Two phases (marked ♻️) are **deliberate refactor phases**: the code already works, and the exercise is changing it safely with a defined end state. Refactoring working code on purpose — without breaking behaviour — is itself a senior skill this curriculum trains twice: once early with a small blast radius (Phase 4), once at the end with the test suite as a safety net (Phase 24).

---

## The three pillars (the real 80/20)

Everything below serves three skills. Internalise these and the rest is detail:

1. **Dependency injection** — FastAPI's spine. Auth, DB sessions, config, and testing all reduce to "this is just a dependency."
2. **The data & transaction layer** — modelling data correctly and making state changes safe under concurrency and failure. This is where "knows FastAPI" becomes "can run a backend."
3. **Testability** — a codebase you can change without fear. This is the actual deliverable of senior engineering; everything else is scaffolding.

At every phase, keep asking: *which pillar is this teaching me?*

---

## Progress dashboard

Status ladder for each phase: `☐ Not started` → `◐ In progress` → `☑ Built (criteria pass)` → `★ Understood (can explain it cold)`.

### Part A — Foundations & the catalog
| # | Phase | Core concept | Status |
|---|-------|--------------|--------|
| 0 | Foundation & setup | Project shape, app lifecycle, auto-docs | ☑ |
| 1 | Product catalog (read) | Schemas vs models, `get_db` dependency | ☑ |
| 2 | Catalog (write) + filtering | Validation, pagination, filtering | ☑ |
| 3 | Database migrations | Schema versioning with Alembic | ☑ |
| 4 | ♻️ Refactor: dependency wiring | Constructor injection, composition root | ☐ |
| 5 | Soft deletes & SKUs | Lifecycle columns, staged migrations, constraints as guards | ☐ |

### Part B — Identity & access
| # | Phase | Core concept | Status |
|---|-------|--------------|--------|
| 6 | Users & authentication | Hashing, OAuth2 flow, JWT | ☐ |
| 7 | Authorization | `get_current_user`, roles/scopes | ☐ |

### Part C — The transactional core
| # | Phase | Core concept | Status |
|---|-------|--------------|--------|
| 8 | Cart | Relationships, per-user state | ☐ |
| 9 | **Checkout & orders** ★ | **Transactions, race conditions, isolation levels, idempotency** | ☐ |
| 10 | Query performance | N+1 & eager loading, `EXPLAIN`/indexes, connection pooling | ☐ |

### Part D — Async work & integrations
| # | Phase | Core concept | Status |
|---|-------|--------------|--------|
| 11 | Sync vs async: the event loop | `def` vs `async def`, blocking, the threadpool | ☐ |
| 12 | Background work | `BackgroundTasks` & its limits | ☐ |
| 13 | Payment integration | Outbound resilience (timeouts, retries, backoff) + inbound webhooks, signatures, idempotency (again) | ☐ |
| 13b | Product images & object storage | Presigned URLs, S3-style storage, files stay OUT of the DB and OFF your API | ☐ |

### Part E — Scaling the read path & hardening
| # | Phase | Core concept | Status |
|---|-------|--------------|--------|
| 14 | Caching | Cache-aside, Redis, TTL, **invalidation** | ☐ |
| 15 | Auth hardening | Refresh tokens, rotation, revocation (real logout) | ☐ |
| 16 | Search | Postgres full-text search & tool judgement | ☐ |
| 17 | Rate limiting | Throttling, algorithms, `429` | ☐ |

### Part F — Real-time
| # | Phase | Core concept | Status |
|---|-------|--------------|--------|
| 18 | Order status over WebSocket | WebSockets, connection management | ☐ |

### Part G — Quality, operations & delivery
| # | Phase | Core concept | Status |
|---|-------|--------------|--------|
| 19 | Testing ★ | `pytest`, fixtures, dependency overrides | ☐ |
| 20 | Errors, config & middleware | Exception handlers, settings, middleware vs DI | ☐ |
| 21 | Observability | Structured logging, correlation IDs, a taste of metrics | ☐ |
| 22 | Dockerization | Images, Compose, graceful shutdown, readiness vs liveness | ☐ |
| 23 | CI/CD | GitHub Actions: test, lint, build, gate | ☐ |
| 24 | ♻️ Refactor: the async data layer ★ | Async SQLAlchemy end-to-end, protected by the suite | ☐ |

---

## Product scope

**What MiniMart is:** an API where a customer can browse and search products, register, log in, fill a cart, check out into an order (safely, even under retries and concurrency), get a confirmation, watch order status in real time, and where a simulated payment provider confirms payment via webhook. An admin manages the catalog. The whole thing is migrated, cached, rate-limited, tested, observable, containerised, and shipped through CI.

**Deliberately out of scope** (saying no is a senior trait): real payment processing (*simulate* it), recommendations, reviews, coupons, deliverability of real email, GraphQL, microservices, Kubernetes, CQRS/event-sourcing. If you feel the urge to add one, that urge is the lesson.

**Suggested stack:** FastAPI, Pydantic v2 + `pydantic-settings`, SQLAlchemy 2.0, **PostgreSQL** (not SQLite — row locking in Phase 9 and full-text search in Phase 16 need a real DB), **Redis** (caching + rate limiting), Alembic (migrations), `pytest` + `httpx`, Docker + Compose, GitHub Actions. Add tooling — `ruff` (lint), `mypy` (types) — by the testing/CI phases.

---

# PART A — Foundations & the catalog

## Phase 0 — Foundation & setup

**Learning objective:** how a FastAPI app is structured, boots, and documents itself.

**Why it matters:** Seniors have opinions about layout *before* writing an endpoint, because structure is what keeps a codebase changeable. Your schemas *are* your documentation — FastAPI generates interactive docs from them.

**Functional requirements:**
- App boots with one command and serves over HTTP locally.
- `GET /health` returns an OK payload.
- Interactive docs render at `/docs` and `/redoc`.
- The project is organised into layers from day one (see the Architecture section at the end — adopt the domain-based structure now, even with near-empty folders).

**Acceptance criteria:**
- [x] App starts cleanly; `/docs` shows the OpenAPI UI.
- [x] `GET /health` returns `200` JSON.
- [x] Folders separate routing, models, schemas, services, and data access.

**Self-check / interview questions:**
- What does `uvicorn` do, and how does it relate to your app object?
- Where did `/docs` come from — what generated it?

---

## Phase 1 — Product catalog (read path)

**Learning objective:** the most important FastAPI habit — **three layers of data** (DB model, input schema, output schema) — plus the `yield` dependency for DB sessions.

**Why it matters (pillars 1 & 2):** Beginners merge DB model and API schema into one class and regret the coupling the first time the two shapes need to diverge. The `get_db` dependency that opens a session and closes it in a `finally` is *the* canonical example of why DI exists.

**Functional requirements:**
- Products live in the DB (SQLAlchemy model): id, name, description, price, stock quantity, category.
- `GET /products` returns a **paginated** list (choose offset vs cursor consciously).
- `GET /products/{id}` returns one product or `404`.
- JSON is shaped by an **output schema** (`response_model`), never the raw DB model.
- The DB session arrives via a dependency, not created inline.

| Method | Path | Auth | Success | Errors |
|--------|------|------|---------|--------|
| GET | `/products` | none | `200` + page | — |
| GET | `/products/{id}` | none | `200` + product | `404` |

**Acceptance criteria:**
- [x] Listing is paginated and returns page metadata.
- [x] Missing id returns `404`, not `500` or empty `200`.
- [x] DB model and output schema are distinct.
- [x] No route creates its own DB session.

**Self-check / interview questions:**
- Give a concrete scenario where merging DB model and response schema bites you.
- In `get_db`, what runs after the `yield`, and why does that guarantee matter?

---

## Phase 2 — Catalog write path + filtering

**Learning objective:** input validation, the input-vs-output schema split, and real pagination/filtering.

**Why it matters:** Validation at the edges is half of FastAPI's value — bad data is rejected with a clear `422` before touching your logic, and you didn't hand-write that check. Every real list endpoint needs filtering and pagination, or it ships an endpoint that returns 50,000 rows.

**Functional requirements:**
- `POST /products` creates from an **input schema** (no client-supplied id) → `201`.
- `PATCH /products/{id}` updates (decide partial vs full consciously).
- Invalid input (negative price, missing name) → `422` with field-level detail.
- `GET /products` supports filtering (category, price range) composed with pagination.

| Method | Path | Auth | Success | Errors |
|--------|------|------|---------|--------|
| POST | `/products` | admin (Phase 7) | `201` | `422` |
| PATCH | `/products/{id}` | admin | `200` | `404`, `422` |
| GET | `/products?category=&min_price=&max_price=` | none | `200` | `422` |

**Acceptance criteria:**
- [x] Bad body → `422` with detail you didn't hand-write.
- [x] Create returns `201`, not `200`.
- [x] Input and output schemas are different classes.
- [x] Filtering composes with pagination.

**Self-check / interview questions:**
- What fields differ between create-input and response schemas, and why?
- When does offset pagination duplicate or skip rows, and how does cursor pagination fix it?

---

## Phase 3 — Database migrations (Alembic)

**Learning objective:** version-control your database schema and evolve it safely, without dropping data.

**Why it matters:** In a real job you *never* `DROP TABLE` to add a column — you migrate. "How do you handle schema changes in production?" is a near-guaranteed interview question, and "I ran migrations with Alembic, reviewed the autogenerated diff, and made sure it was backward-compatible for zero-downtime deploys" is a senior answer. Introduce this now: Phase 5's `deleted_at` and `sku` columns are your first real schema changes (including a staged backfill on a populated table), and the users table arrives in Phase 6 right behind them — feel the pain, then solve it properly.

**Functional requirements:**
- Alembic manages the schema. From this phase on, **every** schema change goes through a migration — no manual table edits.
- Migrations are autogenerated *then reviewed and corrected* (never trusted blindly), and committed to version control.
- Both `upgrade` and `downgrade` work.

**Acceptance criteria:**
- [x] You can build the entire database from migrations alone, from empty.
- [x] A new column is added via a migration with no data loss.
- [x] `downgrade` cleanly reverses the latest migration.
- [x] Migration files are in git.

**Self-check / interview questions:**
- Why never autogenerate-and-apply without reading the migration first? What does Alembic miss?
- What makes a migration *backward-compatible*, and why does that matter for deploying without downtime? (Hint: the old code runs against the new schema for a moment.)
- What's the danger of a destructive migration (dropping/renaming a column), and how do you do it safely in stages?

---

## Phase 4 — ♻️ Refactor: dependency wiring (the composition root)

**Learning objective:** class-level dependency injection — constructor injection, provider functions, and the **composition root** — plus the discipline of refactoring working code deliberately, with a defined end state and unchanged behaviour.

**Why it matters (pillars 1 & 3):** The earlier phases taught request-level DI (`get_db`); this phase completes the picture one level down. A service that *constructs* its own repositories is coupled to their constructors (every signature change ripples through the codebase) and cannot be unit-tested without monkeypatching. Constructor injection fixes both — and it's what makes Phase 19's "test a service with fakes, no DB, no patching" possible. This is also the first ♻️ refactor phase on purpose: the blast radius is still tiny (two services), so you learn the *habit* of safe refactoring before the stakes rise. (Origin story and full mental model: `tutorials/guides/dependency-injection-wiring.md`.)

**Functional requirements:**
- Services declare their collaborators (repositories, session) as **constructor parameters**; no service constructs its own repository anywhere.
- Small **provider functions** (per domain, in `dependencies.py` or at the top of the router module) act as the composition root; they are the *only* place any repository or service is constructed.
- Routers keep declaring exactly one dependency — the service — and never see repositories.
- Behaviour is unchanged: every endpoint responds identically before and after the refactor.

**Acceptance criteria:**
- [ ] Grepping service files for `Repository(` finds nothing — services receive, never build.
- [ ] Each repository and service class is constructed in exactly **one** provider function.
- [ ] Thought experiment passes: adding a parameter to any repository's constructor would touch exactly one file.
- [ ] All endpoints verified to behave identically pre/post refactor (manual for now; the Phase 19 suite guards this permanently later).

**Self-check / interview questions:**
- FastAPI caches each dependency per request. Why is that caching a *correctness* requirement for your service-owned transaction boundary, not just an optimisation? (What would two sessions in one request do to `with db.begin()`?)
- What exactly does constructor injection buy you in Phase 19 that self-construction can't?
- When is plain inline construction the *right* call, and why isn't a DI container/auto-wiring library ever the answer in FastAPI?

---

## Phase 5 — Catalog data lifecycle: soft deletes & SKUs

**Learning objective:** columns that carry business meaning — lifecycle (`deleted_at`) and identity (`sku`) — the constraints that guard them (partial unique indexes), and the **staged, backfilling migration** that adds a required unique column to a table that already has rows.

**Why it matters (pillar 2):** "How do you delete data without destroying history?" and "what identifies a product besides your database id?" are day-one production modelling questions. Soft deletes preserve referential history (orders must survive their product being removed from the store) but tax every read query forever — choosing them means engineering for that tax, not just adding a column. And the SKU backfill is Phase 3's "staged migration" self-check answer turned into something you actually did.

**Functional requirements:**
- **Soft delete:** a nullable `deleted_at` timestamp on products (NULL = alive). `DELETE /products/{id}` sets it and returns `204`. A soft-deleted product returns `404` on fetch and disappears from lists and (later) search — deleted means *behaves deleted*. The row stays; future orders history stays intact.
- `deleted_at` is a **timestamp, not a boolean** — it must answer *when*, enabling audits and retention/purge jobs later.
- `is_active` **stays and keeps a distinct meaning** ("merchant hid it — business state, merchant-reversible") vs `deleted_at` ("lifecycle — it's gone from the store"). Two concepts, two columns; document the distinction.
- Read-path filtering (`deleted_at IS NULL`) is enforced **centrally in the repository layer** — one enforcement point, not a condition sprinkled per query.
- **SKU:** unique, required, immutable after creation. **Hybrid assignment:** the client may supply one; the *service* generates one when absent. PATCH must not change it.
- Duplicate SKU → `409`, produced by catching `IntegrityError` and **discriminating by constraint name** — with two constraints able to fire on one insert (category FK, SKU uniqueness), a blanket catch would mislabel errors.
- Uniqueness is a **partial unique index**: `UNIQUE (sku) WHERE deleted_at IS NULL` — a deleted product frees its SKU for reuse.
- The migration adding `sku` to the populated products table is **staged**: add nullable → backfill existing rows → set `NOT NULL` + add the index.

| Method | Path | Auth | Success | Errors |
|--------|------|------|---------|--------|
| DELETE | `/products/{id}` | admin (Phase 7) | `204` | `404` |
| POST | `/products` (with/without `sku`) | admin (Phase 7) | `201` | `409` duplicate sku, `422` |

**Acceptance criteria:**
- [ ] Deleting a product: `204`; then `404` on fetch, absent from lists — but the row is still in the DB with `deleted_at` set.
- [ ] `is_active` and `deleted_at` coexist with documented, distinct meanings.
- [ ] `sku` added via a staged migration (nullable → backfill → NOT NULL), no data loss, and `downgrade` works.
- [ ] POST without a `sku` gets a generated one; POST with a duplicate `sku` → `409`, and it cannot be confused with the category-`422` (constraint-name discrimination proven).
- [ ] Delete a product, then create a new one reusing its SKU → succeeds (partial index proven).
- [ ] PATCH attempting to change `sku` is rejected.

**Self-check / interview questions:**
- Why a timestamp over a boolean for soft deletes? And why keep `id` as the primary key and FK target when `sku` is unique (surrogate vs natural key)?
- Why can't a required unique column be added to a populated table in one migration step? Walk the stages and what each protects.
- What breaks if *one* repository query forgets `deleted_at IS NULL`, and what *structurally* prevents that in your codebase?
- What would a plain (non-partial) unique index on `sku` do to your soft-delete story?

---

# PART B — Identity & access

## Phase 6 — Users & authentication

**Learning objective:** authentication done properly — password hashing, the OAuth2 password flow, JWT issuance, and the statelessness tradeoff.

**Why it matters (pillar 1):** This is where beginners do dangerous things (plaintext, home-rolled crypto) and where "auth is just a dependency" gets set up. Understanding *why* JWTs are stateless — and that you therefore can't easily revoke them — is a real interview question.

**Functional requirements:**
- `POST /auth/register` creates a user; the password is **hashed** (bcrypt/argon2) before storage. Plaintext never hits the DB.
- `POST /auth/login` (OAuth2 password flow) returns a **JWT** on success.
- Wrong credentials → `401` with no hint about which part failed.
- The token encodes the user and an expiry.

| Method | Path | Auth | Success | Errors |
|--------|------|------|---------|--------|
| POST | `/auth/register` | none | `201` + user (no password) | `409` taken, `422` |
| POST | `/auth/login` | none | `200` + token | `401` |

**Acceptance criteria:**
- [ ] The users table holds hashes, never plaintext.
- [ ] Login returns a JWT decoding to the right user with an expiry.
- [ ] Register response never includes the password/hash.
- [ ] Duplicate registration → `409`, not a raw DB error.

**Self-check / interview questions:**
- Why hash *and salt* — what attack does the salt defeat?
- An account is compromised and you must log it out *now*. With stateless JWTs, what can't you easily do, and what are the options (short expiry + refresh tokens, a denylist)? You'll *build* the answer in Phase 15.

---

## Phase 7 — Authorization & protected routes

**Learning objective:** the payoff of DI — `get_current_user` as a dependency — plus role/scope-based access control.

**Why it matters (pillar 1):** Protecting a route becomes one declared dependency, and it *composes*: layer "must be admin" on top of "must be logged in" and FastAPI runs the chain. This elegance is what the whole framework is built around.

**Functional requirements:**
- `get_current_user` validates the JWT and loads the user; protected routes declare it.
- `GET /me` returns the current user.
- Admin-only actions (Phase 2 writes, Phase 5 delete) are guarded by a role check built *on top of* `get_current_user`.
- No token → `401`; valid token, wrong role → `403`.

| Method | Path | Auth | Success | Errors |
|--------|------|------|---------|--------|
| GET | `/me` | logged-in | `200` | `401` |
| POST | `/products` | admin | `201` | `401`, `403` |

**Acceptance criteria:**
- [ ] No token → `401`; non-admin on admin route → `403`.
- [ ] `current_user` is injected via `Depends`, not parsed in each route.
- [ ] The admin check is a separate dependency layered on the auth one (composition, not copy-paste).

**Self-check / interview questions:**
- Precisely, when is it `401` vs `403`?
- How does FastAPI order the resolution of chained dependencies?

---

# PART C — The transactional core

## Phase 8 — Cart

**Learning objective:** modelling relationships and per-user state; the first real service-layer muscle.

**Why it matters:** Relationships appear (user → cart → items → products) and you first feel the pull to put logic somewhere other than the route. Build the habit: routes handle HTTP, services handle rules.

**Functional requirements:**
- An authenticated user can add items, update quantities, remove items, and view their cart.
- The cart is **scoped to the current user** — never see or touch another's cart.
- Adding more than available stock is rejected (a preview; the *real* enforcement is at checkout).
- Cart contents validate against existing products.

| Method | Path | Auth | Success | Errors |
|--------|------|------|---------|--------|
| GET | `/cart` | logged-in | `200` | `401` |
| POST | `/cart/items` | logged-in | `200`/`201` | `404`, `422` |
| PATCH | `/cart/items/{id}` | logged-in | `200` | `404`, `422` |
| DELETE | `/cart/items/{id}` | logged-in | `204` | `404` |

**Acceptance criteria:**
- [ ] Two users have fully independent carts; A can never read B's.
- [ ] Cart logic lives in a service, not the route.
- [ ] Adding a nonexistent product → `404`.
- [ ] Adding a soft-deleted product → `404` (Phase 5's filtering holds here too).

**Self-check / interview questions:**
- Where exactly did you draw the route-vs-service line, and why there?
- Why can't the cart-time stock check be the final word on inventory?
- How do your services acquire their repositories, and what would it cost to change a repository's constructor? (See `tutorials/guides/dependency-injection-wiring.md`.)

---

## Phase 9 — Checkout & orders ★ the senior-maker

**Learning objective:** database transactions, the service layer for real, and the two ideas worth more than every other phase combined — **concurrency/race conditions** and **idempotency** — plus the vocabulary underneath them: **transaction isolation levels**.

**Why it matters (pillar 2):** This is the line between "knows FastAPI" and "can be trusted with production." Two customers buy the last unit at once — do you oversell? A customer's request is retried — do you double-charge? These transfer to every backend you'll ever build. Slow down here. Struggle here on purpose.

> ### 📘 Concept primer: idempotency (read this before building)
> **Definition:** an operation is *idempotent* if doing it many times has the same effect as doing it once. `GET` is naturally idempotent; `POST /orders` is naturally **not** — call it twice, get two orders. Idempotency keys make an unsafe operation safe to repeat.
>
> **The real enemy isn't the double-click — it's the unreliable network.** Picture it: the client sends "place order," your server succeeds, but the *response* is lost on the way back (dropped connection, dead zone, timeout). The client doesn't know it worked, so it retries. Without protection you've now created two orders and charged twice. The double-click is just the most visible case of a general problem: any layer between client and server (browser, mobile retry logic, load balancer) may replay a request.
>
> **The mechanism (check → store → return):**
> 1. The **client** generates a unique key (a UUID) standing for *one intended action* and sends it, usually in an `Idempotency-Key` header.
> 2. The **server**, before doing any work, looks the key up. **Not seen** → process it, store the result against the key, return it. **Seen** → skip the work entirely, return the *stored* result.
> 3. The retry therefore gets the *original* order back — same response, no second order, no second charge.
>
> **Two subtleties that signal depth:** (a) the key must be **client-generated** — only the client knows two requests are "the same intent"; (b) handle the race where two requests with the *same key* arrive simultaneously (a unique constraint on the key, or a lock). The canonical real-world reference is **Stripe's API**, which works exactly this way — worth naming in an interview.

**Functional requirements:**
- `POST /orders` (checkout) turns the user's cart into an order:
  - Total is computed **server-side** from current prices. Never trust a client-sent total.
  - Stock is decremented per item; inventory must **never** go negative.
  - The whole thing is **one transaction**: any failure rolls back *everything* — no order, no stock change, no partial state.
  - **Concurrency-safe:** two checkouts racing for the last unit → exactly one `201`, the other a clean `409`, never an oversell and never a `500`. (Use row locking — `SELECT ... FOR UPDATE` — or an atomic conditional update; understand both.)
  - **Idempotent:** accepts an `Idempotency-Key`; replaying it returns the *same* order, never a second one.
- Orders have a status (`pending → paid → shipped → delivered`), listable/fetchable by their owner.
- **Know your isolation level:** find out what level your transactions actually run at (Postgres default: `READ COMMITTED`) and observe in `psql` what one transaction can see of another's work.

| Method | Path | Auth | Success | Errors |
|--------|------|------|---------|--------|
| POST | `/orders` (+ `Idempotency-Key`) | logged-in | `201` + order | `409` out of stock, `400` empty cart, `422` |
| GET | `/orders` | logged-in | `200` | `401` |
| GET | `/orders/{id}` | owner/admin | `200` | `403`, `404` |

> ### 🔬 Build-it-wrong-first plan (the race condition)
> A race condition is invisible on a single request — it only appears under concurrency, which is exactly why it ships to production undetected. So you'll *cause* an oversell before you prevent one.
>
> **Act 1 — Build it naive (check-then-act).** Implement checkout the obvious way: read the product's stock, check `if stock >= quantity`, then decrement and create the order. No lock. This reads as perfectly correct — and it is, for one request at a time.
>
> **Act 2 — Reproduce the oversell.** Set a product's stock to 1 and fire two checkouts *concurrently* (a small script with two threads, or async tasks). Watch both pass the `if` check before either decrements — and end up with two orders and stock at `-1`. You've just oversold. **Tip:** on a fast local machine the window between read and write is tiny and may not trigger reliably, so *artificially widen it* — drop a small `sleep` between the read and the decrement to force the race every time. Understanding that races are probabilistic and timing-dependent is itself a senior insight worth stating in an interview.
>
> **Act 3 — Close the window.** Fix it two ways and understand both: **pessimistic** (`SELECT ... FOR UPDATE` locks the row so the second request waits), and **atomic conditional update** (a single `UPDATE ... SET stock = stock - q WHERE stock >= q` that lets the database arbitrate, succeeding for exactly one). Re-run Act 2's script: exactly one `201`, one `409`, stock never negative.
>
> **Act 4 — Prove it (the senior part).** In Phase 19 you turn Act 2's script into a permanent **concurrency test** that asserts no oversell. Most candidates *talk* about race conditions; you'll have a test that demonstrates you can reproduce and prevent one.

**Acceptance criteria:**
- [ ] **Act 1 done:** a naive check-then-act checkout exists.
- [ ] **Act 2 done:** you reproduced an oversell with concurrent requests (widening the window if needed) and saw stock go negative.
- [ ] Stock = 1, two simultaneous checkouts → exactly one `201`, one `409`; total sold = 1, never 2. (Phase 19 makes you *prove* this.)
- [ ] A forced mid-transaction failure leaves the DB exactly as before — no order row, no stock decrement.
- [ ] Replaying with the same `Idempotency-Key` returns the original order; the order count does not increase.
- [ ] Order total is recomputed server-side; tampering with a client-sent price has no effect.
- [ ] A user can't fetch another user's order (`403`/`404`).
- [ ] In one `psql` experiment (two terminals) you observed what `READ COMMITTED` lets a second transaction see, and you can state *why* the oversell is possible at that level.

**Self-check / interview questions:**
- Trace two racing requests through your code. *Where* is the oversell window, and how does your lock/atomic update close it?
- Optimistic vs pessimistic locking — which did you use, and when is the other better?
- Why must the idempotency key be client-generated, not server-generated?
- Name Postgres's isolation levels. At `READ COMMITTED`, what exactly did each racing transaction *see* that made the oversell possible? Would `SERIALIZABLE` have prevented it without explicit locks — and what new failure mode (serialization errors + retry loops) would that buy you?

---

## Phase 10 — Query performance: N+1, indexes & the connection pool

**Learning objective:** the three ways a correct data layer gets slow — the **N+1 query problem**, **missing indexes** (read the plan with `EXPLAIN ANALYZE`), and an exhausted **connection pool** — and how to *witness* each before fixing it.

**Why it matters:** These are the clearest tells between a junior and a senior ORM/DB user, and all three are invisible until you look beneath the ORM: at the SQL emitted, the plan Postgres chose, and the pool the session borrowed from. "This query is slow — what do you do?" and "what happens when you run out of DB connections?" are near-guaranteed interview questions, and the only durable way to learn them is to build it wrong on purpose, witness it, then fix it.

> ### 🔬 Build-it-wrong-first plan — Part 1: the N+1
> This phase is deliberately structured so the bug lives in your app before you hunt it. Do not skip Act 1 — the naive version is a *required deliverable*, not a mistake.
>
> **Act 1 — Build it naive (don't optimise).** Implement `GET /orders` the obvious, innocent way: fetch the user's orders, then loop over them and access each order's `items`. This is the code everyone writes first and it looks completely reasonable. With SQLAlchemy's default lazy-loading, touching `order.items` inside the loop quietly fires a fresh query *every iteration*.
>
> **Act 2 — Witness it (this is the act that teaches).** Turn on SQL logging (`echo=True` or log statements). Seed ~10 orders and hit the endpoint: watch the log print 1 query for the orders, then 10 more — one per order — for the items. Eleven queries for one page. Now seed 100 orders and watch it become 101. *Seeing the query count scale with your data* is what makes the lesson permanent — far more than any explanation.
>
> **Act 3 — Fix it and compare.** Rewrite the query with eager loading (`selectinload` or `joinedload`) so the items come back in a constant number of queries regardless of order count. Hit the same endpoint; watch 101 drop to 1–2. The before/after in *your own logs* is the whole lesson — and the exact story you'll tell in an interview.
>
> **Act 4 — Lock it in (the senior part).** In Phase 19 you'll write a test that **counts the queries** a request makes and asserts it stays under a threshold, so the N+1 can never silently creep back. "I assert query counts in my test suite" is a genuinely impressive thing to say, because most people don't.

**Two things to understand while you're in it (interviewers probe here):**
- **Lazy-loading is a feature, not a bug.** The ORM helpfully fetches related data only when you touch it — convenient right up until you touch it in a loop. The fix isn't "never lazy-load"; it's "load eagerly when you know you'll need the relationship across a collection."
- **`selectinload` vs `joinedload`.** Roughly: `joinedload` pulls everything in one big `JOIN` (good for one-to-one or small sets, but can balloon rows and duplicate parent data on one-to-many), while `selectinload` runs a second query with an `IN` clause (usually better for one-to-many collections like order→items). Reasoning about *that tradeoff*, not just naming the functions, is what reads as senior.

> ### 🔬 Part 2: read the plan (`EXPLAIN ANALYZE` & B-tree indexes)
> Seed a few thousand products. In `psql`, run `EXPLAIN ANALYZE` on your Phase 2 filter query (`WHERE category_id = … AND price BETWEEN …`) and read the plan: **Seq Scan** — Postgres reads every row. Add a B-tree index (via a migration — every schema change migrates) and watch the same query flip to an **Index Scan**. Then go one step further: try a **composite index** matching your commonest filter combination, and check whether Postgres actually uses it. Finally, articulate the cost: every index slows every write and takes space — which is why you don't index every column.

> ### 🔬 Part 3: exhaust the pool
> Every request borrows a DB connection from SQLAlchemy's **pool**; the pool is finite. Shrink it deliberately (`pool_size=2`, small `max_overflow`), add a temporarily slow endpoint (or a `pg_sleep` query), and fire many concurrent requests. Witness what happens: requests queue waiting for a connection, then `TimeoutError`. This is one of the most common real production incidents. Reason about sizing (pool × workers vs Postgres `max_connections`) and know the name **PgBouncer** for when many app processes multiply the problem.

**Acceptance criteria:**
- [ ] **N+1 Act 1 done:** a naive `GET /orders` exists and (temporarily) exhibits the N+1.
- [ ] **N+1 Act 2 done:** you can show the *before* — query count scaling as 1+N in the logs (demonstrate at 10 and 100 orders).
- [ ] **N+1 Act 3 done:** the *after* — a constant, small query count regardless of N.
- [ ] You can explain `selectinload` vs `joinedload` and when each wins.
- [ ] **N+1 Act 4 (in Phase 19):** a query-count test guards the endpoint against regression.
- [ ] Captured before/after `EXPLAIN ANALYZE` plans for a filtered catalog query: Seq Scan → Index Scan, with the index added via a migration.
- [ ] Reproduced pool exhaustion with a deliberately tiny pool, and you can explain the queue-then-timeout behaviour and the sizing tradeoff.

**Self-check / interview questions:**
- Why does ORM lazy-loading cause N+1 in the first place?
- When is `joinedload` (one big JOIN) worse than `selectinload` (a second `IN` query)?
- How would you *catch* an N+1 before it reaches production?
- What does `Seq Scan` in a query plan tell you, and why not simply index every column?
- A request can't get a connection from the pool — what happens, which settings decide, and how do you size a pool across multiple workers?

---

# PART D — Async work & integrations

## Phase 11 — Sync vs async: the event loop 🔬

**Learning objective:** how FastAPI actually runs your code — the **event loop**, the **threadpool**, `def` vs `async def` — and what "blocking" concretely means.

**Why it matters:** This is the single most-asked FastAPI interview topic, and most users of the framework cannot answer it. FastAPI is async-first, but this project's data layer is deliberately synchronous — and that combination is *safe*, for a reason you must be able to state precisely. One wrongly-placed blocking call inside an `async def` route freezes *every* request on the server; knowing why — and the three ways out — is the difference between using the framework and understanding it. (This phase is concepts-first; the full async conversion of the data layer is Phase 24, once the test suite exists to protect it.)

> ### 🔬 Build-it-wrong-first plan (freeze the whole server)
> **Act 1 — Build it wrong.** Add a temporary endpoint as `async def` containing a *synchronous* `time.sleep(5)` (standing in for any blocking call: a sync HTTP request, a heavy computation, a sync DB query).
>
> **Act 2 — Witness it.** While that endpoint sleeps, hit `GET /health` from another terminal: **it hangs too.** One request froze the entire server — every user, every endpoint. Now understand why: `async def` routes run *on the event loop itself*, a single thread that juggles thousands of requests by never waiting; a blocking call stops the juggler mid-juggle.
>
> **Act 3 — Fix it three ways, and understand each.** (a) Declare the route as plain `def` — FastAPI runs sync routes in a **threadpool**, so blocking is contained to one thread; (b) make the work genuinely async (`await asyncio.sleep`, an async HTTP client) so the loop keeps juggling; (c) keep `async def` but offload the blocking call explicitly (`run_in_threadpool` / `asyncio.to_thread`). Re-run Act 2 after each: `/health` stays responsive.
>
> **Act 4 — Apply it to your own app.** State precisely why every route in this project is safe today (they're `def` → threadpool → sync SQLAlchemy blocks a worker thread, never the loop), and find the ceiling that protection has (the threadpool's default ~40 threads caps concurrent in-flight requests).

**Acceptance criteria:**
- [ ] **Act 1–2 done:** reproduced the freeze — a sync sleep in an `async def` route visibly hangs `GET /health`.
- [ ] **Act 3 done:** fixed all three ways; each verified to keep `/health` responsive; you can say when each fix is the right one.
- [ ] You can state precisely why this project's `def` routes + sync SQLAlchemy don't block the loop, and name the threadpool ceiling that comes with it.
- [ ] In writing: your rules for choosing `def` vs `async def` for any new endpoint.

**Self-check / interview questions:**
- Explain the event loop in one paragraph a junior would understand.
- Why doesn't `async` make CPU-bound work faster? What *does* it make better, and under what workload?
- A teammate declares every route `async def` "for performance" while calling the sync DB — what happens under load, and why is it *worse* than plain `def`?
- Where do your Phase 9 row locks sit relative to all this — does async change what the *database* serialises?

---

## Phase 12 — Background work (order confirmation email)

**Learning objective:** `BackgroundTasks` for fire-and-forget work — and, more importantly, its limits.

**Why it matters:** The checkout response shouldn't block while an email "sends." The *senior* lesson is knowing when `BackgroundTasks` isn't enough: it runs inside your web process, so if that process dies the work is silently lost, with no retries. Being able to say *when* you'd reach for a real queue (arq, Celery, RQ + Redis) is the real learning.

**Functional requirements:**
- After a successful checkout, a confirmation email is "sent" (logged or written to a fake outbox) **without blocking** the response.
- The work is scheduled as a background task, not awaited inline.

**Acceptance criteria:**
- [ ] Checkout returns promptly; the email work happens after the response.
- [ ] You can name, in writing, two scenarios where `BackgroundTasks` loses work and a durable queue wouldn't.

**Self-check / interview questions:**
- The server crashes one millisecond after the response but before the task runs. What happens to the email? How does a durable queue change that?
- What belongs in `BackgroundTasks`, and what should move to a queue?
- What is the **transactional outbox pattern**, and which exact failure of "commit the order, then schedule the email" does it close? (Describe only — building it is out of scope.)

---

## Phase 13 — Payment integration: outbound resilience & the inbound webhook

**Learning objective:** both directions of talking to another system. **Outbound:** calling a flaky external service like an adult — explicit timeouts, retries with exponential backoff + jitter, idempotency keys *sent* (Phase 9's concept pointed outward), circuit breaking described. **Inbound:** handling a webhook — inversion of control, signature verification, and idempotency reinforced from a second angle.

**Why it matters:** Webhooks are everywhere (Stripe, GitHub, Slack), and so are outbound calls to services that hang, flap, and fail — that's half of distributed systems in practice. An outbound call with no timeout hangs your worker when the provider slows down; retries without backoff DDoS your own vendor; retries without an idempotency key double-charge your customer. Inbound, the provider calls *you*, unprompted — so you trust nothing without **verifying a signature**, you process **idempotently** (providers retry aggressively), and you return the status code that tells them whether to retry. Doing idempotency in two shapes — sending the key outbound, honouring event ids inbound — is exactly why this phase exists: the concept will stick.

**Functional requirements:**
- **Outbound:** checkout (or a payment-initiation step) makes a real `httpx` call to the simulated provider, with:
  - an **explicit timeout** — a hanging provider must not hang your request handling indefinitely;
  - **retries with exponential backoff + jitter**, on transient failures only (timeouts, `5xx`) — never on `4xx`;
  - an **`Idempotency-Key` header sent**, so *your* retries are safe on the provider's side;
  - a **circuit breaker** understood and described (not necessarily built): after N consecutive failures, stop calling and fail fast — retrying into an outage makes it worse (retry storm).
- **Inbound:** an endpoint the "provider" calls to confirm payment for an order.
- **Verify a signature** (HMAC over the payload with a shared secret) before trusting anything; reject invalid signatures.
- Process **idempotently**: the same provider event id is applied at most once, even if delivered repeatedly.
- On success, transition the order to `paid`.
- Return a status code that tells the provider to stop retrying on success, and to retry on a transient failure.

| Method | Path | Auth | Success | Errors |
|--------|------|------|---------|--------|
| POST | `/webhooks/payments` | signature | `200` | `400`/`401` bad signature |

**Acceptance criteria:**
- [ ] The outbound call has an explicit timeout; with the provider deliberately hanging, your request fails fast instead of hanging.
- [ ] Transient provider failures (timeout/`5xx`) are retried with backoff; a `4xx` is not retried.
- [ ] The outbound request carries an idempotency key.
- [ ] You can describe a circuit breaker and explain a retry storm.
- [ ] An invalid/missing signature is rejected; the order is *not* touched.
- [ ] Replaying the same event applies it once; the order doesn't flip twice or double-anything.
- [ ] A valid event moves the order to `paid`.
- [ ] Your status codes distinguish "handled, stop retrying" from "transient, please retry."

**Self-check / interview questions:**
- Why must *every* outbound call have a timeout — what exactly happens to your server, thread by thread, when the provider slows down and you have none?
- Why never retry a `400`? Why add jitter to backoff?
- Why verify the signature — what attack does an unverified webhook endpoint invite?
- Why *must* webhook processing be idempotent, given how providers behave?
- What do you return on a duplicate event, and why does that choice matter to the provider?

---

## Phase 13b — Product images & object storage (presigned URLs)

**Learning objective:** handling user-uploaded files the way production systems do — an S3-compatible object store (MinIO locally), **presigned URLs** so bytes flow client ↔ storage *directly*, and a database that stores **pointers, never blobs**.

**Why it matters:** "Where do uploaded files go?" is a question every backend eventually answers, and the naive answers are all wrong in instructive ways: bytes in the DB bloat backups and drag megabytes through the connection pool; proxying uploads through your API burns request workers on dumb byte-shuffling (your Phase 11 threadpool ceiling, spent on file transfer). The senior pattern inverts it: your API *signs permission slips* (presigned URLs — HMAC signatures, the same cryptographic idea you verified inbound in Phase 13) and the client talks to storage directly. Your server never touches a single image byte. This is how Stripe file uploads, GitHub release assets, and every mobile app's avatar flow actually work.

**Functional requirements:**
- **MinIO** joins Compose as the S3-compatible store (the API reaches it by service name; credentials from env via settings — no secrets in code).
- Products gain an image pointer (e.g. `image_key`/`image_url`) via an **Alembic migration** — the store's key, never the file, in Postgres.
- **Upload flow (admin-only, Phase 7 guards it):**
  1. Client asks your API for an upload slot for a product.
  2. API validates (product exists, content type is an allowed image type, size cap declared) and returns a **presigned PUT URL** + the object key it chose (client never picks keys — path traversal by naming is not a thing you allow).
  3. Client PUTs the file **directly to MinIO** with that URL. Your API never receives the bytes.
  4. Client confirms; API verifies the object actually exists in the store (never trust "I uploaded it"), then persists the key on the product.
- **Read path:** product responses expose a usable image URL. Decide consciously: public-read bucket (simple, fine for product images) vs presigned GET (private data — know when each is right).
- Presigned URLs **expire** (short TTL) and constrain what they permit (method, key, content type).
- **Orphan story:** an upload that's never confirmed leaves a dangling object. Have an answer — lifecycle/TTL rule on the bucket, or a cleanup job — described is enough, built is better.

| Method | Path | Auth | Success | Errors |
|--------|------|------|---------|--------|
| POST | `/products/{id}/image/presign` | admin | `200` + URL & key | `401`, `403`, `404`, `422` bad content type |
| PUT | *(the presigned URL — straight to MinIO)* | signature in URL | `200` from store | store rejects bad/expired signature |
| POST | `/products/{id}/image/confirm` | admin | `200` + product | `404`, `409`/`400` object not found in store |

**Acceptance criteria:**
- [ ] `docker compose up` includes MinIO; the API reaches it by service name, credentials from env.
- [ ] The image pointer column arrived via a reviewed Alembic migration.
- [ ] Full flow works: presign → direct PUT → confirm → product read returns a URL that actually renders the image.
- [ ] The API demonstrably never handles file bytes (no upload endpoint accepts a body with the file; the PUT goes to MinIO's port, not yours).
- [ ] A disallowed content type is refused at presign time; an expired/tampered presigned URL is refused by the store.
- [ ] Confirming an upload that never happened → clean `4xx`, product untouched.
- [ ] Non-admin attempts → `401`/`403` (Phase 7 composition reused).
- [ ] You can explain your orphaned-object answer.

**Self-check / interview questions:**
- Why not store the image in Postgres as `BYTEA`? Name the *three* costs (pool, backups, cache/memory), not just "it's bad practice."
- Why not accept the upload in your API and forward it to storage? What exactly does that spend, in Phase 11 terms (threadpool workers, event loop)?
- How does a presigned URL actually work — what's signed, by whom, verified by whom? Relate it to the webhook signature you verified in Phase 13.
- Why must the *server* choose the object key, and why must confirm *check the store* instead of trusting the client?
- When is a public-read bucket wrong, and what replaces it? What changes when a CDN sits in front?

---

# PART E — Scaling the read path & hardening

## Phase 14 — Caching (Redis)

**Learning objective:** the **cache-aside** pattern with Redis, TTLs, graceful degradation, and the genuinely hard part — **cache invalidation**.

**Why it matters:** Caching is a top-tier senior topic, and invalidation is famously one of the two hard problems in computing. The product catalog is the perfect target: easy to cache, but the moment an admin edits a product you face the real question — how do you stop serving stale data? You'll learn it the only way it sticks: cache without invalidation, *serve stale data on purpose*, then fix it.

> ### 🔬 Build-it-wrong-first plan (stale cache)
> Invalidation is abstract until you've watched your own API confidently return wrong data. So the staleness bug is a required step.
>
> **Act 1 — Cache the reads (no invalidation yet).** Add cache-aside to product reads: check Redis → on miss, hit the DB and populate → return. Set a TTL. Confirm it works by hitting a product twice and observing the second read served from cache (fewer DB queries / faster).
>
> **Act 2 — Witness the staleness.** As admin, update a product's price. Now read it again — and watch your API cheerfully return the *old* price from the cache. This is the bug that causes real incidents ("why is the site showing the wrong price?"), and seeing your own code do it is the lesson.
>
> **Act 3 — Invalidate on write.** Make product update/delete invalidate (or refresh) the affected cache entries, so the next read reflects the change. Re-run Act 2: the new price appears immediately. Now reason about the edges — what about the *list* cache, not just the detail entry? (Invalidating related keys is where it gets genuinely hard.) Remember Phase 5: a *soft delete* is a write too — the cached detail entry must die with the product.
>
> **Act 4 — Harden (the senior part).** Stop Redis entirely and hit the API — it must **degrade gracefully** to the DB, not `500`. Then reason about a **cache stampede**: when a hot key expires and 1,000 requests all miss at once and hammer the DB. Note the mitigations (a short lock, staggered TTLs, background refresh). You don't have to fully build stampede protection, but being able to describe it is the interview payoff.

**Acceptance criteria:**
- [ ] **Act 1 done:** repeated reads are served from cache (observable: fewer DB queries / faster responses).
- [ ] **Act 2 done:** you reproduced stale data — an updated product still read the old value from cache before invalidation existed.
- [ ] **Act 3 done:** after an admin update, the next read reflects the change — no stale data (detail *and* list, and soft-deleted products vanish from cache too).
- [ ] **Act 4 done:** with Redis down, the API still serves correct data from the DB, and you can describe a stampede mitigation.

**Self-check / interview questions:**
- Cache-aside vs write-through — the tradeoffs?
- What's a cache stampede (thundering herd), and how would you mitigate it?
- Why is invalidation hard — what goes wrong if you get the TTL or the invalidation trigger wrong?

---

## Phase 15 — Auth hardening: refresh tokens & real logout

**Learning objective:** complete the JWT story you started in Phase 6 — short-lived access tokens, a **refresh-token flow with rotation**, and **revocation via a Redis denylist**. Statelessness was a tradeoff; this is where you buy back the part you gave up.

**Why it matters (pillar 1):** "So how *do* you log out a stateless JWT?" is the single most reliable auth follow-up in interviews. Phase 6 taught you to *say* the answer (short expiry + refresh tokens + a denylist); this phase makes you *build* it — and it reuses the Redis you stood up in Phase 14, so the marginal cost is low. It also forces a real security judgement call: what does your API do when Redis — now part of your auth path — is down?

**Functional requirements:**
- Access tokens become **short-lived** (e.g. ~15 minutes). `POST /auth/login` now returns an access token *and* a longer-lived **refresh token**.
- `POST /auth/refresh` exchanges a valid refresh token for a new access token — no password re-entry.
- **Rotation:** each refresh use issues a *new* refresh token and invalidates the old one; presenting an already-used refresh token is rejected (and, ideally, revokes the whole family — describe this even if you don't build it).
- `POST /auth/logout` revokes the current tokens via a **Redis denylist**, with each entry's TTL equal to the token's *remaining* lifetime (so the denylist cleans itself up).
- The auth dependency (`get_current_user`) checks the denylist; a revoked-but-unexpired access token is rejected.
- **Decide and implement the Redis-down failure mode deliberately** — fail open (accept tokens unchecked) vs fail closed (reject all auth) — and be able to defend the choice.

| Method | Path | Auth | Success | Errors |
|--------|------|------|---------|--------|
| POST | `/auth/refresh` | refresh token | `200` + new tokens | `401` invalid/reused |
| POST | `/auth/logout` | logged-in | `204` | `401` |

**Acceptance criteria:**
- [ ] An expired access token → `401`; the refresh flow issues a new one without re-login.
- [ ] After logout, the *still-unexpired* access token is rejected — you demonstrably revoked a stateless JWT.
- [ ] Refresh-token reuse is detected and rejected (rotation works).
- [ ] Denylist entries expire with their tokens (no unbounded growth — prove it with a TTL check in `redis-cli`).
- [ ] Redis down: your chosen failure mode happens *on purpose*, and you can defend it.

**Self-check / interview questions:**
- What did statelessness buy you in Phase 6, and exactly how much of it did this phase spend to get revocation back?
- Why rotate refresh tokens — what attack does detecting *reuse* of an old one reveal?
- Fail open vs fail closed when the denylist store is down — argue both sides, then commit.
- Why does every denylist entry need a TTL?

---

## Phase 16 — Search (Postgres full-text search)

**Learning objective:** real full-text search in Postgres — and the *judgement* of when the database is enough versus when you'd reach for a dedicated engine.

**Why it matters:** The SQL isn't the senior signal; the judgement is. "I used Postgres FTS because it was right for this scale, and here's exactly when I'd graduate to Elasticsearch/OpenSearch" is the kind of tool-fit reasoning interviewers screen for.

**Functional requirements:**
- Search products by name/description using Postgres **full-text search** (`tsvector`/`tsquery`), **not** `LIKE '%term%'`.
- Rank results by relevance.
- Add a GIN index (via a migration — reinforcing Phase 3) so search stays fast as the catalog grows.
- Soft-deleted products (Phase 5) never appear in results.

| Method | Path | Auth | Success |
|--------|------|------|---------|
| GET | `/products/search?q=` | none | `200` + ranked results |

**Acceptance criteria:**
- [ ] Search returns relevant, ranked results via FTS, not naive `LIKE`.
- [ ] A GIN index backs the search, added through a migration.
- [ ] A soft-deleted product does not appear in search results.

**Self-check / interview questions:**
- Why is `LIKE '%term%'` slow and non-scalable?
- When would you move from Postgres FTS to Elasticsearch/OpenSearch — what does the dedicated engine buy you, and what new problem (a second copy of your data that can go stale) does it create?
- What does a GIN index actually do?

---

## Phase 17 — Rate limiting

**Learning objective:** protect endpoints from abuse, learn the common throttling algorithms, and return the right thing when a client exceeds the limit.

**Why it matters:** A real production concern (brute-force on login, abuse of checkout) and a frequent interview topic. It also reuses the Redis you stood up in Phase 14, so the marginal cost is low and the payoff high.

**Functional requirements:**
- Limit requests per client (by IP and/or user) on sensitive endpoints (login, checkout, webhook).
- On exceeding the limit, return `429` with a `Retry-After` header.
- Track counters in **Redis** so the limit holds across multiple app processes.

**Acceptance criteria:**
- [ ] Exceeding the limit returns `429` with `Retry-After`.
- [ ] The limit resets after its window.
- [ ] The limit holds across more than one app process (shared Redis state).

**Self-check / interview questions:**
- Fixed window vs sliding window vs token bucket — the tradeoffs?
- Why must the counter live in Redis rather than in-process memory?
- What headers should a well-behaved rate-limited API return?

---

# PART F — Real-time

## Phase 18 — Order status over WebSocket

**Learning objective:** WebSockets — persistent, bidirectional connections — and connection-lifecycle management.

**Why it matters:** The real-time feature you wanted, placed late on purpose: genuinely useful here (push order status as it changes) but a smaller slice of "senior" than the data layer. The real skill is managing connections — authenticating the socket and cleaning up on disconnect. (Note: WebSocket handlers are natively `async` — your Phase 11 event-loop understanding is load-bearing here.)

**Functional requirements:**
- A client opens a WebSocket and subscribes to updates for an order it owns (authenticate the connection).
- A status change (e.g. `paid → shipped`) is pushed to the connected client in real time.
- Disconnects are handled cleanly — no leaks, no crash when sending to a gone client.

**Acceptance criteria:**
- [ ] Changing an order's status server-side pushes the update to the client without polling.
- [ ] A client can only subscribe to its own orders.
- [ ] A dropped connection is handled without unhandled server errors.

**Self-check / interview questions:**
- How is authenticating a WebSocket different from a normal request — where does the token go?
- With 10,000 clients across multiple processes, why does an in-memory dict of connections stop working, and what's the usual fix (a pub/sub backplane — and note you already have Redis)?

---

# PART G — Quality, operations & delivery

## Phase 19 — Testing ★ pillar three

**Learning objective:** `pytest`, fixtures, the `httpx` test client, and the killer feature — **dependency overrides**.

**Why it matters (pillar 3):** This is where DI's value becomes undeniable and where "senior" is most clearly earned. FastAPI lets you override *any* dependency in tests — swap the real DB for a test DB, swap `get_current_user` for a fake user — via `app.dependency_overrides`. A suite you trust is what lets you refactor fearlessly — and Phase 24 will put that claim to the test, literally.

**Functional requirements:**
- Tests cover behaviour, not just `200`s: validation failures, auth failures, the `403`/`404`/`409` paths.
- The DB dependency is overridden with a test database.
- `get_current_user` is overridden to test protected routes without logging in each time.
- At least one service is unit-tested **with fake repositories, no DB at all** — the Phase 4 constructor-injection payoff, collected.
- **Targeted tests for the hard phases:** a concurrency test proving no oversell (Phase 9); an idempotency-replay test (Phases 9 & 13); a **query-count assertion** catching N+1 (Phase 10); a webhook signature-rejection test (Phase 13); a soft-delete behaviour test and a SKU-reuse-after-delete test (Phase 5); a revoked-token test (Phase 15); a cache-behaviour test (Phase 14); a rate-limit test (Phase 17).

**Acceptance criteria:**
- [ ] The full suite runs with one command, independent of any real/dev database.
- [ ] At least one test overrides `get_current_user`; at least one overrides the DB.
- [ ] At least one service-level unit test uses fake repositories and never touches Postgres.
- [ ] The concurrency test proves exactly one of two racing checkouts wins.
- [ ] A test fails if an N+1 regression reappears (query count asserted).
- [ ] Error paths (`401`/`403`/`404`/`409`/`422`/`429`) are covered, not only success.

**Self-check / interview questions:**
- Why is `app.dependency_overrides` only possible *because* you used DI instead of a global session?
- What makes a test flaky, and how do you keep the concurrency test deterministic enough to trust?
- Which tests were only possible because services receive their repositories (Phase 4) instead of building them?

---

## Phase 20 — Errors, configuration & middleware

**Learning objective:** consistent error handling, environment-based config, and the middleware-vs-dependency judgement call.

**Why it matters:** These are the habits that separate a hobby project from a deployable one. The middleware nuance is a senior tell: middleware runs on *every* request and can't easily reach route-specific dependency context, so it's for truly global concerns. Reaching for middleware where a dependency belongs is a classic beginner mistake.

**Functional requirements:**
- Custom exception handlers produce a **consistent error shape** across the API; raw stack traces never leak to clients. (Domain exceptions raised by services are mapped to status codes here — see the Architecture section. This also retires the per-route `try/except` blocks you've been accumulating since Phase 2, and unifies the two `detail` shapes your `422`s have carried since then.)
- Status codes are deliberate and consistent throughout.
- Config (DB URL, JWT secret, Redis URL, token expiry) comes from env vars via `pydantic-settings`. **No secrets in code.**
- At least one middleware for a global concern: inject a **request-ID** into every request/response (used by Phase 21). Configure CORS here too.

**Acceptance criteria:**
- [ ] Every error response shares one JSON shape; no stack trace reaches a client.
- [ ] Grepping for the JWT secret / DB password finds nothing — all from env.
- [ ] Every response carries a middleware-added request-ID.
- [ ] You can give one concrete example each of "belongs in middleware" vs "belongs in a dependency."

**Self-check / interview questions:**
- Why can't middleware easily use the result of `get_current_user`? What's structurally different about where it sits?
- Why is a request-ID worth the trouble during a production incident?

---

## Phase 21 — Observability: structured logging (+ a taste of metrics)

**Learning objective:** structured (JSON) logs stamped with a correlation ID, so a single request can be traced end-to-end across layers — plus a first, small contact with **metrics** so all three observability pillars are things you've touched, not just named.

**Why it matters:** This is the skill that separates people who can debug production from people who can't. Logging, metrics, and tracing are the three pillars of observability; you'll do logging properly here, stand up a minimal metrics signal, and at least be able to *speak* to tracing.

**Functional requirements:**
- Emit **JSON** logs (machine-parseable), not ad-hoc print/plain-text.
- Every log line for a request carries the **request-ID** from Phase 20's middleware, so all logs for one request can be filtered together.
- Log key events with context (checkout placed, payment confirmed, errors) at appropriate levels.
- Never log secrets or sensitive PII (passwords, tokens, full card data).
- **Metrics taste:** expose request counts and latency (per route/status) — a simple middleware feeding a `/metrics` endpoint, or `prometheus-fastapi-instrumentator`. Know what p50/p95/p99 mean and read yours.

**Acceptance criteria:**
- [ ] All logs for one request can be retrieved by filtering on its request-ID, across layers.
- [ ] Logs are valid JSON.
- [ ] No secret or sensitive PII appears in any log line.
- [ ] Request counts and latency percentiles are observable somewhere (endpoint or logged summary), and you can explain p95 vs average.

**Self-check / interview questions:**
- Why structured logs over plain text — what does it enable?
- What are the three pillars of observability, and what does each answer?
- What should never appear in logs, and why?
- Why do seniors quote p95/p99 latency rather than the average — what does an average hide?

---

## Phase 22 — Dockerization (+ graceful shutdown & readiness)

**Learning objective:** containerise the app and orchestrate it with its dependencies, so "works on my machine" stops being a caveat — and understand what happens to **in-flight requests** when the container is told to die.

**Why it matters:** Packaging forces total clarity about what your app depends on and how it runs. Compose gives a one-command app + Postgres + Redis environment, which also makes the Phase 9 row-locking and Phase 14 caching behave like production. And every deploy anywhere ends with your process receiving `SIGTERM` mid-request — knowing the termination sequence, and the difference between "the process is up" and "it's actually ready for traffic," is the bridge between having containers and operating them.

**Functional requirements:**
- A `Dockerfile` builds the app (slim/multi-stage image; avoid running as root where you can).
- A `docker-compose.yml` brings up app + **PostgreSQL** + **Redis** with one command.
- The database (and Redis, if you want) persist across restarts via named volumes.
- Config is passed via environment (wired to Phase 20 settings); **no secrets baked into the image**.
- The app reaches Postgres/Redis by their Compose service names; the API is reachable from the host.
- **Graceful shutdown:** understand the `SIGTERM` → grace period → `SIGKILL` sequence, and verify what uvicorn does with an in-flight request on `docker stop`.
- **Liveness vs readiness:** split the health story — *liveness* = "the process is alive" (must NOT check the DB, or a DB blip restart-loops your app); *readiness* = "actually able to serve" (DB reachable, migrations applied). Wire Compose's `healthcheck` to readiness.

**Acceptance criteria:**
- [ ] `docker compose up` starts app + DB + Redis; the API is reachable from the host.
- [ ] Restarting the stack preserves data (volumes work).
- [ ] Inspecting the image reveals no hard-coded secrets.
- [ ] The app connects to Postgres/Redis by service name, not `localhost`.
- [ ] The image is slim / multi-stage, not multi-GB.
- [ ] Experiment done: `docker stop` during a slow in-flight request — you observed whether it completed, and you can narrate the SIGTERM sequence either way.
- [ ] Health endpoints distinguish liveness from readiness, and the Compose healthcheck uses readiness.

**Self-check / interview questions:**
- Why does Dockerfile layer ordering matter for build speed — what comes before what?
- Inside the Compose network, why is the DB host its service name and not `localhost`? What *is* `localhost` from the app container's view?
- Why keep secrets out of the image even for a learning project?
- What's the difference between `SIGTERM` and `SIGKILL` for your in-flight requests?
- Why must the liveness check *not* include the database, while readiness must?

---

## Phase 23 — CI/CD with GitHub Actions

**Learning objective:** an automated pipeline that runs on every push — tests, linting, type-checking, and a Docker build — gating merges so broken code can't reach `main`.

**Why it matters:** This is real-world delivery, and it makes "it works on my machine" structurally impossible. Being able to say "every PR runs the suite against a Postgres service container, plus `ruff` and `mypy`, and won't merge red" is a concrete, senior-sounding thing you'll have actually done.

**Functional requirements:**
- A workflow triggered on push/PR that: runs the **test suite** (with **Postgres and Redis as service containers** so integration tests are real), runs **linting** (`ruff`) and **type-checking** (`mypy`), and **builds the Docker image**.
- Failing tests/lint/types fail the check and block merge.
- Dependencies are cached for speed.

**Acceptance criteria:**
- [ ] Pushing a branch triggers the pipeline.
- [ ] A deliberately failing test turns the check red and blocks merge.
- [ ] The pipeline spins up Postgres (and Redis) as services to run integration tests — not mocks.
- [ ] The Docker image builds in CI.

**Self-check / interview questions:**
- Why run tests in CI when you already run them locally?
- What's the difference between CI and CD, and which does this pipeline do?
- Why use a real DB service container in CI instead of mocking the database?

---

## Phase 24 — ♻️ Refactor: the async data layer ★ the capstone

**Learning objective:** convert the entire I/O path to async — `create_async_engine`, `AsyncSession`, an async `get_db`, async repositories/services/routes — **protected by the test suite**. The deliverable isn't async; it's the *demonstration* that a suite you trust lets you rewrite your data layer without fear.

**Why it matters (pillar 3, collected):** This is the promise of the whole curriculum made concrete. You built sync-first on purpose (simpler mental model, identical architecture); now you pay down that decision as a *safe, verified* migration — the exact kind of infrastructure change seniors are trusted with. Every phase converges here: the Phase 11 event-loop model tells you *why* and *what* changes; the Phase 19 suite tells you *whether you broke anything*; the Phase 9 guarantees (no oversell, idempotency) must survive the rewrite, and your tests prove they do. "I migrated a working data layer from sync to async behind a green test suite, and my concurrency tests never flinched" is a genuinely senior interview story.

**Functional requirements:**
- Async engine + `AsyncSession`; `get_db` becomes an async yield dependency; repositories, services, and routes go `async` end-to-end — no sync DB calls left on request paths.
- Behaviour is identical: same endpoints, same status codes, same error shapes. The CI pipeline stays green.
- The Phase 9 guarantees still hold and the suite still proves them: the concurrency test (no oversell — row locks behave the same; the *database* still arbitrates) and the idempotency-replay test pass unchanged in what they assert.
- Keep a short migration log: every failure the suite caught during conversion (this list is the evidence for the capstone's thesis).

**Acceptance criteria:**
- [ ] The whole request path is async; no sync SQLAlchemy session remains on any route.
- [ ] The full suite is green before and after; behaviour verified identical.
- [ ] Concurrency and idempotency tests pass — the guarantees survived the rewrite.
- [ ] Your migration log names at least the classic async traps you hit or avoided (lazy-loading's implicit IO under async, session-per-task discipline, what `MissingGreenlet` means).
- [ ] You can honestly answer: did it get *faster*? (Measure or reason — for which workload would async win, and did yours?)

**Self-check / interview questions:**
- What breaks when you touch a lazy relationship in async SQLAlchemy, and why? (What is "implicit IO," and why does async make it explicit?)
- Which parts of the conversion would have been terrifying without the suite — and which bugs did the suite actually catch? (You kept the log.)
- Did async make your app faster? Defend your answer with the Phase 11 model: what workload benefits, and where was your bottleneck actually?
- Now that you've run both: when would you *start* a project async-first, and when sync-first?

---

# Architecture & project structure (reference)

You asked for the *best* way to organise this, not someone's preference. The honest truth: **there is no single official "FastAPI way" for large-app structure** — the docs are deliberately light. But there's strong professional convergence on a set of principles and a layout, and these are what make you defensible in an interview.

## The one principle everything derives from

**Separation of concerns, organised as layers with a dependency rule:** each layer has one responsibility, and dependencies point *inward* — toward business logic, never outward toward the web framework. The test for "where does this code go?" is: *would it still be true if I swapped FastAPI for a CLI, or Postgres for MongoDB?* Business rules survive both swaps (centre); HTTP parsing dies with the framework (edge); queries die with the database (bottom).

## The four layers — and the rule that governs them

> **The router decides nothing. The service decides *what* should happen. The repository *does* it.**

- **Router / API layer** — owns HTTP and nothing else. Parses the request, declares dependencies (`current_user`, `db`), calls *one* service function, maps the result or a domain exception to a status code and `response_model`. If a route is more than a few lines, logic has leaked in. It should read like a table of contents.
- **Service layer** — the business logic and the part that makes you employable. The use case ("checkout") lives here: the rules, the orchestration of multiple steps, and — critically — **the transaction boundary**. Services are testable without any HTTP context.
- **Repository (data-access) layer** — encapsulates *how* you talk to the DB ("get product by id", "decrement stock atomically with a row lock", "find order by idempotency key"). Returns models/data; knows nothing about HTTP. Your `SELECT ... FOR UPDATE` lives here.
- **Models vs schemas** — SQLAlchemy DB models and Pydantic request/response schemas are separate things sitting beside the layers.

## Your checkout, traced through the layers (memorise this as a story)

1. **Router** (`POST /orders`): pulls `current_user` and `db` from `Depends`, reads the idempotency key, calls `order_service.checkout(...)`. Catches `OutOfStockError → 409`, `EmptyCartError → 400`; serialises the order. That's *all*.
2. **Service** (`checkout(...)`): opens the transaction; checks the idempotency key (repo); loads the cart (repo); reserves stock atomically per line (repo, with the row lock); computes the total **server-side**; creates the order (repo); commits; schedules the confirmation email; on any failure rolls back and raises a **domain** exception. Note: it raises `OutOfStockError`, **not** `HTTPException(409)` — it doesn't know what HTTP is. The router owns that translation.
3. **Repository**: each DB operation — `get_cart_for_update`, `decrement_stock_atomic`, `create_order`, `find_by_idempotency_key`. No business decisions.

That separation — services raise domain errors, the router/handler maps them to status codes — is a small thing that signals real maturity, because most tutorials sloppily raise `HTTPException` from deep in the logic.

## The transaction-boundary question (interview gold)

**Where does the transaction live? The service layer — never the repository.** A transaction is a *business* unit of work ("a checkout fully happens or fully doesn't") spanning multiple repository calls that must commit together. If each repo method committed on its own, you couldn't make them atomic. So the repository runs queries; the *service* decides commit vs rollback.

## Class wiring: who builds what (the composition root)

Services *declare* their collaborators (constructor parameters); they never construct them. Small **provider functions** — chained with `Depends`, one per domain in `dependencies.py` — are the only place repositories and services get built. FastAPI resolves the graph per request and caches each dependency, so every repository in a request shares one `Session` — which is precisely what makes the service-owned transaction boundary real. Full treatment: `tutorials/guides/dependency-injection-wiring.md`, built in Phase 4.

## The repository pattern: hold the nuance

SQLAlchemy's `Session` is *already* a Unit of Work and the ORM is *already* a data-access abstraction, so a thin repository can be ceremony for a tiny app. The mature position: a repository earns its keep when you want to unit-test services without a DB, keep complex queries out of business logic, or preserve the option to swap data stores. **Build it here** (the practice is the point), but be able to say "for a tiny CRUD service I'd skip it as over-engineering." That *judgement* is what's being screened.

## Layout: domain-based beats layer-based

**Layer-based** (folders by role: `routers/`, `services/`, …) is intuitive but smears one feature across five folders and gets unwieldy. **Domain-based** (folders by feature, each owning its router/service/repository/schemas/models) keeps a feature's code together and scales — it's the community-standard structure (popularised by the *fastapi-best-practices* repo, modelled on Netflix's open-source Dispatch app). For your store:

```
src/
├── products/   router.py  service.py  repository.py  schemas.py  models.py  exceptions.py
├── auth/        router.py  service.py  repository.py  schemas.py  models.py  dependencies.py
├── cart/        router.py  service.py  repository.py  schemas.py  models.py
├── orders/      router.py  service.py  repository.py  schemas.py  models.py  exceptions.py
├── payments/    router.py  service.py  repository.py  schemas.py  (webhook lives here)
├── core/        config.py (pydantic-settings)  security.py  database.py  cache.py (redis)
├── common/      dependencies.py (get_db)  pagination.py  exceptions.py (base)  logging.py
└── main.py      (creates the app, includes each domain's router)
alembic/         (migrations)
tests/
.github/workflows/   (CI/CD)
Dockerfile  docker-compose.yml
```

## Architecture questions you should be able to answer in an interview

- Where does business logic go, and why not in the route or the repository?
- Where is the transaction boundary, and why there?
- Why separate DB models from API schemas — give a concrete failure of merging them.
- Do you always need a repository layer? When would you skip it?
- How do your services acquire their repositories, and why does that choice decide whether they're unit-testable?
- Layer-based vs domain-based structure — which did you choose and why?
- How do you keep services testable without spinning up the whole app?

---

# Resources worth your time (skip the rest)

Most of what you'll find Googling is preference dressed up as gospel. These four are the signal:

1. **FastAPI "Bigger Applications" docs** — the closest thing to an official word on `APIRouter` and wiring. Light but authoritative. (fastapi.tiangolo.com → Tutorial → Bigger Applications)
2. **zhanymkanov/fastapi-best-practices** (GitHub) — the de-facto community standard; opinionated, written from real startup experience. The domain-based structure above comes from here.
3. **Netflix/dispatch** (GitHub) — a real, large, open-source FastAPI app. Reading production code beats any tutorial; this is where the structure was proven.
4. **"Architecture Patterns with Python"** by Percival & Gregory — *the* deep, framework-agnostic treatment of Repository, Service Layer, and Unit of Work in Python. Free online at **cosmicpython.com**. If you read one thing for genuine interview depth, read this; it turns "I copied a folder structure" into "I understand why."

**A deliberate caution:** be skeptical of the "Production-Ready FastAPI 2026" blog genre. The architecture they describe is broadly sound and good for folder ideas, but they routinely raise `HTTPException` from inside services and take other shortcuts that contradict the clean separation above — useful for layout, not for the discipline.

---

# Definition of "senior" for this project

You've genuinely levelled up — not just finished — when all of these are true:

- [ ] You reach for a **dependency** by reflex and can explain when middleware would be wrong instead.
- [ ] You keep **DB model, input schema, and output schema** separate without thinking.
- [ ] You can **draw the checkout transaction** and point to the exact oversell window and how you closed it.
- [ ] You can **explain idempotency** to someone using your own checkout *and* payment integration as two examples — in both directions (keys you honour, keys you send).
- [ ] You can **show an N+1 and its fix** from your own logs, and a **Seq Scan → Index Scan** from your own query plans.
- [ ] You can **explain the event loop** and defend every `def` vs `async def` choice in your codebase.
- [ ] You can **reason about caching invalidation** and name a stampede mitigation.
- [ ] Your **test suite lets you refactor fearlessly** — and you *proved* it by rewriting the data layer async behind it (Phase 24).
- [ ] `docker compose up` hands someone your whole stack, and **CI goes green** on every push.
- [ ] You know what you **deliberately left out** and can justify each omission.

---

# Final reflection prompts

When the dashboard is full, write a paragraph on each. If you can, you've internalised it; if you can't, that's the phase to revisit.

1. Which phase changed how you think about backends the most, and why?
2. Where did you over-engineer, and where did you under-engineer? How would you re-scope from scratch?
3. Explain dependency injection to a beginner in three sentences, using something you built.
4. Your store suddenly gets 100× the traffic. Which part breaks first, what's the first thing you'd change, and which phase here gave you the tools to diagnose it? (You don't need to *build* it — the diagnostic instinct is the senior skill.)
5. You refactored the whole data layer in Phase 24. What did the test suite catch that manual testing never would have? What does that tell you about the real cost of skipping tests on a "small" project?
