from __future__ import annotations

import logging
from typing import Callable, List, Optional

from services.pw3270 import PW3270

from .models import (
    GestaoBaseCollector,
    GestaoBaseData,
    PipelineAuditHooks,
    PlanRowEnriched,
    ProgressCallback,
)
from .pipeline import run_pipeline
from .portal import portal_po_provider
from .terminal import session

logger = logging.getLogger(__name__)


def _sample_data() -> GestaoBaseData:
    exemplos = [
        PlanRowEnriched(
            numero="1234567890",
            dt_propost="01/02/2024",
            tipo="PR1",
            situac="P.RESC.",
            resoluc="123/45",
            razao_social="Empresa Alfa Ltda",
            saldo_total="12.345,67",
            cnpj="12.345.678/0001-90",
        ),
        PlanRowEnriched(
            numero="2345678901",
            dt_propost="15/03/2024",
            tipo="PR2",
            situac="SIT. ESPECIAL (Portal PO)",
            resoluc="",
            razao_social="Empresa Beta S.A.",
            saldo_total="8.900,10",
            cnpj="98.765.432/0001-10",
        ),
    ]
    portal_po = [
        {"Plano": "2345678901", "CNPJ": "98.765.432/0001-10", "Tipo": "ESPECIAL"},
    ]
    return GestaoBaseData(rows=exemplos, raw_lines=[], portal_po=portal_po, descartados_974=0)


class DryRunCollector(GestaoBaseCollector):
    def collect(
        self,
        progress: Optional[ProgressCallback] = None,
        audit_hooks: Optional[PipelineAuditHooks] = None,
    ) -> GestaoBaseData:
        logger.info("Executando coleta de Gestão da Base em modo dry-run")
        if progress:
            progress(10.0, None, "Captura simulada iniciada")
            progress(35.0, 1, "Dados simulados coletados")
            progress(50.0, 2, "Situação especial simulada aplicada")
            progress(65.0, 3, "Dados simulados enriquecidos")
        data = _sample_data()
        if audit_hooks:
            audit_hooks.stage_started(
                "CAPTURA_PLANOS", "Captura simulada de Planos", data={}
            )
            capture_metrics = {
                "capturados_total": len(data.rows),
                "descartados_974": data.descartados_974,
                "erros_parse": len(data.raw_lines),
            }
            audit_hooks.stage_finished(
                "CAPTURA_PLANOS", "Captura simulada concluída", capture_metrics
            )

            audit_hooks.stage_started(
                "SITUACAO_ESPECIAL",
                "Portal PO simulado",
                data={"qtde_po_capturados": len(data.portal_po)},
            )
            sit_especial = sum(
                1
                for row in data.rows
                if (row.situac or "").upper().startswith("SIT. ESPECIAL")
            )
            audit_hooks.stage_finished(
                "SITUACAO_ESPECIAL",
                "Situação especial simulada concluída",
                {
                    "qtde_po_capturados": len(data.portal_po),
                    "sit_especial": sit_especial,
                },
            )

            audit_hooks.stage_started(
                "GUIA_GRDE", "Verificação GRDE simulada", data={}
            )
            grde_emitida = sum(1 for row in data.rows if row.situac == "GRDE Emitida")
            audit_hooks.stage_finished(
                "GUIA_GRDE",
                "Verificação GRDE simulada concluída",
                {
                    "qtde_grde_emitida": grde_emitida,
                    "qtde_grde_nao_emitida": len(data.rows) - grde_emitida,
                },
            )
        return data


class TerminalCollector(GestaoBaseCollector):  # pragma: no cover - integrações reais
    def __init__(
        self, senha: str, portal_provider: Optional[Callable[[], List[dict]]] = None
    ) -> None:
        if PW3270 is None:
            raise RuntimeError("Biblioteca pw3270 não disponível no ambiente")
        self.senha = senha
        self.portal_provider = portal_provider or portal_po_provider

    def collect(
        self,
        progress: Optional[ProgressCallback] = None,
        audit_hooks: Optional[PipelineAuditHooks] = None,
    ) -> GestaoBaseData:
        assert PW3270 is not None
        pw = PW3270()
        with session(pw):
            return run_pipeline(
                pw,
                self.senha,
                portal_provider=self.portal_provider,
                progress=progress,
                audit_hooks=audit_hooks,
            )
