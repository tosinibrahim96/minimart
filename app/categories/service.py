"""Business logic: decides *what* should happen, owns the transaction boundary,
raises domain exceptions (never HTTPException)."""

from sqlalchemy.orm import Session

from app.categories.repository import CategoryRepository
from app.categories.exceptions import CategoryNotFoundError
from app.categories.models import Category
from collections.abc import Sequence


class CategoryService:
    def __init__(self, db: Session):
        self.repository = CategoryRepository(db)

    def list_categories(self) -> Sequence[Category]:
        return self.repository.list_categories()

    def get_category(self, category_id: int) -> Category:
        category = self.repository.get_category(category_id)
        if category is None:
            raise CategoryNotFoundError(f"Category with id {category_id} not found")
        return category
