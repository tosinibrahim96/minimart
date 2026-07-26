"""SQLAlchemy ORM models (the DB shape). Separate from the Pydantic schemas so
the persisted shape and the API shape can diverge without coupling."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        Index(
            "uq_users_email",
            text("lower(email)"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
