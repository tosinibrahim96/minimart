from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",  # also read a local .env file if present
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unrelated env vars instead of erroring
    )

    database_url: str  # populated from the DATABASE_URL env var


settings = Settings()  # one instance, imported wherever config is needed
