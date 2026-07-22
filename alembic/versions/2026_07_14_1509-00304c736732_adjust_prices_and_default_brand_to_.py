"""adjust prices and default brand to products

Revision ID: 00304c736732
Revises: ad0c40281ada
Create Date: 2026-07-14 15:09:47.314204

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "00304c736732"
down_revision: str | Sequence[str] | None = "ad0c40281ada"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fail fast if another session holds a lock, instead of queueing forever
    # behind it (and making everyone queue behind us).
    op.execute("SET lock_timeout = '5s'")

    # -- Data fixes: transactional, roll back together if anything fails --
    # GREATEST guarantees the floor even if a future row sits below 10;
    # bare "* 5" only works because today's minimum happens to be 11.99.
    op.execute("UPDATE products SET price = GREATEST(price * 5, 50) WHERE price < 50")
    op.execute("UPDATE products SET brand = 'Unbranded' WHERE brand IS NULL")

    # -- Guards, big-table style: register instantly (no scan)... --
    op.execute(
        "ALTER TABLE products ADD CONSTRAINT ck_products_minimum_price "
        "CHECK (price >= 50) NOT VALID"
    )
    op.execute(
        "ALTER TABLE products ADD CONSTRAINT ck_products_brand_not_null "
        "CHECK (brand IS NOT NULL) NOT VALID"
    )

    # ...then validate in SEPARATE transactions, so the scan runs under the
    # weak lock with the heavy ADD-locks already released. This is the point
    # where atomicity is deliberately spent to buy lock-friendliness.
    with op.get_context().autocommit_block():
        op.execute("ALTER TABLE products VALIDATE CONSTRAINT ck_products_minimum_price")
        op.execute(
            "ALTER TABLE products VALIDATE CONSTRAINT ck_products_brand_not_null"
        )

    # PG12+: SET NOT NULL skips its table scan because the validated CHECK
    # above already proves no NULLs exist. instant even on a huge table.
    op.alter_column("products", "brand", nullable=False)
    op.drop_constraint(op.f("ck_products_brand_not_null"), "products", type_="check")


def downgrade() -> None:
    op.execute("SET lock_timeout = '5s'")

    # Mirror of upgrade, reversed: loosen NOT NULL *before* nulling brands,
    # or the UPDATE would violate the constraint we're unwinding.
    op.alter_column("products", "brand", nullable=True)
    op.execute("UPDATE products SET brand = NULL WHERE brand = 'Unbranded'")
    op.drop_constraint(op.f("ck_products_minimum_price"), "products", type_="check")
    # Prices are NOT restored: the original sub-50 values were overwritten and
    # no longer exist. Recovering them requires a backup taken before this ran.
