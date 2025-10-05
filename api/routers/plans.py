from __future__ import annotations

import logging
import unicodedata
import base64
import json
import math
import time
from decimal import Decimal
from datetime import datetime, timezone
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.params import Param
from psycopg import AsyncConnection
from psycopg.errors import InvalidAuthorizationSpecification, UniqueViolation

try:  # pragma: no cover - allow running under test stubs
    from psycopg.errors import QueryCanceled  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - fallback for tests without full psycopg

    class QueryCanceled(Exception): ...


from psycopg.rows import dict_row

from api.models import (
    PlanBlockRequest,
    PlanBlockResponse,
    PlanQueueStatusResponse,
    PlanSummaryResponse,
    PlanUnblockRequest,
    PlanUnblockResponse,
    PlansFilters,
    PlansPaging,
    PlansResponse,
)
from api.dependencies import get_connection_manager
from infra.db import bind_session
from infra.repositories._helpers import (
    extract_date_from_timestamp,
    normalizar_situacao,
    only_digits,
    to_decimal,
)
from api.security import resolve_request_matricula, role_required

try:  # pragma: no cover - fallback for tests overriding this attribute
    from shared.config import get_principal_settings  # type: ignore
except Exception:  # pragma: no cover - default stub when config is absent

    def get_principal_settings():
        class _Principal:
            matricula: str | None = None

        return _Principal()


from shared.text import normalize_document

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/plans",
    tags=["plans"],
    dependencies=[Depends(role_required("GESTOR"))],
)


_STATUS_LABELS = {
    "P_RESCISAO": "P. RESCISAO",
    "SIT_ESPECIAL": "SIT. ESPECIAL",
    "GRDE_EMITIDA": "GRDE Emitida",
    "LIQUIDADO": "LIQUIDADO",
    "RESCINDIDO": "RESCINDIDO",
    "EM_ATRASO": "EM ATRASO",
    "EM_DIA": "EM DIA",
}

_FILTER_SITUATION_CODES: tuple[str, ...] = (
    "EM_DIA",
    "EM_ATRASO",
    "P_RESCISAO",
    "SIT_ESPECIAL",
    "RESCINDIDO",
    "LIQUIDADO",
    "GRDE_EMITIDA",
)
_FILTER_SITUATION_SET = set(_FILTER_SITUATION_CODES)

_ALLOWED_OVERDUE_THRESHOLDS: set[int] = {90, 100, 120}

_ALLOWED_SALDO_THRESHOLDS: tuple[int, ...] = (10000, 50000, 150000, 500000, 1_000_000)
_ALLOWED_SALDO_SET = set(_ALLOWED_SALDO_THRESHOLDS)

_DT_SITUATION_RANGE_CLAUSES: dict[str, tuple[str | None, str | None]] = {
    "LAST_3_MONTHS": (
        "dt_situacao >= date_trunc('month', CURRENT_DATE) - INTERVAL '2 months'",
        None,
    ),
    "LAST_2_MONTHS": (
        "dt_situacao >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month'",
        None,
    ),
    "LAST_MONTH": (
        "dt_situacao >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month'",
        "dt_situacao < date_trunc('month', CURRENT_DATE)",
    ),
    "THIS_MONTH": (
        "dt_situacao >= date_trunc('month', CURRENT_DATE)",
        None,
    ),
}

SALDO_RANGES: dict[str, tuple[int | None, int | None]] = {
    "10_50k": (10_000, 50_000),
    "50_150k": (50_000, 150_000),
    "150_500k": (150_000, 500_000),
    "500_1000k": (500_000, 1_000_000),
    "gte_1000k": (1_000_000, None),
}

SALDO_FILTER_KEYS: tuple[str, ...] = tuple(SALDO_RANGES.keys())

_ACTIVE_BLOCK_PREDICATE = (
    "bloqueio.ativo = TRUE\n"
    "       AND bloqueio.unlocked_at IS NULL\n"
    "       AND (bloqueio.expires_at IS NULL OR bloqueio.expires_at > now())"
)


def _unwrap_query_param(value: Any) -> Any:
    """Return the underlying default when a FastAPI ``Param`` is provided."""

    if isinstance(value, Param):
        return value.default
    return value


def _normalize_situacao_filter(values: Sequence[str] | str | None) -> list[str]:
    if values is None:
        return []

    if isinstance(values, str):
        iterable: Sequence[str] = [values]
    else:
        iterable = values

    normalized: list[str] = []
    for value in iterable:
        candidate = str(value or "").strip().upper()
        if candidate in _FILTER_SITUATION_SET and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _normalize_dias_min(value: int | None) -> int | None:
    if value is None:
        return None
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return None
    return candidate if candidate in _ALLOWED_OVERDUE_THRESHOLDS else None


def _normalize_saldo_min(value: int | None) -> int | None:
    if value is None:
        return None
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return None
    return candidate if candidate in _ALLOWED_SALDO_SET else None


def _normalize_saldo_key(value: str | None) -> str | None:
    if not value:
        return None
    candidate = str(value).strip().lower()
    if not candidate:
        return None
    return candidate if candidate in SALDO_RANGES else None


def _normalize_dt_range(value: str | None) -> str | None:
    if not value:
        return None
    candidate = str(value).strip().upper()
    return candidate if candidate in _DT_SITUATION_RANGE_CLAUSES else None


PLAN_DEFAULT_QUERY = f"""
    SELECT
        planos.plano_id,
        planos.numero_plano,
        planos.documento,
        planos.razao_social,
        planos.situacao,
        planos.dias_em_atraso,
        planos.saldo,
        planos.dt_situacao,
        (pending.plano_id IS NOT NULL) AS em_tratamento,
        COUNT(*) OVER () AS total_count,
        trat.filas,
        trat.users_enfileirando,
        trat.lotes,
        (bloqueio.id IS NOT NULL) AS bloqueado,
        bloqueio.created_at AS bloqueado_em,
        bloqueio.unlocked_at AS desbloqueado_em,
        bloqueio.motivo AS motivo_bloqueio
      FROM app.vw_planos_busca AS planos
LEFT JOIN app.vw_tratamento_enfileirado AS trat ON trat.plano_id = planos.plano_id
LEFT JOIN app.planos_em_tratamento() AS pending ON pending.plano_id = planos.plano_id
LEFT JOIN app.plano_bloqueio AS bloqueio
        ON bloqueio.plano_id = planos.plano_id
       AND {_ACTIVE_BLOCK_PREDICATE}
     ORDER BY planos.saldo DESC NULLS LAST, planos.dt_situacao DESC NULLS LAST, planos.numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

PLAN_SEARCH_BY_NUMBER_QUERY = f"""
    SELECT
        planos.plano_id,
        planos.numero_plano,
        planos.documento,
        planos.razao_social,
        planos.situacao,
        planos.dias_em_atraso,
        planos.saldo,
        planos.dt_situacao,
        (pending.plano_id IS NOT NULL) AS em_tratamento,
        COUNT(*) OVER () AS total_count,
        trat.filas,
        trat.users_enfileirando,
        trat.lotes,
        (bloqueio.id IS NOT NULL) AS bloqueado,
        bloqueio.created_at AS bloqueado_em,
        bloqueio.unlocked_at AS desbloqueado_em,
        bloqueio.motivo AS motivo_bloqueio
      FROM app.vw_planos_busca AS planos
LEFT JOIN app.vw_tratamento_enfileirado AS trat ON trat.plano_id = planos.plano_id
LEFT JOIN app.planos_em_tratamento() AS pending ON pending.plano_id = planos.plano_id
LEFT JOIN app.plano_bloqueio AS bloqueio
        ON bloqueio.plano_id = planos.plano_id
       AND {_ACTIVE_BLOCK_PREDICATE}
     WHERE planos.numero_plano = %(number)s
        OR planos.numero_plano LIKE %(number_prefix)s
     ORDER BY planos.saldo DESC NULLS LAST, planos.dt_situacao DESC NULLS LAST, planos.numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

PLAN_SEARCH_BY_NAME_QUERY = f"""
    SELECT
        planos.plano_id,
        planos.numero_plano,
        planos.documento,
        planos.razao_social,
        planos.situacao,
        planos.dias_em_atraso,
        planos.saldo,
        planos.dt_situacao,
        (pending.plano_id IS NOT NULL) AS em_tratamento,
        COUNT(*) OVER () AS total_count,
        trat.filas,
        trat.users_enfileirando,
        trat.lotes,
        (bloqueio.id IS NOT NULL) AS bloqueado,
        bloqueio.created_at AS bloqueado_em,
        bloqueio.unlocked_at AS desbloqueado_em,
        bloqueio.motivo AS motivo_bloqueio
      FROM app.vw_planos_busca AS planos
LEFT JOIN app.vw_tratamento_enfileirado AS trat ON trat.plano_id = planos.plano_id
LEFT JOIN app.planos_em_tratamento() AS pending ON pending.plano_id = planos.plano_id
LEFT JOIN app.plano_bloqueio AS bloqueio
        ON bloqueio.plano_id = planos.plano_id
       AND {_ACTIVE_BLOCK_PREDICATE}
     WHERE planos.razao_social ILIKE %(name_pattern)s
     ORDER BY planos.saldo DESC NULLS LAST, planos.dt_situacao DESC NULLS LAST, planos.numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

PLAN_SEARCH_BY_DOCUMENT_QUERY = f"""
    SELECT
        planos.plano_id,
        planos.numero_plano,
        planos.documento,
        planos.razao_social,
        planos.situacao,
        planos.dias_em_atraso,
        planos.saldo,
        planos.dt_situacao,
        (pending.plano_id IS NOT NULL) AS em_tratamento,
        COUNT(*) OVER () AS total_count,
        trat.filas,
        trat.users_enfileirando,
        trat.lotes,
        (bloqueio.id IS NOT NULL) AS bloqueado,
        bloqueio.created_at AS bloqueado_em,
        bloqueio.unlocked_at AS desbloqueado_em,
        bloqueio.motivo AS motivo_bloqueio
      FROM app.vw_planos_busca AS planos
LEFT JOIN app.vw_tratamento_enfileirado AS trat ON trat.plano_id = planos.plano_id
LEFT JOIN app.planos_em_tratamento() AS pending ON pending.plano_id = planos.plano_id
LEFT JOIN app.plano_bloqueio AS bloqueio
        ON bloqueio.plano_id = planos.plano_id
       AND {_ACTIVE_BLOCK_PREDICATE}
     WHERE planos.documento = %(document)s
       AND planos.tipo_doc IN ('CNPJ', 'CPF', 'CEI')
     ORDER BY planos.saldo DESC NULLS LAST, planos.dt_situacao DESC NULLS LAST, planos.numero_plano
     LIMIT %(limit)s OFFSET %(offset)s
"""

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
KEYSET_DEFAULT_PAGE_SIZE = 10
KEYSET_MAX_PAGE_SIZE = 200
# Simple in-memory TTL cache for total counts
_total_count_cache: dict[str, tuple[float, int]] = {}


def _normalize_days(value: Any) -> int | None:
    """Convert the raw ``dias_em_atraso`` value to an integer."""

    try:
        days = int(value)
    except (TypeError, ValueError):
        return None
    return max(days, 0)


def _normalize_balance(value: Any) -> Decimal | None:
    """Convert the raw balance to ``Decimal`` when possible."""

    decimal_value = to_decimal(value)
    if decimal_value is None:
        return None
    return decimal_value


def _normalize_queue_count(value: Any) -> int:
    """Coerce queue counters to non-negative integers."""

    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _normalize_document(value: Any) -> str | None:
    """Return a cleaned document identifier (digits only when available)."""

    return normalize_document(value)


def _remove_accents(value: str) -> str:
    """Return the ASCII representation of ``value`` without diacritics."""

    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalize_expires_at(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_status(value: Any) -> str | None:
    """Normalize status descriptions to the expected dashboard labels."""

    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    ascii_text = _remove_accents(text)
    upper_ascii = ascii_text.upper()
    compact = upper_ascii.replace(" ", "_")
    # Heurística para capturar descrições como "Passível de Rescisão"
    if "PASSIV" in upper_ascii and "RESC" in upper_ascii:
        normalized = "P_RESCISAO"
    elif "ATRASO" in upper_ascii:
        normalized = "EM_ATRASO"
    elif compact in {"EM_DIA", "EMDIA"}:
        normalized = "EM_DIA"
    else:
        normalized = normalizar_situacao(ascii_text)

    label = _STATUS_LABELS.get(normalized)
    if label is not None:
        return label
    return text


def _row_to_plan_summary(row: dict[str, Any]) -> PlanSummaryResponse:
    """Transform a database row into the API response model."""

    plan_id_raw = row.get("plano_id") or row.get("plan_id") or row.get("id")
    plan_id = str(plan_id_raw).strip() if plan_id_raw else None
    number = str(row.get("numero_plano") or "").strip()
    document = _normalize_document(
        row.get("numero_inscricao") or row.get("documento") or row.get("document")
    )
    company_name_raw = row.get("razao_social") or row.get("razao")
    company_name = str(company_name_raw).strip() or None if company_name_raw else None
    status_raw = row.get("situacao") or row.get("status")
    status = _format_status(status_raw)
    days_overdue = _normalize_days(
        row.get("dias_em_atraso") or row.get("dias_atraso") or row.get("dias_atrasados")
    )
    balance_raw = row.get("saldo")
    if balance_raw is None:
        balance_raw = row.get("saldo_total")
    if balance_raw is None:
        balance_raw = row.get("valor_atrasado")
    balance = _normalize_balance(balance_raw)
    status_date = extract_date_from_timestamp(row.get("dt_situacao"))

    filas = _normalize_queue_count(row.get("filas"))
    users = _normalize_queue_count(row.get("users_enfileirando") or row.get("users"))
    lotes = _normalize_queue_count(row.get("lotes"))
    treatment_queue = PlanQueueStatusResponse(
        enqueued=any(value > 0 for value in (filas, users, lotes)),
        filas=filas,
        users=users,
        lotes=lotes,
    )

    in_treatment_flag = bool(row.get("em_tratamento") or row.get("in_treatment"))

    blocked_value = row.get("bloqueado")
    blocked = bool(blocked_value) if blocked_value is not None else False
    blocked_at = _normalize_expires_at(row.get("bloqueado_em"))
    unlocked_at = _normalize_expires_at(row.get("desbloqueado_em"))
    block_reason_raw = row.get("motivo_bloqueio")
    block_reason: str | None = None
    if block_reason_raw is not None:
        text = str(block_reason_raw).strip()
        block_reason = text or None

    return PlanSummaryResponse(
        plan_id=plan_id,
        number=number,
        document=document,
        company_name=company_name,
        status=status,
        days_overdue=days_overdue,
        balance=balance,
        status_date=status_date,
        treatment_queue=treatment_queue,
        in_treatment=in_treatment_flag,
        blocked=blocked,
        blocked_at=blocked_at,
        unlocked_at=unlocked_at,
        block_reason=block_reason,
    )


def _get_query_params(request: Request | None) -> set[str]:
    """Return the normalized set of query parameter names if available."""

    try:
        qp = getattr(request, "query_params", None)
        if qp is None:
            return set()
        # FastAPI provides a Mapping-like object
        return {str(k).lower() for k in dict(qp).keys()}
    except Exception:  # pragma: no cover - defensive
        return set()


def _should_use_keyset(request: Request | None) -> bool:
    """Decide whether to use keyset pagination based on request query params."""

    params = _get_query_params(request)
    # Opt-in to keyset when any of the advanced pagination or filter params are provided.
    keyset_triggers = {
        "cursor",
        "direction",
        "page",
        "page_size",
        "tipo_doc",
        "situacao",
        "dias_min",
        "saldo_key",
        "saldo_min",
        "dt_sit_range",
    }
    return any(k in params for k in keyset_triggers)


def _b64url_encode_json(obj: dict[str, Any]) -> str:
    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    return token


def _b64url_decode_json(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        padding = "=" * (-len(token) % 4)
        data = base64.urlsafe_b64decode(token + padding)
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def _build_filters(
    search: str | None,
    *,
    tipo_doc: str | None,
    occurrences_only: bool = False,
    situacoes: Sequence[str] | None = None,
    dias_min: int | None = None,
    saldo_key: str | None = None,
    saldo_min: int | None = None,
    dt_sit_range: str | None = None,
    table_alias: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return SQL WHERE clause and params according to filtering semantics."""

    normalized_search = (search or "").strip()
    digits = only_digits(normalized_search)
    params: dict[str, Any] = {}
    clauses: list[str] = []

    def col(name: str) -> str:
        return f"{table_alias}.{name}" if table_alias else name

    if digits and len(digits) in (11, 12, 14):
        clauses.append(f"{col('documento')} = %(document)s")
        params["document"] = digits
        if tipo_doc and tipo_doc in {"CNPJ", "CPF", "CEI"}:
            clauses.append(f"{col('tipo_doc')} = %(tipo_doc)s")
            params["tipo_doc"] = tipo_doc
        else:
            clauses.append(f"{col('tipo_doc')} IN ('CNPJ','CPF','CEI')")
    elif normalized_search.isdigit() and normalized_search:
        params["number"] = normalized_search
        params["number_prefix"] = f"{normalized_search}%"
        clauses.append(
            f"({col('numero_plano')} = %(number)s OR {col('numero_plano')} LIKE %(number_prefix)s)"
        )
    elif normalized_search:
        params["name_pattern"] = f"%{normalized_search}%"
        clauses.append(f"{col('razao_social')} ILIKE %(name_pattern)s")

    if situacoes:
        params["situacoes"] = list(situacoes)
        clauses.append(f"{col('situacao_codigo')} = ANY(%(situacoes)s::text[])")

    if dias_min is not None:
        params["dias_min"] = dias_min
        clauses.append(
            f"{col('atraso_desde')} <= CURRENT_DATE - make_interval(days => %(dias_min)s)"
        )

    saldo_lo: int | None = None
    saldo_hi: int | None = None

    if saldo_key:
        saldo_lo, saldo_hi = SALDO_RANGES.get(saldo_key, (None, None))
    elif saldo_min is not None:
        saldo_lo = saldo_min

    if saldo_lo is not None:
        params["saldo_lo"] = saldo_lo
        clauses.append(f"COALESCE({col('saldo')}, 0) >= %(saldo_lo)s")
    if saldo_hi is not None:
        params["saldo_hi"] = saldo_hi
        clauses.append(f"COALESCE({col('saldo')}, 0) < %(saldo_hi)s")

    if dt_sit_range:
        start_clause, end_clause = _DT_SITUATION_RANGE_CLAUSES[dt_sit_range]
        if start_clause:
            clauses.append(
                start_clause
                if not table_alias
                else start_clause.replace("dt_situacao", f"{table_alias}.dt_situacao")
            )
        if end_clause:
            clauses.append(
                end_clause
                if not table_alias
                else end_clause.replace("dt_situacao", f"{table_alias}.dt_situacao")
            )

    if occurrences_only:
        clauses.append(f"{col('situacao_codigo')} <> 'P_RESCISAO'")

    if clauses:
        return " WHERE " + " AND ".join(clauses), params
    return "", params


async def _fast_total_count(
    connection: AsyncConnection,
    *,
    where_sql: str,
    params: dict[str, Any],
    cache_key: str,
) -> int | None:
    """Attempt a fast COUNT(*) with a short statement timeout, else cache.

    - Try with statement_timeout ≈ 1500ms.
    - On timeout, return a cached value (if available). If no cache, return None.
    - On success, update cache (TTL 60s) and return the value.
    """

    try:
        async with connection.cursor(row_factory=dict_row) as cur:
            # Ensure a local, short timeout to avoid slow counts
            await cur.execute("BEGIN")
            await cur.execute("SET LOCAL statement_timeout = '1500ms'")
            await cur.execute(
                f"SELECT COUNT(*) AS cnt FROM app.vw_planos_busca AS planos{where_sql}",
                params,
            )
            row = await cur.fetchone()
            await cur.execute("COMMIT")
        count_raw = row.get("cnt") if row else None
        value = int(count_raw) if count_raw is not None else 0
        _total_count_cache[cache_key] = (time.time() + 60.0, value)
        return value
    except QueryCanceled:
        # Timed out: try cache
        cached = _total_count_cache.get(cache_key)
        if cached and cached[0] > time.time():
            return cached[1]
        return None
    except Exception:  # pragma: no cover - defensive
        logger.exception("Falha ao executar COUNT(*) para grid de planos")
        cached = _total_count_cache.get(cache_key)
        if cached and cached[0] > time.time():
            return cached[1]
        return None


async def _fetch_keyset_page(
    connection: AsyncConnection,
    *,
    search: str | None,
    tipo_doc: str | None,
    occurrences_only: bool,
    situacoes: Sequence[str] | None,
    dias_min: int | None,
    saldo_key: str | None,
    saldo_min: int | None,
    dt_sit_range: str | None,
    page_size: int,
    cursor_token: str | None,
    direction: str | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Fetch a keyset page ordered by saldo desc then numero_plano asc.

    Returns (rows, has_more) where `rows` are in display order.
    """

    where_sql, params = _build_filters(
        search,
        tipo_doc=tipo_doc,
        occurrences_only=occurrences_only,
        situacoes=situacoes,
        dias_min=dias_min,
        saldo_key=saldo_key,
        saldo_min=saldo_min,
        dt_sit_range=dt_sit_range,
        table_alias="planos",
    )

    seek_condition = ""
    order_sql = " ORDER BY COALESCE(planos.saldo,0) DESC, planos.numero_plano ASC"
    is_prev = direction == "prev"

    if cursor_token:
        payload = _b64url_decode_json(cursor_token) or {}
        saldo_raw = payload.get("s")
        numero_raw = payload.get("n")
        # Treat saldo NULL as 0 and keep precision by passing as text to DB
        try:
            saldo_val = Decimal(str(saldo_raw)) if saldo_raw is not None else Decimal(0)
        except Exception:
            saldo_val = Decimal(0)
        numero_val = str(numero_raw or "")
        if is_prev:
            seek_condition = (
                "(COALESCE(planos.saldo,0) > %(first_saldo)s"
                " OR (COALESCE(planos.saldo,0) = %(first_saldo)s AND planos.numero_plano < %(first_numero)s))"
            )
            params.update({"first_saldo": saldo_val, "first_numero": numero_val})
            order_sql = (
                " ORDER BY COALESCE(planos.saldo,0) ASC, planos.numero_plano DESC"
            )
        else:
            seek_condition = (
                "(COALESCE(planos.saldo,0) < %(last_saldo)s"
                " OR (COALESCE(planos.saldo,0) = %(last_saldo)s AND planos.numero_plano > %(last_numero)s))"
            )
            params.update({"last_saldo": saldo_val, "last_numero": numero_val})

    limit_sql = " LIMIT %(limit)s"
    params["limit"] = page_size + 1  # fetch sentinel to detect has_more

    # Build WHERE/AND composition correctly
    where_clause = where_sql  # includes leading " WHERE " or empty
    if seek_condition:
        where_clause = (
            f"{where_clause} AND {seek_condition}"
            if where_clause
            else f" WHERE {seek_condition}"
        )

    sql = (
        "SELECT planos.plano_id, planos.numero_plano, planos.documento, planos.razao_social, planos.situacao,"
        " planos.dias_em_atraso, planos.saldo, planos.dt_situacao,"
        " (pending.plano_id IS NOT NULL) AS em_tratamento,"
        " trat.filas, trat.users_enfileirando, trat.lotes,"
        " (bloqueio.id IS NOT NULL) AS bloqueado,"
        " bloqueio.created_at AS bloqueado_em,"
        " bloqueio.unlocked_at AS desbloqueado_em,"
        " bloqueio.motivo AS motivo_bloqueio"
        " FROM app.vw_planos_busca AS planos"
        " LEFT JOIN app.vw_tratamento_enfileirado AS trat ON trat.plano_id = planos.plano_id"
        " LEFT JOIN app.planos_em_tratamento() AS pending ON pending.plano_id = planos.plano_id"
        " LEFT JOIN app.plano_bloqueio AS bloqueio"
        "        ON bloqueio.plano_id = planos.plano_id"
        f"       AND {_ACTIVE_BLOCK_PREDICATE}"
        f"{where_clause}{order_sql}{limit_sql}"
    )

    async with connection.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        fetched = await cur.fetchall()

    has_more = len(fetched) > page_size

    if is_prev:
        # Results are in inverse order; trim then restore display order
        # Trim based on sentinel
        trimmed = fetched[:page_size]
        trimmed.reverse()
        rows = trimmed
    else:
        rows = fetched[:page_size]

    return rows, has_more


async def _fetch_plan_rows(
    connection: AsyncConnection,
    *,
    search: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """Execute the SQL query returning plans for the dashboard."""

    normalized_search = (search or "").strip()
    digits = only_digits(normalized_search)

    if digits and len(digits) in (11, 12, 14):
        query = PLAN_SEARCH_BY_DOCUMENT_QUERY
        params = {"document": digits, "limit": limit, "offset": offset}
    elif normalized_search.isdigit() and normalized_search:
        query = PLAN_SEARCH_BY_NUMBER_QUERY
        number_prefix = f"{normalized_search}%"
        params = {
            "number": normalized_search,
            "number_prefix": number_prefix,
            "limit": limit,
            "offset": offset,
        }
    elif normalized_search:
        query = PLAN_SEARCH_BY_NAME_QUERY
        name_pattern = f"%{normalized_search}%"
        params = {
            "name_pattern": name_pattern,
            "limit": limit,
            "offset": offset,
        }
    else:
        query = PLAN_DEFAULT_QUERY
        params = {"limit": limit, "offset": offset}

    async with connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(query, params)
        rows = await cursor.fetchall()
    return list(rows)


@router.get("", response_model=PlansResponse)
async def list_plans(
    request: Request,
    q: str | None = Query(None, max_length=255, description="Termo de busca"),
    limit: int = Query(
        DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description="Quantidade de itens por página",
    ),
    offset: int = Query(0, ge=0, description="Deslocamento para paginação"),
    # Keyset pagination params (opt-in; keeps legacy limit/offset working)
    page: int = Query(1, ge=1, description="Página atual (base 1)"),
    page_size: int = Query(
        KEYSET_DEFAULT_PAGE_SIZE,
        ge=1,
        le=KEYSET_MAX_PAGE_SIZE,
        description="Itens por página (keyset)",
    ),
    cursor: str | None = Query(
        None, description="Cursor de paginação (base64 url-safe)"
    ),
    direction: str | None = Query(
        None, pattern="^(next|prev)$", description="Direção da navegação"
    ),
    tipo_doc: str | None = Query(
        None,
        pattern="^(CNPJ|CPF|CEI)$",
        description="Tipo do documento quando 'q' for numérico",
    ),
    occurrences_only: bool = Query(
        False,
        description="Quando verdadeiro, retorna apenas planos com ocorrências (exclui P. RESCISAO)",
    ),
    situacao: list[str] | None = Query(
        None, description="Filtro por situação (códigos normalizados)"
    ),
    dias_min: int | None = Query(
        None, description="Mínimo de dias em atraso (90, 100, 120)"
    ),
    saldo_min: int | None = Query(
        None,
        description="Saldo mínimo em reais (10000, 50000, 150000, 500000, 1000000)",
    ),
    saldo_key: str | None = Query(
        None,
        pattern=r"^(10_50k|50_150k|150_500k|500_1000k|gte_1000k)$",
        description="Faixa de saldo pré-definida",
    ),
    dt_sit_range: str | None = Query(
        None,
        description="Intervalo relativo para dt_situacao (LAST_3_MONTHS, LAST_2_MONTHS, LAST_MONTH, THIS_MONTH)",
    ),
) -> PlansResponse:
    """Return the consolidated plans available for the dashboard."""

    matricula = resolve_request_matricula(request, get_principal_settings)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    q = _unwrap_query_param(q)
    limit = _unwrap_query_param(limit)
    offset = _unwrap_query_param(offset)
    page = _unwrap_query_param(page)
    page_size = _unwrap_query_param(page_size)
    cursor = _unwrap_query_param(cursor)
    direction = _unwrap_query_param(direction)
    tipo_doc = _unwrap_query_param(tipo_doc)
    occurrences_only = _unwrap_query_param(occurrences_only)
    situacao = _unwrap_query_param(situacao)
    dias_min = _unwrap_query_param(dias_min)
    saldo_min = _unwrap_query_param(saldo_min)
    saldo_key = _unwrap_query_param(saldo_key)
    dt_sit_range = _unwrap_query_param(dt_sit_range)

    limit = int(limit) if limit is not None else DEFAULT_LIMIT
    offset = int(offset) if offset is not None else 0
    page = int(page) if page is not None else 1
    page_size = int(page_size) if page_size is not None else KEYSET_DEFAULT_PAGE_SIZE
    occurrences_only = bool(occurrences_only) if occurrences_only is not None else False
    cursor = str(cursor) if cursor is not None else None
    direction = str(direction) if direction is not None else None
    tipo_doc = str(tipo_doc).upper() if tipo_doc else None
    saldo_key = str(saldo_key).lower() if saldo_key else None
    dt_sit_range = str(dt_sit_range).upper() if dt_sit_range else None

    situacao_values = _normalize_situacao_filter(situacao)
    dias_threshold = _normalize_dias_min(dias_min)
    saldo_threshold = _normalize_saldo_min(saldo_min)
    saldo_key_value = _normalize_saldo_key(saldo_key)
    dt_range_value = _normalize_dt_range(dt_sit_range)

    filters_applied = bool(
        situacao_values
        or dias_threshold is not None
        or saldo_key_value is not None
        or saldo_threshold is not None
        or dt_range_value is not None
    )

    filters_model = PlansFilters(
        situacao=situacao_values or None,
        dias_min=dias_threshold,
        saldo_key=saldo_key_value,
        saldo_min=saldo_threshold if saldo_key_value is None else None,
        dt_sit_range=dt_range_value,
    )
    if not (
        filters_model.situacao
        or filters_model.dias_min is not None
        or filters_model.saldo_key is not None
        or filters_model.saldo_min is not None
        or filters_model.dt_sit_range is not None
    ):
        filters_model = None

    connection_manager = get_connection_manager()
    use_keyset = _should_use_keyset(request)
    if not use_keyset:
        if (
            filters_applied
            or cursor
            or direction
            or page != 1
            or page_size != KEYSET_DEFAULT_PAGE_SIZE
        ):
            use_keyset = True
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            if use_keyset:
                rows, has_more = await _fetch_keyset_page(
                    connection,
                    search=q,
                    tipo_doc=tipo_doc,
                    occurrences_only=occurrences_only,
                    situacoes=situacao_values,
                    dias_min=dias_threshold,
                    saldo_key=saldo_key_value,
                    saldo_min=saldo_threshold,
                    dt_sit_range=dt_range_value,
                    page_size=page_size,
                    cursor_token=cursor,
                    direction=direction or "next",
                )
                # total count with timeout + cache
                where_sql, count_params = _build_filters(
                    q,
                    tipo_doc=tipo_doc,
                    occurrences_only=occurrences_only,
                    situacoes=situacao_values,
                    dias_min=dias_threshold,
                    saldo_key=saldo_key_value,
                    saldo_min=saldo_threshold,
                    dt_sit_range=dt_range_value,
                    table_alias="planos",
                )
                cache_key = (
                    f"{matricula}|{q or ''}|{tipo_doc or ''}|occ={occurrences_only}"
                    f"|situ={','.join(situacao_values) if situacao_values else ''}"
                    f"|dias={dias_threshold or ''}|saldo_key={saldo_key_value or ''}|"
                    f"saldo={saldo_threshold or ''}|dt={dt_range_value or ''}"
                )
                total_count = await _fast_total_count(
                    connection,
                    where_sql=where_sql,
                    params=count_params,
                    cache_key=cache_key,
                )
            else:
                rows = await _fetch_plan_rows(
                    connection,
                    search=q,
                    limit=limit,
                    offset=offset,
                )
    except (PermissionError, InvalidAuthorizationSpecification) as exc:
        logger.exception("Erro ao carregar planos do banco de dados")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso inválidas.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive programming
        logger.exception("Erro ao carregar planos do banco de dados")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível carregar os planos.",
        ) from exc

    items = [_row_to_plan_summary(row) for row in rows]

    if use_keyset:
        # Compute paging metadata
        showing_from = (page - 1) * page_size + 1 if items else 0
        showing_to = showing_from + len(items) - 1 if items else 0

        next_cursor_val = None
        prev_cursor_val = None
        if items:
            # saldo for cursor treats None as 0
            first = rows[0]
            last = rows[-1]
            first_s = first.get("saldo")
            last_s = last.get("saldo")
            first_s = Decimal(str(first_s)) if first_s is not None else Decimal(0)
            last_s = Decimal(str(last_s)) if last_s is not None else Decimal(0)
            prev_cursor_val = _b64url_encode_json(
                {
                    "s": str(first_s),
                    "n": str(first.get("numero_plano") or ""),
                }
            )
            next_cursor_val = _b64url_encode_json(
                {
                    "s": str(last_s),
                    "n": str(last.get("numero_plano") or ""),
                }
            )

        total_known = total_count is not None
        total_pages = math.ceil((total_count or 0) / page_size) if total_known else None
        paging = PlansPaging(
            page=page,
            page_size=page_size,
            has_more=has_more,
            next_cursor=next_cursor_val,
            prev_cursor=prev_cursor_val,
            showing_from=showing_from,
            showing_to=showing_to,
            total_count=total_count if total_known else None,
            total_pages=total_pages,
        )

        # Keep 'total' for backward compatibility: when known use total_count else len(items)
        total_compat = (total_count or 0) if total_known else len(items)
        return PlansResponse(
            items=items, total=total_compat, paging=paging, filters=filters_model
        )

    # Legacy offset-based path preserved for compatibility
    if rows:
        total_raw = rows[0].get("total_count")
        total = int(total_raw) if total_raw is not None else len(rows)
    else:
        total = 0
    return PlansResponse(items=items, total=total, paging=None, filters=filters_model)


@router.post("/block", response_model=PlanBlockResponse)
async def block_plan(
    request: Request,
    payload: PlanBlockRequest,
) -> PlanBlockResponse:
    matricula = resolve_request_matricula(request, get_principal_settings)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    motivo = (payload.motivo or "").strip() or None
    expires_at = _normalize_expires_at(payload.expires_at)

    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            async with connection.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT app.plano_bloquear(%s::uuid, %s::text, %s::timestamptz) AS blocked",
                    (str(payload.plano_id), motivo, expires_at),
                )
                row = await cur.fetchone()
    except UniqueViolation as exc:
        logger.info("Plano já estava bloqueado (idempotente).", exc_info=exc)
        return PlanBlockResponse(
            plano_id=payload.plano_id,
            blocked=True,
            message="already blocked",
        )
    except InvalidAuthorizationSpecification as exc:
        logger.exception("Sessão sem autorização para bloquear plano")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso inválidas.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao bloquear plano")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível bloquear o plano.",
        ) from exc

    blocked_raw = row.get("blocked") if row else None
    blocked_flag: bool
    if isinstance(blocked_raw, bool):
        blocked_flag = blocked_raw
    elif blocked_raw is None:
        blocked_flag = True
    elif isinstance(blocked_raw, (int, float)):
        blocked_flag = bool(blocked_raw)
    elif isinstance(blocked_raw, str):
        blocked_flag = blocked_raw.strip().lower() in {"t", "true", "1", "ok"}
    else:
        blocked_flag = True
    message: str | None = None
    if not blocked_flag:
        blocked_flag = True
        message = "already blocked"

    return PlanBlockResponse(
        plano_id=payload.plano_id,
        blocked=blocked_flag,
        message=message,
    )


@router.post("/unblock", response_model=PlanUnblockResponse)
async def unblock_plan(
    request: Request,
    payload: PlanUnblockRequest,
) -> PlanUnblockResponse:
    matricula = resolve_request_matricula(request, get_principal_settings)
    if not matricula:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso ausentes.",
        )

    connection_manager = get_connection_manager()
    try:
        async with connection_manager as connection:
            await bind_session(connection, matricula)
            async with connection.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT app.plano_desbloquear(%s::uuid) AS affected",
                    (str(payload.plano_id),),
                )
                row = await cur.fetchone()
    except InvalidAuthorizationSpecification as exc:
        logger.exception("Sessão sem autorização para desbloquear plano")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais de acesso inválidas.",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Erro ao desbloquear plano")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível desbloquear o plano.",
        ) from exc

    affected_raw = None
    if row:
        if "affected" in row:
            affected_raw = row.get("affected")
        else:
            # fallback for unnamed columns
            affected_raw = next(iter(row.values())) if row else None

    affected = int(affected_raw) if affected_raw is not None else 0
    if affected <= 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plano não estava bloqueado ou não existe.",
        )

    return PlanUnblockResponse(plano_id=payload.plano_id, blocked=False)


__all__ = ["router", "list_plans", "block_plan", "unblock_plan"]
