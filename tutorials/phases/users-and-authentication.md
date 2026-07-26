# How to Build Users & Authentication: Hashing, the OAuth2 Password Flow, and JWTs

> **Status: IN PROGRESS — covers reading (step 0), the users table (step 1), and register (step 2), all verified; login (step 3) pending.**

> Add real users to MiniMart: registration with properly hashed passwords, login via the
> OAuth2 password flow, and a signed JWT that makes authentication stateless.

**Phase:** 6 — Users & authentication
**Concept it taught:** Password hashing done consciously (Argon2id, parameters chosen from
OWASP, not copied from a tutorial), the OAuth2 password grant as a *first-party* flow, and
the statelessness tradeoff of JWTs — what a signature buys you, and what revocation costs.
**Why it matters:** This is the phase where beginners do dangerous things (plaintext,
home-rolled crypto, unmaintained libraries). It also sets up "auth is just a dependency"
for Phase 7, and plants the tradeoff (you can't easily revoke a stateless token) that
Phase 15 exists to pay back.

## Prerequisites

- Phases 0–5 complete (the stack runs in Compose; Alembic owns the schema; the
  constraint-name-discrimination pattern from Phase 5 exists to be reused).
- Reading done **before building** (see step 0) — the whole point is that the security
  decisions below were made from primary sources, not from a tutorial's defaults.

## Steps

### 0) Reading time — and the decisions it produced

**Read:** the OWASP Password Storage Cheat Sheet (the stable gate from the spec's reading
map), plus companion reads: Dropbox's ["How Dropbox securely stores your passwords"](https://dropbox.tech/security/how-dropbox-securely-stores-your-passwords)
and its HN thread. Practical primary doc for the build: FastAPI's Security tutorial
(the OAuth2 password-flow chapters).

The reading produced real decisions and killed several misconceptions. Recording both —
the misconceptions are the interview gold.

**Hashing vs encryption (and Dropbox's pepper).** They differ on one axis: can you get
the original back? Encryption is a locked safe — two-way, reversible with a key. Hashing
is a fingerprint — one-way, no key, information genuinely destroyed. Passwords get
*hashed* because login never needs the original back (the user brings it; you only
compare fingerprints), and because an encrypted password table implies a key somewhere
that reverses every password. Dropbox's scheme is `AES256(bcrypt(SHA512(pw)), pepper)` —
they *encrypt* with the global pepper instead of hashing it in, and the reason is
**rotation**: if the pepper were hash input, replacing a leaked pepper would need every
user's plaintext again (only available at their next login); as an encryption layer, they
can decrypt and re-encrypt every row offline, tonight, no users involved. Reversibility —
the thing that makes encryption wrong for the password itself — is exactly what makes it
right for the pepper layer.

**The OWASP Argon2 parameter table, decoded.** The knobs: `m` = memory in KiB
(`m=19456` = 19 MiB per hash), `t` = passes over that memory, `p` = parallelism.
Memory-hardness is the point — GPU crackers have thousands of cores but scarce fast
memory per core, so forcing ~19–46 MiB per guess is what makes massive parallelism
uneconomical. The five parameter rows are *roughly equal cost*, trading memory against
iterations — a menu for what your server can afford, not a ranking. The
"Do not use with Argon2i" warnings on the `t=1`/`t=2` rows exist because Argon2 is a
family: Argon2**d** (memory access depends on the secret — GPU-hostile but leaks via
cache-timing side channels), Argon2**i** (access pattern independent — side-channel-safe,
but published attacks compute it in *less* memory than configured when passes < 3),
Argon2**id** (hybrid, the recommended default). The warning applies only to the `i`
variant; we're using `id`, so the headline `m=19 MiB, t=2, p=1` row is fine.

**Library landscape (2026) — the cargo-cult trap.** `passlib`, which most FastAPI
tutorials still recommend, is unmaintained (last release 2020) and broke against
bcrypt ≥ 4.1. Current choices: use the `bcrypt` library directly (if bcrypt), or
**`pwdlib`** for Argon2 (maintained by the FastAPI Users author; wraps `argon2-cffi`;
its hash-format-detection layer enables the verify-old-hash-then-rehash migration
pattern). Similar story on the JWT side: older tutorials say `python-jose`; check what
FastAPI's own docs use now before committing.

**OAuth2, corrected.** Two misconceptions died in the reading:
1. OAuth2 is an ***authorization*** (delegation) framework, not authentication —
   "login with Google" is **OpenID Connect**, an authentication layer on top of OAuth2.
2. The third party is optional. FastAPI's `/token` endpoint implements the OAuth2
   **password grant** — a first-party flow where our own client sends
   username + password and gets an access token. It's genuinely OAuth2 because we follow
   its rules: form-encoded (`application/x-www-form-urlencoded`) `username`/`password`
   fields (the RFC mandates this — hence the login endpoint deliberately does *not* take
   JSON like the rest of the API), the `{"access_token": ..., "token_type": "bearer"}`
   response shape, `Authorization: Bearer <token>` on requests, and `401` +
   `WWW-Authenticate` (that header is RFC 6750). OAuth 2.1 deprecates the password grant
   *for third-party apps*; first-party is fine, and knowing the caveat is a senior signal.

**Where JWT fits:** OAuth2 doesn't specify the token format — it could be an opaque
string looked up per request. A JWT is a *signed, self-contained* claims package: the
server verifies the signature and reads who the token belongs to with **no lookup**.
Anyone can base64-decode a JWT (decode ≠ verify — the payload is readable by design);
the signature is the security. That "no lookup" is statelessness, and its price — no
easy revocation — is this phase's central tradeoff.

**Kerckhoffs's principle (why the form-encoded endpoint "leaking" our mechanism is
fine).** The mechanism was never secret: `WWW-Authenticate: Bearer` announces the scheme,
the JWT header is readable, `/docs` publishes the whole flow. Kerckhoffs (1883): a system
must be secure even if everything about it except the *key* is public. Our security lives
in the Argon2 cost and the signing key — knowing we use them speeds up nothing. Obscurity
can garnish defense-in-depth; the moment a design relies on it, the design is broken.

**Deliberately deferred (and why):**
- **Logout & refresh tokens → Phase 15.** A logout endpoint on pure stateless JWTs is
  theater ("please delete your copy" — the token stays valid until expiry). Real
  revocation needs a Redis denylist (Redis arrives in Phase 14). This phase's job is to
  *feel* the tradeoff and be able to explain the fix cold: short expiry bounds the damage
  window, refresh tokens make short expiry livable, a denylist buys true revocation back.
  Design nudge adopted: don't wall off a second token type when choosing claims.
- **Rate-limited login → Phase 17** (the spec already names login as a target). This
  phase's related defense is the **uniform `401`** — never revealing whether username or
  password was wrong defeats user enumeration, the recon step before brute force.

**Decisions record:**

| Decision | Choice | Why |
|---|---|---|
| Hash algorithm | **Argon2id** | Greenfield system — OWASP/current consensus default; bcrypt is the "existing deployment" answer (migrated via rehash-on-login) |
| Hashing library | **pwdlib** (wraps `argon2-cffi`) | passlib is unmaintained/broken; pwdlib is maintained and its format detection enables future rehash migration |
| Parameters | **pwdlib `PasswordHash.recommended()`** → argon2-cffi defaults: Argon2id, 64 MiB, t=3, p=4 | This *is* the RFC 9106 first-recommended set, above OWASP's 19 MiB minimum — a default chosen knowingly, not blindly. Accepted cost: memory-hardness is per-concurrent-hash, so sync routes × ~40 threadpool threads × 64 MiB ≈ 2.5 GB worst case — a second reason login gets rate-limited in Phase 17, and why OWASP's smaller rows exist for constrained servers |
| JWT library | **PyJWT** | What FastAPI's docs now use; `python-jose` is unmaintained (CVEs in 2024) — outdated-tutorial trap dodged, same as passlib |
| `sub` claim | **`user:{id}`** — DB id, prefixed | Id over email: immutable (emails change; `sub` must be stable), no PII in a publicly-decodable payload (decode ≠ verify), and PK lookup is the cheapest `get_current_user` query — Phase 5's surrogate-key lesson again. Prefix namespaces the *subject* against future non-user token audiences (FastAPI docs advice); it is NOT the access-vs-refresh distinction — that's a separate `type` claim in Phase 15 (`sub` = who it's about, same user in both). Gotcha: RFC 7519 requires `sub` be a string and PyJWT ≥ 2.10 enforces it on decode — the prefix satisfies that for free; a bare int id would fail |
| Password policy | **min 8, max 128, no composition rules** (Pydantic input schema) | NIST SP 800-63B: length is the guess-space factor Argon2's per-guess cost multiplies; composition rules add predictability, not entropy (`P@ssw0rd1`), and NIST dropped them. The *max* is a security control too: hashing is deliberately expensive, so unbounded input is a DoS lever (Django 2013: 1 MB passwords burned seconds of CPU each; fix was a 4096-byte cap). Edge-only by necessity — the DB stores the hash, so plaintext rules structurally can't be DB constraints (contrast the ₦50 CHECK) |
| Other claims & expiry | `exp` (validated automatically by PyJWT on decode); **15 minutes** | Short expiry is the damage bound for a stateless token — exactly the window Phase 15's refresh tokens make livable. Use timezone-aware UTC (`datetime.now(timezone.utc)`) — `utcnow()` is deprecated in 3.12 and naive datetimes make expiry drift by your UTC offset |

### 1) The users table

**Where the user model lives: `app/auth/`, not `app/users/`.** A domain is named for a
business capability, not a table — and MiniMart's only user-facing capability is
authentication (register, login, `/me`, later refresh/logout). A `users/` domain would own
one model and zero endpoints forever: speculative structure. Netflix's Dispatch — the
production app this layout is modelled on — makes the same call (`auth/models.py` holds
`DispatchUser`). The split becomes right when a real user-management surface (profiles,
admin CRUD, preferences) accumulates; extracting it then is a mechanical refactor.

**The model we landed on** (`app/auth/models.py`):

```python
class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        Index(
            "uq_users_email",
            text("lower(email)"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_admin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
```

**Decisions in that shape (each one survived an argument):**

- **`password_hash`, not `password`.** A convention, not a standard — and the industry is
  honestly split (Rails: `password_digest`, chosen deliberately; Devise: `encrypted_password`;
  fastapi-users and FastAPI's tutorial: `hashed_password`; Django: plain `password`, hash
  inside, for twenty years). The argument is free clarity: `user.password == submitted` is
  the classic bug that *silently never matches* against a hash column; `user.password_hash ==
  submitted` is visibly absurd. Name the column for what's in it.
- **One role flag (`is_admin`), not `is_admin` + `is_superuser`.** First draft had both —
  cargo-culted from fastapi-users' base model. Two booleans encode four states, two of them
  meaningless, for an app whose spec only ever has customer vs admin. One representation per
  concept. (Graduate to a `role` enum or role tables when a third role actually exists.)
- **No `deleted_at` / `is_active` — deferred consciously.** First draft copied products'
  lifecycle wholesale. On a *users* table these columns aren't inert: if a user can be
  deactivated, then login and `get_current_user` must check the flag — a lifecycle column
  auth doesn't enforce looks like a guard and guards nothing. The imagined feature ("admin
  locks a user out") is one migration + two checks when it's real, and Phase 15's denylist
  does the part a DB flag can't (killing already-issued tokens instantly).
- **Email is a case-insensitive identifier, enforced in two layers.** RFC 5321 technically
  allows a case-sensitive local part; no real provider distinguishes, and phone keyboards
  auto-capitalize — case-sensitive emails yield "wrong credentials" mysteries and duplicate
  accounts. Layer 1: lowercase at the edge, one place, before store and lookup (what Devise
  and every auth provider do). Layer 2: the DB enforces it regardless of write path (Phase 5's
  lesson) via a **functional unique index** — `UNIQUE ... (lower(email))` — chosen over
  Postgres's `citext` type because the behaviour is written where you can read it (explicit
  over magic); `citext` is the alternative to name in an interview. Consequence: original
  capitalization is not preserved; for an email nobody has ever missed it.
- **How a functional index works:** an index is a sorted structure of *values* beside the
  table, and the indexed thing can be any expression — a bare column is just the simplest
  case. Postgres computes `lower(email)` at write time and files *that*; `UNIQUE` applies to
  what's filed, so `Foo@x.com` and `foo@x.com` collide. **Query-side rule:** only a query
  using the *same expression* (`WHERE lower(email) = …`) uses the index — the repository's
  email lookups must match. (This is a Phase 10 concept met early — the assigned reading,
  use-the-index-luke.com, covers exactly this in *The Where Clause* → case-insensitive search.)
- **No index on `is_admin`.** Two independent reasons. Selectivity: a boolean splits the
  table in ~half, and past a few percent of the table the planner prefers a Seq Scan and
  ignores the index — you'd pay the write tax for nothing. App reality: no query ever filters
  `WHERE is_admin` — the admin check reads the flag on a row already fetched by PK from the
  JWT. Index for queries you run, not queries you imagine. *When it would be right:* rare
  value + real query → partial index (`Index("ix_users_admins", "id",
  postgresql_where=text("is_admin"))`) holding only the handful of admin rows.
- **Single-step migration, no staging.** Unlike the SKU work, this is a *new, empty* table —
  staged migrations exist to protect populated tables. Knowing when the ritual applies is
  part of the ritual.

**The migration** (autogenerated, then read): columns/defaults carried over faithfully; PK
named by the convention (`op.f('pk_users')`); the line worth reading twice was the
expression index — `op.create_index('uq_users_email', 'users',
[sa.literal_column('lower(email)')], unique=True)` — which modern Alembic detects
correctly (older versions silently dropped expression indexes from the diff). Note
`onupdate=func.now()` is ORM-level, not DDL: raw-SQL UPDATEs won't touch `updated_at`
(known tradeoff, consistent with products).

**Verify:** `alembic upgrade head`, then a downgrade → upgrade cycle. Then prove the index
in psql — insert a user, insert again with different casing:

```
ERROR:  duplicate key value violates unique constraint "uq_users_email"
DETAIL:  Key (lower(email::text))=(admin@example.com) already exists.
```

Two things in that output: the DETAIL shows the *computed* value collided (the index never
saw the original casing), and the error **names the constraint** — the exact string the
register service will discriminate on for its `409`, same pattern as the SKU. Clean up psql
test rows afterwards: a row with plaintext in `password_hash` can never log in (pwdlib
can't parse it as a hash) and contradicts the column's name. (Aside: inserting
`is_admin=true` via raw SQL is one legitimate answer to Phase 7's bootstrap-admin problem —
done for real, with a properly generated hash.)

### 2) Register — the auth domain slice

The full domain shape, wired like products: `router.py` (maps `UserAlreadyExistsError → 409`,
decides nothing else) → `service.py` (owns the transaction, hashes, raises domain errors) →
`repository.py` (2.0 `select()` style; email lookups use `func.lower(User.email) == email.lower()`
so they hit the functional index — the query must repeat the index's expression) →
providers in `dependencies.py` as the composition root.

**The persistence-shape schema (the step's big lesson).** Two broken drafts preceded it:

1. *Pass the API input schema to the repo* — `User(**UserCreate.model_dump())` crashes with
   `TypeError: 'password' is an invalid keyword argument for User`. It works for products
   only because `ProductCreate`'s fields coincidentally match the model's. Auth is the first
   place input schema and model **deliberately diverge** (client sends `password`, DB stores
   `password_hash`) — Phase 1's "when does merging shapes bite?" answered by our own code.
   A first draft patched this by *mutating the input schema* (`data.password = hash`) —
   stuffing a hash into a field named `password`, the exact naming lie the column rename
   exists to prevent.
2. *Fix by inheritance* — `class UserCreateSave(UserCreate)` still carries `password`
   (inheritance = parent's fields *plus more*; we needed `password` *replaced by*
   `password_hash`). The two schemas are siblings describing different **stages** of the
   data, not parent and child.

The landed pattern — a standalone persistence schema whose contract is "exactly the model's
constructor kwargs":

```python
class UserCreateSave(BaseModel):
    """Persistence shape: exactly the User model's constructor kwargs.
    The plaintext password never enters this class."""
    email: str          # plain str: validation/normalization already happened at the edge
    password_hash: str
```

The service maps API shape → persistence shape (the mapping *is* the hashing step), the
repo's `User(**data.model_dump())` is safe *by design*, and the plaintext password's
lifetime shrinks to the inside of `create_account` — it structurally cannot reach the
repository. Rule extracted: **a repo may accept a schema only if that schema's contract is
the model's kwargs.** With many shared fields, map with explicit construction at the
boundary — not `model_dump(exclude=...)` dict surgery, which fails at runtime instead of
in mypy when a field is renamed.

**The transaction boundary, and the roads not taken.** `with self.db.begin():` commits on
clean exit, rolls back on any exception — exactly one of the two, on every exit path. The
alternatives each teach why it wins: *manual try/commit/except/rollback* is the same
semantics attached to discipline instead of scope (an early return skips the commit; a
forgotten rollback poisons the pooled connection for the next request); *commit inside
repository methods* makes multi-step units of work impossible to compose (Phase 9's
checkout is five repo calls that must be atomic together); *commit-per-request in `get_db`
teardown* (a real, named pattern) makes the boundary invisible and — worse — commits
**after** the response is formed, so a failed commit can follow a `201` the client already
received. Service-owned `begin()` puts the boundary in the layer that makes the business
decision, visibly, before the status code is chosen.

**flush vs commit (what "in the DB" means).** `flush()` sends and executes the INSERT on
the server *inside the open transaction* — proof: the unique constraint fires at flush
(that's where `IntegrityError` comes from). But the row is invisible to other transactions
and evaporates on rollback; COMMIT makes it permanent and public. Layering: `add()` =
photocopy in the session → `flush()` = executed on the DB, transaction-private → `COMMIT` =
durable and visible. (Two-terminal psql demo of this is Phase 9's isolation experiment in
miniature.)

**`expire_on_commit` and the post-commit `refresh`.** Sessions default to
`expire_on_commit=True`: COMMIT stamps every loaded object "possibly outdated" (other
transactions can now touch the master rows). Touching any attribute of an expired object
fires **one** SELECT reloading the whole row; `self.db.refresh(user)` is that same SELECT
made explicit at a chosen moment. Inside the transaction the object was already complete —
flush + Postgres RETURNING populate the PK *and* server defaults — so the refresh loads
nothing new; it only clears the stale stamp. Products *must* do it this way (its service
returns the ORM model; serialization happens post-commit in the router). Auth builds
`UserRead` itself, so it could instead `model_validate(user)` *inside* the block, pre-
expiry, and skip the SELECT. Decision: keep `refresh` — one PK SELECT per registration is
nothing, it matches products, and the explicit line beats an implicit reload inside
Pydantic's serializer. Rejected: `expire_on_commit=False` (global invisible policy change).

**No pre-check — the constraint is the guard.** First draft did check-then-act (`SELECT`
by email, then insert): two concurrent registrations both pass the check and the loser
becomes an uncaught `IntegrityError` → 500 — a miniature of Phase 9's oversell window. The
landed version drops the pre-check entirely and catches `IntegrityError`, discriminating
by constraint name (`uq_users_email` → `UserAlreadyExistsError`; anything else re-raises),
mirroring the SKU pattern. The DB enforces; the service translates.

**The timing-equalizing dummy hash.** `_authenticate` verifies against a module-level
`_DUMMY_HASH` when the email doesn't exist, so "no such user" and "wrong password" take
the same ~Argon2-verify time — without it, response timing leaks which emails are
registered (user enumeration). Module-level = computed **once per process at import**
(~100 ms at startup), not per request. Not an env var on purpose: the dummy's job is to
cost the same as verifying a real hash, and computing it from the same `recommended()`
config keeps it self-consistent when parameters change — a frozen env-var hash would
silently reopen the timing oracle after a params bump. (Env vars are for secrets and
per-environment config; this is neither.)

**Verify (all observed, 2026-07-26):** `POST /auth/register` with `Verify.Flow@Example.COM`
→ `201`, response lowercased, no hash field, `is_admin: false`; duplicate in *different*
casing → `409` with the domain message (normalization + discrimination proven end-to-end);
7-char password → `422` `string_too_short` with field-level detail; and in psql the stored
value begins `$argon2id$v=19$m=65536,t=3,p=4$` — **PHC string format**: the hash embeds its
own algorithm and parameters (64 MiB, t=3, p=4 — exactly `recommended()`'s), which is how
`verify()` needs no configuration and how rehash-on-login migration detects outdated
hashes. The hash documents itself.

### 3) *(pending — login via OAuth2 password flow, JWT issuance, uniform `401`)*

## Run & verify

*(pending — will cover: register → row holds an argon2 hash, never plaintext; login →
JWT decodes to the right user with an expiry; duplicate register → `409`; wrong
credentials → `401` with no hint which part failed)*

## Troubleshooting (real issues we hit)

- **`alembic revision --autogenerate` produced an empty diff — the users table was
  invisible.** Cause: `alembic/env.py` never imported `app.auth.models`. Autogenerate
  compares the DB against `Base.metadata`, and a model only registers itself there *as a
  side effect of its module being imported* — nothing scans the filesystem for models. Fix:
  add `from app.auth import models as auth_models  # noqa: F401` beside the existing
  products/categories imports. **File the signature:** empty or partial autogenerate diff →
  first suspect is a missing model import in `env.py`.
- **`__table_args__` with a single element needs a trailing comma.** `(Index(...))` is just
  parentheses around one object; only `(Index(...),)` is a tuple. Without it SQLAlchemy
  rejects the class with an `ArgumentError`. Caught in review; would have failed at import.
- **Expression index referenced a nonexistent column** — first draft wrote
  `text("lower(name)")` (copy-paste ghost). `text()` is unvalidated SQL: nothing fails at
  import or autogenerate time; it would have exploded at *migration apply* with
  `column "name" does not exist`. Reading the migration before applying is the ritual for
  exactly this class of error.
- **Double uniqueness guard** — first draft had `unique=True` on the email column *and* the
  functional index: two indexes, overlapping jobs, double write tax — and the plain one
  enforces the case-*sensitive* rule we specifically designed away. One source of truth:
  the functional index only.
- **`User(**data.model_dump())` → `TypeError: 'password' is an invalid keyword argument
  for User`.** The API input schema reached the repo; its fields only coincidentally match
  the model for products, and auth is where they deliberately diverge. Fix: the standalone
  persistence schema (see step 2). The inheritance attempt (`UserCreateSave(UserCreate)`)
  reproduces the same crash — the child still carries `password`.
- **Constraint-name typo made duplicates a 500.** The discrimination checked
  `"uq_user_email"`; the index is `uq_users_email` (plural). Every non-duplicate request
  worked, so the code *read* correct — the miss only surfaced on the 409 path, falling
  through to the bare `raise`. Caught by testing the duplicate path against the real
  server; the durable fixes are a shared constant next to the model (a string literal
  can't drift from itself) and Phase 19's duplicate-registration test. Signature to file:
  *IntegrityError discrimination that "never matches" → diff the string against the
  constraint name in the actual Postgres error DETAIL.*

## Interview talking point

"We hash passwords and *encrypt* nothing — except that's exactly backwards for a pepper:
Dropbox encrypts the finished hash with a global pepper *because* encryption is
reversible, which is what makes the pepper rotatable after a leak. And our auth mechanism
is fully public — it's in the OpenAPI docs. That's Kerckhoffs's principle: the security
lives in the Argon2 cost and the signing key, not in obscurity."
