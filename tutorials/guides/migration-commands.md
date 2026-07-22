# Migration Commands Cheat Sheet

> The Alembic workflow for this project, Docker-first. Full conceptual treatment:
> [`../phases/database-migrations.md`](../phases/database-migrations.md). This is just
> the muscle memory.

## The core loop (schema change)

```bash
# 1. Edit the model (app/<domain>/models.py)

# 2. Generate a draft migration from the model↔DB diff
docker compose exec api alembic revision --autogenerate -m "add deleted_at to products"

# 3. READ the generated file in alembic/versions/ — autogenerate is a draft, not truth
#    (it misses data migrations, CHECK constraints, and can propose dropping things
#    it doesn't know about)

# 4. Apply it
docker compose exec api alembic upgrade head

# 5. Prove the downgrade works, then re-apply
docker compose exec api alembic downgrade -1
docker compose exec api alembic upgrade head
```

## Empty migration (data migrations / hand-written SQL)

When there's no model change to diff — re-pricing rows, backfills, raw-SQL constraints —
drop `--autogenerate` to get an empty skeleton you fill in yourself:

```bash
docker compose exec api alembic revision -m "reprice sub-50 products"
```

## Where am I? (status & history)

```bash
docker compose exec api alembic current      # revision the DB is at (reads alembic_version table)
docker compose exec api alembic history      # the whole chain, newest first
docker compose exec api alembic heads        # newest revision in the files
docker compose exec api alembic check        # would autogenerate emit anything? = drift detector
```

`alembic check` saying "No new upgrade operations detected" is the definitive
"models and database agree" test — run it after any hand-written migration.

## Going backwards

```bash
docker compose exec api alembic downgrade -1         # undo the latest migration
docker compose exec api alembic downgrade <rev>      # go to a specific revision
docker compose exec api alembic downgrade base       # tear down to empty (dev only!)
docker compose exec api alembic upgrade head         # rebuild everything from the chain
```

## Reading the generated filename

`2026_07_14_1509-00304c736732_adjust_prices.py` = date_time-revisionid_slug (our
`file_template` in `alembic.ini`). **Ordering is NOT the filename** — it's the
`down_revision` pointer inside each file; names are for humans, so renaming a file is safe.

## Review checklist for every generated migration

- Does `upgrade()` do exactly what you intended — and nothing extra (no surprise drops)?
- Does `downgrade()` honestly reverse it? (Data destroyed in `upgrade()` can't come back —
  say so in a comment instead of pretending.)
- Constraint names: hand-written names go through the naming convention — pass short names
  in models (`name="minimum_price"` → `ck_products_minimum_price`) and wrap final names in
  `op.f()` in ops so they're not double-prefixed.
- New required column on a populated table? One step won't work — stage it:
  add nullable → backfill → `NOT NULL`.
- Ruff runs automatically on generated files (post-write hook in `alembic.ini`).

## Gotchas already paid for (don't pay twice)

- **`alembic` not found** → the running image predates the dependency; `docker compose up -d --build`.
- **Never `op.execute("COMMIT;")`** — use `op.get_context().autocommit_block()` when a
  statement genuinely needs its own transaction (VALIDATE CONSTRAINT, CREATE INDEX
  CONCURRENTLY). Details: soft-deletes-and-skus tutorial, Troubleshooting.
- **Never import app models in a migration** — migrations are frozen history; models evolve.
