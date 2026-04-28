import sys
from loguru import logger
from app.core.config import settings

def setup_logging():
    logger.remove()  #xóa log mặc định của python

    # format log hiển thị
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    logger.add(sys.stderr, format=log_format, level="DEBUG" if settings.DEBUG else "INFO")
    logger.info(f"Đã khởi tạo Logger. Môi trường: {settings.ENVIRONMENT}")


