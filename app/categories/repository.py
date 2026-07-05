"""Data-access layer: *does* the DB work (queries, writes). Knows nothing about
HTTP; makes no business decisions; never owns the transaction."""

from sqlalchemy import select

from sqlalchemy.orm import Session
from app.categories.models import Category
from collections.abc import Sequence


class CategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_categories(self) -> Sequence[Category]:
        result = self.db.execute(select(Category))
        return result.scalars().all()

    def get_category(self, category_id: int) -> Category | None:
        return self.db.get(Category, category_id)
