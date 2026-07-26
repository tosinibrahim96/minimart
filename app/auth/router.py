"""HTTP layer: parses requests, declares dependencies, calls the service, maps
results/domain errors to status codes. Decides nothing on its own."""

from fastapi import APIRouter, HTTPException, status

from app.auth.dependencies import AuthServiceDep
from app.auth.exceptions import UserAlreadyExistsError
from app.auth.schemas import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, service: AuthServiceDep) -> UserRead:
    try:
        return service.create_account(data)
    except UserAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
