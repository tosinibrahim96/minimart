from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security.oauth2 import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt import ExpiredSignatureError
from pwdlib import PasswordHash
from pydantic import ValidationError

from app.auth.exceptions import (
    ExpiredTokenError,
    ForbiddenError,
    InvalidSubjectError,
    InvalidTokenError,
)
from app.auth.repository import UserRepository
from app.auth.schemas import (
    TokenPayload,
    UserRead,
)
from app.auth.service import AuthService
from app.common.dependencies import DbSession
from app.core.config import settings


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


Oauth2PasswordRequestFormDep = Annotated[OAuth2PasswordRequestForm, Depends()]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
Oauth2BearerTokenDep = Annotated[str, Depends(oauth2_scheme)]


def parse_bearer_token(token: Oauth2BearerTokenDep) -> TokenPayload:
    try:
        invalid_token_error_message = "The access token is invalid"
        expired_token_error_message = "The access token expired"
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return TokenPayload.model_validate(payload)
    except ExpiredSignatureError as e:
        raise ExpiredTokenError(expired_token_error_message) from e
    except (ValidationError, jwt.InvalidTokenError) as e:
        raise InvalidTokenError(invalid_token_error_message) from e


TokenPayloadDep = Annotated[TokenPayload, Depends(parse_bearer_token)]


def get_current_user(
    token_payload: TokenPayloadDep, user_repository: UserRepositoryDep
) -> UserRead:
    user_id = _get_user_id_from_payload(token_payload)
    user = user_repository.get_user_by_id(user_id)
    if user is None:
        raise InvalidTokenError("The access token is invalid")
    return UserRead.model_validate(user)


CurrentUserDep = Annotated[UserRead, Depends(get_current_user)]


def get_admin_user(current_user: CurrentUserDep) -> UserRead:
    if current_user.is_admin:
        return current_user
    else:
        raise ForbiddenError("The user is not authorized to access this resource")


AdminUserDep = Annotated[UserRead, Depends(get_admin_user)]


def _get_user_id_from_payload(token_payload: TokenPayload) -> int:
    try:
        error_message = "Invalid subject"
        sub = token_payload.sub
        check_sub = sub.split(":")
        if len(check_sub) != 2 or check_sub[0] != "user":
            raise InvalidSubjectError(error_message)
        return int(check_sub[1])
    except ValueError as e:
        raise InvalidSubjectError(error_message) from e
