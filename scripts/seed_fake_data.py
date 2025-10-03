# python -m scripts.seed_fake_data --tenant-id 8f6c2279-7fe5-41bb-8a78-be564e9f45e4 --truncate
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterator, Sequence, Tuple
from uuid import UUID

import psycopg
from psycopg import Connection, OperationalError

try:
    from psycopg import conninfo as psycopg_conninfo
except Exception:  # pragma: no cover - optional dependency surface
    psycopg_conninfo = None
from psycopg.errors import UndefinedFunction
from psycopg.rows import dict_row
from urllib.parse import urlsplit, urlunsplit

from shared.config import get_database_settings, get_principal_settings


LOGGER = logging.getLogger("seed")


Identifier = int | str


SQL_INSERT_TIPO_PLANO = """INSERT INTO ref.tipo_plano (codigo, descricao, ativo)
VALUES (%s, %s, TRUE)
RETURNING id
"""

SQL_INSERT_RESOLUCAO = """INSERT INTO ref.resolucao (codigo, descricao, ativo)
VALUES (%s, %s, TRUE)
RETURNING id
"""

SQL_INSERT_EMPREGADOR = """INSERT INTO app.empregador (
    tenant_id, tipo_inscricao_id, numero_inscricao, razao_social,
    email, telefone
)
VALUES (
    app.current_tenant_id(), %s, %s, %s,
    %s, %s
)
ON CONFLICT (tenant_id, tipo_inscricao_id, numero_inscricao)
DO UPDATE SET
    razao_social = COALESCE(EXCLUDED.razao_social, app.empregador.razao_social),
    email = COALESCE(EXCLUDED.email, app.empregador.email),
    telefone = COALESCE(EXCLUDED.telefone, app.empregador.telefone)
RETURNING id
"""

SQL_INSERT_PLANO = """INSERT INTO app.plano (
    tenant_id, numero_plano, empregador_id,
    tipo_plano_id, resolucao_id, situacao_plano_id,
    dt_proposta, saldo_total, atraso_desde
)
VALUES (
    app.current_tenant_id(), %s, %s,
    %s, %s, %s,
    %s, %s, %s
)
ON CONFLICT (numero_plano)
DO UPDATE SET
    empregador_id     = EXCLUDED.empregador_id,
    tipo_plano_id     = EXCLUDED.tipo_plano_id,
    resolucao_id      = EXCLUDED.resolucao_id,
    situacao_plano_id = EXCLUDED.situacao_plano_id,
    dt_proposta       = EXCLUDED.dt_proposta,
    saldo_total       = EXCLUDED.saldo_total,
    atraso_desde      = COALESCE(EXCLUDED.atraso_desde, app.plano.atraso_desde)
RETURNING id
"""

SQL_INSERT_PLANO_HIST = """INSERT INTO app.plano_situacao_hist (
    tenant_id, plano_id, situacao_plano_id, mudou_em, mudou_por, observacao
)
VALUES (
    app.current_tenant_id(),
    %s,
    %s,
    %s::timestamptz,
    app.current_user_id(),
    %s
)
"""

SQL_MERGE_PARCELA = """WITH sel AS (
    SELECT id
      FROM app.parcela
     WHERE tenant_id = app.current_tenant_id()
       AND plano_id = %s
       AND nr_parcela = %s
       AND vencimento = %s
     LIMIT 1
),
ins AS (
    INSERT INTO app.parcela (
        tenant_id, plano_id, nr_parcela, vencimento, valor,
        situacao_parcela_id, pago_em, valor_pago, qtd_parcelas_total
    )
    SELECT
        app.current_tenant_id(), %s, %s, %s, %s,
        %s, %s, %s, %s
    WHERE NOT EXISTS (SELECT 1 FROM sel)
    RETURNING id, 'insert'::text AS acao
),
upd AS (
    UPDATE app.parcela p
       SET valor = %s,
           situacao_parcela_id = COALESCE(%s, p.situacao_parcela_id),
           pago_em = %s,
           valor_pago = %s,
           qtd_parcelas_total = COALESCE(%s, p.qtd_parcelas_total),
           updated_at = now(),
           updated_by = app.current_user_id()
     WHERE p.id = (SELECT id FROM sel)
    RETURNING p.id, 'update'::text AS acao
)
SELECT * FROM ins
UNION ALL
SELECT * FROM upd
UNION ALL
SELECT id, 'noop'::text AS acao FROM sel
"""

SQL_INSERT_EVENTO = """INSERT INTO audit.evento
  (tenant_id, event_time, entity, entity_id, event_type, severity, message, data, user_id)
VALUES
  (app.current_tenant_id(), now(), %s, %s, %s, %s, %s, %s, app.current_user_id())
"""

SQL_INSERT_JOB_RUN = """INSERT INTO audit.job_run (tenant_id, job_name, status, payload, user_id)
VALUES (app.current_tenant_id(), %s, 'RUNNING', %s, app.current_user_id())
RETURNING tenant_id, started_at, id
"""

SQL_TRUNCATE_ORDER = (
    (
        "audit.evento",
        "DELETE FROM audit.evento WHERE tenant_id = app.current_tenant_id()",
    ),
    (
        "audit.job_run",
        "DELETE FROM audit.job_run WHERE tenant_id = app.current_tenant_id()",
    ),
    (
        "app.parcela",
        "DELETE FROM app.parcela WHERE tenant_id = app.current_tenant_id()",
    ),
    (
        "app.plano_situacao_hist",
        "DELETE FROM app.plano_situacao_hist WHERE tenant_id = app.current_tenant_id()",
    ),
    ("app.plano", "DELETE FROM app.plano WHERE tenant_id = app.current_tenant_id()"),
    (
        "app.empregador",
        "DELETE FROM app.empregador WHERE tenant_id = app.current_tenant_id()",
    ),
)

PLAN_TYPES = [
    ("ADM", "Plano Administrativo"),
    ("JUD", "Plano Judicial"),
    ("INS", "Plano Inscrito"),
    ("AJ", "Plano Acordo Judicial"),
    ("AI", "Plano Administrativo Interno"),
    ("AJI", "Plano Acordo Judicial Interno"),
]

RESOLUCOES = [
    ("974/20", "Resolução 974/20"),
    ("430/98", "Resolução 430/98"),
    ("321/10", "Resolução 321/10"),
    ("112/18", "Resolução 112/18"),
]

JOB_NAMES = ["pipeline:sync", "pipeline:recompute", "import:plans", "metrics:refresh"]

EVENT_TYPES = ["STATE_CHANGE", "RESOURCE_SYNC", "VALIDATION", "ERROR"]

EVENT_SEVERITIES = ["INFO", "NOTICE", "WARNING", "ERROR"]

EVENT_ENTITIES = ["app.plano", "app.empregador", "app.pipeline", "app.job"]


@dataclass(slots=True)
class Employer:
    id: Identifier
    numero_inscricao: str
    razao_social: str


@dataclass(slots=True)
class PlanRecord:
    id: Identifier
    numero_plano: str
    situacao_plano_id: Identifier
    situacao_codigo: str


@dataclass(slots=True)
class SeedStats:
    empregadores: int = 0
    planos: int = 0
    historicos: int = 0
    parcelas: int = 0
    job_runs: int = 0
    eventos: int = 0


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed realistic tenant data for local integration testing.",
    )
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID to target")
    parser.add_argument(
        "--employers", type=int, default=5, help="Number of employers to generate"
    )
    parser.add_argument(
        "--plans-per-employer",
        type=int,
        default=20,
        help="Number of plans to create per employer",
    )
    parser.add_argument(
        "--status-changes-per-plan",
        type=int,
        help="If provided, fixed number of status entries per plan",
    )
    parser.add_argument(
        "--parcelas-per-plano",
        type=int,
        help="If provided, fixed number of installments per plan",
    )
    parser.add_argument(
        "--job-runs", type=int, default=10, help="Number of job runs to generate"
    )
    parser.add_argument(
        "--events-per-run",
        type=int,
        help="If provided, fixed number of events per job run",
    )
    parser.add_argument(
        "--truncate", action="store_true", help="Clear tenant data before seeding"
    )
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")
    parser.add_argument(
        "--dry-run", action="store_true", help="Build data but rollback before commit"
    )
    return parser.parse_args(argv)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def mask_dsn_for_log(dsn: str) -> str:
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return "***"

    netloc = parts.netloc
    if "@" in netloc:
        creds, host = netloc.rsplit("@", 1)
        user = creds.split(":", 1)[0] if creds else ""
        netloc = f"{user}@{host}" if user else host

    masked = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return masked or "***"


def normalize_identifier(value: Any) -> Identifier:
    if isinstance(value, int):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return text
        try:
            return int(text)
        except ValueError:
            return text
    return str(value)


def _coerce_identifier(value: Identifier) -> Identifier:
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        raise ValueError("Identifier value cannot be blank")
    return text


def _first_value(row: Any) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        for value in row.values():
            return value
        return None
    if isinstance(row, (list, tuple)):
        return row[0] if row else None
    return row


def _resolve_seed_principal() -> tuple[str, str, str, str]:
    principal = get_principal_settings()

    matricula = (principal.matricula or "SEED_BOT").strip() or "SEED_BOT"
    nome = (principal.nome or "Seed Bot").strip() or "Seed Bot"
    email = (principal.email or "").strip().lower()
    if not email or "@" not in email:
        local_part = matricula.lower().replace(" ", "_") or "seed_bot"
        email = f"{local_part}@seed.bot"
    perfil = (principal.perfil or "admin").strip() or "admin"

    return matricula, nome, email, perfil


def _normalize_severity(value: str) -> str:
    normalized = value.strip().lower()
    match normalized:
        case "warning" | "warn":
            return "warn"
        case "error" | "err":
            return "error"
        case "info" | "information":
            return "info"
        case _:
            return "info"


def _normalize_job_status(value: str) -> str:
    normalized = (value or "").strip().lower()
    match normalized:
        case "running":
            return "RUNNING"
        case "success" | "ok" | "done":
            return "SUCCESS"
        case "skipped" | "skip" | "cancelled" | "canceled":
            return "SKIPPED"
        case "error" | "err" | "failure" | "failed":
            return "ERROR"
        case _:
            return "ERROR"


def _maybe_rewrite_localhost(dsn: str) -> str:
    if os.name != "nt":
        return dsn
    if "localhost" not in dsn.lower():
        return dsn

    keyval_pattern = re.compile(
        r"(?i)(host\s*=\s*)(\"localhost\"|'localhost'|localhost)"
    )

    if psycopg_conninfo is not None:
        try:
            params = psycopg_conninfo.conninfo_to_dict(dsn)
        except Exception:  # pragma: no cover - fallback for unparsable DSNs
            pass
        else:
            host = params.get("host")
            if host and host.lower() == "localhost":
                params["host"] = "127.0.0.1"
                return psycopg_conninfo.make_conninfo(**params)

    parts = urlsplit(dsn)
    if parts.scheme:
        hostname = parts.hostname
        if hostname and hostname.lower() == "localhost":
            username = parts.username
            password = parts.password
            auth = ""
            if username is not None:
                auth = username
                if password is not None:
                    auth = f"{auth}:{password}"
            elif password is not None:
                auth = f":{password}"

            netloc = "127.0.0.1"
            if auth:
                netloc = f"{auth}@{netloc}"
            if parts.port:
                netloc = f"{netloc}:{parts.port}"
            return urlunsplit(
                (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
            )

    def replace_keyval(match: re.Match[str]) -> str:
        prefix, value = match.groups()
        if value.startswith(('"', "'")):
            quote = value[0]
            return f"{prefix}{quote}127.0.0.1{quote}"
        return f"{prefix}127.0.0.1"

    rewritten_dsn, count = keyval_pattern.subn(replace_keyval, dsn, count=1)
    if count:
        return rewritten_dsn

    return dsn


def _iter_candidate_dsn() -> Iterator[Tuple[str, str]]:
    seen: set[str] = set()

    dsn_raw = os.getenv("DATABASE_URL")
    if dsn_raw:
        dsn = dsn_raw.strip()
        if (dsn.startswith("'") and dsn.endswith("'")) or (
            dsn.startswith('"') and dsn.endswith('"')
        ):
            dsn = dsn[1:-1]
        normalized = _maybe_rewrite_localhost(dsn)
        for candidate in (normalized, dsn):
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            label = "DATABASE_URL (normalized)" if candidate != dsn else "DATABASE_URL"
            yield candidate, label

    settings = get_database_settings()
    config_dsn = settings.dsn
    if config_dsn and config_dsn not in seen:
        seen.add(config_dsn)
        yield config_dsn, "shared.config"


def connect() -> Connection:
    candidates = list(_iter_candidate_dsn())
    if not candidates:
        LOGGER.error(
            "No database connection information found; set DATABASE_URL or configure shared.config.",
        )
        sys.exit(1)

    last_exc: OperationalError | None = None
    for idx, (dsn, source) in enumerate(candidates):
        masked = mask_dsn_for_log(dsn)
        if source.endswith("normalized"):
            LOGGER.info("DATABASE_URL host normalized for Windows: %s", masked)
        try:
            conn = psycopg.connect(dsn)
        except OperationalError as exc:
            last_exc = exc
            log_fn = LOGGER.error if idx == len(candidates) - 1 else LOGGER.warning
            log_fn(
                "Could not connect using %s=%s (sanitized); %s",
                source,
                masked,
                exc,
            )
            continue

        LOGGER.info("Database connection established using %s settings", source)
        conn.row_factory = dict_row
        return conn

    assert last_exc is not None  # mypy assurance
    raise last_exc


def ensure_tenant_and_user(conn: Connection, tenant_id: UUID) -> None:
    LOGGER.info("Stage 1: configuring tenant context")
    matricula, nome, email, perfil = _resolve_seed_principal()
    tenant_str = str(tenant_id)
    with conn.cursor() as cur:
        try:
            cur.execute("SELECT app.set_tenant(%s)", (tenant_str,))
            LOGGER.debug("app.set_tenant applied successfully")
        except UndefinedFunction:
            LOGGER.debug("app.set_tenant not available; falling back to GUCs")
            cur.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_str,))

        seed_user_uuid: str | None = None
        try:
            cur.execute(
                "SELECT app.ensure_usuario(%s, %s, %s, %s, %s)",
                (tenant_str, matricula, nome, email, perfil),
            )
            row = cur.fetchone()
            value = _first_value(row)
            if value:
                seed_user_uuid = str(value)
                LOGGER.debug("Seed user provisioned with id %s", seed_user_uuid)
        except UndefinedFunction:
            LOGGER.debug(
                "app.ensure_usuario not available; skipping seed user provisioning"
            )
        except Exception as exc:
            LOGGER.warning(
                "Failed to provision seed user via app.ensure_usuario; continuing with fallback: %s",
                exc,
            )

        guc_user_value = seed_user_uuid or matricula
        if seed_user_uuid:
            try:
                cur.execute("SELECT app.set_user(%s)", (seed_user_uuid,))
                LOGGER.debug("app.set_user applied for seed user %s", seed_user_uuid)
            except UndefinedFunction:
                LOGGER.debug("app.set_user not available; falling back to GUCs")
            except Exception as exc:
                LOGGER.warning(
                    "Failed to apply app.set_user for seed user %s; falling back to GUCs: %s",
                    seed_user_uuid,
                    exc,
                )
            else:
                guc_user_value = seed_user_uuid

        cur.execute("SELECT set_config('app.user_id', %s, true)", (guc_user_value,))


def truncate_tenant_data(conn: Connection) -> None:
    LOGGER.info("Stage 2: truncating tenant data")
    with conn.cursor() as cur:
        for label, sql in SQL_TRUNCATE_ORDER:
            cur.execute(sql)
            LOGGER.info("%s: removed %s rows", label, cur.rowcount)


def fetch_reference_map(
    conn: Connection, schema: str, table: str
) -> dict[str, Identifier]:
    query = f"SELECT codigo, id FROM {schema}.{table}"
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
    mapping: dict[str, Identifier] = {}
    for row in rows:
        codigo = str(row["codigo"]).strip().upper()
        identifier_raw = row["id"]
        if identifier_raw is None:
            LOGGER.warning(
                "%s.%s has entry %s with null id; skipping", schema, table, codigo
            )
            continue
        mapping[codigo] = normalize_identifier(identifier_raw)
    return mapping


def get_or_create_tipo_plano(
    conn: Connection, codigo: str, descricao: str
) -> Identifier:
    normalized = codigo.strip().upper()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM ref.tipo_plano WHERE codigo = %s", (normalized,))
        row = cur.fetchone()
        if row:
            return normalize_identifier(row["id"])
        cur.execute(SQL_INSERT_TIPO_PLANO, (normalized, descricao))
        created = cur.fetchone()
    LOGGER.debug("Created ref.tipo_plano %s -> %s", normalized, created["id"])
    return normalize_identifier(created["id"])


def get_or_create_resolucao(
    conn: Connection, codigo: str, descricao: str
) -> Identifier:
    normalized = codigo.strip()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM ref.resolucao WHERE codigo = %s", (normalized,))
        row = cur.fetchone()
        if row:
            return normalize_identifier(row["id"])
        cur.execute(SQL_INSERT_RESOLUCAO, (normalized, descricao))
        created = cur.fetchone()
    LOGGER.debug("Created ref.resolucao %s -> %s", normalized, created["id"])
    return normalize_identifier(created["id"])


def insert_empregador(
    conn: Connection,
    tipo_inscricao_id: Identifier,
    numero_inscricao: str,
    razao_social: str,
    email: str,
    telefone: str,
) -> Identifier:
    with conn.cursor() as cur:
        cur.execute(
            SQL_INSERT_EMPREGADOR,
            (
                _coerce_identifier(tipo_inscricao_id),
                numero_inscricao,
                razao_social,
                email,
                telefone,
            ),
        )
        row = cur.fetchone()
    return normalize_identifier(row["id"])


def insert_plano(
    conn: Connection,
    numero_plano: str,
    empregador_id: Identifier,
    tipo_plano_id: Identifier,
    resolucao_id: Identifier,
    situacao_plano_id: Identifier,
    dt_proposta: date,
    saldo_total: Decimal,
    atraso_desde: date | None,
) -> Identifier:
    numero_plano_str = str(numero_plano).strip()
    if not numero_plano_str:
        raise ValueError("numero_plano must not be empty")
    if not numero_plano_str.isdigit():
        numero_plano_str = "".join(ch for ch in numero_plano_str if ch.isdigit())
    if not numero_plano_str:
        raise ValueError(f"Invalid numero_plano provided: {numero_plano}")
    if len(numero_plano_str) > 10:
        raise ValueError(
            f"numero_plano '{numero_plano_str}' exceeds 10 digits; adjust generator"
        )

    params = (
        numero_plano_str,
        _coerce_identifier(empregador_id),
        _coerce_identifier(tipo_plano_id),
        _coerce_identifier(resolucao_id),
        _coerce_identifier(situacao_plano_id),
        dt_proposta,
        saldo_total,
        atraso_desde,
    )
    with conn.cursor() as cur:
        cur.execute(
            SQL_INSERT_PLANO,
            params,
        )
        row = cur.fetchone()
    return normalize_identifier(row["id"])


def insert_plano_hist(
    conn: Connection,
    plano_id: Identifier,
    situacao_id: Identifier,
    mudou_em: datetime,
    observacao: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            SQL_INSERT_PLANO_HIST,
            (
                _coerce_identifier(plano_id),
                _coerce_identifier(situacao_id),
                mudou_em,
                observacao,
            ),
        )


def upsert_parcela(
    conn: Connection,
    plano_id: Identifier,
    nr_parcela: int,
    vencimento: date,
    valor: Decimal,
    situacao_parcela_id: Identifier | None,
    pago_em: date | None,
    valor_pago: Decimal | None,
    qtd_total: int | None,
) -> None:
    params = (
        _coerce_identifier(plano_id),
        nr_parcela,
        vencimento,
        _coerce_identifier(plano_id),
        nr_parcela,
        vencimento,
        valor,
        _coerce_identifier(situacao_parcela_id)
        if situacao_parcela_id is not None
        else None,
        pago_em,
        valor_pago,
        qtd_total,
        valor,
        _coerce_identifier(situacao_parcela_id)
        if situacao_parcela_id is not None
        else None,
        pago_em,
        valor_pago,
        qtd_total,
    )
    with conn.cursor() as cur:
        cur.execute(SQL_MERGE_PARCELA, params)
        cur.fetchall()


def open_job_run(
    conn: Connection, job_name: str, payload: dict[str, object]
) -> tuple[Identifier, datetime]:
    with conn.cursor() as cur:
        cur.execute(SQL_INSERT_JOB_RUN, (job_name, json.dumps(payload)))
        row = cur.fetchone()
    return normalize_identifier(row["id"]), row["started_at"]


def log_event(
    conn: Connection,
    entity: str,
    entity_id: str,
    event_type: str,
    severity: str,
    message: str,
    data: dict[str, object],
) -> None:
    normalized_severity = _normalize_severity(severity)
    with conn.cursor() as cur:
        cur.execute(
            SQL_INSERT_EVENTO,
            (
                entity,
                entity_id,
                event_type,
                normalized_severity,
                message,
                json.dumps(data, default=str),
            ),
        )


def adjust_recent_event_times(
    conn: Connection, desired_times: Sequence[datetime]
) -> None:
    if not desired_times:
        return
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM audit.evento WHERE tenant_id = app.current_tenant_id() ORDER BY id DESC LIMIT %s",
            (len(desired_times),),
        )
        rows = cur.fetchall()
        if len(rows) < len(desired_times):
            LOGGER.warning(
                "Could not collect %s freshly inserted events; timeline adjustments skipped",
                len(desired_times),
            )
            return
        ids = [normalize_identifier(row["id"]) for row in rows]
    ids.reverse()
    with conn.cursor() as cur:
        for event_id, event_time in zip(ids, desired_times, strict=False):
            cur.execute(
                "UPDATE audit.evento SET event_time = %s WHERE id = %s",
                (event_time, _coerce_identifier(event_id)),
            )


def close_job_run(
    conn: Connection, run_id: Identifier, status: str
) -> tuple[datetime | None, datetime | None]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'audit' AND table_name = 'job_run'"
        )
        cols = {row["column_name"] for row in cur.fetchall()}
    if "status" not in cols:
        LOGGER.info(
            "audit.job_run.status column absent; skipping close for run %s", run_id
        )
        return None, None

    if "finished_at" in cols:
        update_sql = "UPDATE audit.job_run SET status=%s, finished_at=now() WHERE id=%s RETURNING started_at, finished_at"
    else:
        update_sql = "UPDATE audit.job_run SET status=%s WHERE id=%s RETURNING started_at, NULL::timestamptz"

    normalized_status = _normalize_job_status(status)
    with conn.cursor() as cur:
        cur.execute(update_sql, (normalized_status, _coerce_identifier(run_id)))
        row = cur.fetchone()
    return row["started_at"], row["finished_at"]


def adjust_job_run_times(
    conn: Connection,
    run_id: Identifier,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE audit.job_run SET started_at = %s, finished_at = %s WHERE id = %s",
            (started_at, finished_at, _coerce_identifier(run_id)),
        )


def humanize_duration(started_at: datetime, finished_at: datetime) -> str:
    delta = finished_at - started_at
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes:02d}m {seconds:02d}s"


def normalize_seed(seed_value: int | None, rng: random.Random) -> None:
    if seed_value is not None:
        rng.seed(seed_value)
    else:
        random_seed = random.SystemRandom().randint(0, 2_147_483_647)
        rng.seed(random_seed)
        LOGGER.info("Random seed auto-selected: %s", random_seed)


def generate_razao_social(rng: random.Random, index: int) -> str:
    prefixes = ["Cooperativa", "Empresa", "Companhia", "Grupo", "Serviços"]
    suffixes = ["Ltda", "SA", "ME", "EPP", "Holdings"]
    prefix = rng.choice(prefixes)
    suffix = rng.choice(suffixes)
    return f"{prefix} Integrada {index:03d} {suffix}"


def generate_email(nome: str) -> str:
    sanitized = nome.lower().replace(" ", ".")
    return f"contato@{sanitized.replace(',', '').replace('-', '')}.com"


def generate_phone(rng: random.Random) -> str:
    return (
        f"({rng.randint(11, 99)}) {rng.randint(3000, 9999)}-{rng.randint(1000, 9999)}"
    )


def generate_numero_inscricao(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(14))


def generate_numero_plano(rng: random.Random, existing: set[str]) -> str:
    while True:
        numero = "".join(str(rng.randint(0, 9)) for _ in range(10))
        if numero not in existing:
            existing.add(numero)
            return numero


def choose_status_sequence(
    rng: random.Random,
    situacoes_plano: dict[str, Identifier],
    forced_length: int | None,
    final_codigo: str,
) -> list[tuple[Identifier, str]]:
    codes = list(situacoes_plano.keys())
    if not codes:
        raise RuntimeError("No situacao_plano entries available")
    desired_len = forced_length or rng.randint(3, 8)
    desired_len = max(2, desired_len)

    final_entry = (situacoes_plano[final_codigo], final_codigo)

    history: deque[tuple[int, str]] = deque()
    available_codes = [code for code in codes if code != final_codigo]

    if available_codes:
        attempts = 0
        max_attempts = max(10, desired_len * 4)
        chosen_codes = set()
        while len(history) < desired_len - 1 and attempts < max_attempts:
            code = rng.choice(available_codes)
            attempts += 1
            if len(chosen_codes) == len(available_codes):
                history.append((situacoes_plano[code], code))
                continue
            if code in chosen_codes:
                continue
            history.append((situacoes_plano[code], code))
            chosen_codes.add(code)

    while len(history) < desired_len - 1:
        history.append(final_entry)

    history.append(final_entry)
    return list(history)


def pick_plan_situacao(
    rng: random.Random, situacoes_plano: dict[str, Identifier]
) -> tuple[Identifier, str]:
    if not situacoes_plano:
        raise RuntimeError("ref.situacao_plano is empty")
    codigo = rng.choice(list(situacoes_plano.keys()))
    return situacoes_plano[codigo], codigo


def pick_parcela_status(
    rng: random.Random,
    situacoes_parcela: dict[str, Identifier],
) -> tuple[Identifier | None, str | None]:
    if not situacoes_parcela:
        return None, None
    codigo = rng.choice(list(situacoes_parcela.keys()))
    return situacoes_parcela[codigo], codigo


def load_tipo_inscricao_id(conn: Connection) -> Identifier:
    mapping = fetch_reference_map(conn, "ref", "tipo_inscricao")
    if "CNPJ" in mapping:
        return mapping["CNPJ"]
    if mapping:
        return next(iter(mapping.values()))
    raise RuntimeError("ref.tipo_inscricao is empty; cannot seed empregadores")


def load_situacao_parcela(conn: Connection) -> dict[str, Identifier]:
    mapping = fetch_reference_map(conn, "ref", "situacao_parcela")
    if not mapping:
        LOGGER.warning(
            "ref.situacao_parcela is empty; installments will be created without status"
        )
    return mapping


def load_situacao_plano(conn: Connection) -> dict[str, Identifier]:
    mapping = fetch_reference_map(conn, "ref", "situacao_plano")
    if not mapping:
        raise RuntimeError("ref.situacao_plano is empty; cannot seed plans")
    return mapping


def quantize_value(number: float) -> Decimal:
    return Decimal(number).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def seed_employers(
    conn: Connection,
    rng: random.Random,
    tipo_inscricao_id: Identifier,
    total: int,
    stats: SeedStats,
) -> list[Employer]:
    LOGGER.info("Stage 3: inserting empregadores (%s requested)", total)
    employers: list[Employer] = []
    for idx in range(1, total + 1):
        razao_social = generate_razao_social(rng, idx)
        numero_inscricao = generate_numero_inscricao(rng)
        email = generate_email(razao_social)
        telefone = generate_phone(rng)
        employer_id = insert_empregador(
            conn,
            tipo_inscricao_id,
            numero_inscricao,
            razao_social,
            email,
            telefone,
        )
        employers.append(Employer(employer_id, numero_inscricao, razao_social))
    stats.empregadores += len(employers)
    LOGGER.info("Inserted/updated %s empregadores", len(employers))
    return employers


def seed_plans_and_related(
    conn: Connection,
    rng: random.Random,
    employers: Sequence[Employer],
    situacoes_plano: dict[str, Identifier],
    situacoes_parcela: dict[str, Identifier],
    plans_per_employer: int,
    status_changes_per_plan: int | None,
    parcelas_per_plano: int | None,
    stats: SeedStats,
) -> list[PlanRecord]:
    LOGGER.info(
        "Stage 4: inserting planos, historicos e parcelas (%s por empregador)",
        plans_per_employer,
    )
    existing_plan_numbers: set[str] = set()
    seeded_plans: list[PlanRecord] = []
    today = datetime.now(timezone.utc)

    for employer in employers:
        tipo_codigo, tipo_desc = rng.choice(PLAN_TYPES)
        tipo_plano_id = get_or_create_tipo_plano(conn, tipo_codigo, tipo_desc)
        resolucao_codigo, resolucao_desc = rng.choice(RESOLUCOES)
        resolucao_id = get_or_create_resolucao(conn, resolucao_codigo, resolucao_desc)

        for _ in range(plans_per_employer):
            numero_plano = generate_numero_plano(rng, existing_plan_numbers)
            situacao_plano_id, situacao_codigo = pick_plan_situacao(
                rng, situacoes_plano
            )

            proposta_offset = rng.randint(20, 240)
            dt_proposta = (today - timedelta(days=proposta_offset)).date()
            saldo_total = quantize_value(rng.uniform(5_000, 250_000))
            atraso_desde = None
            if situacao_codigo in {"P_RESCISAO", "RESCINDIDO", "EM_ATRASO"}:
                atraso_desde = (today - timedelta(days=rng.randint(10, 180))).date()

            plano_id = insert_plano(
                conn,
                numero_plano,
                employer.id,
                tipo_plano_id,
                resolucao_id,
                situacao_plano_id,
                dt_proposta,
                saldo_total,
                atraso_desde,
            )
            stats.planos += 1
            seeded_plans.append(
                PlanRecord(plano_id, numero_plano, situacao_plano_id, situacao_codigo)
            )

            hist_sequence = choose_status_sequence(
                rng,
                situacoes_plano,
                status_changes_per_plan,
                situacao_codigo,
            )
            change_start = datetime.combine(
                dt_proposta, datetime.min.time(), tzinfo=timezone.utc
            )
            for offset, (status_id, status_code) in enumerate(hist_sequence):
                change_delay = rng.randint(1, 10)
                mudou_em = change_start + timedelta(days=offset * change_delay)
                observacao = f"Mudança automática: {status_code}"
                insert_plano_hist(conn, plano_id, status_id, mudou_em, observacao)
                stats.historicos += 1

            parcelas_total = (
                parcelas_per_plano
                if parcelas_per_plano is not None
                else rng.randint(0, 12)
            )
            for nr in range(1, parcelas_total + 1):
                vencimento = dt_proposta + timedelta(days=30 * nr)
                valor = quantize_value(rng.uniform(500, 25_000))
                situacao_parcela_id, situacao_parcela_codigo = pick_parcela_status(
                    rng, situacoes_parcela
                )
                pago_em = None
                valor_pago: Decimal | None = None
                if situacao_parcela_codigo == "PAGA":
                    pago_em = vencimento + timedelta(days=rng.randint(-5, 5))
                    valor_pago = valor
                elif situacao_parcela_codigo == "EM_ATRASO":
                    pago_em = None
                    valor_pago = None
                upsert_parcela(
                    conn,
                    plano_id,
                    nr,
                    vencimento,
                    valor,
                    situacao_parcela_id,
                    pago_em,
                    valor_pago,
                    parcelas_total,
                )
                stats.parcelas += 1

    LOGGER.info(
        "Seeded %s planos, %s históricos de situação e %s parcelas",
        stats.planos,
        stats.historicos,
        stats.parcelas,
    )
    return seeded_plans


def seed_job_runs_and_events(
    conn: Connection,
    rng: random.Random,
    plans: Sequence[PlanRecord],
    total_runs: int,
    events_per_run: int | None,
    stats: SeedStats,
) -> None:
    LOGGER.info("Stage 5: inserting job runs e eventos (%s runs)", total_runs)
    if not plans:
        LOGGER.warning("No planos seeded; audit logs will reference generic entities")

    for run_index in range(total_runs):
        job_name = rng.choice(JOB_NAMES)
        status = "SUCCESS" if run_index % 3 != 0 else rng.choice(["FAILURE", "SUCCESS"])
        payload = {
            "requested_by": "seed-bot",
            "retries": rng.randint(0, 2),
            "correlation_id": f"run-{run_index:04d}",
        }

        run_id, started_at_actual = open_job_run(conn, job_name, payload)
        job_duration_minutes = rng.randint(2, 90)
        job_start = datetime.now(timezone.utc) - timedelta(
            days=rng.randint(0, 30), minutes=job_duration_minutes
        )
        job_finish = job_start + timedelta(
            minutes=job_duration_minutes, seconds=rng.randint(10, 350)
        )

        adjust_job_run_times(conn, run_id, job_start, job_start)

        run_events = events_per_run if events_per_run is not None else rng.randint(3, 6)
        event_times: list[datetime] = []
        for event_offset in range(run_events):
            plano = rng.choice(plans) if plans else None
            entity = rng.choice(EVENT_ENTITIES)
            entity_id = str(plano.id if plano else rng.randint(1, 9999))
            event_type = rng.choice(EVENT_TYPES)
            severity = rng.choice(EVENT_SEVERITIES)
            message = f"{job_name} event {event_offset + 1}"
            data = {"info": f"detail-{rng.randint(1000, 9999)}"}
            log_event(conn, entity, entity_id, event_type, severity, message, data)
            event_time = job_start + timedelta(minutes=event_offset)
            event_times.append(event_time)
        adjust_recent_event_times(conn, event_times)

        started_at, finished_at = close_job_run(conn, run_id, status)
        if started_at is None:
            continue
        adjust_job_run_times(conn, run_id, job_start, job_finish)
        stats.job_runs += 1
        stats.eventos += run_events

        try:
            duration_text = humanize_duration(job_start, job_finish)
        except Exception as exc:  # pragma: no cover
            LOGGER.debug("Failed to compute duration: %s", exc)
            duration_text = "".join([])
        LOGGER.info(
            "Job run %s closed with status %s (duration %s)",
            run_id,
            status,
            duration_text,
        )


def print_counts(conn: Connection) -> None:
    LOGGER.info("Stage 6: resumo dos totais")
    tables = [
        "app.empregador",
        "app.plano",
        "app.plano_situacao_hist",
        "app.parcela",
        "audit.job_run",
        "audit.evento",
    ]
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(
                f"SELECT COUNT(*) AS total FROM {table} WHERE tenant_id = app.current_tenant_id()"
            )
            row = cur.fetchone()
            LOGGER.info("%s: %s registros", table, row["total"])

    LOGGER.info("Top 5 pipeline status entries:")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT job_name, status, last_update_at, duration_text "
            "FROM app.vw_pipeline_status ORDER BY last_update_at DESC LIMIT 5"
        )
        for row in cur.fetchall():
            LOGGER.info(
                " - %s (%s) última atualização %s duração %s",
                row["job_name"],
                row["status"],
                row["last_update_at"],
                row["duration_text"],
            )

    samples = {
        "app.plano": "SELECT id, numero_plano, saldo_total, situacao_plano_id FROM app.plano WHERE tenant_id = app.current_tenant_id() ORDER BY id DESC LIMIT 3",
        "app.plano_situacao_hist": "SELECT plano_id, situacao_plano_id, mudou_em, observacao FROM app.plano_situacao_hist WHERE tenant_id = app.current_tenant_id() ORDER BY mudou_em DESC LIMIT 3",
        "audit.evento": "SELECT event_time, entity, event_type, severity, message FROM audit.evento WHERE tenant_id = app.current_tenant_id() ORDER BY event_time DESC LIMIT 3",
    }
    with conn.cursor() as cur:
        for table, sql in samples.items():
            LOGGER.info("Samples from %s:", table)
            cur.execute(sql)
            for row in cur.fetchall():
                LOGGER.info(" %s", row)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    configure_logging()
    rng = random.Random()
    normalize_seed(args.seed, rng)

    try:
        tenant_uuid = UUID(args.tenant_id)
    except ValueError as exc:
        LOGGER.error("Invalid tenant UUID: %s", exc)
        return 1

    conn = connect()
    try:
        ensure_tenant_and_user(conn, tenant_uuid)

        if args.truncate:
            truncate_tenant_data(conn)

        tipo_inscricao_id = load_tipo_inscricao_id(conn)
        situacoes_plano = load_situacao_plano(conn)
        situacoes_parcela = load_situacao_parcela(conn)

        stats = SeedStats()

        employers = seed_employers(conn, rng, tipo_inscricao_id, args.employers, stats)
        plans = seed_plans_and_related(
            conn,
            rng,
            employers,
            situacoes_plano,
            situacoes_parcela,
            args.plans_per_employer,
            args.status_changes_per_plan,
            args.parcelas_per_plano,
            stats,
        )
        seed_job_runs_and_events(
            conn,
            rng,
            plans,
            args.job_runs,
            args.events_per_run,
            stats,
        )

        LOGGER.info(
            "Planned inserts: empregadores=%s planos=%s historicos=%s parcelas=%s job_runs=%s eventos=%s",
            stats.empregadores,
            stats.planos,
            stats.historicos,
            stats.parcelas,
            stats.job_runs,
            stats.eventos,
        )

        if args.dry_run:
            conn.rollback()
            LOGGER.info("Dry-run activated; all changes rolled back")
        else:
            conn.commit()
            LOGGER.info("Seeding committed successfully")
            print_counts(conn)
    except Exception:
        conn.rollback()
        LOGGER.exception("Error while seeding; transaction rolled back")
        return 1
    finally:
        conn.close()

    if args.dry_run:
        LOGGER.info("Dry-run completed; final counts skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
