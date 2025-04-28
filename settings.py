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

    # Stripe billing settings
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_price_id_50_credits: Optional[str] = None

    # Add other settings variables here as needed
    # Application base URL (for constructing callback URLs etc.)
    app_base_url: str = "http://localhost:8000"  # Default for local dev


@lru_cache()
def get_settings() -> Settings:
    return Settings()
