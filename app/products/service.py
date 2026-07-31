"""Business logic: decides *what* should happen, owns the transaction boundary,
raises domain exceptions (never HTTPException)."""

import secrets
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.categories.exceptions import CategoryNotFoundError
from app.categories.repository import CategoryRepository
from app.products.exceptions import DuplicateSKUError, ProductNotFoundError
from app.products.models import Product
from app.products.repository import ProductRepository
from app.products.schemas import (
    ProductCreate,
    ProductListParams,
    ProductRead,
    ProductUpdate,
)

# Crockford base32: no I, L, O, U — nothing a human can misread aloud
_SKU_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_SKU_LENGTH = 8
_SKU_PREFIX = "SKU-"
_SKU_MAX_ATTEMPTS = 5


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

    def create_product(self, data: ProductCreate) -> ProductRead:
        has_sku_from_customer = data.sku is not None

        for _ in range(_SKU_MAX_ATTEMPTS):
            if not has_sku_from_customer:
                data.sku = self._generate_sku()
            try:
                category = self.category_repository.get_category(data.category_id)
                if category is None:
                    raise CategoryNotFoundError(
                        f"Category with id {data.category_id} not found"
                    )
                new_product = self.product_repository.create_product(data)
                product_read = ProductRead.model_validate(new_product)
                self.db.commit()
            except IntegrityError as e:
                match self._constraint_name(e):
                    case "uq_products_sku" if has_sku_from_customer:
                        raise DuplicateSKUError(f"SKU {data.sku} already exists") from e
                    case "uq_products_sku":
                        self.db.rollback()
                        continue
                    case "fk_products_category_id_categories":
                        raise CategoryNotFoundError(
                            f"Category with id {data.category_id} not found"
                        ) from e
                    case _:
                        raise
            else:
                return product_read
        raise RuntimeError(
            f"Could not generate a unique SKU after {_SKU_MAX_ATTEMPTS} attempts"
        )

    def update_product(self, product_id: int, data: ProductUpdate) -> ProductRead:
        product = self.get_product(product_id)
        if data.category_id is not None:
            category = self.category_repository.get_category(data.category_id)
            if category is None:
                raise CategoryNotFoundError(
                    f"Category with id {data.category_id} not found"
                )
        try:
            product = self.product_repository.update_product(product, data)
            product_read = ProductRead.model_validate(product)
            self.db.commit()
        except IntegrityError as e:
            raise CategoryNotFoundError(
                f"Category with id {data.category_id} not found"
            ) from e
        return product_read

    def delete_product(self, product_id: int) -> None:
        product = self.get_product(product_id)
        self.product_repository.soft_delete(product)
        self.db.commit()

    def _generate_sku(self) -> str:
        code = "".join(secrets.choice(_SKU_ALPHABET) for _ in range(_SKU_LENGTH))
        return f"{_SKU_PREFIX}{code}"

    @staticmethod
    def _constraint_name(e: IntegrityError) -> str | None:
        # e.orig is the raw driver error; only psycopg errors carry .diag —
        # getattr keeps this None-safe and mypy-clean for other error shapes.
        diag = getattr(e.orig, "diag", None)
        return getattr(diag, "constraint_name", None)
