"""HTTP layer: parses requests, declares dependencies, calls the service, maps
results/domain errors to status codes. Decides nothing on its own."""

from app.common.pagination import Page, PaginationParams
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query

from app.common.dependencies import DbSession
from app.products.service import ProductService
from app.products.schemas import ProductRead
from app.products.exceptions import ProductNotFoundError


def get_product_service(db: DbSession) -> ProductService:
    return ProductService(db)


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=Page[ProductRead])
def list_products(
    service: ProductServiceDep, params: Annotated[PaginationParams, Query()]
):
    products, total = service.list_products(params)
    return Page.create(items=products, total=total, params=params)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, service: ProductServiceDep):
    try:
        return service.get_product(product_id)
    except ProductNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
