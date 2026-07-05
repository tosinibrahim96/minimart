import math
from typing import Generic, TypeVar
from collections.abc import Sequence
from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int

    @classmethod
    def create(
        cls, items: Sequence[T], total: int, params: PaginationParams
    ) -> "Page[T]":
        pages = math.ceil(total / params.per_page) if total else 0
        return cls(
            items=items, total=total, page=params.page, per_page=params.per_page, pages=pages
        )
