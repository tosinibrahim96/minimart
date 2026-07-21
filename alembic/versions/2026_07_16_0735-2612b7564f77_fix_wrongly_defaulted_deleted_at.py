"""fix wrongly defaulted deleted_at

Revision ID: 2612b7564f77
Revises: 64fd60b29dcc
Create Date: 2026-07-16 07:35:15.738295

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2612b7564f77"
down_revision: str | Sequence[str] | None = "64fd60b29dcc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("products", "deleted_at", server_default=None)
    op.execute("UPDATE products SET deleted_at = NULL WHERE deleted_at IS NOT NULL")


def downgrade() -> None:
    """Restore the (buggy) schema default. Schema only."""
    op.alter_column("products", "deleted_at", server_default=sa.text("now()"))
    # The wrongly-stamped timestamps this migration nulled are destroyed
    # information — they cannot be restored, and we do NOT fabricate them
    # with a fresh NOW(): that would mark every alive product deleted.
