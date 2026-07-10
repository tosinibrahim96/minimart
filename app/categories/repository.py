"""Data-access layer: *does* the DB work (queries, writes). Knows nothing about
HTTP; makes no business decisions; never owns the transaction."""

from collections.abc import Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.categories.models import Category
from app.categories.schemas import CategoryFilter


class CategoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_categories(
        self, limit: int, offset: int, filters: CategoryFilter
    ) -> tuple[Sequence[Category], int]:
        conditions = self._filter_conditions(filters)
        items_stmt = (
            select(Category)
            .where(*conditions)
            .order_by(Category.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(Category).where(*conditions)
        items = self.db.execute(items_stmt).scalars().all()
        count = self.db.execute(count_stmt).scalar_one()
        return items, count

    def get_category(self, category_id: int) -> Category | None:
        return self.db.get(Category, category_id)

    def _filter_conditions(self, filters: CategoryFilter) -> list[ColumnElement[bool]]:
        conditions = []
        if filters.name is not None:
            conditions.append(Category.name.icontains(filters.name, autoescape=True))
        return conditions
