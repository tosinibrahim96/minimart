"""HTTP layer: parses requests, declares dependencies, calls the service, maps
results/domain errors to status codes. Decides nothing on its own."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.categories.dependencies import CategoryServiceDep
from app.categories.exceptions import CategoryNotFoundError
from app.categories.schemas import CategoryListParams, CategoryRead
from app.common.pagination import Page

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=Page[CategoryRead])
def list_categories(
    service: CategoryServiceDep,
    params: Annotated[CategoryListParams, Query()],
):
    categories, total = service.list_categories(params)
    return Page.create(items=categories, total=total, params=params)


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(category_id: int, service: CategoryServiceDep):
    try:
        return service.get_category(category_id)
    except CategoryNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
