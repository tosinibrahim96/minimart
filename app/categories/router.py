"""HTTP layer: parses requests, declares dependencies, calls the service, maps
results/domain errors to status codes. Decides nothing on its own."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.common.dependencies import DbSession
from app.categories.service import CategoryService
from app.categories.schemas import CategoryRead
from app.categories.exceptions import CategoryNotFoundError


def get_category_service(db: DbSession) -> CategoryService:
    return CategoryService(db)


CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
def list_categories(service: CategoryServiceDep):
    return service.list_categories()


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(category_id: int, service: CategoryServiceDep):
    try:
        return service.get_category(category_id)
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
