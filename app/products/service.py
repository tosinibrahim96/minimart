"""Business logic: decides *what* should happen, owns the transaction boundary,
raises domain exceptions (never HTTPException)."""

from app.common.pagination import PaginationParams
from sqlalchemy.orm import Session
from collections.abc import Sequence
from app.products.repository import ProductRepository
from app.products.exceptions import ProductNotFoundError
from app.products.models import Product


class ProductService:
    def __init__(self, db: Session):
        self.repository = ProductRepository(db)

    def list_products(self, params: PaginationParams) -> tuple[Sequence[Product], int]:
        offset = (params.page - 1) * params.per_page
        products = self.repository.list_products(limit=params.per_page, offset=offset)
        product_count = self.repository.count_products()
        return products, product_count

    def get_product(self, product_id: int) -> Product:
        product = self.repository.get_product(product_id)
        if product is None:
            raise ProductNotFoundError(f"Product with id {product_id} not found")
        return product
