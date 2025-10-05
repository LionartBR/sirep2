-- 2024-10-07: Robust plan blocking and migration safeguards
SET ROLE sirep_tech;

-- A1) Ensure global uniqueness for pending treatment items
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_trat_item_unique_pending
  ON app.tratamento_item (plano_id)
  WHERE status = 'pending';

-- A2) Upsert-only active plan blocks (no race conditions on re-block)
CREATE OR REPLACE FUNCTION app.plano_bloquear(
  p_plano_id uuid,
  p_motivo   text DEFAULT NULL,
  p_expires  timestamptz DEFAULT NULL
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, public, pg_temp
AS $$
DECLARE v_tenant uuid;
BEGIN
  IF NOT app.current_user_is_admin() AND NOT app.is_tech() THEN
    RAISE EXCEPTION 'only GESTOR/tech can block' USING ERRCODE='insufficient_privilege';
  END IF;

  SELECT tenant_id INTO v_tenant FROM app.plano WHERE id = p_plano_id;
  IF v_tenant IS NULL THEN
    RAISE EXCEPTION 'plan % not found', p_plano_id;
  END IF;

  INSERT INTO app.plano_bloqueio (
    tenant_id, plano_id, ativo, motivo, expires_at,
    created_at, blocked_by, unlocked_at, unlocked_by
  )
  VALUES (
    v_tenant, p_plano_id, TRUE, p_motivo, p_expires,
    now(), app.current_user_id(), NULL, NULL
  )
  ON CONFLICT (plano_id) WHERE (ativo)
  DO UPDATE SET
    motivo      = COALESCE(EXCLUDED.motivo, app.plano_bloqueio.motivo),
    expires_at  = COALESCE(EXCLUDED.expires_at, app.plano_bloqueio.expires_at),
    created_at  = now(),
    blocked_by  = EXCLUDED.blocked_by,
    unlocked_at = NULL,
    unlocked_by = NULL;

  RETURN TRUE;
END $$;

GRANT EXECUTE ON FUNCTION app.plano_bloquear(uuid, text, timestamptz) TO sirep_app, sirep_admin;

-- A3) Snapshot migration ignores blocked plans, enforces global pending uniqueness,
--      and reactivates skipped items within the same OPEN lot
CREATE OR REPLACE FUNCTION app.tratamento_migrar_planos_global(p_filters jsonb DEFAULT NULL)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = app, public, pg_temp
AS $$
DECLARE v_lote uuid;
BEGIN
  -- open or reuse user's OPEN lot
  BEGIN
    INSERT INTO app.tratamento_lote (tenant_id, user_id, grid, status, source_filter)
    VALUES (app.current_tenant_id(), app.current_user_id(), 'PLANOS_P_RESCISAO', 'OPEN', p_filters)
    RETURNING id INTO v_lote;
  EXCEPTION WHEN unique_violation THEN
    SELECT id INTO v_lote
    FROM app.tratamento_lote
    WHERE tenant_id = app.current_tenant_id()
      AND user_id   = app.current_user_id()
      AND grid      = 'PLANOS_P_RESCISAO'
      AND status    = 'OPEN'
    LIMIT 1;
  END;

  INSERT INTO app.tratamento_item (
    tenant_id, lote_id, plano_id, numero_plano, documento, razao_social,
    saldo, dt_situacao, situacao_codigo
  )
  SELECT
    app.current_tenant_id(),
    v_lote,
    p.id, p.numero_plano,
    e.numero_inscricao, e.razao_social,
    p.saldo_total,
    p.dt_situacao_atual::date,
    sp.codigo
  FROM app.plano p
  JOIN app.empregador e  ON e.id = p.empregador_id
  JOIN ref.situacao_plano sp ON sp.id = p.situicao_plano_id
  WHERE sp.codigo = 'P_RESCISAO'
    AND NOT EXISTS (
      SELECT 1 FROM app.plano_bloqueio b
      WHERE b.plano_id = p.id
        AND b.ativo = TRUE
        AND b.unlocked_at IS NULL
        AND (b.expires_at IS NULL OR b.expires_at > now())
    )
    AND NOT EXISTS (
      SELECT 1 FROM app.tratamento_item ti
      WHERE ti.plano_id = p.id
        AND ti.status   = 'pending'
    )
  ON CONFLICT (tenant_id, lote_id, plano_id)
  DO UPDATE SET
    status       = 'pending',
    processed_at = NULL
  WHERE app.tratamento_item.status <> 'pending';

  RETURN v_lote;
END $$;

GRANT EXECUTE ON FUNCTION app.tratamento_migrar_planos_global(jsonb)
  TO sirep_app, sirep_admin, sirep_worker;

RESET ROLE;
