from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # `.env.prod` takes priority over `.env`
        env_file=(".env", ".env.prod")
    )

    openrouter_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Cognito Settings (Optional for local dev)
    cognito_user_pool_id: Optional[str] = None
    cognito_app_client_id: Optional[str] = None
    cognito_domain: Optional[str] = None
    aws_region: Optional[str] = None

    # Add other settings variables here as needed


@lru_cache()
def get_settings() -> Settings:
    return Settings()
