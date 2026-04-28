from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, ConfigDict


class AuditLogItem(BaseModel):
    id: int
    user_id: Optional[int]
    session_id: str
    user_query: str
    rewritten_query: Optional[str]
    bot_response: str
    references: Optional[List[Dict[str, Any]]]
    processing_time: Optional[float]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogDashboardResponse(BaseModel):
    total: int
    page: int
    size: int
    total_pages: int
    data: List[AuditLogItem]


class AdminSummaryResponse(BaseModel):
    total_users: int
    active_users: int
    total_sessions: int
    total_audit_logs: int
    recent_logs: List[AuditLogItem]


class AuditLogUpdate(BaseModel):
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    user_query: Optional[str] = None
    rewritten_query: Optional[str] = None
    bot_response: Optional[str] = None
    references: Optional[List[Dict[str, Any]]] = None
    processing_time: Optional[float] = None
