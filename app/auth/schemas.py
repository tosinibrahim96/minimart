"""Pydantic request/response schemas (the API shape). Kept separate from the DB
models — input schema, output schema, and model are three distinct classes."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class TokenPayload(BaseModel):
    sub: str
    exp: datetime


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr = Field(..., description="The email of the user")
    created_at: datetime = Field(..., description="The creation date of the user")
    updated_at: datetime = Field(..., description="The last update date of the user")
    is_admin: bool = Field(..., description="Whether the user is an admin")


class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="The email of the user")
    password: str = Field(
        ..., min_length=8, max_length=128, description="The password of the user"
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return v.strip().lower()


class UserCreateSave(BaseModel):
    """Persistence shape: exactly the User model's constructor kwargs.
    The plaintext password never enters this class."""

    email: str
    password_hash: str
