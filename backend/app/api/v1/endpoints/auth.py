from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select

from app.domain.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.domain.schemas.user import UserResponse
from app.infrastructure.database.models import User
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.auth_service import auth_service
from app.api.deps.auth import get_current_user

router = APIRouter()


@router.post("/register", response_model=UserResponse)
async def register(request: RegisterRequest):
    async with AsyncSessionLocal() as db:
        existing_user = await db.scalar(select(User).where(User.email == request.email))
        if existing_user:
            raise HTTPException(status_code=400, detail="Email đã tồn tại")

        user = User(
            email=request.email,
            full_name=request.full_name,
            hashed_password=auth_service.hash_password(request.password),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == request.email))
        if not user:
            raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")

        if not auth_service.verify_password(request.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Tài khoản của bạn đã bị khóa. Vui lòng liên hệ Admin.")

        token = auth_service.create_access_token(str(user.id))
        return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)
