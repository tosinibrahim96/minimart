# MiniMart API — Project Memory

## What this is
A deliberately lean FastAPI online store, built as a **learning project** to reach
senior-level backend skills. Lean by design: every feature exists to teach one concept.
The full plan, phases, acceptance criteria, and progress live in @docs/learning-spec.md.

## How to work with me  (READ FIRST — most important section)
My goal is to become interview-ready: *I* must be able to build and explain everything
here. Shipping speed is NOT the goal; my understanding is.
- **Do NOT write implementations for me.** When I'm stuck, give hints, the relevant
  concept, and the tradeoffs — then let me write the code.
- Only write full code if I explicitly say "show me the code" / "write it for me".
- When I ask "how do I X", explain the approach and the *why*, point me at the right
  pattern, and let me try first.
- When reviewing my code, tell me what's wrong and why; let me fix it myself.
- Always give the senior framing: "here's why, and here's when you'd choose the
  alternative" — I need to defend these decisions in interviews.
- When two approaches are reasonable, explain both and let me choose. Don't decide for me.
- **Explain like I'm a beginner, with examples — this beats staying "high-level".** For any
  non-obvious concept, follow this shape: (1) start from something I already know; (2) introduce
  the new idea in those same terms, defining every piece of jargon the first time; (3) show a
  concrete, runnable example (a REPL snippet or tiny worked case — examples over prose); (4) add
  an analogy if it makes it stick; (5) ONLY THEN tie it back to the technical/senior/interview
  framing. Complexity comes LAST. Go down to fundamentals rather than waving at a concept — being
  thorough is preferred. (Model: the base-10-vs-base-2 "ruler" explanation of `Decimal` vs `float`.)
- Be direct. Tell me plainly when I'm wrong or cargo-culting.

## Definition of Done — the completion ritual (every phase, no exceptions)
A phase/task is "done" only when BOTH are true: (1) the matching checkbox(es) in
@docs/learning-spec.md are ticked, and (2) a reproducible tutorial for it exists under
`tutorials/phases/`. Never treat a phase as complete until both hold.
When I finish a phase I'll type `/done` (or just tell you a phase is finished) — run the
`done` skill, which verifies the acceptance criteria, ticks the boxes, and writes the
tutorial (using @tutorials/_TEMPLATE.md, in the style of @tutorials/phases/project-setup.md).
Tutorials are organised into two folders: `tutorials/phases/` holds the per-phase tutorials
(one per phase, the DoD deliverable); `tutorials/guides/` holds cross-cutting how-tos that
surface mid-session but aren't tied to a single phase (e.g. @tutorials/guides/dependency-management.md).
`_TEMPLATE.md` stays at the `tutorials/` root.
Note: tutorials are written *after* I've built the thing — they document the working code
I arrived at, so including final code there is a record of my work, not you writing my
implementation. Coach mode still applies while I'm building.

## Stack
FastAPI · Pydantic v2 + pydantic-settings · SQLAlchemy 2.0 · PostgreSQL · Redis ·
Alembic · pytest + httpx · Docker + Docker Compose · ruff + mypy · GitHub Actions.
Python 3.12, managed with **uv**. Package root is `app/`. Use PostgreSQL, never SQLite.

## Architecture rules (non-negotiable)
- Domain-based layout under `app/`: each feature owns its own router / service /
  repository / schemas / models.
- **The router decides nothing. The service decides *what*. The repository *does* it.**
- Routers handle only HTTP. Business logic → services. DB queries → repositories.
- Services raise DOMAIN exceptions (e.g. `OutOfStockError`); routers map them to HTTP
  status codes. **Never raise `HTTPException` inside a service.**
- The transaction boundary lives in the service, never the repository.
- Keep DB models, input schemas, and output schemas as three separate classes.
- All config from env via pydantic-settings. No secrets in code, ever.
- Any schema change goes through an Alembic migration — never edit tables by hand.

## Commands  (Docker-first: only Docker is required to run anything; `uv` on host is optional, for locking)
The stack — api (+ Postgres + Redis in later phases) — runs in Compose. The dev image is
built from the `dev` target and includes dev tools (pytest/ruff/mypy/alembic). The venv
lives at `/opt/venv` (on PATH), so inside the container you call tools directly — no
`uv run` prefix. The dev server runs inside the `api` container with `--reload`.
- Start everything:  docker compose up --build      # reloading dev server (api service)
- Stop everything:   docker compose down
- Tail logs:         docker compose logs -f api
- Shell into api:    docker compose exec api bash
- Tests:             docker compose exec api pytest
- Lint + types:      docker compose exec api sh -c "ruff check . && mypy ."
- Migrate (apply):   docker compose exec api alembic upgrade head
- Migrate (create):  docker compose exec api alembic revision --autogenerate -m "msg"
- Change deps:       docker compose run --rm api uv add <pkg>   then   docker compose build
                     # (no-host alternative to `uv add`; updates pyproject.toml + uv.lock via the mount)
Gotchas:
- The `dev` build target installs WITH dev deps; the `prod` target uses `--no-dev`. Run
  dev/test commands against the dev image, or tools fail with "command not found".
- The venv MUST live outside the bind-mounted `/app` (we put it at `/opt/venv`); otherwise
  the source mount hides it and the container has no installed packages.

## Conventions
- Every endpoint gets tests, including the error paths (401/403/404/409/422).
- One logical change per commit; conventional commit messages.
- Do NOT add any AI/Claude attribution anywhere: no co-author trailer
  (`Co-Authored-By: Claude ...`) and no "Generated with Claude Code" (or similar) line in
  commit messages, PR titles, or PR bodies. Keep all of them attribution-free.
- Make minimal changes — don't refactor unrelated code unless I ask.
