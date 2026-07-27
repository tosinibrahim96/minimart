"""Data-access layer: *does* the DB work (queries, writes). Knows nothing about
HTTP; makes no business decisions; never owns the transaction."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.schemas import UserCreateSave


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.execute(
            select(User).where(func.lower(User.email) == email.lower())
        ).scalar_one_or_none()

    def create_user(self, data: UserCreateSave) -> User:
        new_user = User(**data.model_dump())
        self.db.add(new_user)
        self.db.flush()
        return new_user
