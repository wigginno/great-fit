"""Authentication helpers integrating AWS Cognito JWTs.

This module provides a FastAPI dependency ``get_current_user`` that:
1. Extracts the ``Authorization: Bearer <id_token>`` header.
2. Downloads / caches the JSON Web Key Set (JWKS) for your Cognito User Pool.
3. Verifies signature, expiration and audience.
4. Creates or fetches a ``models.User`` database row on-the-fly.

Environment variables expected at runtime (injected via App Runner / Docker):
    COGNITO_USER_POOL_ID     - e.g. "us-east-1_abcd1234"
    COGNITO_APP_CLIENT_ID    - the user-pool client facing ID (audience)
    AWS_REGION               - pool region (falls back to us-east-1)

If any variable is missing the dependency raises 500 to signal mis-config.
"""
from __future__ import annotations

import os
import logging
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, status
from jose import jwt, JWTError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
import crud

logger = logging.getLogger(__name__)


class TokenPayload(BaseModel):
    sub: str
    email: str | None = None
    exp: int
    aud: str


class AuthSettings(BaseModel):
    region: str
    user_pool_id: str
    client_id: str

    @property
    def issuer(self) -> str:  # cognito issuer URL
        return f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"


@lru_cache
def _load_settings() -> AuthSettings:
    region = os.getenv("AWS_REGION", "us-east-1")
    user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
    client_id = os.getenv("COGNITO_APP_CLIENT_ID")
    if not user_pool_id or not client_id:
        raise RuntimeError(
            "Missing COGNITO_USER_POOL_ID or COGNITO_APP_CLIENT_ID env vars"
        )
    return AuthSettings(region=region, user_pool_id=user_pool_id, client_id=client_id)


@lru_cache
def _get_jwks():
    settings = _load_settings()
    logger.info("Fetching JWKS from %s", settings.jwks_url)
    resp = httpx.get(settings.jwks_url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _verify_token(token: str) -> TokenPayload:
    settings = _load_settings()
    jwks = _get_jwks()

    try:
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=settings.client_id,
            issuer=settings.issuer,
        )
        return TokenPayload.model_validate(payload)
    except JWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# --- FastAPI dependency ---
UserInDB = dict  # alias for crud.User object but avoid circular import typing

async def get_current_user(
    authorization: Annotated[str | None, Depends(lambda request: request.headers.get("Authorization"))],
    db: Session = Depends(get_db),
) -> UserInDB:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ")[1]
    payload = _verify_token(token)

    # Upsert user in DB
    user = crud.get_user_by_email(db, payload.email or payload.sub)
    if not user:
        user = crud.create_user(db, crud.schemas.UserCreate(email=payload.email or payload.sub))
        db.commit()
    return user
