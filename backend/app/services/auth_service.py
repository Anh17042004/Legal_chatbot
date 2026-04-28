import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid

import jwt

from app.core.config import settings


@dataclass(frozen=True)
class AccessTokenData:
    subject: str
    issued_at: int
    expires_at: int


class AuthService:
    @staticmethod
    def hash_password(password: str) -> str:
        pepper = settings.AUTH_SECRET_KEY.encode("utf-8")
        digest = hmac.new(pepper, password.encode("utf-8"), hashlib.sha256).hexdigest()
        return digest

    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        expected = AuthService.hash_password(password)
        return secrets.compare_digest(expected, hashed_password)

    @staticmethod
    def create_access_token(subject: str) -> str:
        now = datetime.now(timezone.utc)
        expires_delta = timedelta(seconds=settings.ACCESS_TOKEN_TTL_SECONDS)
        payload = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int((now + expires_delta).timestamp()),
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(payload, settings.AUTH_SECRET_KEY, algorithm="HS256")


    @staticmethod
    def verify_access_token(token: str) -> AccessTokenData:
        try:
            payload = jwt.decode(
                token,
                settings.AUTH_SECRET_KEY,
                algorithms=["HS256"],
                options={
                    "require": ["sub", "iat", "exp"]
                },
            )
            return AccessTokenData(
                subject=str(payload["sub"]),
                issued_at=int(payload["iat"]),
                expires_at=int(payload["exp"]),
            )
        except (
            jwt.ExpiredSignatureError,
            jwt.InvalidTokenError,
            KeyError,
            TypeError,
            ValueError,
        ):
            raise ValueError("Token khong hop le") from None


auth_service = AuthService()