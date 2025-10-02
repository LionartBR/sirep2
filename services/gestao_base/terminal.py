from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import replace
from hashlib import md5
from time import sleep
from typing import Iterable, Iterator, List, Optional, Tuple

from services.pw3270 import PW3270

from .constants import (
    COL_START,
    COL_WIDTH,
    DATA_LINES,
    FOOTER_MSG_POS,
    MAX_ATTEMPTS,
    POS_E50H_NUMERO,
    POS_E527_CNPJ,
    POS_E527_NUMERO,
    POS_E527_RAZAO,
    POS_E527_SALDO,
    POS_GRDE,
    REQUEST_DELAY,
    STATUS_HINT_POS,
)
from .models import PlanRow, PlanRowEnriched

logger = logging.getLogger(__name__)


def hash_lines(lines: Iterable[str]) -> str:
    return md5("\n".join(lines).encode()).hexdigest()


def parse_pagination(texto: str) -> Tuple[int, int, int]:
    import re

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


def open_e527(pw: PW3270):  # pragma: no cover
    goto_tx(pw, "E527")


def open_e50h(pw: PW3270):  # pragma: no cover
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
) -> List[PlanRowEnriched]:  # pragma: no cover
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
