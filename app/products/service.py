"""Business logic: decides *what* should happen, owns the transaction boundary,
raises domain exceptions (never HTTPException)."""

from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.categories.exceptions import CategoryNotFoundError
from app.categories.repository import CategoryRepository
from app.products.exceptions import ProductNotFoundError
from app.products.models import Product
from app.products.repository import ProductRepository
from app.products.schemas import ProductCreate, ProductListParams, ProductUpdate


class ProductService:
    def __init__(
        self,
        db: Session,
        product_repository: ProductRepository,
        category_repository: CategoryRepository,
    ):
        self.db = db
        self.product_repository = product_repository
        self.category_repository = category_repository

    def list_products(self, params: ProductListParams) -> tuple[Sequence[Product], int]:
        products, count = self.product_repository.list_products(
            limit=params.per_page, offset=params.offset, filters=params
        )
        return products, count

    def get_product(self, product_id: int) -> Product:
        product = self.product_repository.get_product(product_id)
        if product is None:
            raise ProductNotFoundError(f"Product with id {product_id} not found")
        return product

    def create_product(self, data: ProductCreate) -> Product:
        with self.db.begin():
            category = self.category_repository.get_category(data.category_id)
            if category is None:
                raise CategoryNotFoundError(
                    f"Category with id {data.category_id} not found"
                )

            try:
                new_product = self.product_repository.create_product(data)
            except IntegrityError as e:
                raise CategoryNotFoundError(
                    f"Category with id {data.category_id} not found"
                ) from e
        self.db.refresh(new_product)
        return new_product

    def update_product(self, product_id: int, data: ProductUpdate) -> Product:
        with self.db.begin():
            product = self.get_product(product_id)
            if data.category_id is not None:
                category = self.category_repository.get_category(data.category_id)
                if category is None:
                    raise CategoryNotFoundError(
                        f"Category with id {data.category_id} not found"
                    )
            try:
                product = self.product_repository.update_product(product, data)
            except IntegrityError as e:
                raise CategoryNotFoundError(
                    f"Category with id {data.category_id} not found"
                ) from e
        self.db.refresh(product)
        return product
