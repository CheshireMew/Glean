
class APIException(Exception):
    def __init__(
        self,
        message: str,
        code: int = 400,
        error_type: str | None = None,
        *,
        headers: dict | None = None,
    ):
        self.message = message
        self.code = code
        self.error_type = error_type or self.__class__.__name__
        self.headers = headers or {}
        super().__init__(self.message)


class ValidationError(APIException):
    def __init__(self, message: str, details: dict | None = None):
        self.details = details
        super().__init__(message, code=400, error_type="ValidationError")


class NotFoundError(APIException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, code=404, error_type="NotFoundError")


class DatabaseError(APIException):
    def __init__(self, message: str):
        super().__init__(message, code=500, error_type="DatabaseError")


class ConfigurationError(APIException):
    def __init__(self, message: str = "系统配置不完整"):
        super().__init__(message, code=503, error_type="ConfigurationError")


class AuthenticationError(APIException):
    def __init__(self, message: str = "认证失败", *, headers: dict | None = None):
        super().__init__(message, code=401, error_type="AuthenticationError", headers=headers)


class PermissionError(APIException):
    def __init__(self, message: str = "权限不足"):
        super().__init__(message, code=403, error_type="PermissionError")


class BusinessError(APIException):
    def __init__(self, message: str):
        super().__init__(message, code=400, error_type="BusinessError")


class ConflictError(APIException):
    def __init__(self, message: str):
        super().__init__(message, code=409, error_type="ConflictError")


class ServiceUnavailableError(APIException):
    def __init__(self, message: str):
        super().__init__(message, code=503, error_type="ServiceUnavailableError")
