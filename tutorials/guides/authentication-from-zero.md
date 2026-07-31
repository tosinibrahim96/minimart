# Authentication from zero: HTTP auth, Bearer, OAuth2, JWT, and OIDC — who owns which rule

> **Why this guide exists:** while building Phase 6 (login) and reading for Phase 7
> (protected routes), the boundaries got fuzzy: "OAuth2 is for *authorization*, OpenID
> Connect adds *authentication* — but our login form is authentication, and it came from
> the OAuth2 chapter of the FastAPI docs?? And which spec says a 401 must carry
> `WWW-Authenticate`?" This guide builds the whole stack up from zero so every rule we
> implemented has a named owner.

---

## 1. Two words that everyone conflates

Start from something you already know: a nightclub with a bouncer.

- **Authentication (authn)** — *who are you?* The bouncer checks your ID at the door.
- **Authorization (authz)** — *what are you allowed to do?* Your wristband says whether
  you can enter the VIP area. The wristband doesn't say who you are — it says what you
  may do.

They're separate questions, asked at separate moments, often by separate mechanisms.
In MiniMart:

| Question | Where it happens | Mechanism |
|---|---|---|
| Who are you? (at login) | `POST /auth/login` | email + password, verified against the Argon2 hash |
| Who are you? (on every later request) | `get_current_user` (Phase 7) | JWT signature + expiry check |
| What may you do? | the admin dependency (Phase 7) | the `is_admin` flag, checked per request |

Notice the middle row: **verifying a token is still authentication** — you're
re-establishing *who is calling* on every request, just with a token instead of a
password. Authorization only starts once identity is settled.

HTTP status codes follow the same split: **401 = authentication failed** (we don't know
who you are — no ID, fake ID), **403 = authorization failed** (we know exactly who you
are, and the answer is no — real ID, no wristband).

---

## 2. The layer cake

The stack we're using is five layers, each defined by a different spec, each solving a
different problem. Bottom-up:

```
Layer 4  OIDC             "log in WITH Google"      — identity layer on OAuth2
Layer 3  JWT (RFC 7519)   what the token LOOKS like — a token format
Layer 2  OAuth2 (RFC 6749) how tokens are OBTAINED  — an authorization-delegation framework
Layer 1  Bearer (RFC 6750) how tokens are PRESENTED — one HTTP auth scheme
Layer 0  HTTP  (RFC 9110)  the challenge/response frame — 401, WWW-Authenticate, Authorization
```

### Layer 0 — HTTP's own authentication framework (RFC 9110 §11)

This is the oldest layer, decades older than OAuth. HTTP itself defines a generic
challenge/response protocol:

1. Client requests a protected resource with no credentials.
2. Server replies **`401 Unauthorized`** and — the spec says **MUST** — includes a
   **`WWW-Authenticate`** header naming which *scheme(s)* it will accept. This is the
   *challenge*: "you may try again, and here's the kind of credentials I take."
3. Client retries with an **`Authorization`** request header carrying credentials in
   that scheme.

The original scheme is `Basic` (base64 of `user:password` on every request — try it:
`curl -u alice:secret http://...` just sets `Authorization: Basic YWxpY2U6c2VjcmV0`).
The framework is *pluggable*: `Basic`, `Digest`, `Bearer`, `Negotiate` are all schemes
slotting into the same 401/`WWW-Authenticate`/`Authorization` frame.

**→ This layer owns:** the `401` status, the "401 MUST carry `WWW-Authenticate`" rule,
and the `Authorization` header itself. When our login route returns
`headers={"WWW-Authenticate": "Bearer"}`, we are obeying *HTTP*, not OAuth.

### Layer 1 — the Bearer scheme (RFC 6750)

"Bearer" means: **whoever bears (holds) this token gets in — no further proof of
identity required**. Like a movie ticket: the usher doesn't check that you're the
person who bought it. That's what makes tokens convenient (no password on every
request) and dangerous (a stolen token works perfectly until it expires — this is
exactly the Phase 6 revocation conversation).

RFC 6750 defines:
- the wire format: `Authorization: Bearer eyJhbGciOi...`
- the error taxonomy in the `WWW-Authenticate` challenge, which maps precisely onto the
  Phase 7 status-code question:
  - `invalid_token` (missing/expired/bad signature) → **401** — authentication failed
  - `insufficient_scope` (valid token, not enough privilege) → **403** — authorization failed

**→ This layer owns:** how the token travels, and the 401-vs-403 boundary for
token-protected endpoints.

### Layer 2 — OAuth 2.0 (RFC 6749): how tokens are obtained

Here's the problem OAuth was actually invented for, and it is **not** "log in to my own
API." Around 2007, apps wanted to act on your data *at another company*. Example: a
photo-printing site wants to fetch your Google photos. The pre-OAuth answer was
horrifying: *give the printing site your Google password*. Full account access,
unrevocable except by changing the password, password stored by a third party.

OAuth is the **valet key**: a limited key you hand a valet that starts the car but
won't open the trunk. It defines four roles:

- **Resource owner** — you (the user who owns the photos)
- **Client** — the printing site (wants limited access)
- **Authorization server** — Google's login/consent screens (checks your identity, asks
  "allow PrintCo to read your photos?", mints the token)
- **Resource server** — Google's photos API (accepts the token)

The client gets a **scoped, expiring, revocable access token** instead of your
password. That's why OAuth is called an ***authorization* framework** — its output is a
grant of limited access (the wristband), and it deliberately says nothing about how
the client learns *who you are*.

RFC 6749 defines several **grant types** (flows for obtaining a token). The one we
used, the **password grant** (§4.3, "Resource Owner Password Credentials"), is the odd
one out: the client collects your username and password directly and swaps them for a
token. For a *third-party* client this defeats OAuth's entire purpose (the client saw
your password!) — the spec allowed it only for *first-party, highly-trusted* clients
as a migration path from Basic auth. It is **formally removed in OAuth 2.1**
(still an IETF draft as of 2026, but its recommendations are already industry
practice) and already deprecated by the OAuth Security BCP (RFC 9700).

**→ This layer owns:** the form encoding and the exact field names `username` /
`password` (§4.3.2 mandates them — that's why our login endpoint takes form data and
why the email arrives in a field called `username`), and the token response shape
`{"access_token": ..., "token_type": "bearer"}` (§5.1).

### Layer 3 — JWT (RFC 7519): what the token looks like

OAuth deliberately does **not** say what an access token looks like — it could be a
random opaque string the server looks up in a table. JWT is one *format*: a
self-contained, signed document (`header.payload.signature`) the resource server can
verify **without any lookup** — just check the signature and expiry. That's the
statelessness we bought in Phase 6, and the revocation problem it costs (Phase 15
buys it back).

**→ This layer owns:** the claim names (`sub`, `exp`), "`sub` must be a string," and
the signature mechanics (HS256 etc.).

### Layer 4 — OpenID Connect: the missing authentication layer

People kept abusing OAuth for login ("if PrintCo can get a token for my Google photos,
that sort of proves I'm me… right?") — with real security holes, because an access
token proves *a grant happened*, not *who is standing here now*. OIDC fixed this
properly: a thin layer **on top of** OAuth2 that adds an **ID token** (a JWT with
standardized identity claims: who authenticated, when, how) and a `userinfo` endpoint.
"Sign in with Google/GitHub/Apple" is OIDC.

Back to the bouncer: OAuth hands out **wristbands** (access — bouncer doesn't care who
you are), OIDC hands out **ID cards** (identity). OIDC = "OAuth, plus the driver's
license."

**→ This layer owns:** federated login. We don't use it — MiniMart authenticates its
own users directly.

---

## 3. So what is MiniMart actually doing?

**First-party authentication that borrows OAuth2's wire shapes.** All four OAuth roles
collapse into one or two parties:

- Resource owner = our user
- Client = curl / Swagger UI / a future frontend (first-party — *ours*)
- Authorization server = **us** (`POST /auth/login` mints the token)
- Resource server = **us** (every protected route verifies it)

Because the client is first-party, "the client sees your password" is not a
vulnerability — the client and the server are the same trust domain. The password
grant's *shape* (form fields, token response, Bearer presentation) is just a
well-specified, tooling-supported convention for "send credentials, get a token" —
which is why FastAPI's security utilities and Swagger's Authorize button speak it
natively.

**What would a "real" deployment do instead?** A production system with a browser
frontend typically runs the **authorization-code flow with PKCE**: the app redirects
to a login page served by the authorization server, the user enters credentials
*there*, and the app receives a one-time code it exchanges for tokens. Same idea even
first-party — it keeps passwords out of API payloads and enables SSO. Knowing that the
password grant is (a) fine for a first-party API like this and (b) removed from OAuth
2.1 for third parties *is* the senior answer.

---

## 4. Every rule we implemented, and which spec owns it

| Thing in our code | Owner |
|---|---|
| `401` on bad credentials | HTTP — RFC 9110 §15.5.2 |
| `headers={"WWW-Authenticate": "Bearer"}` on the 401 | HTTP — RFC 9110 §11.6.1 (MUST); value = the scheme, from RFC 6750 §3 |
| Login takes **form data** with fields named `username`/`password` | OAuth2 — RFC 6749 §4.3.2 |
| Response `{"access_token": ..., "token_type": "bearer"}` | OAuth2 — RFC 6749 §5.1 |
| `Authorization: Bearer <token>` on requests (Phase 7) | Bearer — RFC 6750 §2.1 |
| 401 (bad token) vs 403 (valid token, no privilege) | Bearer — RFC 6750 §3.1 (`invalid_token` vs `insufficient_scope`) |
| `sub` is a string; `exp` as epoch seconds | JWT — RFC 7519 §4.1 |
| HS256 signature | JWT/JWS — RFC 7519 + RFC 7518 |
| Uniform "Incorrect email or password" (no hint which failed) | Not a spec — OWASP guidance (user-enumeration defense) |

## 5. Which *code* layer owns which rule

The specs above are all **edge protocol** — so in our architecture they live at the
edge, never in the service:

- **Router** owns HTTP vocabulary: status codes, `WWW-Authenticate`, form parsing via
  `OAuth2PasswordRequestForm`. (This is why the 401 + header lives in `router.py`
  while the service raises `InvalidCredentialsError` — the service doesn't know HTTP
  exists.)
- **Service** owns the *authentication decision*: verify the hash, mint the token,
  timing-equalize the failure paths.
- **Dependencies** (Phase 7) are the edge's DI arm: `get_current_user` extracts and
  verifies the Bearer token per request. Dependencies sit at the HTTP edge, so —
  unlike services — raising `HTTPException` there is architecturally acceptable.

---

## 6. Reading list (curated 2026-07)

In order of usefulness for a first pass:

1. **An Illustrated Guide to OAuth and OpenID Connect** — Okta developer blog. The
   gentlest correct explanation of the roles and flows; start here.
   https://developer.okta.com/blog/2019/10/21/illustrated-guide-to-oauth-and-oidc
2. **OAuth 2.0 Simplified** (Aaron Parecki, free web book at oauth.com) — the
   plain-English companion to RFC 6749; his https://oauth.net/2/ and
   https://oauth.net/2.1/ pages track spec status (including the password grant's
   removal: https://oauth.net/2/grant-types/password/).
3. **RFC 6750** (Bearer Token Usage) — short; §3 is the 401/403 taxonomy.
4. **RFC 9110 §11** (HTTP Semantics — Authentication) — the challenge/response frame.
5. **RFC 6749 §1** (roles) and **§4.3** (password grant) — read *after* Parecki, not
   before.
6. Already on the Phase 15 reading map: **RFC 9700** (OAuth Security BCP) and the
   OWASP JWT cheat sheet — where the hardening story continues.

---

## 7. The one-paragraph interview version

> "OAuth 2.0 is an authorization-delegation framework — its job is letting a client
> get limited, revocable access to a user's resources without seeing their password.
> It deliberately doesn't do authentication; OpenID Connect adds that as an identity
> layer on top. What my API does is first-party authentication that *borrows* OAuth2's
> wire conventions — the password grant's form fields and token response, plus the
> Bearer scheme for presenting the JWT — because they're well-specified and the
> tooling speaks them. The password grant is removed in OAuth 2.1 since it defeats
> delegation for third parties, but for a first-party API the client and server share
> one trust domain, so it's a reasonable, standard shape. The 401-vs-403 rule and the
> `WWW-Authenticate` header aren't OAuth at all — they come from HTTP's own
> authentication framework and the Bearer RFC."
