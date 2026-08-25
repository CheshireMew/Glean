from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class OperationLeaseIdentity:
    name: str
    owner_id: str


_current_operation_lease: ContextVar[OperationLeaseIdentity | None] = ContextVar(
    "current_operation_lease",
    default=None,
)


def current_operation_lease() -> OperationLeaseIdentity | None:
    return _current_operation_lease.get()


@contextmanager
def bind_operation_lease(name: str, owner_id: str):
    token = _current_operation_lease.set(OperationLeaseIdentity(name=name, owner_id=owner_id))
    try:
        yield
    finally:
        _current_operation_lease.reset(token)
