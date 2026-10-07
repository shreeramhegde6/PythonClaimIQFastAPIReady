import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from claimiq.config import get_settings
from claimiq.db import get_db
from claimiq.models import RefreshToken, User


password_hash = PasswordHash.recommended()

# Swagger will now ask only for the JWT bearer token.
bearer_scheme = HTTPBearer()


def hash_password(value: str) -> str:
    return password_hash.hash(value)


def verify_password(value: str, hashed: str) -> bool:
    return password_hash.verify(value, hashed)


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)

    payload = {
        "sub": user.id,
        "iat": now,
        "exp": now
        + timedelta(minutes=settings.access_token_minutes),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm="HS256",
    )


def create_refresh_token(
    db: Session,
    user: User,
) -> str:
    raw_token = secrets.token_urlsafe(48)

    token_hash = hashlib.sha256(
        raw_token.encode()
    ).hexdigest()

    refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=get_settings().refresh_token_days),
    )

    db.add(refresh_token)
    db.commit()

    return raw_token


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:
    try:
        token = credentials.credentials

        payload = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=["HS256"],
        )

        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
            )

        user = db.get(User, user_id)

    except HTTPException:
        raise

    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
        ) from exc

    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        ) from exc

    if not user or not user.active:
        raise HTTPException(
            status_code=401,
            detail="Inactive or unavailable user",
        )

    return user


def require_roles(*roles):
    def dependency(
        user: User = Depends(current_user),
    ) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permission",
            )

        return user

    return dependency