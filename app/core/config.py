from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unrelated env vars instead of erroring
    )

    database_url: str  # populated from the DATABASE_URL env var
    jwt_secret: str  # populated from the JWT_SECRET env var
    jwt_access_token_expire_minutes: int = (
        15  # populated from the JWT_ACCESS_TOKEN_EXPIRE_MINUTES env var
    )
    jwt_algorithm: str = "HS256"  # populated from the JWT_ALGORITHM env var
    admin_email: str | None = None  # populated from the ADMIN_EMAIL env var
    admin_password: str | None = None  # populated from the ADMIN_PASSWORD env var


settings = Settings()  # one instance, imported wherever config is needed
