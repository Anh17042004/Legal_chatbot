from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class ChatRequest(BaseModel):
    message: str = Field(description="Câu hỏi pháp lý của người dùng")
    mode: str = Field(default="mix", description="Chế độ query: mix, local, global, hybrid, naive")
    session_id: Optional[str] = Field(default=None, description="ID phiên chat")


class ReferenceItem(BaseModel):
    reference_id: Optional[str] = None
    file_path: Optional[str] = None
    url: Optional[str] = None
    label: Optional[str] = None
    content: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    response: str
    references: List[ReferenceItem] = Field(default_factory=list)


class ChatHistoryItem(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]]


class ChatSessionItem(BaseModel):
    session_id: str
    title: str
    updated_at: datetime
    message_count: int


class ChatSessionListResponse(BaseModel):
    data: List[ChatSessionItem]



