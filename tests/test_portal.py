import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.gestao_base.portal import parse_portal_po


def test_parse_portal_po_handles_missing_fields_and_html_entities():
    payload = [
        {
            "result": True,
            "response": [
                {
                    "cadastro_plano": "123.456-7",
                    "cadastro_inscricao": None,
                    "tipo_descricao": None,
                    "cnpj": "Especial &amp; Unit",
                },
                {
                    "cadastro_plano": "",
                    "cadastro_inscricao": "11.222.333/0001-44",
                    "tipo_descricao": "   ",
                },
                "ignorado",
            ],
        }
    ]

    resultado = parse_portal_po(json.dumps(payload))

    assert resultado == [
        {"Plano": "1234567", "CNPJ": "", "Tipo": "Especial & Unit"}
    ]


def test_parse_portal_po_empty_response():
    payload = [{"result": True, "response": []}]

    assert parse_portal_po(json.dumps(payload)) == []
