from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Json

from domain.enums import Step


logger = logging.getLogger(__name__)

@dataclass(slots=True)
class PlanDTO:
    """Representação simplificada de um plano utilizado no pipeline."""

    id: str
    numero_plano: str
    situacao_atual: Optional[str] = None


class PlansRepository:
    """Realiza operações de leitura e escrita para os planos."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn
        self._situacao_parcela_atraso_id: Optional[str] = None

    def get_by_numero(self, numero_plano: str) -> Optional[PlanDTO]:
        """Busca um plano pelo número normalizado."""

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT p.id, p.numero_plano, sp.codigo AS situacao_atual
                  FROM app.plano AS p
             LEFT JOIN ref.situacao_plano AS sp ON sp.id = p.situacao_plano_id
                 WHERE p.numero_plano = %s
                """,
                (numero_plano,),
            )
            row = cur.fetchone()

        if not row:
            return None

        situacao = row.get("situacao_atual")
        return PlanDTO(
            id=str(row["id"]),
            numero_plano=row["numero_plano"],
            situacao_atual=situacao,
        )

    def upsert(self, numero_plano: str, **campos: Any) -> PlanDTO:
        """Insere ou atualiza o plano consolidando empregador, catálogos e atrasos."""

        campos = dict(campos)
        parcelas_brutas = list(campos.pop("parcelas_atraso", []) or [])

        empregador_id = self._resolver_empregador(campos)
        situacao_id, situacao_codigo = self._resolver_situacao(campos.get("situacao_atual"))
        tipo_id = self._resolver_tipo_plano(campos.get("tipo"))
        resolucao_id = self._resolver_resolucao(campos.get("resolucao"))

        atraso_desde = self._calcular_atraso_desde(
            campos.get("dias_em_atraso"),
            campos.get("dt_situacao_atual"),
        )

        status = campos.get("status")
        status_valor = getattr(status, "value", str(status)) if status is not None else None
        representacao = campos.get("representacao")
        dt_proposta = campos.get("dt_proposta")
        saldo_total = self._to_decimal(campos.get("saldo"))
        dt_situacao_atual = campos.get("dt_situacao_atual")

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO app.plano (
                    tenant_id, numero_plano, empregador_id,
                    tipo_plano_id, resolucao_id, situacao_plano_id,
                    dt_proposta, saldo_total, atraso_desde,
                    representacao, status, dt_situacao_atual
                )
                VALUES (
                    app.current_tenant_id(), %s, %s,
                    %s, %s, %s,
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
                    atraso_desde      = COALESCE(EXCLUDED.atraso_desde, app.plano.atraso_desde),
                    representacao     = EXCLUDED.representacao,
                    status            = EXCLUDED.status,
                    dt_situacao_atual = EXCLUDED.dt_situacao_atual
                RETURNING id
                """,
                (
                    numero_plano,
                    empregador_id,
                    tipo_id,
                    resolucao_id,
                    situacao_id,
                    dt_proposta,
                    saldo_total,
                    atraso_desde,
                    representacao,
                    status_valor,
                    dt_situacao_atual,
                ),
            )
            resultado = cur.fetchone()

        if not resultado:
            raise RuntimeError("Falha ao inserir/atualizar plano")

        plano_id = str(resultado["id"])

        parcelas_preparadas = self._preparar_parcelas(parcelas_brutas)
        if parcelas_preparadas:
            self._lock_plano(plano_id)
            self._persistir_parcelas(plano_id, parcelas_preparadas)
            self._recalcular_atraso(plano_id)

        existente = self.get_by_numero(numero_plano)
        if existente is not None:
            return existente
        return PlanDTO(plano_id, numero_plano, situacao_codigo)

    # -- Helpers -----------------------------------------------------------------

    def _resolver_empregador(self, campos: dict[str, Any]) -> Optional[str]:
        numero = campos.get("numero_inscricao")
        if not numero:
            return campos.get("empregador_id")

        numero_normalizado = self._only_digits(numero) or str(numero).strip()
        if not numero_normalizado:
            return campos.get("empregador_id")

        codigo_tipo = self._inferir_tipo_inscricao(numero_normalizado)
        razao_social = campos.get("razao_social") or None
        email = (campos.get("email") or "").strip() or None
        telefone = (campos.get("telefone") or "").strip() or None

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id FROM ref.tipo_inscricao WHERE codigo = %s",
                (codigo_tipo,),
            )
            tipo = cur.fetchone()
            if not tipo:
                raise RuntimeError(f"Tipo de inscrição desconhecido: {codigo_tipo}")

            cur.execute(
                """
                INSERT INTO app.empregador (
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
                """,
                (tipo["id"], numero_normalizado, razao_social, email, telefone),
            )
            row = cur.fetchone()

        if not row:
            raise RuntimeError("Não foi possível resolver empregador")

        return str(row["id"])

    def _resolver_situacao(self, situacao_raw: Any) -> tuple[Optional[str], Optional[str]]:
        if not situacao_raw:
            return (None, None)

        texto = str(situacao_raw).strip().upper()
        codigo = self._normalizar_situacao(texto)

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id FROM ref.situacao_plano WHERE codigo = %s",
                (codigo,),
            )
            row = cur.fetchone()

        if not row:
            raise RuntimeError(f"Situação não cadastrada: {codigo}")

        return (str(row["id"]), codigo)

    def _resolver_tipo_plano(self, tipo_raw: Any) -> Optional[str]:
        if not tipo_raw:
            return None

        texto = str(tipo_raw).strip()
        if not texto:
            return None

        codigo = self._normalizar_codigo(texto)

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id FROM ref.tipo_plano WHERE codigo = %s",
                (codigo,),
            )
            row = cur.fetchone()
            if row:
                return str(row["id"])

            cur.execute(
                """
                INSERT INTO ref.tipo_plano (codigo, descricao, ativo)
                VALUES (%s, %s, TRUE)
                RETURNING id
                """,
                (codigo, texto),
            )
            inserido = cur.fetchone()

        if not inserido:
            raise RuntimeError("Falha ao resolver tipo de plano")

        return str(inserido["id"])

    def _resolver_resolucao(self, resolucao_raw: Any) -> Optional[str]:
        if not resolucao_raw:
            return None

        codigo = str(resolucao_raw).strip()
        if not codigo:
            return None

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id FROM ref.resolucao WHERE codigo = %s",
                (codigo,),
            )
            row = cur.fetchone()
            if row:
                return str(row["id"])

            cur.execute(
                """
                INSERT INTO ref.resolucao (codigo, descricao, ativo)
                VALUES (%s, %s, TRUE)
                RETURNING id
                """,
                (codigo, codigo),
            )
            inserido = cur.fetchone()

        if not inserido:
            raise RuntimeError("Falha ao resolver resolução")

        return str(inserido["id"])

    @staticmethod
    def _calcular_atraso_desde(
        dias_em_atraso: Any,
        referencia: Any,
    ) -> Optional[date]:
        if dias_em_atraso is None:
            return None

        try:
            dias = int(dias_em_atraso)
        except (TypeError, ValueError):
            return None

        if dias < 0:
            return None

        if isinstance(referencia, datetime):
            base = referencia.date()
        elif isinstance(referencia, date):
            base = referencia
        else:
            base = date.today()
        return base - timedelta(days=dias)

    @staticmethod
    def _inferir_tipo_inscricao(numero: str) -> str:
        texto = "".join(ch for ch in str(numero) if ch.isdigit())
        if len(texto) == 14:
            return "CNPJ"
        if len(texto) == 11:
            return "CPF"
        return "CEI"

    @staticmethod
    def _normalizar_codigo(texto: str) -> str:
        canonico = "".join(
            ch if ch.isalnum() else "_" for ch in texto.upper().strip()
        )
        canonico = "_".join(filter(None, canonico.split("_")))
        return canonico or texto.upper()

    @staticmethod
    def _normalizar_situacao(texto: str) -> str:
        if not texto:
            return "EM_DIA"

        normalizado = texto.strip().upper()
        if not normalizado:
            return "EM_DIA"

        if "GRDE" in normalizado:
            return "GRDE_EMITIDA"
        if "SIT" in normalizado and "ESPECIAL" in normalizado:
            return "SIT_ESPECIAL"
        if "LIQ" in normalizado:
            return "LIQUIDADO"
        if normalizado.startswith("P.") or normalizado.startswith("P ") or normalizado.startswith("PRESC"):
            return "P_RESCISAO"
        if "P. RESCISAO" in normalizado:
            return "P_RESCISAO"
        if normalizado.startswith("RESC") or "RESCINDIDO" in normalizado:
            return "RESCINDIDO"
        return "EM_DIA"

    @staticmethod
    def _only_digits(valor: Any) -> str:
        texto = "".join(ch for ch in str(valor or "") if ch.isdigit())
        return texto

    @staticmethod
    def _safe_int(valor: Any) -> Optional[int]:
        if valor is None:
            return None
        texto = str(valor).strip()
        if not texto:
            return None
        digits = PlansRepository._only_digits(texto)
        candidato = digits or texto
        try:
            return int(candidato)
        except ValueError:
            return None

    @staticmethod
    def _parse_vencimento(valor: Any) -> Optional[date]:
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor
        texto = str(valor or "").strip()
        if not texto:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _to_decimal(valor: Any) -> Optional[Decimal]:
        if valor is None:
            return None
        if isinstance(valor, Decimal):
            return valor
        if isinstance(valor, (int, float)):
            return Decimal(str(valor))
        texto = str(valor).strip()
        if not texto:
            return None
        texto_normalizado = texto.replace(".", "").replace(",", ".")
        try:
            return Decimal(texto_normalizado)
        except InvalidOperation:
            return None

    def _preparar_parcelas(
        self, parcelas: Iterable[Any]
    ) -> list[dict[str, Any]]:
        registros: list[dict[str, Any]] = []
        for bruto in parcelas:
            if not isinstance(bruto, dict):
                continue
            numero = self._safe_int(bruto.get("parcela"))
            if numero is None:
                continue
            vencimento = self._parse_vencimento(bruto.get("vencimento"))
            if vencimento is None:
                continue
            valor = self._to_decimal(bruto.get("valor_num"))
            if valor is None:
                valor = self._to_decimal(bruto.get("valor"))
            if valor is None:
                continue
            qtd_total = self._safe_int(
                bruto.get("qtd_parcelas_total")
                or bruto.get("qtd_total")
                or bruto.get("total")
            )
            registros.append(
                {
                    "nr_parcela": numero,
                    "vencimento": vencimento,
                    "valor": valor,
                    "qtd_total": qtd_total,
                }
            )
        return registros

    def _situacao_parcela_em_atraso(self) -> Optional[str]:
        if self._situacao_parcela_atraso_id is not None:
            return self._situacao_parcela_atraso_id

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id FROM ref.situacao_parcela WHERE codigo = %s",
                ("EM_ATRASO",),
            )
            row = cur.fetchone()

        if row:
            self._situacao_parcela_atraso_id = str(row["id"])
        else:
            logger.warning("Situação de parcela 'EM_ATRASO' não encontrada no catálogo")
            self._situacao_parcela_atraso_id = None
        return self._situacao_parcela_atraso_id

    def _lock_plano(self, plano_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (str(plano_id),),
            )

    def _persistir_parcelas(
        self, plano_id: str, parcelas: list[dict[str, Any]]
    ) -> bool:
        if not parcelas:
            return False

        situacao_id = self._situacao_parcela_em_atraso()
        alterado = False

        merge_sql = """
            WITH sel AS (
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

        for registro in parcelas:
            params = (
                plano_id,
                registro["nr_parcela"],
                registro["vencimento"],
                plano_id,
                registro["nr_parcela"],
                registro["vencimento"],
                registro["valor"],
                situacao_id,
                None,
                None,
                registro.get("qtd_total"),
                registro["valor"],
                situacao_id,
                None,
                None,
                registro.get("qtd_total"),
            )

            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(merge_sql, params)
                rows = cur.fetchall()

            for row in rows:
                acao = row.get("acao")
                if acao in {"insert", "update"}:
                    alterado = True

        return alterado

    def _recalcular_atraso(self, plano_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT app.recalc_plano_atraso(app.current_tenant_id(), %s)",
                (plano_id,),
            )


class EventsRepository:
    """Persiste eventos de auditoria associados a planos."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def log(self, entity_id: str, step: Step | str, message: str) -> None:
        event_type = step.value if isinstance(step, Step) else str(step)
        payload = Json({})

        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit.evento (
                    tenant_id, event_time, entity, entity_id, event_type,
                    severity, message, data, user_id
                )
                VALUES (
                    app.current_tenant_id(), now(), 'plano', %s, %s,
                    'info', %s, %s, app.current_user_id()
                )
                """,
                (entity_id, event_type, message, payload),
            )


class OccurrenceRepository:
    """Registra ocorrências relevantes para auditoria."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def add(
        self,
        numero_plano: str,
        situacao: str,
        cnpj: str,
        tipo: Optional[str],
        saldo: Optional[float],
        dt_situacao_atual: date,
    ) -> None:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id FROM app.plano WHERE numero_plano = %s",
                (numero_plano,),
            )
            plano = cur.fetchone()
            if not plano:
                return

            mensagem = f"Ocorrência {situacao} para plano {numero_plano}"
            documento = PlansRepository._only_digits(cnpj) or (cnpj or "").strip() or None
            if isinstance(saldo, Decimal):
                saldo_json: Optional[str | float] = str(saldo)
            else:
                saldo_json = saldo
            payload = {
                "numero_plano": numero_plano,
                "documento": documento,
                "tipo_plano": tipo,
                "saldo_total": saldo_json,
                "dt_situacao_atual": dt_situacao_atual.isoformat(),
            }

            cur.execute(
                """
                INSERT INTO audit.evento (
                    tenant_id, event_time, entity, entity_id, event_type,
                    severity, message, data, user_id
                )
                VALUES (
                    app.current_tenant_id(), now(), 'plano', %s, 'OCORRENCIA',
                    'info', %s, %s, app.current_user_id()
                )
                """,
                (plano["id"], mensagem, Json(payload)),
            )


__all__ = [
    "EventsRepository",
    "OccurrenceRepository",
    "PlanDTO",
    "PlansRepository",
]
