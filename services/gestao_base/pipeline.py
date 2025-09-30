from __future__ import annotations

import logging
from typing import Callable, Optional

from .constants import MSG_FIM_BLOCO, MSG_ULTIMA_PAGINA, RESOLUCAO_DESCARTAR
from .models import GestaoBaseData, PlanRow, ProgressCallback, PipelineAuditHooks
from .portal import aplica_sit_especial, build_tipo_map
from .terminal import (
    enrich_on_e527,
    iterate_e555_pages,
    login_fge,
    open_e50h,
    open_e527,
    open_e555,
    parse_line,
    pf,
    search_grde,
)

logger = logging.getLogger(__name__)


def run_pipeline(
    pw,
    senha: str,
    portal_provider: Optional[Callable[[], list[dict]]] = None,
    *,
    progress: Optional[ProgressCallback] = None,
    audit_hooks: Optional[PipelineAuditHooks] = None,
) -> GestaoBaseData:  # pragma: no cover - integrações reais
    if progress:
        progress(5.0, None, "Estabelecendo sessão no terminal")
    login_fge(pw, senha)
    if progress:
        progress(10.0, None, "Captura da E555 iniciada")
    open_e555(pw)

    blocos = 0
    raw_lines: list[str] = []
    all_rows: list[PlanRow] = []

    capture_step = "CAPTURA_PLANOS"
    if audit_hooks:
        audit_hooks.stage_started(capture_step, "Iniciando Captura de Planos")

    erros_parse = 0

    try:
        while True:
            blocos += 1
            logger.info("Iniciando bloco %s", blocos)
            footer_after_last: Optional[str] = None
            for page_lines, (_x, y, z), footer in iterate_e555_pages(pw):
                for line in page_lines:
                    parsed = parse_line(line)
                    if parsed:
                        all_rows.append(parsed)
                    else:
                        raw_lines.append(line)
                        erros_parse += 1
                if footer is not None:
                    footer_after_last = footer

            footer_after_last = (footer_after_last or "").strip()
            if MSG_FIM_BLOCO in footer_after_last:
                logger.info("Fim do bloco, avançando para próximo bloco")
                pf(pw, 11)
                continue
            if MSG_ULTIMA_PAGINA in footer_after_last:
                logger.info("Última página, encerrando coleta da E555")
                break
            if footer_after_last:
                logger.warning("Mensagem inesperada no rodapé: %r", footer_after_last)
            break
    except Exception as exc:
        if audit_hooks:
            audit_hooks.stage_failed(
                capture_step,
                f"Falha na captura de planos: {exc}",
                data={"capturados_total": len(all_rows), "erros_parse": erros_parse},
            )
        raise

    dados_filtrados = [row for row in all_rows if row.resoluc != RESOLUCAO_DESCARTAR]
    descartados_974 = len(all_rows) - len(dados_filtrados)
    capture_metrics = {
        "capturados_total": len(dados_filtrados),
        "descartados_974": descartados_974,
        "erros_parse": erros_parse,
    }
    if audit_hooks:
        audit_hooks.stage_finished(
            capture_step,
            "Captura concluída",
            capture_metrics,
        )
    if progress:
        progress(25.0, 1, f"{len(dados_filtrados)} planos capturados na E555")

    portal_step = "SITUACAO_ESPECIAL"
    if audit_hooks:
        audit_hooks.stage_started(
            portal_step, "Verificando Situação Especial (Portal PO)"
        )

    portal_po: list[dict] = []

    try:
        if portal_provider:
            portal_po = portal_provider() or []
            logger.info("Portal PO: %s registros", len(portal_po))
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("Falha ao obter Portal PO: %s", exc)
        portal_po = []

    if progress:
        progress(35.0, 2, "Dados do Portal PO integrados")

    tipos_map = build_tipo_map(portal_po) if portal_po else {}

    dados_ajustados: list[PlanRow] = []
    try:
        dados_ajustados = (
            aplica_sit_especial(dados_filtrados, tipos_map)
            if tipos_map
            else list(dados_filtrados)
        )
    except Exception as exc:
        if audit_hooks:
            audit_hooks.stage_failed(
                portal_step,
                f"Falha ao aplicar situação especial: {exc}",
                data={"qtde_po_capturados": len(portal_po)},
            )
        raise

    sit_especial = sum(
        1 for row in dados_ajustados if "SIT. ESPECIAL" in (row.situac or "")
    )
    portal_metrics = {
        "qtde_po_capturados": len(portal_po),
        "sit_especial": sit_especial,
    }
    if audit_hooks:
        audit_hooks.stage_finished(
            portal_step,
            "Portal PO processado",
            portal_metrics,
        )

    open_e527(pw)
    enriched = enrich_on_e527(pw, dados_ajustados)

    guia_step = "GUIA_GRDE"
    if audit_hooks:
        audit_hooks.stage_started(
            guia_step, "Verificando GRDE (e50h)", data={"planos": len(enriched)}
        )

    try:
        open_e50h(pw)
        enriched = search_grde(pw, enriched)
    except Exception as exc:
        if audit_hooks:
            audit_hooks.stage_failed(
                guia_step,
                f"Falha na verificação de GRDE: {exc}",
                data={"planos": len(enriched)},
            )
        raise

    grde_emitida = sum(1 for row in enriched if row.situac == "GRDE Emitida")
    guia_metrics = {
        "qtde_grde_emitida": grde_emitida,
        "qtde_grde_nao_emitida": len(enriched) - grde_emitida,
    }
    if audit_hooks:
        audit_hooks.stage_finished(
            guia_step,
            "Verificação GRDE concluída",
            guia_metrics,
        )

    if progress:
        progress(50.0, 3, "Captura de dados na E527 concluído")

    return GestaoBaseData(
        rows=enriched,
        raw_lines=raw_lines,
        portal_po=portal_po,
        descartados_974=descartados_974,
    )
