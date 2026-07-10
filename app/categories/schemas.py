"""Pydantic request/response schemas (the API shape). Kept separate from the DB
models — input schema, output schema, and model are three distinct classes."""

from pydantic import BaseModel, ConfigDict, Field

from app.common.pagination import PaginationParams


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = Field(..., examples=["Electronics", "Clothing", "Books"])


class CategoryFilter(BaseModel):
    name: str | None = Field(None, min_length=1)


class CategoryListParams(PaginationParams, CategoryFilter):
    pass
