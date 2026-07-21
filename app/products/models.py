"""SQLAlchemy ORM models (the DB shape). Separate from the Pydantic schemas so
the persisted shape and the API shape can diverge without coupling."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    __table_args__ = (
        CheckConstraint("price >= 50", name="minimum_price"),
        Index(
            "uq_products_sku",
            "sku",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    stock: Mapped[int] = mapped_column(Integer)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """Lifecycle: NULL = alive; a timestamp = soft-deleted (gone from the store,
    row kept for history). Set only by the delete action.
    A timestamp, not a boolean, so it answers *when* (audits, retention jobs).
    Governs read filtering and SKU uniqueness (partial index: deleted rows
    free their SKU). Distinct from is_active. A product is visible if and only if
    deleted_at IS NULL (and, where the business says so, is_active)."""
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    """Business state: merchant hid the product (False) — reversible at will,
    e.g. seasonal items, out-of-season listings. Says nothing about lifecycle:
    an inactive product is still alive, still owns its SKU, still in the DB's
    'current catalog'. Deletion is deleted_at's job, not this flag's.
    Visibility filtering by this flag is audience-dependent (shoppers shouldn't
    see hidden products; the merchant must), so it belongs as a per-query service
    condition — never in the repository's central filter, unlike deleted_at.
    Deferred until Phase 7 introduces audiences; until then all reads return
    inactive products with the flag exposed."""
    brand: Mapped[str] = mapped_column(String(100), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
