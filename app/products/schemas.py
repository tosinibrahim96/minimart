"""Pydantic request/response schemas (the API shape). Kept separate from the DB
models — input schema, output schema, and model are three distinct classes."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core.core_schema import ValidationInfo

from app.common.pagination import PaginationParams


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = Field(..., examples=["Product 1", "Product 2", "Product 3"])
    description: str | None = Field(
        None, examples=["Description 1", "Description 2", "Description 3"]
    )
    price: Decimal = Field(..., examples=[10.0, 20.0, 30.0])
    stock: int = Field(..., examples=[10, 20, 30])
    category_id: int = Field(..., examples=[1, 2, 3])
    created_at: datetime = Field(..., examples=["2026-01-01T12:00:00Z"])
    brand: str = Field(..., max_length=100, examples=["Nike", "Adidas", "Puma"])
    sku: str = Field(..., examples=["SKU-1", "SKU-2", "SKU-3"])


class ProductCreate(BaseModel):
    name: str = Field(
        ..., min_length=3, max_length=50, description="The name of the product"
    )
    description: str | None = Field(
        None, max_length=255, description="The description of the product"
    )
    price: Decimal = Field(
        ...,
        ge=Decimal("50"),
        max_digits=10,
        decimal_places=2,
        description="The price of the product",
        examples=[100.00],
    )
    stock: int = Field(..., ge=0, description="Units on hand; 0 = not yet in stock")
    category_id: int = Field(..., gt=0, description="The category id of the product")
    brand: str = Field(
        ..., min_length=1, max_length=100, examples=["Nike", "Adidas", "Puma"]
    )
    sku: str | None = Field(
        None,
        min_length=3,
        max_length=100,
        examples=[
            "Nike-blue-M",
        ],
    )

    @field_validator("sku", mode="before")
    @classmethod
    def validate_and_normalize_sku(cls, v: str | None) -> str | None:
        if v is None:
            return v

        v = v.strip().upper()
        if not re.match(r"^[A-Z0-9-]+$", v):
            raise ValueError(
                "SKU must contain only alphanumeric characters and hyphens"
            )
        return v


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        None, min_length=3, max_length=50, description="The name of the product"
    )
    description: str | None = Field(
        None, max_length=255, description="The description of the product"
    )
    price: Decimal | None = Field(
        None,
        ge=Decimal("50"),
        max_digits=10,
        decimal_places=2,
        description="The price of the product",
        examples=[100.00],
    )
    stock: int | None = Field(
        None, ge=0, description="Units on hand; 0 = not yet in stock"
    )
    category_id: int | None = Field(
        None, gt=0, description="The category id of the product"
    )
    brand: str | None = Field(
        None, min_length=1, max_length=100, examples=["Nike", "Adidas", "Puma"]
    )

    @field_validator("name", "price", "stock", "category_id", "brand")
    @classmethod
    def reject_explicit_null(cls, v: Any, info: ValidationInfo) -> Any:
        if v is None:
            raise ValueError(f"Field {info.field_name} cannot be null")
        return v


class ProductFilter(BaseModel):
    name: str | None = Field(None, min_length=1)
    category_id: int | None = Field(None)
    in_stock: bool | None = Field(None)
    brand: str | None = Field(None, min_length=1)

    min_price: Decimal | None = Field(None)
    max_price: Decimal | None = Field(None)

    min_created_at: datetime | None = Field(None)
    max_created_at: datetime | None = Field(None)

    @model_validator(mode="after")
    def reject_min_is_greater_than_max(self) -> Self:
        pairs = [("min_price", "max_price"), ("min_created_at", "max_created_at")]
        for min_field, max_field in pairs:
            min_value = getattr(self, min_field)
            max_value = getattr(self, max_field)
            if (
                min_value is not None
                and max_value is not None
                and min_value > max_value
            ):
                raise ValueError(f"{min_field} cannot be greater than {max_field}")
        return self


class ProductListParams(PaginationParams, ProductFilter):
    pass
