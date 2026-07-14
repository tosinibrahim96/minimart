"""Business logic: decides *what* should happen, owns the transaction boundary,
raises domain exceptions (never HTTPException)."""

from collections.abc import Sequence

from app.categories.exceptions import CategoryNotFoundError
from app.categories.models import Category
from app.categories.repository import CategoryRepository
from app.categories.schemas import CategoryListParams


class CategoryService:
    def __init__(self, category_repository: CategoryRepository):
        self.category_repository = category_repository

    def list_categories(
        self, params: CategoryListParams
    ) -> tuple[Sequence[Category], int]:
        categories, count = self.category_repository.list_categories(
            limit=params.per_page, offset=params.offset, filters=params
        )
        return categories, count

    def get_category(self, category_id: int) -> Category:
        category = self.category_repository.get_category(category_id)
        if category is None:
            raise CategoryNotFoundError(f"Category with id {category_id} not found")
        return category
