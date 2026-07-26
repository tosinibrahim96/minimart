"""Business logic: decides *what* should happen, owns the transaction boundary,
raises domain exceptions (never HTTPException)."""

from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.exceptions import UserAlreadyExistsError
from app.auth.models import User
from app.auth.repository import UserRepository
from app.auth.schemas import UserCreate, UserCreateSave, UserRead

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

    def _get_password_hash(self, password: str) -> str:
        return self.password_hash.hash(password)

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return self.password_hash.verify(plain_password, hashed_password)

    def _authenticate(self, email: str, password: str) -> User | None:
        user = self.user_repository.get_user_by_email(email)
        if user is None:
            self._verify_password(password, _DUMMY_HASH)
            return
        if not self._verify_password(password, user.password_hash):
            return
        return user

    @staticmethod
    def _constraint_name(e: IntegrityError) -> str | None:
        # e.orig is the raw driver error; only psycopg errors carry .diag —
        # getattr keeps this None-safe and mypy-clean for other error shapes.
        diag = getattr(e.orig, "diag", None)
        return getattr(diag, "constraint_name", None)
