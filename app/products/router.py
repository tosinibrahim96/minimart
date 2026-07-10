"""HTTP layer: parses requests, declares dependencies, calls the service, maps
results/domain errors to status codes. Decides nothing on its own."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.categories.exceptions import CategoryNotFoundError
from app.common.dependencies import DbSession
from app.common.pagination import Page
from app.products.exceptions import ProductNotFoundError
from app.products.schemas import (
    ProductCreate,
    ProductListParams,
    ProductRead,
    ProductUpdate,
)
from app.products.service import ProductService


def get_product_service(db: DbSession) -> ProductService:
    return ProductService(db)


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=Page[ProductRead])
def list_products(
    service: ProductServiceDep, params: Annotated[ProductListParams, Query()]
):
    products, total = service.list_products(params)
    return Page.create(items=products, total=total, params=params)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, service: ProductServiceDep):
    try:
        return service.get_product(product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, service: ProductServiceDep):
    try:
        return service.create_product(data)
    except CategoryNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)
        ) from e


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(product_id: int, data: ProductUpdate, service: ProductServiceDep):
    try:
        return service.update_product(product_id, data)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except CategoryNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)
        ) from e
