from __future__ import annotations

import logging
import math
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any, Optional

from domain.enums import PlanStatus, Step
from infra.config import settings
from infra.repositories import OccurrenceRepository
from services.base import StepJobContext

from .models import GestaoBaseData, ProgressCallback
from .parcelas import normalize_parcelas_atraso
from .utils import only_digits, parse_date_any, parse_money_brl

logger = logging.getLogger(__name__)


def clean_inscricao(raw: str | None) -> str:
    texto = (raw or "").strip()
    digits = only_digits(texto)
    return digits or texto


def _representacao_value(raw: str | None, fallback: str | None) -> str | None:
    texto = (raw or "").strip()
    if texto:
        return texto
    return fallback or None


def _infer_plan_status(situacao: str | None) -> PlanStatus | None:
    texto = (situacao or "").strip()
    if not texto:
        return None
    normalizado = texto.upper()
    if normalizado.startswith("P.RESC") or normalizado.startswith("PRESC"):
        return PlanStatus.PASSIVEL_RESC
    if "ESPECIAL" in normalizado:
        return PlanStatus.ESPECIAL
    if "LIQ" in normalizado:
        return PlanStatus.LIQUIDADO
    if "GRDE" in normalizado:
        return PlanStatus.NAO_RESCINDIDO
    if normalizado.startswith("RESC"):
        return PlanStatus.RESCINDIDO
    return PlanStatus.PASSIVEL_RESC


def _normalize_situacao_tokens(situacao: str | None) -> list[str]:
    """Converte a situação em tokens maiúsculos sem acentuação."""

    texto = (situacao or "").strip()
    if not texto:
        return []

    decomposed = unicodedata.normalize("NFKD", texto)
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    tokens = [
        token
        for token in re.split(r"[^A-Z0-9]+", ascii_only.upper())
        if token
    ]
    return tokens


def _tokens_indicate_passivel_rescisao(tokens: list[str]) -> bool:
    """Retorna ``True`` se os tokens representam "passível rescisão"."""

    if not tokens:
        return False

    saw_passivel = False
    saw_passivel_component = False

    for token in tokens:
        if token == "P":
            saw_passivel_component = True
            continue
        if token in {"DE", "DA", "DO"}:
            continue
        if token.startswith("PASSIVEL"):
            saw_passivel = True
            if "RESC" in token:
                saw_passivel_component = True
            continue
        if token.startswith("PRESC"):
            saw_passivel_component = True
            continue
        if token in {"RESC", "RESCISAO"}:
            saw_passivel_component = True
            continue
        if token.startswith("RESC") and token not in {"RESC", "RESCISAO"}:
            return False
        if token.startswith("LIQ") or token == "GRDE" or token.startswith("ESPECIAL"):
            return False
        if saw_passivel_component:
            # After identifying a passível component we allow extra descriptors
            # (e.g. "EM", "ANALISE", "DEFERIDA") without invalidating the match.
            continue
        return False

    has_abbreviation = any(token.startswith("PRESC") for token in tokens)
    prefix_is_p = tokens[0] == "P"
    return saw_passivel_component and (saw_passivel or has_abbreviation or prefix_is_p)


def _should_register_occurrence(situacao: str | None) -> bool:
    tokens = _normalize_situacao_tokens(situacao)
    if not tokens:
        return False
    return not _tokens_indicate_passivel_rescisao(tokens)


def format_summary(stats: dict[str, int]) -> str:
    total = stats.get("importados", 0)
    novos = stats.get("novos", 0)
    atualizados = stats.get("atualizados", 0)
    detalhes: list[str] = []
    if novos:
        detalhes.append(f"{novos} novos")
    if atualizados:
        detalhes.append(f"{atualizados} atualizados")
    if detalhes:
        return f"{total} planos ({', '.join(detalhes)})"
    if total:
        return f"{total} planos"
    return "Nenhum plano processado"


def persist_rows(
    context: StepJobContext,
    data: GestaoBaseData,
    progress_callback: Optional[ProgressCallback] = None,
) -> dict[str, int]:
    hoje = datetime.now(UTC).date()
    processados = 0
    novos = 0
    atualizados = 0
    total_rows = len(data.rows)

    if progress_callback:
        if total_rows:
            progress_callback(55.0, 4, f"Persistindo {total_rows} planos capturados")
        else:
            progress_callback(55.0, 4, "Nenhum plano para persistir")

    if not total_rows:
        if progress_callback:
            progress_callback(100.0, 4, "Persistência concluída")
        return {"importados": 0, "novos": 0, "atualizados": 0}

    occurrence_repo = OccurrenceRepository(context.db) if not settings.DRY_RUN else None
    occurrence_registrados: set[str] = set()

    for idx, row in enumerate(data.rows, start=1):
        processados += 1
        existente = context.plans.get_by_numero(row.numero)
        situacao = (row.situac or "").strip()
        tipo = (row.tipo or "").strip()
        dt_proposta = parse_date_any(row.dt_propost)
        saldo_raw = parse_money_brl(getattr(row, "saldo_total", None))
        saldo = None if math.isnan(saldo_raw) else saldo_raw
        cnpj_value = getattr(row, "cnpj", None)
        inscricao_canonica = clean_inscricao(cnpj_value)
        inscricao_original = (cnpj_value or "").strip()

        campos: dict[str, Any] = {
            "dt_situacao_atual": hoje,
            "situacao_anterior": existente.situacao_atual if existente else None,
        }

        parcelas_normalizadas, dias_calculado = normalize_parcelas_atraso(
            getattr(row, "parcelas_atraso", None),
            referencia=hoje,
        )

        if situacao:
            campos["situacao_atual"] = situacao
        if tipo:
            campos["tipo"] = tipo
        if dt_proposta is not None:
            campos["dt_proposta"] = dt_proposta
        if saldo is not None:
            campos["saldo"] = saldo
        resolucao = (row.resoluc or "").strip()
        if resolucao:
            campos["resolucao"] = resolucao
        razao_social = (
            getattr(row, "razao_social", getattr(row, "nome", "")) or ""
        ).strip()
        if razao_social:
            campos["razao_social"] = razao_social
        if inscricao_canonica:
            campos["numero_inscricao"] = inscricao_canonica
        representacao = _representacao_value(inscricao_original, inscricao_canonica)
        if representacao is not None:
            campos["representacao"] = representacao
        campos["parcelas_atraso"] = parcelas_normalizadas

        campos["dias_em_atraso"] = dias_calculado

        status = _infer_plan_status(situacao)
        if status is not None:
            campos["status"] = status
        elif existente is None:
            campos["status"] = PlanStatus.PASSIVEL_RESC

        plan = context.plans.upsert(numero_plano=row.numero, existing=existente, **campos)

        if occurrence_repo and _should_register_occurrence(situacao):
            numero_plano = row.numero.strip()
            if numero_plano and numero_plano not in occurrence_registrados:
                cnpj_ocorrencia = (
                    representacao or inscricao_original or inscricao_canonica
                )
                if cnpj_ocorrencia:
                    occurrence_repo.add(
                        numero_plano=numero_plano,
                        situacao=situacao,
                        cnpj=cnpj_ocorrencia,
                        tipo=tipo or None,
                        saldo=saldo,
                        dt_situacao_atual=hoje,
                    )
                    occurrence_registrados.add(numero_plano)
                else:
                    logger.debug(
                        "Ocorrência ignorada para plano %s: CNPJ ausente",
                        numero_plano,
                    )

        if existente is None:
            novos += 1
            mensagem = "Plano importado via Gestão da Base"
        else:
            atualizados += 1
            mensagem = "Plano atualizado via Gestão da Base"
        context.events.log(plan.id, Step.ETAPA_1, mensagem)

        if progress_callback:
            percentual = 55.0 + (idx / total_rows) * 45.0
            progress_callback(percentual, None, None)

    if progress_callback:
        progress_callback(100.0, 4, "Persistência concluída")

    return {
        "importados": processados,
        "novos": novos,
        "atualizados": atualizados,
    }
