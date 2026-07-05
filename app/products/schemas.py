"""Pydantic request/response schemas (the API shape). Kept separate from the DB
models — input schema, output schema, and model are three distinct classes."""

from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict
from decimal import Decimal


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
