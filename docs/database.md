# SIREP DB — Documentação do Esquema (PostgreSQL)

- **Versão PG:** 17.6  
- **Banco de Dados:** `sirep_db`  
- **Timezone:** `America/Sao_Paulo`
- **Encoding:** `UTF8`  
- **Collate/CType (Windows):** `Portuguese_Brazil.1252`
- **Extensões usadas:** `pgcrypto` (UUID/gen_random_uuid), `citext`, `pg_trgm`, `btree_gin`

## Visão geral

- Arquitetura multi-tenant com RLS por `tenant_id` (todas as tabelas de negócio possuem essa coluna).
- Perfis de sessão: `admin`, `worker`, `tech` (supervisão).
- Auditoria com carimbos `created_at/_by`, `updated_at/_by`, `deleted_at/_by` e histórico de situação de plano.
- Particionamento mensal para logs/auditoria (`audit.*`).

## Papéis (roles)

- `sirep_tech`: administração técnica (DDL, bypass de RLS via funções).
- `sirep_admin`: administração funcional por tenant.
- `sirep_worker`: operação (atualização de planos, leitura do restante).
- `sirep_app`: papel de conexão do backend (RLS garante o isolamento).

## Schemas

- `ref` — catálogos/lookups (códigos estáveis, sem acento/espaço).
- `app` — tabelas de negócio e funções de sessão/RLS.
- `audit` — execução de pipelines e eventos (particionado por data).

## Convenções comuns de colunas

- `id uuid PRIMARY KEY DEFAULT gen_random_uuid()`
- `tenant_id uuid NOT NULL` (FK `app.tenant`)
- Soft-audit: `created_at timestamptz DEFAULT now()`, `created_by uuid`, `updated_at timestamptz`, `updated_by uuid`, `deleted_at timestamptz`, `deleted_by uuid`
- Tabelas `ref.*`: `codigo citext UNIQUE`, `descricao text NOT NULL`, `sort_order smallint`, `ativo boolean DEFAULT true`

## 1) Catálogos — `ref.*`

### 1.1 `ref.tipo_inscricao`

- Campos: `id`, `codigo` (`CNPJ` | `CPF` | `CEI`), `descricao`, `sort_order`, `ativo`
- Índices: `UNIQUE(codigo)`

### 1.2 `ref.situacao_plano`

- Exemplos de `codigo`: `EM_DIA`, `P_RESCISAO`, `RESCINDIDO`, `LIQUIDADO`, `SIT_ESPECIAL`, `GRDE_EMITIDA`
- Índices: `UNIQUE(codigo)`

### 1.3 `ref.tipo_plano`

- Exemplos de `codigo`: `ADM`, `JUD`, `INS`, `AJ`, `AI`, `AJI`, `JI`, `JA`
- Índices: `UNIQUE(codigo)`

### 1.4 `ref.resolucao`

- Exemplos de `codigo`: `974/20`, `430/98`
- Índices: `UNIQUE(codigo)`

### 1.5 `ref.situacao_parcela`

- Exemplos de `codigo`: `PAGA`, `EM_ATRASO`, `A_VENCER`
- Índices: `UNIQUE(codigo)`

### 1.6 `ref.base_fgts`

- Exemplos de `codigo`: `SP`, `RJ`, `BR`, `BA`, `SC`, …
- Índices: `UNIQUE(codigo)`

### (Opcional) `ref.etapa_gestao`

- Catálogo de etapas do pipeline
- Códigos: `CAPTURA_PLANOS`, `SITUACAO_ESPECIAL`, `GUIA_GRDE`

## 2) Negócio — `app.*`

### 2.1 `app.tenant`

- Campos: `id`, `nome citext UNIQUE`, `ativo boolean`, soft-audit
- RLS: `SELECT` do próprio `id` ou `is_tech()`
- Índices: `UNIQUE(nome)`

### 2.2 `app.usuario`

- Campos: `id`, `tenant_id`, `matricula citext`, `nome text`, `email citext NOT NULL`, `perfil text CHECK (perfil IN ('admin','worker'))`, `ativo boolean`, soft-audit
- Restrição única: `(tenant_id, matricula)`
- RLS: `SELECT` por tenant; `INSERT/UPDATE/DELETE` apenas `admin/tech`

### 2.3 `app.empregador`

- Campos: `id`, `tenant_id`, `tipo_inscricao_id` (FK `ref.tipo_inscricao`), `numero_inscricao text` (só dígitos), `razao_social citext`, `email`, `telefone`, `ativo`, soft-audit
- Restrição única: `(tenant_id, tipo_inscricao_id, numero_inscricao)`
- Índices: `GIN (razao_social gin_trgm_ops)`, `(tenant_id, numero_inscricao)`
- RLS: `SELECT` por tenant; `INSERT/UPDATE/DELETE` `admin/tech`

### 2.4 `app.empregador_base_fgts`

- Campos: `tenant_id`, `empregador_id`, `base_fgts_id` (FK `ref.base_fgts`)
- PK: `(tenant_id, empregador_id, base_fgts_id)`
- RLS: igual a `empregador`

### 2.5 `app.plano`

- Campos principais: `id`, `tenant_id`, `empregador_id` (FK `app.empregador`), `numero_plano text` (só dígitos, `UNIQUE` global), `tipo_plano_id` (FK `ref.tipo_plano`), `resolucao_id` (FK `ref.resolucao`), `situacao_plano_id` (FK `ref.situacao_plano`), `competencia_ini date`, `competencia_fim date`, `dt_proposta date`, `qtd_parcelas smallint`, `saldo_total numeric`, `atraso_desde date` (mantido por trigger), `representacao text`, `status text`, `dt_situacao_atual timestamptz`, soft-audit
- Índices: `UNIQUE(numero_plano)`, `(tenant_id, numero_plano)`, `(empregador_id)`, `(situacao_plano_id)`
- RLS: `SELECT` por tenant; `INSERT` `admin/tech`; `UPDATE` `worker/admin/tech` (linhas do tenant); `DELETE` apenas `admin/tech`

### 2.6 `app.plano_situacao_hist`

- Campos: `id`, `tenant_id`, `plano_id` (FK `app.plano`), `situacao_plano_id` (FK `ref.situacao_plano`), `mudou_em timestamptz` (data efetiva), `mudou_por uuid`, `observacao text`
- Índices: `(plano_id, mudou_em DESC)`, `(tenant_id)`, `(situacao_plano_id)`
- RLS: `SELECT` por tenant; `INSERT` `worker/admin/tech` (via trigger); `UPDATE/DELETE` `admin/tech`

### 2.7 `app.parcela`

- Campos: `id`, `tenant_id`, `plano_id`, `nr_parcela int`, `vencimento date`, `valor numeric`, `situacao_parcela_id` (FK `ref.situacao_parcela`), `pago_em date`, `valor_pago numeric`, `qtd_parcelas_total smallint`, soft-audit
- Restrição única: `(tenant_id, plano_id, nr_parcela, vencimento)`
- Índices: `(tenant_id, situacao_parcela_id, vencimento)`, `(plano_id)`
- RLS: igual a `plano`

### 2.8 `app.comunicacao`

- Uso para contato com empregador
- Campos: `id`, `tenant_id`, `plano_id`, `metodo_id` (FK `ref.metodo_comunicacao`), `assunto text`, `corpo text`, `enviado_em timestamptz`, `status text`, soft-audit
- RLS: `SELECT` por tenant; `INSERT/UPDATE/DELETE` `admin/tech`

## 3) Auditoria/Logs — `audit.*` (particionado)

> Nota: Em tabelas particionadas por `RANGE`, a PK/UNIQUE deve incluir a coluna de partição.

### 3.1 `audit.job_run`

- Partição por: `started_at timestamptz`
- Campos: `tenant_id`, `started_at`, `id`, `job_name text`, `status text` (`RUNNING` | `SUCCESS` | `ERROR` | `SKIPPED`), `finished_at timestamptz`, `payload jsonb`, `error_msg text`, `user_id uuid`
- PK: `(tenant_id, started_at, id)`
- Índices: `(tenant_id, started_at)`, `(job_name, started_at)`
- RLS: `SELECT/INSERT/UPDATE` por tenant; `tech` geral
- Helpers: `audit._ym(ts)`, `audit.ensure_job_run_partition(ts)`, trigger `audit.tg_ensure_job_run_partition()`

### 3.2 `audit.job_step`

- Partição por: `job_started_at timestamptz`
- Campos: `tenant_id`, `job_started_at`, `job_id`, `step_code citext`, `etapa_id uuid NULL`, `status text` (`PENDING` | `RUNNING` | `SUCCESS` | `ERROR` | `SKIPPED`), `started_at`, `finished_at`, `message text`, `data jsonb`, `user_id`
- PK: `(tenant_id, job_started_at, job_id, step_code)`
- FK lógica: `(tenant_id, job_started_at, job_id) → audit.job_run`
- Índices: `(tenant_id, job_started_at DESC, job_id)`, `(step_code)`
- RLS/Helpers: iguais a `job_run`; `audit.ensure_job_step_partition`, trigger `tg_ensure_job_step_partition`

### 3.3 `audit.evento`

- Partição por: `event_time timestamptz`
- Campos: `tenant_id`, `event_time`, `id`, `entity text` (`'pipeline' | 'plano' | ...`), `entity_id uuid`, `event_type text`, `severity text` (`'info' | 'warn' | 'error'`), `message text`, `data jsonb`, `user_id uuid`
- PK: `(tenant_id, event_time, id)`
- Índices: `(tenant_id, event_time)`, `(entity, event_time)`
- RLS/Helpers: `audit.ensure_evento_partition`, trigger `tg_ensure_evento_partition`

## 4) Funções — `app.*`

### Sessão/Contexto & RLS

- `app.set_tenant(p_tenant uuid) RETURNS void` — define `app.tenant_id` na sessão.
- `app.set_user(p_user uuid) RETURNS void` — define `app.user_id` na sessão.
- `app.current_tenant_id() RETURNS uuid` — lê GUC da sessão.
- `app.current_user_id() RETURNS uuid` — lê GUC da sessão.
- `app.current_user_perfil() RETURNS text` — retorna `'admin' | 'worker' | NULL`.
- `app.current_user_is_admin() RETURNS boolean`
- `app.current_user_is_worker() RETURNS boolean`
- `app.is_tech() RETURNS boolean` — `pg_has_role(current_user,'sirep_tech','member')`.

### Provisionamento/Login

- `app.ensure_usuario(p_tenant, p_matricula, p_nome NULL, p_email NULL, p_perfil NULL) RETURNS uuid` — upsert de usuário por `(tenant, matricula)`, `email` obrigatório (usa placeholder se faltar).
- `app.set_principal(p_tenant, p_matricula, p_nome NULL, p_email NULL, p_perfil NULL) RETURNS uuid` — provisiona/garante usuário e define `app.tenant_id`/`app.user_id`.
- `app.set_principal_by_matricula(p_matricula, p_auto_create boolean DEFAULT false, p_nome NULL, p_email NULL, p_perfil text DEFAULT 'admin') RETURNS uuid` — resolve `(tenant,user)` pela matrícula; cria tenant/usuário padrão se `p_auto_create=true`.
- `app.provision_tenant_and_user(p_matricula, p_nome, p_email NULL, p_perfil 'admin', p_tenant_nome NULL) RETURNS (tenant_id uuid, user_id uuid)` — cria (ou reutiliza) tenant `TENANT_<matricula>` e usuário; ajusta sessão.
- `app.login_matricula(p_matricula citext) RETURNS uuid` — usado pelo backend para ligar sessão (define tenant, usuário e perfil ativos).

### Regras de negócio

- `app.recalc_plano_atraso(p_tenant uuid, p_plano uuid) RETURNS void` — recalcula `plano.atraso_desde` com base nas parcelas em atraso.

### Triggers (funções)

- `app.tg_enforce_tenant()` — preenche `NEW.tenant_id` e impede cross-tenant.
- `app.tg_audit_stamp()` — mantém `created_at/_by` e `updated_at/_by`.
- `app.tg_audit_stamp_hist()` — idem para histórico (só carimba se campo vier `NULL`).
- `app.tg_plano_log_situacao()` — insere linha em `plano_situacao_hist` ao `INSERT/UPDATE` de `plano`. Usa `current_setting('app.situacao_effective_ts', true)` se definido; caso contrário, `now()`.
- `app.tg_parcela_recalc_plano_atraso()` — ao `INSERT/UPDATE/DELETE` em `app.parcela`, chama `app.recalc_plano_atraso(...)`.

## 5) Views úteis

### 5.1 `app.vw_planos_busca`

- Colunas: `plano_id`, `numero_plano`, `razao_social`, `tipo_doc` (`CNPJ/CPF/CEI`), `documento` (só dígitos), `situacao_codigo/descricao`, `dias_em_atraso`, `saldo`, `dt_situacao`
- Uso: busca por número do plano, razão social (`ILIKE %...%`) e documento (`CNPJ/CEI/CPF`).

### 5.2 Exports (opcional, usadas pela UI)

- `app.vw_export_rescindidos_cnpj` / `app.vw_export_rescindidos_cpf` / `app.vw_export_rescindidos_cei` — exportam apenas números (um por linha) de planos rescindidos por período/filtros.
- `app.vw_export_eventos` — exporta logs/eventos por período.

> As views de export respeitam RLS via `app.current_tenant_id()`.

## 6) Policies de RLS (resumo)

- Regra padrão nas tabelas `app.*`: `USING (tenant_id = app.current_tenant_id() OR app.is_tech())` com `WITH CHECK` similar.
- Para `UPDATE/DELETE`, exige perfil conforme tabela.
- Leitura de views: `GRANT SELECT` para `sirep_app`, `sirep_admin`, `sirep_worker`.

## 7) Índices recomendados (resumo)

- `app.plano`: `UNIQUE(numero_plano)`; `(tenant_id, numero_plano)`; `(empregador_id)`; `(situacao_plano_id)`
- `app.empregador`: `UNIQUE(tenant_id, tipo_inscricao_id, numero_inscricao)`; `GIN (razao_social gin_trgm_ops)`; `(tenant_id, numero_inscricao)`
- `app.parcela`: `UNIQUE(tenant_id, plano_id, nr_parcela, vencimento)`; `(tenant_id, situacao_parcela_id, vencimento)`; `(plano_id)`
- `app.plano_situacao_hist`: `(plano_id, mudou_em DESC)`; `(tenant_id)`
- `audit.job_run`: `(tenant_id, started_at)`; `(job_name, started_at)`
- `audit.job_step`: `(tenant_id, job_started_at DESC, job_id)`; `(step_code)`
- `audit.evento`: `(tenant_id, event_time)`; `(entity, event_time)`

## 8) Padrões de uso no backend

- Ligar sessão pelo usuário (matrícula):
  ```sql
  SELECT app.login_matricula(:matricula::citext);
  SET TIME ZONE 'America/Sao_Paulo';
  ```
- Upsert de empregador por `(tenant, tipo_doc, numero)` (`UNIQUE`).
- Upsert de plano por `numero_plano` (`UNIQUE` global) com cláusula:
  ```sql
  ON CONFLICT (numero_plano) DO UPDATE ...
  WHERE app.plano.tenant_id = app.current_tenant_id();
  ```
- Parcelas: `INSERT/UPDATE` por `(tenant, plano, nr_parcela, vencimento)` — trigger recalcula atraso.
- Histórico de situação: usar `SET LOCAL app.situacao_effective_ts = :data_iso` para gravar data oficial.
- Logs/etapas: `audit.job_run` + `audit.job_step` + `audit.evento` (particionado, RLS).

## 9) Exemplos rápidos

### Login de sessão

```sql
SELECT app.login_matricula('C150930'::citext);
```

### Grid de planos (CNPJ)

```sql
SELECT * FROM app.vw_planos_busca
WHERE tipo_doc = 'CNPJ' AND razao_social ILIKE '%DEMO%'
ORDER BY dt_situacao DESC NULLS LAST
LIMIT 50 OFFSET 0;
```

### Marcar rescisão com data efetiva

```sql
SET LOCAL app.situacao_effective_ts = '2025-10-01 00:00:00-03';
UPDATE app.plano
   SET situacao_plano_id = (SELECT id FROM ref.situacao_plano WHERE codigo='RESCINDIDO')
 WHERE numero_plano='2011003279' AND tenant_id = app.current_tenant_id();
```

## Anexos (boas práticas)

- Normalize `numero_plano`/documentos para só dígitos na aplicação.
- Defina `statement_timeout` por transação se quiser limitar jobs (ex.: `SET LOCAL statement_timeout='300s'`).
- Mantenha cache de catálogos no backend (`codigo → id`) com recarga eventual.
