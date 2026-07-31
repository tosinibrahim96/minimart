# How to protect routes with `get_current_user` and a layered admin guard

> One line: turn the Phase 6 JWT into working access control — one declared dependency per protected route, with the admin check *composed* on top, never copy-pasted.

**Phase:** 07 — Authorization & protected routes
**Concept it taught:** the payoff of dependency injection — `get_current_user` as a dependency, role checks layered via sub-dependencies, exception handlers as the app-level mapping point, the 401-vs-403 boundary — plus an unplanned heavyweight: SQLAlchemy autobegin and where the transaction boundary *really* lives once dependencies read before services write.
**Why it matters:** "Protecting a route is one declared dependency, and checks compose" is what FastAPI is built around; 401 vs 403, "where do roles get enforced," and "who owns the transaction" are near-guaranteed interview probes.

## Prerequisites

- Phase 6 complete: register/login issuing a JWT with `sub: "user:{id}"`, 15-min expiry; `is_admin` boolean (defaults false).
- Phase 4's composition root: providers in `app/auth/dependencies.py`, services receive collaborators.
- Read: `tutorials/guides/authentication-from-zero.md` (written at this phase's start — see Step 0).

## Steps

### 0) Reading time + the decisions record

No book chapters assigned (spec reading map) — primary docs + companion reads:

1. FastAPI tutorial — *Get Current User*, *Simple OAuth2 with Password and Bearer*.
2. FastAPI tutorial — *Sub-dependencies*, *Dependencies in path operation decorators*.
3. RFC 6750 §3 — the 401-vs-403 taxonomy: `invalid_token` → 401, `insufficient_scope` → 403.
4. OWASP Authorization Cheat Sheet — deny by default; enforce server-side on every request.
5. fastapi-best-practices repo → Dependencies sections.

**Spin-off guide:** the reading surfaced "OAuth2 is authorization, so why is my login OAuth2? Which spec owns `WWW-Authenticate`?" — answered across five specs in **`tutorials/guides/authentication-from-zero.md`** (the HTTP-auth → Bearer → OAuth2 → JWT → OIDC layer cake; MiniMart = first-party authentication borrowing OAuth2's wire shapes; the password grant is removed in OAuth 2.1 but reasonable for a first-party API).

**Decisions made (with the why):**

| Decision | Choice | Why (and the alternative) |
|---|---|---|
| Trust token claims vs load user from DB | **Load the user from the DB on every request** | A JWT proves *identity at mint time*; `is_admin` can change within the token's 15-min lifetime (demoted admin, deleted user). Cost: one PK SELECT per authenticated request. Interview counterpoint: roles-in-token with staleness bounded by short expiry is a latency-vs-freshness trade some high-scale systems make. |
| Bootstrap admin | **Env-driven script (`ADMIN_EMAIL`/`ADMIN_PASSWORD` via settings), idempotent** — Django `createsuperuser` pattern | Reproducible everywhere (fresh DBs, CI, teammates), nothing in git. Rejected: psql flip (manual, per-environment, unaudited — and prod DBs shouldn't take ad-hoc writes); interactive prompts (first draft — lost the reproducibility rationale). |
| Promotion endpoint | **Not building it** | "Not all admins should mint admins" is the slippery slope from the flat `is_admin` boolean into RBAC (roles tables, grants, audit). MiniMart stays flat on purpose; the senior answer is naming the graduation trigger. |
| Where `get_current_user` lives | `app/auth/dependencies.py` | It's a dependency (the HTTP edge's DI arm), not business logic. Products importing the admin guard from auth = first cross-domain dependency; direction is right (auth is what everything depends on). |
| How dependency failures become 401s | **Domain exceptions + `@app.exception_handler`** (over raising `HTTPException` in the dependency) | Keeps "dependencies raise domain errors, one place maps them" symmetric with services; it's Phase 20's mechanism early. Tradeoff owned: action-at-a-distance, but explicitly registered in `main.py`. |
| Expired vs invalid in the 401 | **Distinguished via message/`error_description`** | Clients need to know when to refresh (Phase 15). RFC 6750's registered code is `invalid_token` for both; "expired" travels in the description. Not an oracle — the caller knows their own token's state. |
| **Transaction style after the autobegin collision** | **Option A: commit-as-you-go** — no `with db.begin()` anywhere; services end write methods with explicit `self.db.commit()`; `get_db`'s `close()` is the rollback safety net | The guard's per-request SELECT autobegins a transaction on the shared session, so every service `begin()` was doomed to `InvalidRequestError`. Option B (keep `begin()`; every pre-service reader must `rollback()` its read-transaction) preserves the scope-tied block but sprinkles hygiene at the edge. Option C (transaction-per-request in `get_db`) was re-rejected — invisible boundary. A is the documented SQLAlchemy 2.0 style; the boundary is still service-owned, spelled `commit()` at the end instead of `begin()` at the start. |

### 1) The dependency chain: extractor → parser → user loader

Three small dependencies in `app/auth/dependencies.py`, composed by `Depends`, cached per request:

```
oauth2_scheme (OAuth2PasswordBearer)   → raw token from Authorization: Bearer (401 if absent)
  └─ parse_bearer_token                → jwt.decode (signature+expiry) → TokenPayload (shape)
       └─ get_current_user             → strict "user:{id}" sub parse → DB load → UserRead
            └─ CurrentUserDep          → what routes declare
```

- `tokenUrl="auth/login"` is OpenAPI metadata for Swagger's Authorize button — the class never calls the endpoint.
- `algorithms=[...]` is a **whitelist** — defeats the `alg: none` attack.
- `TokenPayload.model_validate` guards *shape*: PyJWT verifies signature and expiry, not claims presence — a signed token with no `sub` passes decode.
- Domain exceptions (`InvalidTokenError` ← `ExpiredTokenError`, `InvalidSubjectError`) are plain `Exception` subclasses translated from library errors via qualified imports (`except jwt.InvalidTokenError: raise InvalidTokenError(...)`).
- **One** handler in `main.py` maps all three to 401 + `WWW-Authenticate: Bearer error="invalid_token", error_description="..."` — Starlette walks `type(exc).__mro__`, so the base-class registration catches every subclass, and `str(exc)` carries each site's message.
- `GET /me` = one declared dependency, one-line body.

### 2) Admin guard: composition, not copy-paste

`get_admin_user` depends on `CurrentUserDep`, checks `is_admin`, raises `ForbiddenError` → a second handler maps it to **403** (no `WWW-Authenticate` needed — RFC 6750 makes `insufficient_scope` there a MAY). Exposed as `AdminUserDep`. Per-request caching makes the layering free: token decoded once, user loaded once, even with both dependencies in the tree. Naming lesson repeated from Phase 6: first name was `IsAdminDep` — reads boolean, holds a user. Names must not lie about types.

### 3) Retro-guarding the product writes — and the autobegin detonation

`POST /products`, `PATCH /products/{id}`, `DELETE /products/{id}` each declare `admin_user: AdminUserDep`. Public GETs stay open. (Alternative spelling for pure gatekeeping: `dependencies=[Depends(get_admin_user)]` in the decorator — signals "guard, not input.")

**The landmine (predicted in Phase 6, hit here — twice).** SQLAlchemy 2.0 sessions are **autobegin**: the first DB touch (SELECT, flush, even `refresh`) silently opens a transaction that stays open until `commit()`/`rollback()`/`close()`. `with db.begin():` demands a clean session and raises `InvalidRequestError: A transaction is already begun on this Session` otherwise — the library refusing to guess whose work belongs in the block. Three-line proof (container REPL):

```python
db = SessionLocal()
db.in_transaction()                 # False
db.execute(select(User).limit(1))   # a mere read...
db.in_transaction()                 # True — autobegin
db.begin()                          # 💥 InvalidRequestError
```

It fired first in the bootstrap script (both branches: `create_account`'s post-commit `refresh` left a transaction open; the exists-branch's `get_user_by_email` did the same), and would have fired on every guarded write endpoint — `get_current_user`'s SELECT precedes every service `begin()` on the same request-cached session. Phase 4's one-session-per-request, which *makes* the service-owned boundary possible, is also what delivers the collision. Resolution: **Option A** (decisions table) plus two enabling fixes:

- **Kill the `refresh` wart**: build the output schema *inside* the transaction — after flush (PostgreSQL's `RETURNING` has already populated id/timestamps/defaults on the ORM object), before commit — then return the plain pydantic object. One less SELECT, and the session ends clean. Placing `model_validate` after the commit without refresh would *work* but silently reopen a transaction via `expire_on_commit` — the same bug in a different hat.
- **The commit map** (the boundary rule, re-spelled): every service write method ends with `self.db.commit()` as its last happy-path act — `create_account`, `update_user_is_admin`, `create_product`, `update_product`, `delete_product`. Repositories still never commit. Pure reads (login, lists, `get_current_user`) never commit — their autobegun read-transactions get absorbed into the next write's commit or rolled back by `get_db`'s `close()`.
- **The retry trap**: `create_product`'s SKU-collision retry must `self.db.rollback()` before `continue`. Under `with begin()` the block exit rolled back automatically; under commit-as-you-go, *handled-and-keep-going* error paths must clear the aborted transaction themselves or the retry dies with `PendingRollbackError`. Paths that raise don't need it — cleanup happens downstream.

### 4) The bootstrap script (`app/auth/scripts/create_admin.py`)

Env-driven (`settings.admin_email`/`admin_password`, wired `.env` → compose `${...}` → settings; optional fields so the API boots without them, script validates presence and exits 1 with a clear message). **The script is its own composition root** — no request, no `Depends`; it wires session → repository → service by hand, which only works because services don't import FastAPI (the "second entry point into an unchanged kitchen" lesson). Three idempotent states, all verified live: missing → create + promote; exists-and-admin → no-op, exit 0; exists-not-admin → promote. The exists check rides on catching `UserAlreadyExistsError` from the create attempt — no check-then-act race. `sys.exit` codes throughout; the password is never printed.

## Run & verify

All verified 2026-07-31, gates clean (`ruff check app/ && mypy app/`):

| Check | Result |
|---|---|
| Bootstrap run 1 / run 2 | admin ensured / "already a registered admin", exit 0 both times; DB shows `is_admin = true` |
| `POST /products` — no token / non-admin / admin | `401` / `403` / **`201`** (the landmine's grave) |
| `PATCH /products/{id}` — same trio | `401` / `403` / `200` with updated field |
| `DELETE /products/{id}` — same trio | `401` / `403` / `204`; subsequent GET → `404` (soft delete intact through the refactor) |
| `GET /me` — valid / garbage token | `200` / `401` |
| Token failure matrix (11 rows, step 1) | 10× `401` with RFC 6750 `WWW-Authenticate`, 1× `200` |

Admin token for manual testing: log in with the `.env` credentials; adversarial tokens: mint in-container with the real secret (recipe in this file's history / Phase 19 fixture-to-be).

## Troubleshooting (real issues we hit)

- **Every bad token 500'd despite route-level `try/except` for exactly those exceptions** → dependency exceptions can never reach a route body: FastAPI resolves dependencies *first*, then calls the body with the results — the `except` blocks wrapped a plain return of an already-computed value (catching a delivery-truck crash while unboxing the delivered package). Fix: app-level `@app.exception_handler` (or raise `HTTPException` inside the dependency — it's the HTTP edge).
- **`NameError: name 'InvalidSubjectError' is not defined` → 500** → raised an exception class never defined/imported. `ruff` (F821) and `mypy` had it flagged — they weren't run before review. **Gate rule: `ruff check app/ && mypy app/` before asking for review, every time** (it was red three separate times this phase; the third was a live outage — a half-done rename, `repository.find` → `get_user_by_id`, missed the call site and 500'd every authenticated request).
- **`sub: "order:1"` logged in as user 1 (200!)** → `split(":")[1]` ignores the prefix — the namespace check existed in the token but not in the code; fail-open. Fix: validate both halves, fail closed. (Requires a signed token to exploit — but Phase 15's second token type is exactly what this check must reject.)
- **`sub: "42"` → `IndexError` → 500** → indexed `[1]` without a length check.
- **Valid token, deleted user → 500** → the ghost-user case — the very scenario DB-loading was chosen for — raised an exception the router didn't catch. Fix: raise the token-domain exception the handler maps.
- **`expires_in` passed to `TokenResponse(...)` but missing from responses** → Pydantic v2 defaults to `extra='ignore'`: unknown constructor kwargs are silently dropped. Declare the field on the schema. (The pydantic mypy plugin would flag this call.)
- **Domain exceptions subclassing `PyJWTError`** → re-couples what they exist to decouple; the `import ... as AuthInvalidTokenError` aliasing dance was the smell. Fix: plain `Exception` subclasses + qualified library references (`jwt.InvalidTokenError`).
- **`error`/`error_description` as standalone HTTP headers** → RFC 6750 puts them *inside* the `WWW-Authenticate` value; and `expired_token` isn't a registered code — use `invalid_token` + description.
- **`except X as e: raise X(msg) from e` ritual** → catching only to re-raise the same class is dead weight. Catch only to translate or handle.
- **Bootstrap script printed "User has been updated to admin" but the DB said `is_admin = false`** → the promote UPDATE ran on an autobegun transaction nobody committed; `with Session(engine)` closing = implicit **rollback**. Silent data loss, *caused by* breaking the transaction-boundary rule (the script orchestrated a business operation via raw repository calls, so no one owned the commit). flush ≠ commit, part two.
- **`InvalidRequestError: A transaction is already begun on this Session`** → autobegin (see Step 3): some earlier session touch (guard SELECT, `refresh`, script read) opened a transaction; `with begin()` refuses to join. Systemic fix chosen: commit-as-you-go. Related trap: after a *handled* `IntegrityError` where you keep using the session (retry loops), `rollback()` first or the next statement raises `PendingRollbackError`.
- **Raw traceback instead of the script's "Error creating admin user" message** → an exception raised *inside* an `except` handler is not caught by sibling `except` clauses of the same `try` — it propagates.
- **basedpyright: "Match statements require Python 3.10 or newer"** → editor-only false positive: Docker-first means no host venv, so the language server fell back to macOS system Python (3.9.6) and judged 3.12 code by 3.9 rules. Fix: pin `pythonVersion = "3.12"` under `[tool.basedpyright]` in `pyproject.toml`, or `uv sync` a host `.venv` purely for editor intelligence. Container `ruff`+`mypy` remain the gates of record.

## Concepts that confused me (and the plain-English answer)

- **"Does `OAuth2PasswordBearer(tokenUrl=...)` call the login endpoint?"** → No. At request time it only reads the `Authorization` header (401 if missing). `tokenUrl` is OpenAPI metadata so *Swagger UI in the browser* knows where to POST the Authorize form. Wrong value breaks only `/docs`.
- **"How does ONE handler catch three exception types?"** → Starlette walks the escaping exception's `__mro__` (class ancestry) for a registered handler — base-class registration catches all subclasses. Designing exceptions as a small hierarchy = one mapping point.
- **"Dependency results are cached — the best-practices example"** → per-request dict keyed by the dependency *function*; a function appearing twice in the tree runs once. The point: compose small single-purpose dependencies freely — shared sub-dependencies cost nothing. Phase 4's one-session-per-request is the same mechanism.
- **"What is autobegin? Why did `with begin()` explode?"** → A 2.0 session opens a transaction on *first touch* and leaves it open until commit/rollback/close; `begin()` is a promise of a *fresh* tab and refuses if one's already open with items on it — whose are they? The error is the library forcing an explicit boundary decision.
- **"Does login's `_authenticate` SELECT leave a dangling transaction?"** → Yes, and it's fine: open transactions are only hazardous meeting an explicit `begin()` (none remain under Option A). Reads end via `get_db` close → rollback of nothing. Caveat filed for Phase 10: *long-lived* idle-in-transaction is a real production smell (`idle_in_transaction_session_timeout`, `pg_stat_activity`); ours lives milliseconds. And the day login writes (`last_login_at`), it joins the commit map — the classification is "does it persist," not "is it called login."
- **"`user_read` is assigned inside `try` — how is it visible at the function's end?"** → Python has function scope, not block scope: `try`/`with`/`if`/`for` don't create scopes (only `def`/`class`/lambdas/comprehensions do). The real question is "did the assignment line *run* on this path" — every path that skips it also raises, so the `return` is never reached unassigned. That invariant, not scoping, is what future edits must preserve.
- **"Where exactly does `model_validate` go?"** → After flush, before commit, inside the method's transactional span. At flush, PostgreSQL's `RETURNING` already populated server-generated fields on the ORM object; `model_validate` copies them into a plain object that `expire_on_commit` can't touch. After commit without refresh = silent re-SELECT + reopened transaction.
- **"How do I test paths past `jwt.decode`?"** → Mint tokens in-container with the real secret via `settings` — expired = negative minutes, missing claims = encode without them, wrong prefix = any `sub`. Not a bypass: only the key holder can mint, and you're the key holder.
- **"Is there an autofix for mypy, like `ruff --fix`?"** → No — mypy is diagnosis-only, by design: most type errors have several valid fixes (`return None` vs change the annotation vs redesign), and only you know which states your intent. Ruff autofixes exist because those errors have exactly one correct output. Nearby tools: IDE "add return type" quick-fixes, `mypy --install-types` for stubs, and annotation generators (`autotyping`, `MonkeyType`) for migrating big untyped codebases. Annotations here are hand-written on purpose — they're design statements.

## Interview talking points

- "I load the user from the DB on every authenticated request rather than trusting role claims — a JWT proves identity at mint time; authorization state can change within its lifetime. Roles-in-token with short expiry is the latency trade I can name."
- "Dependency exceptions can't be caught in route bodies — dependencies resolve first — so token failures map to 401 in one app-level handler keyed on my domain exception base class via the MRO walk; the admin guard is a second dependency composed on the first, and 403 means 'authenticated but insufficient' per RFC 6750."
- "My auth dependency's SELECT autobegan a transaction on the request-scoped session, and my service's explicit `begin()` refused to join it. I chose commit-as-you-go — the service still owns the boundary, spelled as an explicit commit at the end — and learned the retry-path rollback trap the hard way."
- "My admin bootstrap is an idempotent env-driven script that reuses the registration service verbatim — possible only because the business logic has zero web-framework imports. Its first version silently lost the promotion to a rollback-on-close, which is exactly why the transaction boundary must have an owner."
