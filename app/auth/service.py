"""Business logic: decides *what* should happen, owns the transaction boundary,
raises domain exceptions (never HTTPException)."""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.exceptions import InvalidCredentialsError, UserAlreadyExistsError
from app.auth.models import User
from app.auth.repository import UserRepository
from app.auth.schemas import (
    TokenPayload,
    TokenResponse,
    UserCreate,
    UserCreateSave,
    UserRead,
)
from app.core.config import settings

_DUMMY_PASSWORD = "password"
_DUMMY_HASH = PasswordHash.recommended().hash(_DUMMY_PASSWORD)


class AuthService:
    def __init__(
        self,
        db: Session,
        user_repository: UserRepository,
        password_hash: PasswordHash,
    ):
        self.db = db
        self.user_repository = user_repository
        self.password_hash = password_hash

    def create_account(self, data: UserCreate) -> UserRead:
        with self.db.begin():
            try:
                password_hash = self._get_password_hash(data.password)
                user = self.user_repository.create_user(
                    UserCreateSave(email=data.email, password_hash=password_hash)
                )
            except IntegrityError as e:
                if self._constraint_name(e) == "uq_users_email":
                    raise UserAlreadyExistsError(
                        f"User with email {data.email} already exists"
                    ) from e
                raise
        self.db.refresh(user)
        return UserRead.model_validate(user)

    def login(self, email: str, password: str) -> TokenResponse:
        user = self._authenticate(email, password)
        if user is None:
            raise InvalidCredentialsError("Incorrect email or password")
        return TokenResponse(access_token=self._create_access_token(user.id), token_type="bearer")

    def _get_password_hash(self, password: str) -> str:
        return self.password_hash.hash(password)

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return self.password_hash.verify(plain_password, hashed_password)

    def _authenticate(self, email: str, password: str) -> User | None:
        email = email.strip().lower()
        user = self.user_repository.get_user_by_email(email)
        if user is None:
            self._verify_password(password, _DUMMY_HASH)
            return
        if not self._verify_password(password, user.password_hash):
            return
        return user

    def _create_access_token(self, user_id: int) -> str:
        expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
        payload = TokenPayload(sub=f"user:{user_id}", exp=expire)
        encoded_jwt = jwt.encode(payload.model_dump(), settings.jwt_secret, algorithm=settings.jwt_algorithm)
        return encoded_jwt

    @staticmethod
    def _constraint_name(e: IntegrityError) -> str | None:
        # e.orig is the raw driver error; only psycopg errors carry .diag —
        # getattr keeps this None-safe and mypy-clean for other error shapes.
        diag = getattr(e.orig, "diag", None)
        return getattr(diag, "constraint_name", None)
