from __future__ import annotations

import html
import json
import logging
import math
import re
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from hashlib import md5
from time import sleep
from typing import Any, Callable, Iterable, Iterator, List, Optional, Protocol, Tuple
from json import JSONDecodeError

from sirep.domain.enums import PlanStatus, Step
from sirep.infra.config import settings
from sirep.infra.repositories import OccurrenceRepository
from sirep.infra.runtime_credentials import (
    get_gestao_base_password,
    set_gestao_base_password,
)
from sirep.services.base import (
    ServiceResult,
    StepJobContext,
    StepJobOutcome,
    run_step_job,
)

from sirep.services.pw3270 import PW3270

logger = logging.getLogger(__name__)

# ---------------------------- Config / Constantes ----------------------------

DATA_LINES = range(10, 20)  # linhas onde estão os dados na E555
COL_START = 1
COL_WIDTH = 80

STATUS_HINT_POS = (21, 45, 21)  # "Linhas x a y de z"
FOOTER_MSG_POS = (22, 1, 80)  # Mensagens "FGEN2213"/"FGEN1389"

POS_E527_NUMERO = (6, 71)
POS_E527_RAZAO = (5, 18, 62)
POS_E527_SALDO = (19, 50, 30)
POS_E527_CNPJ = (4, 37, 18)

POS_E50H_NUMERO = (6, 71)
POS_GRDE = (9, 2, 33)

MAX_ATTEMPTS = 3
REQUEST_DELAY = 0.2

RESOLUCAO_DESCARTAR = "974/20"

MSG_FIM_BLOCO = "FGEN2213"
MSG_ULTIMA_PAGINA = "FGEN1389"

TIPOS_PREDET = [
    "Ação Judicial/Ajuste",
    "Acompanhamento diferenciado",
    "Controle Representação",
    "Em depuração",
    "Erro de encadeamento",
    "Garantido por Dep. Jud.",
    "PROFUT",
    "Regularização de Plano Indevido",
    "Retorno Pré-formalizado",
]


# ------------------------------ Utilitários ---------------------------------


def only_digits(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


def parse_date_any(raw: str | None) -> Optional[date]:
    texto = (raw or "").strip()
    if not texto:
        return None
    formatos = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")
    for fmt in formatos:
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def parse_money_brl(raw: str | None) -> float:
    if raw is None:
        return math.nan
    texto = str(raw)
    negativo = "(" in texto and ")" in texto
    limpo = re.sub(r"[^\d.,-]", "", texto)
    limpo = limpo.replace(".", "").replace(",", ".")
    try:
        valor = float(limpo)
    except ValueError:
        return math.nan
    return -valor if negativo else valor


# --------------------- Parcelas em atraso helpers ---------------------------


def _first_non_empty(mapping: dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for key in keys:
        if key not in mapping:
            continue
        raw = mapping.get(key)
        if raw is None:
            continue
        texto = str(raw).strip()
        if texto:
            return texto
    return None


def _parse_vencimento(raw: Any) -> tuple[Optional[date], Optional[str]]:
    if isinstance(raw, datetime):
        return raw.date(), raw.date().isoformat()
    if isinstance(raw, date):
        return raw, raw.isoformat()

    texto = str(raw or "").strip()
    if not texto:
        return None, None

    try:
        parsed = datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        return None, texto

    return parsed, texto


def _split_parcela_string(
    texto: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    partes = [p.strip() for p in re.split(r"\s{2,}", texto.strip()) if p.strip()]
    if not partes:
        return (None, None, None)
    if len(partes) == 1:
        return (partes[0], None, None)
    if len(partes) == 2:
        return (partes[0], partes[1], None)
    return (partes[0], partes[1], partes[-1])


def _normalize_parcelas_atraso(
    parcelas: Optional[Iterable[Any]],
    *,
    referencia: Optional[date] = None,
) -> tuple[list[dict[str, Any]], Optional[int]]:
    if not parcelas:
        return ([], None)

    referencia = referencia or date.today()

    registros: list[tuple[Optional[date], int, dict[str, Any], Optional[int]]] = []

    for idx, item in enumerate(parcelas):
        numero: Optional[str] = None
        valor_raw: Optional[str] = None
        venc_raw: Optional[Any] = None

        if isinstance(item, dict):
            numero = _first_non_empty(
                item,
                ("parcela", "numero", "sequencia", "id", "codigo"),
            )
            valor_candidate = _first_non_empty(
                item,
                ("valor", "valor_parcela", "valor_atraso", "valor_nominal"),
            )
            valor_raw = valor_candidate
            venc_raw = item.get("vencimento")
            if venc_raw is None:
                venc_raw = item.get("dt_vencimento")
            if venc_raw is None:
                venc_raw = item.get("data_vencimento")
            if venc_raw is None:
                venc_raw = item.get("data")
            if venc_raw is None:
                venc_raw = item.get("venc")
        elif isinstance(item, (list, tuple)):
            numero = (
                str(item[0]).strip()
                if len(item) >= 1 and str(item[0]).strip()
                else None
            )
            valor_raw = str(item[1]).strip() if len(item) >= 2 else None
            venc_raw = item[2] if len(item) >= 3 else None
        else:
            texto = str(item or "").strip()
            if not texto:
                continue
            numero, valor_raw, venc_string = _split_parcela_string(texto)
            venc_raw = venc_string

        vencimento, vencimento_texto = _parse_vencimento(venc_raw)
        entrada: dict[str, Any] = {}
        if numero:
            entrada["parcela"] = numero

        valor_texto = str(valor_raw or "").strip()
        if valor_texto:
            entrada["valor"] = valor_texto
            valor_num = parse_money_brl(valor_texto)
            if not math.isnan(valor_num):
                entrada["valor_num"] = valor_num

        if vencimento is not None:
            entrada["vencimento"] = vencimento.isoformat()
            if vencimento_texto and vencimento_texto != entrada["vencimento"]:
                entrada["vencimento_texto"] = vencimento_texto
        elif vencimento_texto:
            entrada["vencimento"] = vencimento_texto

        dias_atraso: Optional[int] = None
        if vencimento is not None:
            delta = (referencia - vencimento).days
            if delta >= 0:
                dias_atraso = delta

        # Remove campos vazios para evitar registros inúteis
        entrada = {
            chave: valor for chave, valor in entrada.items() if valor not in (None, "")
        }
        if not entrada and dias_atraso is None:
            continue

        registros.append((vencimento, idx, entrada, dias_atraso))

    if not registros:
        return ([], None)

    registros.sort(
        key=lambda item: (
            item[0] is None,
            item[0] or date.max,
            item[1],
        )
    )

    selecionados: list[dict[str, Any]] = []
    dias_coletados: list[int] = []
    for vencimento, _, entrada, dias_atraso in registros[:3]:
        selecionados.append(entrada)
        if dias_atraso is not None:
            dias_coletados.append(dias_atraso)

    dias_total = max(dias_coletados) if dias_coletados else None
    return (selecionados, dias_total)


# ---------------------------- Modelos de Dados ------------------------------


@dataclass(frozen=True)
class PlanRow:
    numero: str
    dt_propost: str
    tipo: str
    situac: str
    resoluc: str
    nome: str


@dataclass(frozen=True)
class PlanRowEnriched:
    numero: str
    dt_propost: str
    tipo: str
    situac: str
    resoluc: str
    razao_social: str
    saldo_total: str
    cnpj: str
    parcelas_atraso: Optional[List[dict[str, Any]]] = None
    dias_atraso: Optional[int] = None


@dataclass(frozen=True)
class GestaoBaseData:
    rows: List[PlanRowEnriched]
    raw_lines: List[str]
    portal_po: List[dict]
    descartados_974: int


ProgressCallback = Callable[[float, Optional[int], Optional[str]], None]


class GestaoBaseCollector(Protocol):
    def collect(
        self, progress: Optional[ProgressCallback] = None
    ) -> GestaoBaseData: ...


# ---------------------------- Helpers Terminais -----------------------------


def hash_lines(lines: Iterable[str]) -> str:
    return md5("\n".join(lines).encode()).hexdigest()


def parse_pagination(texto: str) -> Tuple[int, int, int]:
    match = re.search(r"Linhas\s+(\d+)\s+a\s+(\d+)\s+de\s+(\d+)", texto or "")
    if not match:
        raise ValueError(f"Formato inválido de paginação: '{texto}'")
    x, y, z = map(int, match.groups())
    return (x, z, z) if y == z else (x, y, z)


def parse_line(raw: str) -> Optional[PlanRow]:
    try:
        numero = raw[2:13].strip()
        dt_prop = raw[14:26].strip()
        tipo = raw[27:30].strip()
        situac = raw[31:41].strip()
        resoluc = raw[42:49].strip()
        razao_social = raw[54:].strip()
        if not numero:
            return None
        return PlanRow(numero, dt_prop, tipo, situac, resoluc, razao_social)
    except Exception as exc:  # pragma: no cover - proteção defensiva
        logger.warning("Erro ao parsear linha: %s - %s", raw[:60], exc)
        return None


def should_skip_line(raw: str) -> bool:
    texto = (raw or "").strip()
    return (not texto) or texto.startswith("Sel") or texto.startswith("Prox.Trans.")


@contextmanager
def session(pw: PW3270):  # pragma: no cover - integração externa
    pw.connect(delay=100)
    try:
        if not pw.is_connected():
            raise RuntimeError("Sem conexão ao Rede Caixa.")
        logger.info("Conectado ao Rede Caixa.")
        yield
    finally:
        pw.send_pf_key(12)
        pw.disconnect()
        if not pw.is_connected():
            logger.info("Sessão no Rede Caixa encerrada.")


def enter(pw: PW3270):  # pragma: no cover - integração externa
    pw.enter()
    pw.wait_status_ok()
    sleep(REQUEST_DELAY)


def pf(pw: PW3270, n: int):  # pragma: no cover - integração externa
    pw.send_pf_key(n)
    pw.wait_status_ok()
    sleep(REQUEST_DELAY)


def put(pw: PW3270, row: int, col: int, text: str):  # pragma: no cover
    pw.put_string(row, col, text)


def get_text(pw: PW3270, row: int, col: int, length: int) -> str:  # pragma: no cover
    return (pw.get_string(row, col, length) or "").strip()


def fill_and_enter(pw: PW3270, row: int, col: int, text: str):  # pragma: no cover
    put(pw, row, col, text)
    enter(pw)


def goto_tx(pw: PW3270, code: str):  # pragma: no cover
    fill_and_enter(pw, 21, 14, code)


def login_fge(pw: PW3270, senha: str):  # pragma: no cover
    fill_and_enter(pw, 17, 38, "611")
    fill_and_enter(pw, 9, 58, senha)
    fill_and_enter(pw, 4, 15, "FGE")


def open_e555(pw: PW3270):  # pragma: no cover
    goto_tx(pw, "E555")
    fill_and_enter(pw, 7, 18, "06")


def open_e527(pw: PW3270):
    goto_tx(pw, "E527")


def open_e50h(pw: PW3270):
    goto_tx(pw, "E50H")


def read_page_lines(pw: PW3270) -> List[str]:  # pragma: no cover
    lines: List[str] = []
    for lin in DATA_LINES:
        raw = get_text(pw, lin, COL_START, COL_WIDTH)
        if not should_skip_line(raw):
            lines.append(raw)
    return lines


def read_pagination_hint(pw: PW3270) -> Tuple[int, int, int]:  # pragma: no cover
    hint = get_text(pw, *STATUS_HINT_POS)
    return parse_pagination(hint)


def read_footer_message(pw: PW3270) -> str:  # pragma: no cover
    return get_text(pw, *FOOTER_MSG_POS)


def iterate_e555_pages(
    pw: PW3270,
) -> Iterator[
    Tuple[List[str], Tuple[int, int, int], Optional[str]]
]:  # pragma: no cover
    seen_hashes = set()
    attempts = 0

    while True:
        page_lines = read_page_lines(pw)
        page_hash = hash_lines(page_lines)

        if page_hash in seen_hashes:
            attempts += 1
            if attempts >= MAX_ATTEMPTS:
                raise RuntimeError("Loop detectado: página repetida")
        else:
            seen_hashes.add(page_hash)
            attempts = 0

        try:
            x, y, z = read_pagination_hint(pw)
            logger.info(
                "Página: (%s, %s, %s) com %s entradas", x, y, z, len(page_lines)
            )
        except ValueError as exc:
            attempts += 1
            logger.warning("%s", exc)
            if attempts >= MAX_ATTEMPTS:
                raise RuntimeError("Falha ao ler paginação")
            continue

        if y < z:
            yield (page_lines, (x, y, z), None)
            pf(pw, 8)
        else:
            yield (page_lines, (x, y, z), None)
            pf(pw, 8)
            footer = read_footer_message(pw)
            yield ([], (y, y, z), footer)
            break


def enrich_on_e527(
    pw: PW3270, rows: Iterable[PlanRow]
) -> List[PlanRowEnriched]:  # pragma: no cover
    enriched: List[PlanRowEnriched] = []
    for row in rows:
        put(pw, *POS_E527_NUMERO, row.numero)
        enter(pw)
        razao = get_text(pw, *POS_E527_RAZAO)
        saldo = get_text(pw, *POS_E527_SALDO)
        cnpj = get_text(pw, *POS_E527_CNPJ)
        situac = "P. RESCISAO"
        if row.situac.startswith("P.RESC"):
            pf(pw, 9)
            enriched.append(
                PlanRowEnriched(
                    row.numero,
                    row.dt_propost,
                    row.tipo,
                    situac,
                    row.resoluc,
                    razao,
                    saldo,
                    cnpj,
                )
            )
        else:
            pf(pw, 9)
            enriched.append(
                PlanRowEnriched(
                    row.numero,
                    row.dt_propost,
                    row.tipo,
                    row.situac,
                    row.resoluc,
                    razao,
                    saldo,
                    cnpj,
                )
            )
    return enriched


def search_grde(
    pw: PW3270,
    rows: Iterable[PlanRowEnriched],
) -> List[PlanRowEnriched]:
    result: List[PlanRowEnriched] = []

    for row in rows:
        updated = row
        if row.situac != "SIT. ESPECIAL":
            put(pw, *POS_E50H_NUMERO, row.numero)
            enter(pw)

            msg = (get_text(pw, *POS_GRDE) or "").strip().lower()

            if "existe grde" in msg:
                if row.situac != "GRDE Emitida":
                    updated = replace(row, situac="GRDE Emitida")

            pf(pw, 9)

        result.append(updated)

    return result


# ---------------------------- Portal PO Helpers -----------------------------


def portal_po_provider() -> List[dict]:  # - integração real
    import certifi_win32
    import requests
    from requests_negotiate_sspi import HttpNegotiateAuth

    # Sessão autenticada via SSPI
    s = requests.Session()
    s.auth = HttpNegotiateAuth()

    url = "https://www.cefgd.rj.caixa/portalpo/index.php"

    payload = {
        "registro[0][cadastro_inscricao]": "",
        "registro[0][cadastro_unidade_resp]": "0",
        "registro[0][cadastro_tipo_id]": "0",
        "registro[0][criterio]": "0",
        "registro[0][ocorrencia]": "0",
        "sistema": "parcelamento",
        "page": "parc_fora/consulta_tratamento",
        "ajax": "true",
    }

    resp = s.post(url, data=payload, timeout=30)

    return parse_portal_po(
        resp.text
        if resp.headers.get("content-type", "").startswith("application/json")
        else resp.content.decode("utf-8-sig")
    )


def norm_tipo(s: str) -> str:
    s = str(s or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.upper().split())


def norm_plano(raw: str | None) -> str:
    return re.sub(r"\D", "", str(raw or ""))


def parse_portal_po(json_text: str) -> list[dict]:
    try:
        data = json.loads(json_text)
        if not data or not data[0].get("result"):
            return []
        out: list[dict] = []

        for item in data[0].get("response", []):
            plano = norm_plano(item.get("cadastro_plano", ""))
            cnpj = str(item.get("cadastro_inscricao", "")).strip()
            tipo_raw = (item.get("tipo_descricao", item.get("cnpj", ""))).strip()
            tipo = html.unescape(tipo_raw)
            if plano:
                out.append({"Plano": plano, "CNPJ": cnpj, "Tipo": tipo})
        return out
    except JSONDecodeError as e:
        logger.warning(f"JSON inválido do Portal PO: {e}")
        return []
    except Exception as e:
        logger.warning(f"Falha ao parsear JSON do Portal PO: {e}")
        return []


def build_tipo_map(registros_po: list[dict]) -> dict[str, str]:
    tipos = {}
    for r in registros_po:
        p = norm_plano(r.get("Plano", ""))
        t = str(r.get("Tipo", "")).strip()
        if p:
            tipos[p] = t
    return tipos


def aplica_sit_especial(
    dados_filtrados: list,
    tipos_por_plano: dict[str, str],
    *,
    nova_sit: str = "SIT. ESPECIAL",
    tipos_predet: Iterable[str] = TIPOS_PREDET,
) -> list:
    tipos_ok = {norm_tipo(t) for t in tipos_predet}
    ajustados = []

    for r in dados_filtrados:
        plano = norm_plano(r.numero)
        tipo_norm = norm_tipo(tipos_por_plano.get(plano, ""))
        if plano and (tipo_norm in tipos_ok):
            r = replace(r, situac=nova_sit)
        ajustados.append(r)

    return ajustados


# ------------------------------- Coleta ------------------------------------


def run_pipeline(
    pw: PW3270,
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
        logger.warning("Mensagem inesperada no rodapé: %r", footer_after_last)
        break

    dados_filtrados = [row for row in all_rows if row.resoluc != RESOLUCAO_DESCARTAR]
    descartados_974 = len(all_rows) - len(dados_filtrados)
    if progress:
        progress(25.0, 1, f"{len(dados_filtrados)} planos capturados na E555")

    portal_po: list[dict] = []

    try:
        portal_po = portal_provider() or []
        logger.info("Portal PO: %s registros", len(portal_po))
    except Exception as exc:
        logger.warning("Falha ao obter Portal PO: %s", exc)
        portal_po = []
    if progress:
        progress(35.0, 2, "Dados do Portal PO integrados")

    tipos_map = build_tipo_map(portal_po) if portal_po else {}

    dados_ajustados = (
        aplica_sit_especial(dados_filtrados, tipos_map)
        if tipos_map
        else dados_filtrados
    )

    open_e527(pw)
    enriched = enrich_on_e527(pw, dados_ajustados)

    open_e50h(pw)
    enriched = search_grde(pw, dados_ajustados)

    if progress:
        progress(50.0, 3, "Enriquecimento na E527 concluído")

    return GestaoBaseData(
        rows=enriched,
        raw_lines=raw_lines,
        portal_po=portal_po,
        descartados_974=descartados_974,
    )


# ------------------------------- Serviço -----------------------------------


def _clean_inscricao(raw: str | None) -> str:
    """Return a canonical identifier keeping the formatted version when absent."""

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


def _should_register_occurrence(situacao: str | None) -> bool:
    """Identifica situações que devem ser exibidas como ocorrência."""

    texto = (situacao or "").strip()
    if not texto:
        return False
    normalizado = texto.upper()
    if "ESPECIAL" in normalizado:
        return True
    if normalizado.startswith("RESC"):
        return True
    if normalizado.startswith("LIQ"):
        return True
    if "GRDE" in normalizado:
        return True
    return False


def _format_summary(stats: dict[str, int]) -> str:
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


def _persist_rows(
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
        saldo_raw = parse_money_brl(row.saldo_total)
        saldo = None if math.isnan(saldo_raw) else saldo_raw
        inscricao_canonica = _clean_inscricao(row.cnpj)
        inscricao_original = (row.cnpj or "").strip()

        campos: dict[str, Any] = {
            "dt_situacao_atual": hoje,
            "situacao_anterior": existente.situacao_atual if existente else None,
        }

        parcelas_normalizadas, dias_calculado = _normalize_parcelas_atraso(
            row.parcelas_atraso,
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
        razao_social = (row.razao_social or "").strip()
        if razao_social:
            campos["razao_social"] = razao_social
        if inscricao_canonica:
            campos["numero_inscricao"] = inscricao_canonica
        representacao = _representacao_value(inscricao_original, inscricao_canonica)
        if representacao is not None:
            campos["representacao"] = representacao
        campos["parcelas_atraso"] = parcelas_normalizadas or None
        if parcelas_normalizadas:
            campos["parcelas_atraso"] = parcelas_normalizadas

        campos["dias_em_atraso"] = dias_calculado

        status = _infer_plan_status(situacao)
        if status is not None:
            campos["status"] = status
        elif existente is None:
            campos["status"] = PlanStatus.PASSIVEL_RESC

        plan = context.plans.upsert(numero_plano=row.numero, **campos)

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


def _clean_inscricao(raw: str) -> str:
    texto = (raw or "").strip()
    return re.sub(r"\D", "", texto)


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
            resoluc="",  # mantém vazio
            razao_social="Empresa Beta S.A.",
            saldo_total="8.900,10",
            cnpj="98.765.432/0001-10",
        ),
    ]
    portal_po = [
        {"Plano": "2345678901", "CNPJ": "98.765.432/0001-10", "Tipo": "ESPECIAL"},
    ]
    return GestaoBaseData(
        rows=exemplos, raw_lines=[], portal_po=portal_po, descartados_974=0
    )


class DryRunCollector(GestaoBaseCollector):
    def collect(self, progress: Optional[ProgressCallback] = None) -> GestaoBaseData:
        logger.info("Executando coleta de Gestão da Base em modo dry-run")
        if progress:
            progress(10.0, None, "Captura simulada iniciada")
            progress(35.0, 1, "Dados simulados coletados")
            progress(50.0, 2, "Situação especial simulada aplicada")
            progress(65.0, 3, "Dados simulados enriquecidos")
        return _sample_data()


class TerminalCollector(GestaoBaseCollector):  # pragma: no cover - integrações reais
    def __init__(
        self, senha: str, portal_provider: Optional[Callable[[], List[dict]]] = None
    ) -> None:
        if PW3270 is None:
            raise RuntimeError("Biblioteca pw3270 não disponível no ambiente")
        self.senha = senha
        self.portal_provider = portal_provider

    def collect(self, progress: Optional[ProgressCallback] = None) -> GestaoBaseData:
        assert PW3270 is not None
        pw = PW3270()
        with session(pw):
            return run_pipeline(
                pw,
                self.senha,
                portal_provider=self.portal_provider,
                progress=progress,
            )


class GestaoBaseService:
    """Executa as etapas 1–4 da Gestão da Base utilizando a lógica da E555/E527."""

    def __init__(
        self, portal_provider: Optional[Callable[[], List[dict]]] = None
    ) -> None:
        self.portal_provider = portal_provider or (
            portal_po_provider if not settings.DRY_RUN else None
        )

    def _collector(self, senha: Optional[str]) -> Optional[GestaoBaseCollector]:
        if settings.DRY_RUN:
            return DryRunCollector()

        provided = (senha or "").strip()
        if provided:
            set_gestao_base_password(provided)
            resolved = provided
        else:
            resolved = get_gestao_base_password()

        if not resolved:
            logger.warning(
                "Senha da Gestão da Base não disponível; execução será interrompida."
            )
            return None

        return TerminalCollector(resolved, self.portal_provider)

    def execute(
        self,
        senha: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> ServiceResult:
        """Executa a captura de Gestão da Base e persiste os registros."""

        def _run(context: StepJobContext) -> StepJobOutcome:
            collector = self._collector(senha)
            if collector is None:
                return StepJobOutcome(
                    data={"error": "Senha da Gestão da Base não configurada."},
                    status="FAILED",
                    info_update={"summary": "Execução bloqueada por falta de senha"},
                )

            if progress_callback:
                progress_callback(12.0, None, "Captura real da Gestão da Base iniciada")

            data = collector.collect(progress_callback)
            resultado = _persist_rows(context, data, progress_callback)
            summary = _format_summary(resultado)
            return StepJobOutcome(data=resultado, info_update={"summary": summary})

        return run_step_job(step=Step.ETAPA_1, job_name=Step.ETAPA_1, callback=_run)


class GestaoBaseNoOpService:
    """Serviço auxiliar para etapas 2-4 que já são cobertas pela captura consolidada."""

    def __init__(self, step: Step) -> None:
        self.step = step

    def execute(self) -> ServiceResult:
        def _run(_: StepJobContext) -> StepJobOutcome:
            return StepJobOutcome(
                data={"mensagem": "Etapa contemplada na captura consolidada"},
                info_update={"summary": "Nenhuma ação necessária"},
            )

        return run_step_job(step=self.step, job_name=self.step, callback=_run)