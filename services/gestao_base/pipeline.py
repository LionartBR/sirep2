from __future__ import annotations

import logging
from typing import Callable, List, Optional

from .constants import MSG_FIM_BLOCO, MSG_ULTIMA_PAGINA, RESOLUCAO_DESCARTAR
from .models import GestaoBaseData, PlanRow, ProgressCallback
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
    portal_provider: Optional[Callable[[], List[dict]]] = None,
    *,
    progress: Optional[ProgressCallback] = None,
) -> GestaoBaseData:  # pragma: no cover - integrações reais
    if progress:
        progress(5.0, None, "Estabelecendo sessão no terminal")
    login_fge(pw, senha)
    if progress:
        progress(10.0, None, "Captura da E555 iniciada")
    open_e555(pw)

    blocos = 0
    raw_lines: List[str] = []
    all_rows: List[PlanRow] = []

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

    dados_filtrados = [row for row in all_rows if row.resoluc != RESOLUCAO_DESCARTAR]
    descartados_974 = len(all_rows) - len(dados_filtrados)
    if progress:
        progress(25.0, 1, f"{len(dados_filtrados)} planos capturados na E555")

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

    dados_ajustados: List[PlanRow] = (
        aplica_sit_especial(dados_filtrados, tipos_map)
        if tipos_map
        else list(dados_filtrados)
    )

    open_e527(pw)
    enriched = enrich_on_e527(pw, dados_ajustados)

    open_e50h(pw)
    enriched = search_grde(pw, enriched)

    if progress:
        progress(50.0, 3, "Enriquecimento na E527 concluído")

    return GestaoBaseData(
        rows=enriched,
        raw_lines=raw_lines,
        portal_po=portal_po,
        descartados_974=descartados_974,
    )
