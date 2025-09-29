from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, Optional


def only_digits(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


def parse_date_any(raw: str | None) -> Optional[date]:
    texto = (raw or "").strip()
    if not texto:
        return None
    formatos = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")
    for fmt in formatos:
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def parse_money_brl(raw: Any | None) -> float:
    if raw is None:
        return math.nan
    texto = str(raw)
    negativo = "(" in texto and ")" in texto
    limpo = re.sub(r"[^\d.,-]", "", texto)
    limpo = limpo.replace(".", "").replace(",", ".")
    try:
        valor = float(limpo)
    except ValueError:
        return math.nan
    return -valor if negativo else valor
