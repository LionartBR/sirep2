from __future__ import annotations

from dataclasses import dataclass, field

from psycopg import Connection
from psycopg.pq import TransactionStatus

from ._helpers import normalizar_codigo, normalizar_situacao


@dataclass(slots=True)
class LookupCache:
    """Mantém em memória os catálogos utilizados pelo pipeline."""

    tipos_plano: dict[str, str]
    resolucoes: dict[str, str]
    situacoes_plano: dict[str, str]
    tipos_inscricao: dict[str, str]
    bases_fgts: dict[str, str]
    pending_tipos_plano: set[str] = field(default_factory=set)
    pending_resolucoes: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, conn: Connection) -> "LookupCache":
        """Carrega todos os catálogos necessários a partir do banco."""

        with conn.cursor() as cur:
            cur.execute("SELECT codigo, id FROM ref.tipo_plano")
            tipos = {
                normalizar_codigo(str(codigo)): str(ident)
                for codigo, ident in cur.fetchall()
            }

            cur.execute("SELECT codigo, id FROM ref.resolucao")
            resolucoes = {
                str(codigo).strip(): str(ident) for codigo, ident in cur.fetchall()
            }

            cur.execute("SELECT codigo, id FROM ref.situacao_plano")
            situacoes: dict[str, str] = {}
            for codigo, ident in cur.fetchall():
                codigo_raw = str(codigo).strip().upper()
                ident_str = str(ident)
                situacoes[codigo_raw] = ident_str
                codigo_normalizado = normalizar_situacao(codigo_raw)
                situacoes[codigo_normalizado] = ident_str

            cur.execute("SELECT codigo, id FROM ref.tipo_inscricao")
            tipos_inscricao = {
                str(codigo).strip().upper(): str(ident)
                for codigo, ident in cur.fetchall()
            }

            cur.execute("SELECT codigo, id FROM ref.base_fgts")
            bases_fgts = {
                str(codigo).strip(): str(ident)
                for codigo, ident in cur.fetchall()
            }

        return cls(
            tipos_plano=tipos,
            resolucoes=resolucoes,
            situacoes_plano=situacoes,
            tipos_inscricao=tipos_inscricao,
            bases_fgts=bases_fgts,
        )

    def refresh(self, conn: Connection) -> None:
        """Recarrega os catálogos a partir do banco."""

        atualizado = self.load(conn)
        self.tipos_plano = atualizado.tipos_plano
        self.resolucoes = atualizado.resolucoes
        self.situacoes_plano = atualizado.situacoes_plano
        self.tipos_inscricao = atualizado.tipos_inscricao
        self.bases_fgts = atualizado.bases_fgts
        self.pending_tipos_plano.clear()
        self.pending_resolucoes.clear()

    def mark_tipo_plano_pending(self, codigo: str) -> None:
        """Registra que um tipo de plano foi inserido na transação atual."""

        self.pending_tipos_plano.add(codigo)

    def mark_resolucao_pending(self, codigo: str) -> None:
        """Registra que uma resolução foi inserida na transação atual."""

        self.pending_resolucoes.add(codigo)

    def sync_pending(self, conn: Connection) -> None:
        """Sincroniza o cache quando há inserções pendentes."""

        if not (self.pending_tipos_plano or self.pending_resolucoes):
            return

        info = getattr(conn, "info", None)
        status = getattr(info, "transaction_status", None)

        if not isinstance(status, TransactionStatus):
            return

        if status is not TransactionStatus.IDLE:
            return

        self.refresh(conn)


__all__ = ["LookupCache"]
