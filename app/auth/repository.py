"""Data-access layer: *does* the DB work (queries, writes). Knows nothing about
HTTP; makes no business decisions; never owns the transaction."""

from sqlalchemy import func, select, update
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

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.db.execute(
            select(User).where(User.id == user_id)
        ).scalar_one_or_none()

    def create_user(self, data: UserCreateSave) -> User:
        new_user = User(**data.model_dump())
        self.db.add(new_user)
        self.db.flush()
        return new_user

    def update_user_is_admin(self, user_id: int, is_admin: bool):
        self.db.execute(
            update(User).where(User.id == user_id).values(is_admin=is_admin)
        )
        self.db.flush()
