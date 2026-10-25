from pydantic_settings import BaseSettings, SettingsConfigDict


INSECURE_SECRET_PLACEHOLDER = "replace-with-a-long-random-secret"


class Settings(BaseSettings):
    database_path: str = "data/foodloop.db"
    default_safety_buffer: float = 0.05
    forecast_lookback_days: int = 28
    auth_secret_key: str = ""
    auth_token_minutes: int = 30
    upload_max_bytes: int = 5_000_000
    upload_max_rows: int = 50_000
    upload_max_columns: int = 32
    upload_preview_rows: int = 100

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FOODLOOP_", extra="ignore")


settings = Settings()


def validate_security_configuration() -> None:
    secret = settings.auth_secret_key
    if (
        not isinstance(secret, str)
        or not secret
        or secret == INSECURE_SECRET_PLACEHOLDER
        or len(secret) < 32
    ):
        raise RuntimeError(
            "FOODLOOP_AUTH_SECRET_KEY must be a random value of at least 32 characters."
        )
    if (
        isinstance(settings.auth_token_minutes, bool)
        or not isinstance(settings.auth_token_minutes, int)
        or settings.auth_token_minutes <= 0
    ):
        raise RuntimeError("FOODLOOP_AUTH_TOKEN_MINUTES must be a positive integer.")
