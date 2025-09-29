from __future__ import annotations

import math
import sys
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from services.gestao_base.parcelas import normalize_parcelas_atraso


def test_normalize_parcelas_handles_dict_variations():
    referencia = date(2024, 5, 10)
    parcelas = [
        {"parcela": "001", "valor": "1.234,56", "vencimento": date(2024, 5, 1)},
        {
            "numero": "002",
            "valor_parcela": "789,01",
            "data_vencimento": "03/05/2024",
        },
        {
            "sequencia": "003",
            "valor_atraso": "0,00",
            "venc": datetime(2024, 5, 5, 12, 0),
        },
        {"codigo": "004", "valor_nominal": "15,00", "data": "07/05/2024"},
    ]

    normalizados, dias_total = normalize_parcelas_atraso(parcelas, referencia=referencia)

    assert [p["parcela"] for p in normalizados] == ["001", "002", "003"]
    assert normalizados[0]["vencimento"] == "2024-05-01"
    assert normalizados[1]["vencimento"] == "2024-05-03"
    assert normalizados[2]["vencimento"] == "2024-05-05"
    assert math.isclose(normalizados[0]["valor_num"], 1234.56)
    assert math.isclose(normalizados[1]["valor_num"], 789.01)
    assert normalizados[2]["valor_num"] == 0.0
    assert dias_total == 9


def test_normalize_parcelas_accepts_iterables_and_strings():
    referencia = date(2024, 1, 20)
    parcelas = [
        "001   100,00   01/01/2024",
        ("002", "200,00", "05/01/2024"),
        ("003", " ", None),
    ]

    normalizados, dias_total = normalize_parcelas_atraso(parcelas, referencia=referencia)

    assert [p["parcela"] for p in normalizados] == ["001", "002", "003"]
    assert "valor" not in normalizados[2]
    assert dias_total == 19


def test_normalize_parcelas_returns_empty_when_no_data():
    normalizados, dias_total = normalize_parcelas_atraso([], referencia=date(2024, 1, 1))
    assert normalizados == []
    assert dias_total is None

