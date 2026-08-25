from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from pydantic import BaseModel, ConfigDict


class CLIErrorBody(BaseModel):
    type: str
    details: Any = None


class CLIMeta(BaseModel):
    app_version: str
    environment: str
    duration_ms: float


class CLIEnvelope(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    contract_version: int
    success: bool
    command: str | None
    data: Any = None
    message: str
    error: CLIErrorBody | None = None
    meta: CLIMeta


@dataclass(frozen=True)
class ArgumentSpec:
    names: tuple[str, ...]
    kwargs: dict[str, Any]


@dataclass(frozen=True)
class CommandSpec:
    command_id: str
    path: tuple[str, ...]
    help: str
    handler: Callable
    arguments: Sequence[ArgumentSpec] = ()
    input_model: type[BaseModel] | None = None
    input_required: bool = False
    output_schema: dict[str, Any] | None = None
    database_mode: str = "ready"
    requires_worker: bool = False
    requires_yes: bool = False


@dataclass
class CommandResult:
    data: Any = None
    message: str = "操作成功"


class CommandContext:
    def __init__(self, registry: Sequence[CommandSpec]) -> None:
        self.registry = tuple(registry)
        self._settings = None
        self._services = None
        self._database = None

    @property
    def settings(self):
        if self._settings is None:
            from backend.app.core.config import settings

            self._settings = settings
        return self._settings

    @property
    def services(self):
        if self._services is None:
            from backend.app.composition import app_services

            self._services = app_services
        return self._services

    @property
    def database(self):
        if self._database is None:
            from backend.app.infrastructure.database import database

            self._database = database
        return self._database

    @staticmethod
    def project_root() -> Path:
        return Path(__file__).resolve().parents[2]
