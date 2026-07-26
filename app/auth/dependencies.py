from typing import Annotated

from fastapi import Depends
from pwdlib import PasswordHash

from app.auth.repository import UserRepository
from app.auth.service import AuthService
from app.common.dependencies import DbSession


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)


def get_password_hash() -> PasswordHash:
    return PasswordHash.recommended()


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
PasswordHashDep = Annotated[PasswordHash, Depends(get_password_hash)]


def get_auth_service(
    db: DbSession,
    user_repository: UserRepositoryDep,
    password_hash: PasswordHashDep,
) -> AuthService:
    return AuthService(db, user_repository, password_hash)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
