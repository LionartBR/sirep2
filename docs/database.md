# SIREP DB — Documentação do Esquema (PostgreSQL)

* **PostgreSQL**: **17.6**
* **Database**: `sirep_db`
* **Timezone**: `America/Sao_Paulo`
* **Encoding**: `UTF8`
* **Locale (Windows)**: `Portuguese_Brazil.1252` (collate/ctype)
* **Extensões habilitadas**:

  * **`pgcrypto`** (→ `gen_random_uuid()` / UUID)
  * **`citext`** (texto case‑insensitive em catálogos/usuários)
  * **`pg_trgm`** (trigram para busca por razão social)
  * *(opcional)* `btree_gin`

## Visão geral

* **Multi‑tenant** com **RLS**: todas as tabelas de negócio têm `tenant_id` e policies baseadas em `app.current_tenant_id()`.
* **Perfis**: `admin`, `worker`, `tech` (papel do banco `sirep_tech`).
* **Auditoria**: `created_at/_by`, `updated_at/_by`, `deleted_at/_by` + **histórico de situação** (`app.plano_situacao_hist`).
* **Desempenho para UI**:

  * `app.plano.dt_situacao_atual` (data efetiva da situação, mantida por trigger) — elimina `LATERAL` na view de busca.
  * **Índices sargáveis** para SITUAÇÃO, DIAS, SALDO, DT SITUAÇÃO, razão social, documento.
  * **Paginação por keyset** (ordenar por `saldo_total DESC, numero_plano`).

---

## Papéis (roles)

* **`sirep_tech`**: DDL/ops técnicas; pode ser owner de funções `SECURITY DEFINER` quando necessário.
* **`sirep_admin`**: administração funcional **no próprio tenant**.
* **`sirep_worker`**: operação (ex.: `UPDATE` em `app.plano` do tenant).
* **`sirep_app`**: papel de conexão do backend; privilégios amplos de `SELECT`/DML delegados a RLS.

---

## Schemas

* **`ref`** — Catálogos/lookups (códigos estáveis **sem acento/espaço**).
* **`app`** — Tabelas de negócio, views para UI, funções de sessão/RLS.
* **`audit`** — Logs de execução/eventos, **particionados por mês** (retenção 5 anos).

---

## Convenções de colunas (negócio)

* `id uuid PRIMARY KEY DEFAULT gen_random_uuid()`
* `tenant_id uuid NOT NULL` (FK `app.tenant`)
* Soft‑audit padrão:
  `created_at timestamptz DEFAULT now()`, `created_by uuid`,
  `updated_at timestamptz`, `updated_by uuid`,
  `deleted_at timestamptz`, `deleted_by uuid`

---

## 1. Catálogos — `ref.*`

> Todos com: `id uuid`, `codigo citext UNIQUE`, `descricao text NOT NULL`, `sort_order smallint NULL`, `ativo boolean NOT NULL DEFAULT true`.

* **`ref.tipo_inscricao`** — `CNPJ`, `CPF`, `CEI`.
* **`ref.situacao_plano`** — `EM_DIA`, `P_RESCISAO`, `RESCINDIDO`, `LIQUIDADO`, `SIT_ESPECIAL`, `GRDE_EMITIDA`.
* **`ref.tipo_plano`** — `ADM`, `JUD`, `INS`, `AJ`, `AI`, `AJI`, `JI`, `JA`.
* **`ref.resolucao`** — p.ex. `974/20`, `430/98`.
* **`ref.situacao_parcela`** — `PAGA`, `EM_ATRASO`, `A_VENCER`.
* **`ref.base_fgts`** — p.ex. `SP`, `RJ`, `BR`, `BA`, `SC`, …
  *(usada em `app.empregador_base_fgts`)*

---

## 2. Negócio — `app.*`

### 2.1 `app.tenant`

* **Campos**: `id`, `nome citext UNIQUE`, `ativo`, soft‑audit.
* **RLS**: `USING (id = app.current_tenant_id() OR app.is_tech())`.

### 2.2 `app.usuario`

* **Campos**: `id`, `tenant_id`, `matricula citext`, `nome`, `email citext NOT NULL`, `perfil text CHECK (perfil IN ('admin','worker'))`, `ativo`, soft‑audit.
* **UNIQUE**: `(tenant_id, matricula)`.
* **RLS**: `SELECT` por tenant; `INSERT/UPDATE/DELETE` por `admin/tech`.

### 2.3 `app.empregador`

* **Campos**: `id`, `tenant_id`, `tipo_inscricao_id` (FK `ref.tipo_inscricao`), `numero_inscricao text` (**só dígitos**), `razao_social citext`, `email`, `telefone`, `ativo`, soft‑audit.
* **UNIQUE**: `(tenant_id, tipo_inscricao_id, numero_inscricao)`.
* **Índices**: `GIN (razao_social gin_trgm_ops)`, `(tenant_id, numero_inscricao)`.
* **RLS**: `SELECT` por tenant; DML por `admin/tech`.

### 2.4 `app.empregador_base_fgts`

* **Campos**: `tenant_id`, `empregador_id` (FK `app.empregador`), `base_fgts_id` (FK `ref.base_fgts`) — **PK composta** `(tenant_id, empregador_id, base_fgts_id)`.
* **RLS**: igual a `empregador`.

### 2.5 `app.plano`

* **Essenciais**:
  `id`, `tenant_id`, `empregador_id` (FK),
  `numero_plano text` (**só dígitos, UNIQUE global**),
  `tipo_plano_id` (FK `ref.tipo_plano`),
  `resolucao_id` (FK `ref.resolucao`),
  `situacao_plano_id` (FK `ref.situacao_plano`),
  `competencia_ini date`, `competencia_fim date`,
  `dt_proposta date`, `qtd_parcelas smallint`,
  `saldo_total numeric`,
  `atraso_desde date` (**derivado**),
  `representacao text`, `status text`,
  **`dt_situacao_atual timestamptz`** (**derivado por trigger**),
  soft‑audit.

* **Índices principais**:

  * `UNIQUE(numero_plano)`
  * `idx_plano_tenant_situacao` → `(tenant_id, situacao_plano_id)`
  * `idx_plano_tenant_atraso` → `(tenant_id, atraso_desde)`
  * `idx_plano_tenant_saldo_ord` → `(tenant_id, saldo_total DESC, numero_plano)` **(keyset)**
  * `idx_plano_tenant_dt_sit` → `(tenant_id, dt_situacao_atual)`

* **RLS**:

  * `SELECT`: por tenant.
  * `INSERT`: `admin/tech`.
  * `UPDATE`: `worker/admin/tech` (linhas do tenant).
  * `DELETE`: `admin/tech`.

### 2.6 `app.plano_situacao_hist`

* **Campos**: `id`, `tenant_id`, `plano_id` (FK `app.plano` **ON DELETE CASCADE**), `situacao_plano_id` (FK `ref.situacao_plano`), `mudou_em timestamptz`, `mudou_por uuid`, `observacao text`.
* **Índices**: `(plano_id, mudou_em DESC)`, `(tenant_id)`, `(situacao_plano_id)`.
* **RLS**: `SELECT` por tenant; `INSERT` via trigger; `UPDATE/DELETE` por `admin/tech`.

> **Triggers & lógica** (ver §4.3): usamos **duas** triggers separadas (`BEFORE`/`AFTER`) para evitar violação de FK.

### 2.7 `app.parcela`

* **Campos**: `id`, `tenant_id`, `plano_id` (FK), `nr_parcela int`, `vencimento date`, `valor numeric`, `situacao_parcela_id` (FK `ref.situacao_parcela`), `pago_em date`, `valor_pago numeric`, `qtd_parcelas_total smallint`, soft‑audit.
* **UNIQUE**: `(tenant_id, plano_id, nr_parcela, vencimento)`.
* **Índices**: `(tenant_id, situacao_parcela_id, vencimento)`, `(plano_id)`.
* **RLS**: igual a `plano`.
* **Trigger**: recalcula `plano.atraso_desde` após DML (ver §4.3).

### 2.8 `app.comunicacao`

* **Campos**: `id`, `tenant_id`, `plano_id` (FK), `metodo_id` (FK `ref.metodo_comunicacao`), `assunto`, `corpo`, `enviado_em`, `status`, soft‑audit.
* **RLS**: leitura por tenant; DML por `admin/tech`.

---

## 3. Auditoria & Logs — `audit.*` (particionado por mês)

> **Retenção**: 5 anos (60 meses).
> **PKs** incluem a coluna de partição (boa prática em tabelas particionadas).

### 3.1 `audit.job_run`

* **Partição**: `RANGE (started_at)`
* **Campos**: `tenant_id`, `id`, `job_name text`, `status text` (`RUNNING`/`SUCCESS`/`ERROR`/`SKIPPED`), `started_at timestamptz`, `finished_at timestamptz`, `payload jsonb`, `error_msg text`, `user_id uuid`.
* **PK**: `(tenant_id, started_at, id)`.
* **Índices**: `(tenant_id, started_at)`, `(tenant_id, job_name, started_at DESC)`.
* **RLS**: `SELECT/INSERT/UPDATE` por tenant; `tech` geral.
* **Helpers**: `audit._ym(ts)`, `audit.drop_old_partitions_job_run(p_keep_months)`; *(se aplicou)* `audit.ensure_job_run_partition()` + trigger para auto‑criação.

### 3.2 `audit.evento`

* **Partição**: `RANGE (event_time)`
* **Campos**: `tenant_id`, `id`, `event_time`, `entity text` (`'pipeline'|'plano'|...`), `entity_id uuid`, `event_type text`, `severity text` (`'info'|'warn'|'error'`), `message`, `data jsonb`, `user_id uuid`.
* **PK**: `(tenant_id, event_time, id)`.
* **Índices**: `(tenant_id, event_time)`, `(entity, event_time)`.
* **RLS**: `SELECT/INSERT/UPDATE` por tenant; `tech` geral.
* **Helpers**: `audit.drop_old_partitions_evento(p_keep_months)`; *(se aplicou)* `audit.ensure_evento_partition()` + trigger.

### 3.3 `app.vw_pipeline_status` (view)

* **Colunas**: `job_name`, `status`, `last_update_at`, `duration_text`
  (última execução por `job_name` do tenant da sessão).
* **Uso**: UI exibe “Última atualização em” e “Duração da última atualização”.

---

## 4. Funções & Triggers — `app.*`

### 4.1 Sessão/Contexto & RLS (GUCs)

* **GUCs**: `app.tenant_id`, `app.user_id`, `app.situacao_effective_ts`.
* **Funções**:

  * `app.set_tenant(p_tenant uuid) RETURNS void`
  * `app.set_user(p_user uuid) RETURNS void`
  * `app.current_tenant_id() RETURNS uuid`
  * `app.current_user_id() RETURNS uuid`
  * `app.current_user_perfil() RETURNS text`
  * `app.current_user_is_admin() RETURNS boolean`
  * `app.current_user_is_worker() RETURNS boolean`
  * `app.is_tech() RETURNS boolean`
  * **Login/provisionamento**:

    * `app.ensure_usuario(p_tenant, p_matricula, p_nome NULL, p_email NULL, p_perfil NULL) RETURNS uuid` *(usa e‑mail placeholder se não vier)*
    * `app.set_principal(...) RETURNS uuid`
    * `app.set_principal_by_matricula(p_matricula, p_auto_create boolean DEFAULT false, ...) RETURNS uuid`
    * `app.provision_tenant_and_user(...) RETURNS (tenant_id uuid, user_id uuid)`
    * `app.login_matricula(p_matricula citext) RETURNS uuid` *(preferido na API para ligar sessão)*

### 4.2 Regras de negócio

* `app.recalc_plano_atraso(p_tenant uuid, p_plano uuid) RETURNS void` — recalcula `plano.atraso_desde` a partir de `app.parcela`.

### 4.3 Triggers (principais)

> **Situação do plano** (duas triggers para evitar FK antes da linha existir):

* **`app.tg_plano_set_dt_situacao()`** — **BEFORE INSERT/UPDATE OF situacao_plano_id** em `app.plano`
  Seta `NEW.dt_situacao_atual` usando `app._situacao_effective_ts()` (derivado de `app.situacao_effective_ts` ou `now()`).

* **`app.tg_plano_log_situacao_after()`** — **AFTER INSERT/UPDATE OF situacao_plano_id** em `app.plano`
  Insere em `app.plano_situacao_hist` (`mudou_em = NEW.dt_situacao_atual`), sem violar a FK.

* **`app.tg_parcela_recalc_plano_atraso()`** — após DML em `app.parcela`, chama `app.recalc_plano_atraso(...)`.

* **`app.tg_audit_stamp()`** — carimba `created_*`/`updated_*`.

* **`app.tg_enforce_tenant()`** — garante `NEW.tenant_id` coerente e evita cross‑tenant.

> **Helper**: `app._situacao_effective_ts() RETURNS timestamptz` — resolve timestamp efetivo.

---

## 5. Views para UI

### 5.1 `app.vw_planos_busca`

* **Colunas** *(para a grid e filtros)*:
  `plano_id`, `numero_plano`, `razao_social`,
  `tipo_doc` (`CNPJ/CPF/CEI`), `documento` (só dígitos),
  `situacao_codigo`, `situacao`,
  `dias_em_atraso` (cálculo visual),
  `saldo`,
  **`dt_situacao`** (de `p.dt_situacao_atual::date`),
  **`atraso_desde`** (exposto p/ filtros sargáveis de atraso).

* **Dicas de filtro sargável** (usadas pelo backend):

  * **SITUAÇÃO**: `situacao_codigo IN (...)`.
  * **DIAS**: **use `atraso_desde`** → `atraso_desde <= CURRENT_DATE - INTERVAL '90 days'` (não filtre por `dias_em_atraso`).
  * **SALDO**: `saldo >= :min`.
  * **DT SITUAÇÃO**: ranges sobre `dt_situacao` (`date_trunc('month', CURRENT_DATE)` etc.).

### 5.2 `app.vw_pipeline_status`

* **Colunas**: `job_name`, `status`, `last_update_at`, `duration_text`.
* **Uso**: footer/status na UI.

### 5.3 Views de export (opcional)

* `app.vw_export_rescindidos_cnpj` / `cpf` / `cei` — **uma linha = apenas número** do documento.
* `app.vw_export_eventos` — eventos filtrados por período/tenant.

---

## 6. Policies de RLS (padrão)

* **USING**: `(tenant_id = app.current_tenant_id() OR app.is_tech())`
* **WITH CHECK**: igual ao `USING` + restrições de perfil quando aplicável.
* Tabelas **`app.*`** seguem essa regra, com exceções controladas via perfis (`admin/worker`) por tabela/ação.

---

## 7. Índices recomendados (resumo)

* **`app.plano`**

  * `UNIQUE(numero_plano)`
  * `(tenant_id, situacao_plano_id)`
  * `(tenant_id, atraso_desde)`
  * `(tenant_id, saldo_total DESC, numero_plano)` ➊ *(keyset/ordenar)*
  * `(tenant_id, dt_situacao_atual)` ➋ *(filtros por mês/últimos X meses)*

* **`app.empregador`**

  * `UNIQUE(tenant_id, tipo_inscricao_id, numero_inscricao)`
  * `GIN (razao_social gin_trgm_ops)`
  * `(tenant_id, numero_inscricao)`

* **`app.plano_situacao_hist`**

  * `(plano_id, mudou_em DESC)` *(se ainda consultar histórico diretamente)*

* **`audit.job_run` / `audit.evento`**

  * Ver §3.

> **Sargabilidade**: sempre filtre por **`atraso_desde`** (não por cálculo), por **`dt_situacao_atual`** e por **`saldo_total`**. Isso permite usar esses índices com filtros cumulativos.

---

## 8. Padrões de uso no backend

* **Sessão** (sempre no início da request):

  ```sql
  SELECT app.login_matricula(:matricula::citext);
  SET TIME ZONE 'America/Sao_Paulo';
  ```

* **Busca na grid de planos**: usar **`app.vw_planos_busca`** com filtros sargáveis e **keyset pagination** por `saldo DESC, numero_plano`.

* **Upsert de empregador**:

  * Normalizar documento (`só dígitos`).
  * `ON CONFLICT (tenant_id, tipo_inscricao_id, numero_inscricao) DO UPDATE ...`

* **Upsert de plano**:

  * `ON CONFLICT (numero_plano) DO UPDATE ...`
    *(respeitando RLS; garantir `tenant_id=app.current_tenant_id()` na cláusula)*

* **Mudança de situação com data oficial**:

  ```sql
  SET LOCAL app.situacao_effective_ts = :iso_ts;  -- ex.: '2025-10-01 00:00:00-03'
  UPDATE app.plano
     SET situacao_plano_id = (SELECT id FROM ref.situacao_plano WHERE codigo='RESCINDIDO')
   WHERE numero_plano = :numero AND tenant_id = app.current_tenant_id();
  ```

* **Parcelas**: merges por `(tenant, plano, nr_parcela, vencimento)`; trigger recalcula atraso.

* **Logs/etapas**: `audit.job_run` (inicio/fim/status), `audit.evento` (eventos), *(opcional)* `audit.job_step`.

---

## 9. Exemplos rápidos

**Login de sessão**

```sql
SELECT app.login_matricula('C150930'::citext);
```

**Grid de planos (filtro por CNPJ + texto)**

```sql
SELECT *
FROM app.vw_planos_busca
WHERE tipo_doc = 'CNPJ'
  AND razao_social ILIKE '%'||:texto||'%'
ORDER BY saldo DESC NULLS LAST, numero_plano
LIMIT 10;
```

**Filtros cumulativos eficientes (ex.: GRDE + 120+ dias + mês corrente)**

```sql
SELECT *
FROM app.vw_planos_busca
WHERE situacao_codigo = 'GRDE_EMITIDA'
  AND atraso_desde <= CURRENT_DATE - INTERVAL '120 days'
  AND dt_situacao >= date_trunc('month', CURRENT_DATE)::date
ORDER BY saldo DESC NULLS LAST, numero_plano
LIMIT 10;
```

**Rescisão com data efetiva fornecida pelo sistema oficial**

```sql
SET LOCAL app.situacao_effective_ts = '2025-10-01 00:00:00-03';
UPDATE app.plano
SET situacao_plano_id = (SELECT id FROM ref.situacao_plano WHERE codigo='RESCINDIDO')
WHERE numero_plano='2011003279' AND tenant_id = app.current_tenant_id();
```

---

## 10. Boas práticas & notas

* **Normalização**: sempre armazene documentos e `numero_plano` **só dígitos**.
* **Timeouts**: para contagens pesadas de UI, use `SET LOCAL statement_timeout='1500ms'` + cache no backend.
* **Partições**: crie partições mensais antecipadamente (ou use funções `ensure_*`) e limpe com `drop_old_partitions_*` (retenção de 60 meses).
* **RLS**: garanta que a aplicação **sempre** chama `app.login_matricula()` ao abrir a conexão.
* **Auditoria de seeds/tests**: se não quiser `created_by`, limpe `app.user_id` com `SELECT app.set_user(NULL)`; caso queira, crie/obtenha o UUID do usuário e faça `SELECT app.set_user(:uuid)`.

---
