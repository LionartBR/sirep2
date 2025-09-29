from __future__ import annotations

try:  # pragma: no cover - integração opcional
    from pw3270 import emulator as _emulator
except Exception:  # pragma: no cover - ambiente sem dependência
    PW3270 = None
else:  # pragma: no cover - execução real
    PW3270 = getattr(_emulator, "PW3270", None)


__all__ = ["PW3270"]
