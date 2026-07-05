"""Data-access layer: *does* the DB work (queries, writes). Knows nothing about
HTTP; makes no business decisions; never owns the transaction."""

from sqlalchemy import select, func
from collections.abc import Sequence
from sqlalchemy.orm import Session
from app.products.models import Product


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_products(self, limit: int = 10, offset: int = 0) -> Sequence[Product]:
        result = self.db.execute(select(Product).limit(limit).offset(offset))
        return result.scalars().all()

    def count_products(self) -> int:
        result = self.db.execute(select(func.count()).select_from(Product))
        return result.scalar_one()

    def get_product(self, product_id: int) -> Product | None:
        return self.db.get(Product, product_id)
