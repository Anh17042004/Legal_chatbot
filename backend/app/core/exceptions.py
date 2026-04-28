from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses  import JSONResponse
from app.core.logger import logger

class BaseAppException(Exception):
    def __init__(self, status_code: int, message: str, error_code: str = "INTERNAL_ERROR"):
        self.status_code = status_code
        self.message = message
        self.error_code = error_code

# Lỗi Hệ thống
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Lỗi không xác định tại {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"error_code": "SYSTEM_CRASH", "message": "Lỗi hệ thống nghiêm trọng."}
    )

# Lỗi nghiệp vụ
async def app_exception_handler(request: Request, exc: BaseAppException):
    logger.warning(f"AppException: {exc.error_code} - {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": exc.error_code, "message": exc.message}
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error tại {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "Dữ liệu gửi lên không hợp lệ.",
            "detail": exc.errors(),
        },
    )
