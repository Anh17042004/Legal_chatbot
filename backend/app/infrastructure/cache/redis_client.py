import redis.asyncio as redis
from app.core.config import settings
from app.core.logger import logger

class RedisClient:
    def __init__(self):
        self.redis = None
    
    async def connect(self):
        logger.info("🔌 Đang kết nối tới Redis...")
        self.redis = redis.from_url(settings.REDIS_URI, decode_responses=True)

        # test kết nối
        await self.redis.ping()
        logger.info("✅ Redis đã sẵn sàng!")

    async def disconnect(self):
        if self.redis:
            await self.redis.close()
            logger.info("🛑 Đã ngắt kết nối Redis.")

redis_client = RedisClient()

