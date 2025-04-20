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
    # Add other settings variables here as needed


@lru_cache()
def get_settings() -> Settings:
    return Settings()
