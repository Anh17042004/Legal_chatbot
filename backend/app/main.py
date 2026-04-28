import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logger import setup_logging, logger
from app.core.exceptions import BaseAppException, app_exception_handler, global_exception_handler, validation_exception_handler
from app.api.v1.router import api_router
from app.services.lightrag_orchestrator import rag_orchestrator
from app.infrastructure.cache.redis_client import redis_client
from app.services.prompt_manager import prompt_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Chạy trước khi server bật
    setup_logging()
    logger.info(f"🚀 Bật ứng dụng {settings.PROJECT_NAME} v{settings.VERSION}")
    await redis_client.connect() #kết nối redis
    await rag_orchestrator.initialize() # kích hoạt lightrag
    prompt_manager.load_prompts() # load_prompt
    yield
    # Chạy khi server tắt
    await redis_client.disconnect()
    logger.info("🛑 Tắt server an toàn.")


app = FastAPI(
    title = settings.PROJECT_NAME,
    version = settings.VERSION,
    lifespan = lifespan
)

# Cấu hình bảo mật kết nối
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],  # cho phép mọi domain truy cập
    allow_credentials=True, # cho phép gửi credentials,
    allow_methods = ["*"], # cho phép http method
    allow_headers = ["*"]
)

# Đăng ký Router V1 vào FastAPI
app.include_router(api_router, prefix=settings.API_V1_STR)

# đăng ký hàm bắt lỗi
app.add_exception_handler(BaseAppException, app_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# api test
@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION
    }

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        reload=settings.DEBUG
    )