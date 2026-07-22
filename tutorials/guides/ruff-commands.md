# Ruff Commands Cheat Sheet

> The three commands used constantly in this project, Docker-first (tools live in the
> `api` container's venv — no `uv run` prefix needed inside it).

| What | Command |
|------|---------|
| **format** — rewrite files to the canonical style | `docker compose exec api ruff format .` |
| **check** — lint + type-check (what CI will run) | `docker compose exec api sh -c "ruff check . && mypy ."` |
| **fix** — auto-fix the fixable lint findings | `docker compose exec api ruff check . --fix` |

## Notes

- **`format` vs `check --fix` are different jobs:** `format` handles layout (line breaks,
  quotes, blank lines — the Black-style formatter); `check --fix` fixes *lint rules* that
  have safe autofixes (unused imports, import sorting, missing trailing newline). A clean
  pass usually needs both.
- **Dry-run variants** (report, don't touch): `ruff format --check .` and plain
  `ruff check .` — use these to see what *would* change.
- Not everything is auto-fixable — findings without `[*]` in the output need a hand edit.
- Scope any command to a path to keep it fast/focused, e.g.
  `docker compose exec api ruff check app/products/`.
- Config lives in `pyproject.toml`; migrations get auto-fixed at generation time by the
  `post_write_hooks` ruff block in `alembic.ini` (see the database-migrations tutorial).
