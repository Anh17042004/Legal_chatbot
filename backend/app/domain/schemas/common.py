from pydantic import BaseModel
from typing import Any, Optional

class SuccessResponse(BaseModel):
    status: str = "success"
    message: str
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str
    detail: Optional[str] = None