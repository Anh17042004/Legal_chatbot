from sqlalchemy import select
from typing import Any

from app.infrastructure.database.models import AuditLog
from app.infrastructure.database.session import AsyncSessionLocal
from app.core.logger import logger

class AuditService:
    @staticmethod
    async def log_interaction(
        session_id: str,
        user_id: int | None,
        user_query: str,
        rewritten_query: str,
        bot_response: str,
        processing_time: float,
        references: list[dict[str, Any]] | None = None,
    ):
        async with AsyncSessionLocal() as db:
            try:
                new_log = AuditLog(
                    user_id=user_id,
                    session_id=session_id,
                    user_query=user_query,
                    rewritten_query=rewritten_query,
                    bot_response=bot_response,
                    processing_time=round(processing_time, 2),
                    references=references,
                )
                
                # Ném vào DB và lưu lại
                db.add(new_log)
                await db.commit()
                logger.info(f"✅ Đã lưu Audit Log cho Session: {session_id}")
                
            except Exception as e:
                await db.rollback()
                logger.error(f"❌ Lỗi khi lưu Audit Log: {str(e)}")

    @staticmethod
    async def session_belongs_to_user(session_id: str, user_id: int) -> bool:
        async with AsyncSessionLocal() as db:
            try:
                stmt = (
                    select(AuditLog.id)
                    .where(AuditLog.session_id == session_id, AuditLog.user_id == user_id)
                    .limit(1)
                )
                result = await db.execute(stmt)
                return result.first() is not None
            except Exception as e:
                logger.error(f"❌ Lỗi khi kiểm tra quyền truy cập session: {str(e)}")
                return False

    @staticmethod
    async def session_has_logs(session_id: str) -> bool:
        async with AsyncSessionLocal() as db:
            try:
                stmt = select(AuditLog.id).where(AuditLog.session_id == session_id).limit(1)
                result = await db.execute(stmt)
                return result.first() is not None
            except Exception as e:
                logger.error(f"❌ Lỗi khi kiểm tra session tồn tại: {str(e)}")
                return False


    @staticmethod
    async def get_latest_message(session_id: str, limit: int = 10)-> list:
        # lấy N tin nhắn gần nhất cho mỗi session_id
        async with AsyncSessionLocal() as db:
            try:
                stmt = (
                    select(AuditLog)
                    .where(AuditLog.session_id == session_id)
                    .order_by(AuditLog.created_at.desc())
                    .limit(limit)
                )
                result = await db.execute(stmt)
                audit_history = result.scalars().all()  # lấy ra toàn bộ object select được
                messages = []
                for history in reversed(audit_history):
                    messages.append({"role": "user", "content": history.user_query})
                    messages.append({"role": "assistant", "content": history.bot_response})
                return messages
            except Exception as e:
                logger.error(f"❌ Lỗi khi lấy Audit Log: {str(e)}")
                return []

audit_service = AuditService()