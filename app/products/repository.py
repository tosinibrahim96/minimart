"""Data-access layer: *does* the DB work (queries, writes). Knows nothing about
HTTP; makes no business decisions; never owns the transaction."""

from collections.abc import Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.products.models import Product
from app.products.schemas import ProductCreate, ProductFilter, ProductUpdate


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_products(
        self, limit: int, offset: int, filters: ProductFilter
    ) -> tuple[Sequence[Product], int]:
        conditions = self._filter_conditions(filters)
        items_stmt = (
            select(Product)
            .where(*conditions)
            .order_by(Product.id.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(Product).where(*conditions)
        items = self.db.execute(items_stmt).scalars().all()
        count = self.db.execute(count_stmt).scalar_one()
        return items, count

    def get_product(self, product_id: int) -> Product | None:
        return self.db.get(Product, product_id)

    def create_product(self, data: ProductCreate) -> Product:
        new_product = Product(**data.model_dump())
        self.db.add(new_product)
        self.db.flush()
        return new_product

    def update_product(self, product: Product, data: ProductUpdate) -> Product:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(product, field, value)
        self.db.flush()
        return product

    def _filter_conditions(self, filters: ProductFilter) -> list[ColumnElement[bool]]:
        conditions = []

        if filters.name is not None:
            conditions.append(Product.name.icontains(filters.name, autoescape=True))
        if filters.category_id is not None:
            conditions.append(Product.category_id == filters.category_id)
        if filters.in_stock is not None:
            conditions.append(
                Product.stock > 0 if filters.in_stock else Product.stock == 0
            )
        if filters.min_price is not None:
            conditions.append(Product.price >= filters.min_price)
        if filters.max_price is not None:
            conditions.append(Product.price <= filters.max_price)
        if filters.min_created_at is not None:
            conditions.append(Product.created_at >= filters.min_created_at)
        if filters.max_created_at is not None:
            conditions.append(Product.created_at <= filters.max_created_at)
        if filters.brand is not None:
            conditions.append(Product.brand.icontains(filters.brand, autoescape=True))
        return conditions
