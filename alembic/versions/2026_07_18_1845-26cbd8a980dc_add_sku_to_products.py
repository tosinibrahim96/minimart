"""add sku to products

Revision ID: 26cbd8a980dc
Revises: 2612b7564f77
Create Date: 2026-07-18 18:45:15.472798

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "26cbd8a980dc"
down_revision: str | Sequence[str] | None = "2612b7564f77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    # Fail fast if another session holds a lock, instead of queueing forever
    op.execute("SET lock_timeout = '5s'")

    # ### Add nullable sku column to products table ###
    op.add_column("products", sa.Column("sku", sa.String(length=100), nullable=True))

    # ### Populate the sku column with unique values ###
    op.execute("UPDATE products SET sku = CONCAT('SKU-', id) WHERE sku IS NULL")
    op.alter_column("products", "sku", nullable=False)

    op.create_index(
        "uq_products_sku",
        "products",
        ["sku"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### Drop sku column from products table ###
    op.drop_index("uq_products_sku", table_name="products")
    op.drop_column("products", "sku")
    # ### end Alembic commands ###
