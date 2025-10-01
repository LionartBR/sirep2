from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from psycopg import Connection
from psycopg.rows import dict_row

from infra.audit import log_event
from shared.text import normalize_document


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
            documento = normalize_document(cnpj)
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

            log_event(
                self._conn,
                entity="plano",
                entity_id=str(plano["id"]),
                event_type="OCORRENCIA",
                severity="info",
                message=mensagem,
                data=payload,
            )


__all__ = ["OccurrenceRepository"]
