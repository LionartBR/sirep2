from __future__ import annotations

import html
import json
import logging
import unicodedata
from dataclasses import replace
from json import JSONDecodeError
from typing import Iterable, List

from .constants import TIPOS_PREDET
from .models import PlanRow

logger = logging.getLogger(__name__)


def portal_po_provider() -> List[dict]:  # pragma: no cover - integração real
    import certifi_win32
    import requests
    from requests_negotiate_sspi import HttpNegotiateAuth

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
    import re

    return re.sub(r"\D", "", str(raw or ""))


def parse_portal_po(json_text: str) -> list[dict]:
    try:
        data = json.loads(json_text)
        if not data or not data[0].get("result"):
            return []

        out: list[dict] = []
        for item in data[0].get("response", []):
            if not isinstance(item, dict):
                continue

            plano = norm_plano(item.get("cadastro_plano", ""))
            if not plano:
                continue

            cnpj_raw = item.get("cadastro_inscricao")
            cnpj = str(cnpj_raw or "").strip()

            tipo_source = item.get("tipo_descricao")
            if not tipo_source:
                tipo_source = item.get("cnpj")
            tipo = html.unescape(str(tipo_source or "").strip())

            out.append({"Plano": plano, "CNPJ": cnpj, "Tipo": tipo})
        return out
    except JSONDecodeError as e:
        logger.warning(f"JSON inválido do Portal PO: {e}")
        return []
    except Exception as e:  # pragma: no cover - defensivo
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
    dados_filtrados: Iterable[PlanRow],
    tipos_por_plano: dict[str, str],
    *,
    nova_sit: str = "SIT. ESPECIAL",
    tipos_predet: Iterable[str] = TIPOS_PREDET,
) -> list[PlanRow]:
    tipos_ok = {norm_tipo(t) for t in tipos_predet}
    ajustados = []

    for r in dados_filtrados:
        plano = norm_plano(r.numero)
        tipo_norm = norm_tipo(tipos_por_plano.get(plano, ""))
        atualizado = r
        if plano and (tipo_norm in tipos_ok):
            atualizado = replace(r, situac=nova_sit)
        ajustados.append(atualizado)

    return ajustados
