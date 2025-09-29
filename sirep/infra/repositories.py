from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from psycopg import Connection, sql
from psycopg.rows import dict_row
from psycopg.types.json import Json

from sirep.domain.enums import Step


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
        empregador_id = self._resolver_empregador(campos)
        situacao_id, situacao_codigo = self._resolver_situacao(campos.get("situacao_atual"))
        tipo_id = self._resolver_tipo_plano(campos.get("tipo"))
        resolucao_id = self._resolver_resolucao(campos.get("resolucao"))

        atraso_desde = self._calcular_atraso_desde(
            campos.get("dias_em_atraso"),
            campos.get("dt_situacao_atual"),
        )

        status = campos.get("status")
        if status is not None:
            status_valor = getattr(status, "value", str(status))
        else:
            status_valor = None

        representacao = campos.get("representacao")
        dt_proposta = campos.get("dt_proposta")
        saldo = campos.get("saldo")
        dt_situacao_atual = campos.get("dt_situacao_atual")

        payload = {
            "empregador_id": empregador_id,
            "tipo_plano_id": tipo_id,
            "resolucao_id": resolucao_id,
            "situacao_plano_id": situacao_id,
            "dt_proposta": dt_proposta,
            "saldo_total": saldo,
            "atraso_desde": atraso_desde,
            "representacao": representacao,
            "status": status_valor,
            "dt_situacao_atual": dt_situacao_atual,
        }

        columns = [
            "tenant_id",
            "numero_plano",
            "empregador_id",
            "tipo_plano_id",
            "resolucao_id",
            "situacao_plano_id",
            "dt_proposta",
            "saldo_total",
            "atraso_desde",
            "representacao",
            "status",
            "dt_situacao_atual",
        ]

        values = [
            sql.SQL("app.current_tenant_id()"),
            sql.Placeholder(),
            sql.Placeholder(),
            sql.Placeholder(),
            sql.Placeholder(),
            sql.Placeholder(),
            sql.Placeholder(),
            sql.Placeholder(),
            sql.Placeholder(),
            sql.Placeholder(),
            sql.Placeholder(),
            sql.Placeholder(),
        ]

        update_assignments = [
            sql.SQL(
                "empregador_id = COALESCE(EXCLUDED.empregador_id, app.plano.empregador_id)"
            ),
            sql.SQL(
                "tipo_plano_id = COALESCE(EXCLUDED.tipo_plano_id, app.plano.tipo_plano_id)"
            ),
            sql.SQL(
                "resolucao_id = COALESCE(EXCLUDED.resolucao_id, app.plano.resolucao_id)"
            ),
            sql.SQL(
                "situacao_plano_id = COALESCE(EXCLUDED.situacao_plano_id, app.plano.situacao_plano_id)"
            ),
            sql.SQL(
                "dt_proposta = COALESCE(EXCLUDED.dt_proposta, app.plano.dt_proposta)"
            ),
            sql.SQL(
                "saldo_total = COALESCE(EXCLUDED.saldo_total, app.plano.saldo_total)"
            ),
            sql.SQL(
                "atraso_desde = COALESCE(EXCLUDED.atraso_desde, app.plano.atraso_desde)"
            ),
            sql.SQL(
                "representacao = COALESCE(EXCLUDED.representacao, app.plano.representacao)"
            ),
            sql.SQL("status = COALESCE(EXCLUDED.status, app.plano.status)"),
            sql.SQL(
                "dt_situacao_atual = COALESCE(EXCLUDED.dt_situacao_atual, app.plano.dt_situacao_atual)"
            ),
        ]

        params = [
            numero_plano,
            payload["empregador_id"],
            payload["tipo_plano_id"],
            payload["resolucao_id"],
            payload["situacao_plano_id"],
            payload["dt_proposta"],
            payload["saldo_total"],
            payload["atraso_desde"],
            payload["representacao"],
            payload["status"],
            payload["dt_situacao_atual"],
        ]

        insert_query = sql.SQL(
            """
            INSERT INTO app.plano ({columns})
                 VALUES ({values})
            ON CONFLICT (numero_plano)
              DO UPDATE SET {updates}
            RETURNING id
            """
        ).format(
            columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
            values=sql.SQL(", ").join(values),
            updates=sql.SQL(", ").join(update_assignments),
        )

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(insert_query, params)
            resultado = cur.fetchone()

        if not resultado:
            raise RuntimeError("Falha ao inserir/atualizar plano")

        plan_id = str(resultado["id"])
        existente = self.get_by_numero(numero_plano)
        if existente is not None:
            return existente
        return PlanDTO(plan_id, numero_plano, situacao_codigo)

    # -- Helpers -----------------------------------------------------------------

    def _resolver_empregador(self, campos: dict[str, Any]) -> Optional[str]:
        numero = campos.get("numero_inscricao")
        if not numero:
            return campos.get("empregador_id")

        codigo_tipo = self._inferir_tipo_inscricao(numero)
        razao_social = campos.get("razao_social") or None

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
                    tenant_id, tipo_inscricao_id, numero_inscricao, razao_social
                )
                VALUES (
                    app.current_tenant_id(), %s, %s, %s
                )
                ON CONFLICT (tenant_id, tipo_inscricao_id, numero_inscricao)
                DO UPDATE SET
                    razao_social = COALESCE(EXCLUDED.razao_social, app.empregador.razao_social)
                RETURNING id
                """,
                (tipo["id"], numero, razao_social),
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

        if isinstance(referencia, date):
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

        if texto.startswith("P.") or texto.startswith("P "):
            return "P_RESCISAO"
        if texto.startswith("PRESC"):
            return "P_RESCISAO"
        if "SIT" in texto and "ESPECIAL" in texto:
            return "SIT_ESPECIAL"
        if "RESCINDIDO" in texto:
            return "RESCINDIDO"
        if "LIQ" in texto:
            return "LIQUIDADO"
        if "GRDE" in texto:
            return "GRDE_EMITIDA"
        return "EM_DIA"


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
            payload = {
                "cnpj": cnpj,
                "tipo": tipo,
                "saldo": saldo,
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
