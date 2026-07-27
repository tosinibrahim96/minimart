"""HTTP layer: parses requests, declares dependencies, calls the service, maps
results/domain errors to status codes. Decides nothing on its own."""

from fastapi import APIRouter, HTTPException, status

from app.auth.dependencies import AuthServiceDep, Oauth2PasswordRequestFormDep
from app.auth.exceptions import InvalidCredentialsError, UserAlreadyExistsError
from app.auth.schemas import TokenResponse, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, service: AuthServiceDep) -> UserRead:
    try:
        return service.create_account(data)
    except UserAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def login(data: Oauth2PasswordRequestFormDep, service: AuthServiceDep) -> TokenResponse:
    try:
        return service.login(data.username, data.password)
    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
