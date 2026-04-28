import json
from app.infrastructure.cache.redis_client import redis_client
from app.core.logger import logger
from app.services.audit_service import audit_service


class ChatHistoryService:
    def __init__(self):
        self.ttl = 86400  # Lưu lịch sử 24 giờ (giây)
        self.limit_history = 10

    async def get_history(self, session_id: str) -> list:
        if not session_id:
            return []
            
        key = f"session:{session_id}"
        history_json = await redis_client.redis.get(key)
        
        if history_json:
            return json.loads(history_json)
        postgres_messages = await audit_service.get_latest_message(session_id, self.limit_history)
        await redis_client.redis.setex(key, self.ttl, json.dumps(postgres_messages))
        return postgres_messages


    async def add_message(self, session_id: str, role: str, content: str):
        if not session_id:
            return
            
        key = f"session:{session_id}"
        history = await self.get_history(session_id)
        
        # Thêm tin nhắn mới
        history.append({"role": role, "content": content})
        
        # Cắt bớt nếu quá dài
        if len(history) > self.limit_history:
            history = history[-self.limit_history:]
            
        # Lưu lại vào Redis
        await redis_client.redis.setex(key, self.ttl, json.dumps(history))

chat_history = ChatHistoryService()