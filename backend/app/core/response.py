
from datetime import datetime, timezone
from typing import Generic, TypeVar
from pydantic import BaseModel, JsonValue

T = TypeVar("T")


class APIErrorBody(BaseModel):
    type: str
    details: JsonValue | None = None


class PaginationBody(BaseModel):
    total: int
    page: int
    limit: int
    pages: int


class APIEnvelope(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    message: str
    code: int
    timestamp: datetime
    pagination: PaginationBody | None = None
    error: APIErrorBody | None = None


ErrorEnvelope = APIEnvelope[None]


class APIResponse:
    @staticmethod
    def success(data: object | None = None, message: str = "操作成功", code: int = 200):
        return {
            "success": True,
            "data": data,
            "message": message,
            "code": code,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    @staticmethod
    def error(message: str, code: int = 400, error_type: str | None = None, details: JsonValue | None = None):
        return {
            "success": False,
            "data": None,
            "message": message,
            "code": code,
            "error": {
                "type": error_type or "Error",
                "details": details,
            },
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    @staticmethod
    def paginated(data: list[object], total: int, page: int, limit: int, message: str = "查询成功"):
        return {
            "success": True,
            "data": data,
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit if limit > 0 else 0,
            },
            "message": message,
            "code": 200,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
