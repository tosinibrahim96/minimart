"""Pydantic request/response schemas (the API shape). Kept separate from the DB
models — input schema, output schema, and model are three distinct classes."""

from pydantic import BaseModel, Field, ConfigDict


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str = Field(..., examples=["Electronics", "Clothing", "Books"])
