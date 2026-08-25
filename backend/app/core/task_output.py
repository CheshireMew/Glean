from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import io
import sys
from typing import Callable, Iterator


_sink: ContextVar[Callable[[str], None] | None] = ContextVar("task_output_sink", default=None)
_buffer: ContextVar[str] = ContextVar("task_output_buffer", default="")


class _ContextOutput(io.TextIOBase):
    def __init__(self, original):
        self.original = original

    @property
    def encoding(self):
        return self.original.encoding

    def write(self, value: str) -> int:
        written = self.original.write(value)
        sink = _sink.get()
        if sink is None:
            return written
        buffer = _buffer.get() + value
        lines = buffer.split("\n")
        _buffer.set(lines.pop())
        for line in lines:
            normalized = line.rstrip("\r")
            if normalized:
                sink(normalized)
        return written

    def flush(self) -> None:
        self.original.flush()

    def isatty(self) -> bool:
        return self.original.isatty()


def install_context_output() -> None:
    if not isinstance(sys.stdout, _ContextOutput):
        sys.stdout = _ContextOutput(sys.stdout)
    if not isinstance(sys.stderr, _ContextOutput):
        sys.stderr = _ContextOutput(sys.stderr)


@contextmanager
def capture_task_output(sink: Callable[[str], None]) -> Iterator[None]:
    install_context_output()
    sink_token = _sink.set(sink)
    buffer_token = _buffer.set("")
    try:
        yield
    finally:
        trailing = _buffer.get().strip()
        if trailing:
            sink(trailing)
        _buffer.reset(buffer_token)
        _sink.reset(sink_token)
