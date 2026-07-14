from typing import Annotated

from fastapi import Depends

from app.categories.repository import CategoryRepository
from app.categories.service import CategoryService
from app.common.dependencies import DbSession


def get_category_repository(db: DbSession) -> CategoryRepository:
    return CategoryRepository(db)


CategoryRepositoryDep = Annotated[CategoryRepository, Depends(get_category_repository)]


def get_category_service(repository: CategoryRepositoryDep) -> CategoryService:
    return CategoryService(repository)


CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]
