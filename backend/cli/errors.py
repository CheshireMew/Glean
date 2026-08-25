from __future__ import annotations

from typing import Any


class CLIError(Exception):
    def __init__(
        self,
        message: str,
        *,
        exit_code: int = 1,
        error_type: str | None = None,
        details: Any = None,
        data: Any = None,
    ) -> None:
        self.message = message
        self.exit_code = exit_code
        self.error_type = error_type or type(self).__name__
        self.details = details
        self.data = data
        super().__init__(message)


class CLIUsageError(CLIError):
    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message, exit_code=2, error_type="UsageError", details=details)


class CLINotFoundError(CLIError):
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=3, error_type="NotFoundError")


class CLIConflictError(CLIError):
    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message, exit_code=4, error_type="ConflictError", details=details)


class CLIUnavailableError(CLIError):
    def __init__(self, message: str, *, details: Any = None, data: Any = None) -> None:
        super().__init__(
            message,
            exit_code=5,
            error_type="ServiceUnavailableError",
            details=details,
            data=data,
        )


class CLIIncompleteError(CLIError):
    def __init__(self, message: str, *, details: Any = None, data: Any = None) -> None:
        super().__init__(
            message,
            exit_code=6,
            error_type="IncompleteOperation",
            details=details,
            data=data,
        )


class CLITimeoutError(CLIError):
    def __init__(self, message: str, *, data: Any = None) -> None:
        super().__init__(message, exit_code=124, error_type="TimeoutError", data=data)
