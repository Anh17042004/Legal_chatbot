from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_

from app.domain.schemas.user import UserResponse, UserAdminUpdate, UserListResponse
from app.infrastructure.database.models import User
from app.infrastructure.database.session import AsyncSessionLocal
from app.services.auth_service import auth_service
from app.api.deps.auth import require_admin

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="Số trang hiện tại"),
    size: int = Query(20, ge=1, le=100, description="Số dòng trên 1 trang"),
    search: str | None = Query(None, description="Tìm theo email hoặc tên"),
):
    async with AsyncSessionLocal() as db:
        query = select(User)
        if search:
            term = f"%{search}%"
            query = query.where(or_(User.email.ilike(term), User.full_name.ilike(term)))

        total_items = await db.scalar(select(func.count()).select_from(query.subquery())) or 0

        result = await db.execute(
            query.order_by(User.created_at.desc()).offset((page - 1) * size).limit(size)
        )
        users = result.scalars().all()
        return {
            "total": total_items,
            "page": page,
            "size": size,
            "total_pages": (total_items + size - 1) // size if total_items > 0 else 1,
            "data": [UserResponse.model_validate(user) for user in users],
        }


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int):
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy user")
        return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, request: UserAdminUpdate):
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy user")

        updates = request.model_dump(exclude_unset=True)
        password = updates.pop("password", None)

        if "email" in updates:
            email_owner = await db.scalar(select(User).where(User.email == updates["email"], User.id != user_id))
            if email_owner:
                raise HTTPException(status_code=400, detail="Email đã được sử dụng")

        for field, value in updates.items():
            setattr(user, field, value)

        if password:
            user.hashed_password = auth_service.hash_password(password)

        await db.commit()
        await db.refresh(user)
        return UserResponse.model_validate(user)


@router.delete("/{user_id}")
async def delete_user(user_id: int):
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Không tìm thấy user")

        await db.delete(user)
        await db.commit()
        return {"message": "Xóa user thành công"}
