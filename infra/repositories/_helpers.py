from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from shared.text import only_digits


def calcular_atraso_desde(dias_em_atraso: Any) -> Optional[date]:
    """Converte dias em atraso para a data correspondente."""

    if dias_em_atraso is None:
        return None

    try:
        dias = int(dias_em_atraso)
    except (TypeError, ValueError):
        return None

    if dias < 0:
        return None

    base = date.today()
    return base - timedelta(days=dias)


def inferir_tipo_inscricao(numero: str) -> str:
    """Infere o tipo de inscrição a partir da quantidade de dígitos."""

    texto = "".join(ch for ch in str(numero) if ch.isdigit())
    if len(texto) == 14:
        return "CNPJ"
    if len(texto) == 11:
        return "CPF"
    return "CEI"


def normalizar_codigo(texto: str) -> str:
    """Normaliza códigos alfanuméricos removendo caracteres especiais."""

    canonico = "".join(ch if ch.isalnum() else "_" for ch in texto.upper().strip())
    canonico = "_".join(filter(None, canonico.split("_")))
    return canonico or texto.upper()


def normalizar_situacao(texto: str) -> str:
    """Normaliza descrições de situação de plano."""

    if not texto:
        return "EM_DIA"

    normalizado = texto.strip().upper()
    if not normalizado:
        return "EM_DIA"

    if "GRDE" in normalizado:
        return "GRDE_EMITIDA"
    if "SIT" in normalizado and "ESPECIAL" in normalizado:
        return "SIT_ESPECIAL"
    if "LIQ" in normalizado:
        return "LIQUIDADO"
    if normalizado.startswith("P.") or normalizado.startswith("P ") or normalizado.startswith("PRESC"):
        return "P_RESCISAO"
    if "P_RESCISAO" in normalizado or normalizado.startswith("P_RESC"):
        return "P_RESCISAO"
    if "P. RESCISAO" in normalizado:
        return "P_RESCISAO"
    if normalizado.startswith("RESC") or "RESCINDIDO" in normalizado:
        return "RESCINDIDO"
    return "EM_DIA"
def safe_int(valor: Any) -> Optional[int]:
    """Converte valores textuais em inteiros de forma segura."""

    if valor is None:
        return None

    texto = str(valor).strip()
    if not texto:
        return None

    digits = only_digits(texto)
    candidato = digits or texto
    try:
        return int(candidato)
    except ValueError:
        return None


def extract_date_from_timestamp(valor: Any) -> Optional[date]:
    """Extrai a porção de data de um timestamp em diferentes formatos."""

    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()
    if not texto:
        return None

    try:
        parsed = datetime.fromisoformat(texto)
    except ValueError:
        return None

    return parsed.date()


def parse_vencimento(valor: Any) -> Optional[date]:
    """Interpreta diferentes formatos de data de vencimento."""

    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = str(valor or "").strip()
    if not texto:
        return None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def to_decimal(valor: Any) -> Optional[Decimal]:
    """Converte valores numéricos ou textuais para Decimal."""

    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))

    texto = str(valor).strip()
    if not texto:
        return None

    texto_normalizado = texto.replace(".", "").replace(",", ".")
    try:
        return Decimal(texto_normalizado)
    except InvalidOperation:
        return None


__all__ = [
    "calcular_atraso_desde",
    "extract_date_from_timestamp",
    "inferir_tipo_inscricao",
    "normalizar_codigo",
    "normalizar_situacao",
    "only_digits",
    "parse_vencimento",
    "safe_int",
    "to_decimal",
]
