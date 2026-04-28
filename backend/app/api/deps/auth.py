from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.infrastructure.database.models import User
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.auth_service import AccessTokenData, auth_service

bearer_scheme = HTTPBearer(auto_error=False)


def get_token_credentials(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> HTTPAuthorizationCredentials:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thiếu Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization phải dùng Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials


def get_current_token_data(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(get_token_credentials)],
) -> AccessTokenData:
    try:
        return auth_service.verify_access_token(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ hoặc đã hết hạn",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def get_current_user_id(
    token_data: Annotated[AccessTokenData, Depends(get_current_token_data)],
) -> int:
    try:
        return int(token_data.subject)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không chứa user hợp lệ",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


async def get_current_user(
    user_id: Annotated[int, Depends(get_current_user_id)],
) -> User:
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Người dùng không tồn tại",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tài khoản đã bị khóa",
            )

        return user


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền truy cập",
        )

    return current_user
