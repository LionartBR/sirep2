from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import sys
from typing import Any
from unittest.mock import MagicMock

from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infra.repositories import LookupCache, PlanDTO, PlansRepository


def _make_cursor(return_value: Any | None = None) -> tuple[MagicMock, MagicMock]:
    cursor = MagicMock()
    if return_value is not None:
        cursor.fetchone.return_value = return_value
    cursor_cm = MagicMock()
    cursor_cm.__enter__.return_value = cursor
    cursor_cm.__exit__.return_value = False
    return cursor, cursor_cm


def test_registrar_historico_insere_quando_situacao_altera():
    connection = MagicMock()
    cursor, cursor_cm = _make_cursor()
    connection.cursor.return_value = cursor_cm

    repo = PlansRepository(connection)
    repo._registrar_historico_situacao(
        plano_id="plano-1",
        situacao_id="sit-1",
        situacao_codigo="RESCINDIDO",
        situacao_anterior="EM_DIA",
        dt_situacao_atual=date(2024, 5, 1),
        observacao="Carga inicial",
    )

    connection.cursor.assert_called_once_with()
    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO app.plano_situacao_hist" in sql
    assert params == ("plano-1", "sit-1", "2024-05-01", "Carga inicial")


def test_registrar_historico_ignora_quando_situacao_repetida():
    connection = MagicMock()
    repo = PlansRepository(connection)

    repo._registrar_historico_situacao(
        plano_id="plano-1",
        situacao_id="sit-1",
        situacao_codigo="EM_DIA",
        situacao_anterior="em_dia",
        dt_situacao_atual=date(2024, 5, 1),
    )

    connection.cursor.assert_not_called()


def test_registrar_historico_evita_duplicar_sem_situacao_anterior():
    existente = {
        "situacao_plano_id": "sit-1",
        "mudou_em": datetime(2024, 5, 1, 0, 0, tzinfo=timezone.utc),
    }
    connection = MagicMock()
    select_cursor, select_cm = _make_cursor(existente)
    connection.cursor.return_value = select_cm

    repo = PlansRepository(connection)
    repo._registrar_historico_situacao(
        plano_id="plano-1",
        situacao_id="sit-1",
        situacao_codigo="EM_DIA",
        situacao_anterior=None,
        dt_situacao_atual=date(2024, 5, 1),
    )

    connection.cursor.assert_called_once_with(row_factory=dict_row)
    select_cursor.execute.assert_called_once()
    select_cursor.fetchone.assert_called_once()


def test_upsert_registra_historico_quando_informado():
    connection = MagicMock()
    insert_cursor, insert_cm = _make_cursor({"id": "uuid-1"})
    connection.cursor.return_value = insert_cm

    repo = PlansRepository(connection)
    repo._resolver_empregador = MagicMock(return_value=None)
    repo._resolver_situacao = MagicMock(return_value=("sit-1", "RESCINDIDO"))
    repo._resolver_tipo_plano = MagicMock(return_value=None)
    repo._resolver_resolucao = MagicMock(return_value=None)
    repo._calcular_atraso_desde = MagicMock(return_value=None)
    repo._to_decimal = MagicMock(return_value=None)
    repo._registrar_historico_situacao = MagicMock()
    repo.get_by_numero = MagicMock(
        return_value=PlanDTO(id="uuid-1", numero_plano="123", situacao_atual="RESCINDIDO")
    )

    resultado = repo.upsert(
        "123",
        situacao_atual="Rescindido",
        situacao_anterior="EM_DIA",
        dt_situacao_atual=date(2024, 5, 1),
        parcelas_atraso=[],
    )

    assert resultado.numero_plano == "123"
    repo._registrar_historico_situacao.assert_called_once()
    kwargs = repo._registrar_historico_situacao.call_args.kwargs
    assert kwargs == {
        "plano_id": "uuid-1",
        "situacao_id": "sit-1",
        "situacao_codigo": "RESCINDIDO",
        "situacao_anterior": "EM_DIA",
        "dt_situacao_atual": date(2024, 5, 1),
    }


def test_upsert_utiliza_cache_para_resolver_catalogos():
    connection = MagicMock()
    insert_cursor, insert_cm = _make_cursor({"id": "uuid-1"})
    connection.cursor.return_value = insert_cm

    cache = LookupCache(
        tipos_plano={"TIPO_A": "tipo-1"},
        resolucoes={"123": "res-1"},
        situacoes_plano={"RESCINDIDO": "sit-1"},
        tipos_inscricao={"CNPJ": "doc-1"},
        bases_fgts={},
    )

    repo = PlansRepository(connection, lookup_cache=cache)
    repo._resolver_empregador = MagicMock(return_value="emp-1")
    original_tipo = repo._resolver_tipo_plano
    repo._resolver_tipo_plano = MagicMock(side_effect=original_tipo)
    original_situacao = repo._resolver_situacao
    repo._resolver_situacao = MagicMock(side_effect=original_situacao)
    original_resolucao = repo._resolver_resolucao
    repo._resolver_resolucao = MagicMock(side_effect=original_resolucao)
    repo._calcular_atraso_desde = MagicMock(return_value=None)
    repo._to_decimal = MagicMock(return_value=None)
    repo._registrar_historico_situacao = MagicMock()
    repo.get_by_numero = MagicMock(
        return_value=PlanDTO(id="uuid-1", numero_plano="123", situacao_atual="RESCINDIDO")
    )

    resultado = repo.upsert(
        "123",
        situacao_atual="Rescindido",
        tipo="Tipo A",
        resolucao="123",
        parcelas_atraso=[],
    )

    assert resultado.id == "uuid-1"
    repo._resolver_empregador.assert_called_once()
    _, kwargs_emp = repo._resolver_empregador.call_args
    assert kwargs_emp == {"lookup": cache}
    assert repo._resolver_tipo_plano.call_args.kwargs == {"lookup": cache}
    assert repo._resolver_situacao.call_args.kwargs == {"lookup": cache}
    assert repo._resolver_resolucao.call_args.kwargs == {"lookup": cache}

    connection.cursor.assert_called_once_with(row_factory=dict_row)
    assert len(insert_cursor.execute.call_args_list) == 1
    executed_sql = insert_cursor.execute.call_args_list[0][0][0]
    assert "INSERT INTO app.plano" in executed_sql
    assert "ref.tipo_plano" not in executed_sql

def test_resolver_tipo_plano_utiliza_cache_sem_ir_ao_banco():
    connection = MagicMock()
    cache = LookupCache(
        tipos_plano={"EXISTENTE": "tipo-1"},
        resolucoes={},
        situacoes_plano={},
        tipos_inscricao={},
        bases_fgts={},
    )

    repo = PlansRepository(connection, lookup_cache=cache)
    resultado = repo._resolver_tipo_plano("Existente")

    assert resultado == "tipo-1"
    connection.cursor.assert_not_called()


def test_resolver_tipo_plano_atualiza_cache_quando_insere():
    cursor = MagicMock()
    cursor.fetchone.side_effect = [None, {"id": "novo-id"}]
    cursor_cm = MagicMock()
    cursor_cm.__enter__.return_value = cursor
    cursor_cm.__exit__.return_value = False

    connection = MagicMock()
    connection.cursor.return_value = cursor_cm
    cache = LookupCache(
        tipos_plano={},
        resolucoes={},
        situacoes_plano={},
        tipos_inscricao={},
        bases_fgts={},
    )

    repo = PlansRepository(connection, lookup_cache=cache)
    resultado = repo._resolver_tipo_plano("Novo Plano")

    assert resultado == "novo-id"
    assert cache.tipos_plano["NOVO_PLANO"] == "novo-id"
    assert cursor.execute.call_count == 2

