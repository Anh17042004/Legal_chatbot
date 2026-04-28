from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8)

class UserAdminUpdate(UserUpdate):
    credits: Optional[int] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    
class UserResponse(UserBase):
    id: int
    credits: int
    role: str
    is_active: bool
    created_at: datetime

    # Thêm model này để khi trả về JSON cho Frontend, 2 trường credits/role không bị lẫn với password_hash
    model_config = ConfigDict(
        from_attributes=True  # Quan trọng để đọc từ SQLAlchemy model
    )


class UserListResponse(BaseModel):
    total: int
    page: int
    size: int
    total_pages: int
    data: List[UserResponse]
    