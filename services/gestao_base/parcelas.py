from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any, Iterable, Optional

from .utils import parse_money_brl


def _first_non_empty(mapping: dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        if key not in mapping:
            continue
        raw = mapping.get(key)
        if raw is None:
            continue
        texto = str(raw).strip()
        if texto:
            return texto
    return None


def _first_present(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _parse_vencimento(raw: Any) -> tuple[Optional[date], Optional[str]]:
    if isinstance(raw, datetime):
        return raw.date(), raw.date().isoformat()
    if isinstance(raw, date):
        return raw, raw.isoformat()

    texto = str(raw or "").strip()
    if not texto:
        return None, None

    try:
        parsed = datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        return None, texto

    return parsed, texto


def _split_parcela_string(
    texto: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    partes = [p.strip() for p in re.split(r"\s{2,}", texto.strip()) if p.strip()]
    if not partes:
        return (None, None, None)
    if len(partes) == 1:
        return (partes[0], None, None)
    if len(partes) == 2:
        return (partes[0], partes[1], None)
    return (partes[0], partes[1], partes[-1])


def normalize_parcelas_atraso(
    parcelas: Optional[Iterable[Any]],
    *,
    referencia: Optional[date] = None,
) -> tuple[list[dict[str, Any]], Optional[int]]:
    if not parcelas:
        return ([], None)

    referencia = referencia or date.today()

    registros: list[tuple[Optional[date], int, dict[str, Any], Optional[int]]] = []

    for idx, item in enumerate(parcelas):
        numero: Optional[str] = None
        valor_raw: Optional[str] = None
        venc_raw: Optional[Any] = None

        if isinstance(item, dict):
            numero = _first_non_empty(
                item,
                ("parcela", "numero", "sequencia", "id", "codigo"),
            )
            valor_raw = _first_non_empty(
                item,
                ("valor", "valor_parcela", "valor_atraso", "valor_nominal"),
            )
            venc_raw = _first_present(
                item,
                (
                    "vencimento",
                    "dt_vencimento",
                    "data_vencimento",
                    "data",
                    "venc",
                ),
            )
        elif isinstance(item, (list, tuple)):
            numero = (
                str(item[0]).strip()
                if len(item) >= 1 and str(item[0]).strip()
                else None
            )
            valor_raw = str(item[1]).strip() if len(item) >= 2 else None
            venc_raw = item[2] if len(item) >= 3 else None
        else:
            texto = str(item or "").strip()
            if not texto:
                continue
            numero, valor_raw, venc_string = _split_parcela_string(texto)
            venc_raw = venc_string

        vencimento, vencimento_texto = _parse_vencimento(venc_raw)
        entrada: dict[str, Any] = {}
        if numero:
            entrada["parcela"] = numero

        valor_texto = str(valor_raw or "").strip()
        if valor_texto:
            entrada["valor"] = valor_texto
            valor_num = parse_money_brl(valor_texto)
            if not math.isnan(valor_num):
                entrada["valor_num"] = valor_num

        if vencimento is not None:
            entrada["vencimento"] = vencimento.isoformat()
            if vencimento_texto and vencimento_texto != entrada["vencimento"]:
                entrada["vencimento_texto"] = vencimento_texto
        elif vencimento_texto:
            entrada["vencimento"] = vencimento_texto

        dias_atraso: Optional[int] = None
        if vencimento is not None:
            delta = (referencia - vencimento).days
            if delta >= 0:
                dias_atraso = delta

        entrada = {
            chave: valor for chave, valor in entrada.items() if valor not in (None, "")
        }
        if not entrada and dias_atraso is None:
            continue

        registros.append((vencimento, idx, entrada, dias_atraso))

    if not registros:
        return ([], None)

    registros.sort(
        key=lambda item: (
            item[0] is None,
            item[0] or date.max,
            item[1],
        )
    )

    selecionados: list[dict[str, Any]] = []
    dias_coletados: list[int] = []
    for vencimento, _, entrada, dias_atraso in registros[:3]:
        selecionados.append(entrada)
        if dias_atraso is not None:
            dias_coletados.append(dias_atraso)

    dias_total = max(dias_coletados) if dias_coletados else None
    return (selecionados, dias_total)
