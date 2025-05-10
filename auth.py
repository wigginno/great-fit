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
import structlog
from functools import lru_cache
from settings import get_settings
from typing import Annotated, Optional
import time

import httpx
from fastapi import Depends, HTTPException, status, Request
from jose import jwt, JWTError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
import crud

logger = structlog.get_logger(__name__)

# Authentication and billing toggle is now managed via settings.py (auth_billing_enabled)
class TokenPayload(BaseModel):
    sub: str
    email: Optional[str] = None
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
    if not get_settings().auth_billing_enabled:
        # In local-dev mode we won't actually call this, but keep function intact
        raise RuntimeError("Cognito auth disabled in local mode")
    return AuthSettings(region=region, user_pool_id=user_pool_id, client_id=client_id)


@lru_cache
def _get_jwks():
    settings = _load_settings()
    logger.info("Fetching JWKS", jwks_url=settings.jwks_url)
    resp = httpx.get(settings.jwks_url, timeout=10)
    resp.raise_for_status()
    return resp.json()


# Exposed for non-request contexts (e.g., SSE token in query)
def verify_token(token: str) -> TokenPayload:
    """Verify Cognito JWT and return payload.

    Raises HTTPException(401) on failure.
    """
    if not get_settings().auth_billing_enabled:
        # Return dummy payload for local usage
        return TokenPayload(
            sub="local-dev",
            email="local@example.com",
            exp=int(time.time()) + 3600,
            aud="local",
        )

    return _verify_token(token)

# Kept for backwards-compat internal usage
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
            options={"verify_at_hash": False},
        )
        return TokenPayload.model_validate(payload)
    except JWTError as exc:
        logger.warning("JWT verification failed", exc=str(exc))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# Helper to extract Authorization header (works with FastAPI DI)
def _get_authorization_header(request: Request) -> Optional[str]:
    return request.headers.get("Authorization")


# --- FastAPI dependency ---
UserInDB = dict  # alias for crud.User object but avoid circular import typing

async def get_current_user(
    authorization: Annotated[Optional[str], Depends(_get_authorization_header)],
    db: Session = Depends(get_db),
) -> UserInDB:
    if not get_settings().auth_billing_enabled:
        # Local dev: always return / create a default user
        email = "local@example.com"
        user = crud.get_user_by_email(db, email)
        if not user:
            user = crud.create_user(db, crud.schemas.UserCreate(email=email, cognito_sub="local-dev"))
            db.commit()
        return user

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ")[1]
    payload = _verify_token(token)

    # Upsert user in DB
    user = crud.get_user_by_email(db, payload.email or payload.sub)
    if not user:
        user = crud.create_user(
            db,
            crud.schemas.UserCreate(
                email=payload.email or payload.sub, cognito_sub=payload.sub
            ),
        )
        db.commit()
    return user
