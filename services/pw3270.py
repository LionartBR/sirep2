from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class PW3270Protocol(Protocol):  # pragma: no cover - interface estática
    def connect(self, delay: int = ...) -> None: ...

    def is_connected(self) -> bool: ...

    def send_pf_key(self, key: int) -> None: ...

    def disconnect(self) -> None: ...

    def enter(self) -> None: ...

    def wait_status_ok(self) -> None: ...

    def put_string(self, row: int, col: int, text: str) -> None: ...

    def get_string(self, row: int, col: int, length: int) -> str | None: ...


try:  # pragma: no cover - integração opcional
    from pw3270 import emulator as _emulator
except Exception:  # pragma: no cover - ambiente sem dependência
    PW3270: Optional[type[PW3270Protocol]] = None
else:  # pragma: no cover - execução real
    real_cls = getattr(_emulator, "PW3270", None)
    PW3270 = real_cls if isinstance(real_cls, type) else None


__all__ = ["PW3270", "PW3270Protocol"]
