from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_, distinct
from app.infrastructure.database.session import AsyncSessionLocal
from app.infrastructure.database.models import AuditLog, User
from app.domain.schemas.admin import AdminSummaryResponse, AuditLogDashboardResponse, AuditLogItem, AuditLogUpdate
from app.api.deps.auth import require_admin

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/summary", response_model=AdminSummaryResponse)
async def get_admin_summary():
    async with AsyncSessionLocal() as db:
        total_users = await db.scalar(select(func.count()).select_from(User)) or 0
        active_users = await db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0
        total_audit_logs = await db.scalar(select(func.count()).select_from(AuditLog)) or 0
        total_sessions = await db.scalar(
            select(func.count(distinct(AuditLog.session_id))).select_from(AuditLog)
        ) or 0

        recent_stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(5)
        recent_result = await db.execute(recent_stmt)
        recent_logs = recent_result.scalars().all()

        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_sessions": total_sessions,
            "total_audit_logs": total_audit_logs,
            "recent_logs": [AuditLogItem.model_validate(log) for log in recent_logs],
        }

@router.get("/audit-logs", response_model=AuditLogDashboardResponse)
async def get_audit_logs(
    page: int = Query(1, ge=1, description="Số trang     hiện tại"),
    size: int = Query(20, ge=1, le=100, description="Số dòng trên 1 trang"),
    search: str | None = Query(None, description="Từ khóa tìm kiếm")
):
    async with AsyncSessionLocal() as db:
        try:
            query = select(AuditLog)
            if search:
                search_term = f"%{search}%"
                query = query.where(
                    or_(
                        AuditLog.session_id.ilike(search_term),
                        AuditLog.user_query.ilike(search_term)
                    )
                )
            count_stmt = select(func.count()).select_from(query.subquery())
            total_items = await db.scalar(count_stmt)
            stmt = query.order_by(AuditLog.created_at.desc()) \
                        .offset((page - 1) * size) \
                        .limit(size)
            
            result = await db.execute(stmt)
            logs = result.scalars().all()
            items = [AuditLogItem.model_validate(log) for log in logs]
            return {
                "total": total_items,
                "page": page,
                "size": size,
                "total_pages": (total_items + size - 1) // size if total_items > 0 else 1,
                "data": items
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi DB: {str(e)}")


@router.get("/dashboards", response_model=AuditLogDashboardResponse)
async def get_audit_logs_dashboard_compat(
    page: int = Query(1, ge=1, description="Số trang hiện tại"),
    size: int = Query(20, ge=1, le=100, description="Số dòng trên 1 trang"),
    search: str | None = Query(None, description="Từ khóa tìm kiếm"),
):
    # Giữ tương thích route cũ cho frontend hiện tại
    return await get_audit_logs(page=page, size=size, search=search)


@router.get("/audit-logs/{log_id}", response_model=AuditLogItem)
async def get_audit_log(log_id: int):
    async with AsyncSessionLocal() as db:
        log = await db.get(AuditLog, log_id)
        if not log:
            raise HTTPException(status_code=404, detail="Không tìm thấy audit log")
        return AuditLogItem.model_validate(log)


@router.patch("/audit-logs/{log_id}", response_model=AuditLogItem)
async def update_audit_log(log_id: int, payload: AuditLogUpdate):
    async with AsyncSessionLocal() as db:
        log = await db.get(AuditLog, log_id)
        if not log:
            raise HTTPException(status_code=404, detail="Không tìm thấy audit log")

        updates = payload.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(log, field, value)

        await db.commit()
        await db.refresh(log)
        return AuditLogItem.model_validate(log)


@router.delete("/audit-logs/{log_id}")
async def delete_audit_log(log_id: int):
    async with AsyncSessionLocal() as db:
        log = await db.get(AuditLog, log_id)
        if not log:
            raise HTTPException(status_code=404, detail="Không tìm thấy audit log")

        await db.delete(log)
        await db.commit()
        return {"message": "Xóa audit log thành công"}