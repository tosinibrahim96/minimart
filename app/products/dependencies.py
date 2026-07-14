from typing import Annotated

from fastapi import Depends

from app.categories.dependencies import CategoryRepositoryDep
from app.common.dependencies import DbSession
from app.products.repository import ProductRepository
from app.products.service import ProductService


def get_product_repository(db: DbSession) -> ProductRepository:
    return ProductRepository(db)


ProductRepositoryDep = Annotated[ProductRepository, Depends(get_product_repository)]


def get_product_service(
    db: DbSession,
    product_repository: ProductRepositoryDep,
    category_repository: CategoryRepositoryDep,
) -> ProductService:
    return ProductService(db, product_repository, category_repository)


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]
