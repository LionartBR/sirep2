export function registerPlanDetailsModule(context) {
  const layer = document.querySelector('[data-plan-details]');
  if (!layer) {
    context.showPlanDetails = () => {
      context.showToast?.('Detalhes do plano indisponíveis.');
    };
    context.closePlanDetails = () => {};
    return;
  }
  const overlay = layer?.querySelector('[data-plan-details-overlay]') ?? null;
  const panel = layer?.querySelector('[data-plan-details-panel]') ?? null;
  const closeButton = layer?.querySelector('[data-plan-details-close]') ?? null;
  const titleEl = layer?.querySelector('[data-plan-details-title]') ?? null;
  const subtitleEl = layer?.querySelector('[data-plan-details-subtitle]') ?? null;

  const fieldNodes = layer ? Array.from(layer.querySelectorAll('[data-plan-details-field]')) : [];
  const fields = fieldNodes.reduce((acc, node) => {
    const key = node.dataset.planDetailsField;
    if (key) {
      acc[key] = node;
    }
    return acc;
  }, {});

  const documentLabelEl = layer.querySelector('[data-plan-details-label="document"]');

  const state = context;
  state.isPlanDetailsOpen = false;
  state.currentPlanDetails = null;
  let lastFocusedElement = null;
  let planDetailFetchSeq = 0;

  const ensurePlanDetailsCache = () => {
    if (!(state.planDetailsCache instanceof Map)) {
      state.planDetailsCache = new Map();
    }
    return state.planDetailsCache;
  };

  const normalizeIdentifier = (value) => {
    if (value === null || value === undefined) {
      return '';
    }
    if (typeof value === 'string') {
      return value.trim();
    }
    if (typeof value === 'number') {
      return String(value);
    }
    if (typeof value === 'object' && 'toString' in value) {
      return String(value).trim();
    }
    return '';
  };

  const resolvePlanIdentifiers = (source) => {
    const candidates = [];
    if (source && typeof source === 'object') {
      candidates.push(source);
      if (source.raw && typeof source.raw === 'object') {
        candidates.push(source.raw);
      }
    }

    let planId = '';
    let planNumber = '';

    const planIdKeys = ['plan_id', 'planId', 'id', 'plano_id', 'planoId'];
    const planNumberKeys = ['number', 'numero', 'plan_number', 'planNumber', 'numero_plano'];

    for (const candidate of candidates) {
      if (!planId) {
        planId = normalizeIdentifier(getFirstAvailable(candidate, planIdKeys));
      }
      if (!planNumber) {
        planNumber = normalizeIdentifier(getFirstAvailable(candidate, planNumberKeys));
      }
      if (planId && planNumber) {
        break;
      }
    }

    return { planId, planNumber };
  };

  const buildCacheKey = (prefix, value) => {
    const text = normalizeIdentifier(value);
    return text ? `${prefix}:${text}` : null;
  };

  const getCachedDetail = (plan) => {
    const cache = ensurePlanDetailsCache();
    const { planId, planNumber } = resolvePlanIdentifiers(plan);
    const keys = [buildCacheKey('id', planId), buildCacheKey('number', planNumber)];
    for (const key of keys) {
      if (key && cache.has(key)) {
        return cache.get(key);
      }
    }
    return null;
  };

  const storeDetailInCache = (detail) => {
    if (!detail || typeof detail !== 'object') {
      return;
    }
    const cache = ensurePlanDetailsCache();
    const { planId, planNumber } = resolvePlanIdentifiers(detail);
    const idKey = buildCacheKey('id', planId);
    const numberKey = buildCacheKey('number', planNumber);
    if (idKey) {
      cache.set(idKey, detail);
    }
    if (numberKey) {
      cache.set(numberKey, detail);
    }
    if (state.planMetadata instanceof Map) {
      if (planId) {
        const existingById = state.planMetadata.get(planId) ?? {};
        state.planMetadata.set(planId, { ...existingById, detail });
      }
      if (planNumber) {
        const existingByNumber = state.planMetadata.get(planNumber) ?? {};
        state.planMetadata.set(planNumber, { ...existingByNumber, detail });
      }
    }
  };

  const buildDetailUrl = (identifier) => {
    const baseEndpoint = context.PLANS_ENDPOINT ?? '/api/plans';
    const origin = window.location.origin && window.location.origin !== 'null'
      ? window.location.origin
      : window.location.href;
    const normalizedBase = baseEndpoint.startsWith('/') ? baseEndpoint : `/${baseEndpoint}`;
    const encoded = encodeURIComponent(identifier);
    return new URL(`${normalizedBase}/${encoded}/detail`, origin);
  };

  const fetchPlanDetail = async ({ planId, planNumber }) => {
    const identifier = normalizeIdentifier(planId) || normalizeIdentifier(planNumber);
    if (!identifier) {
      return null;
    }

    const headers = new Headers({ Accept: 'application/json' });
    const matricula = state.currentUser?.username?.trim();
    if (matricula) {
      headers.set('X-User-Registration', matricula);
    }

    const response = await fetch(buildDetailUrl(identifier).toString(), { headers });
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      throw new Error(`Failed to load plan detail (${response.status})`);
    }
    return response.json();
  };

  const loadPlanDetail = async (plan) => {
    const identifiers = resolvePlanIdentifiers(plan);
    if (!identifiers.planId && !identifiers.planNumber) {
      return;
    }

    const cached = getCachedDetail(plan);
    if (cached) {
      const normalizedCached = normalizePlanDetails(cached);
      state.currentPlanDetails = normalizedCached;
      populateFields(normalizedCached);
      return;
    }

    const fetchToken = ++planDetailFetchSeq;
    try {
      const detail = await fetchPlanDetail(identifiers);
      if (!detail) {
        if (state.isPlanDetailsOpen && fetchToken === planDetailFetchSeq) {
          context.showToast?.('Plano não encontrado.');
        }
        return;
      }
      storeDetailInCache(detail);
      if (fetchToken !== planDetailFetchSeq || !state.isPlanDetailsOpen) {
        return;
      }
      const normalizedDetail = normalizePlanDetails(detail);
      state.currentPlanDetails = normalizedDetail;
      populateFields(normalizedDetail);
    } catch (error) {
      console.error('Falha ao carregar os detalhes do plano.', error);
      if (state.isPlanDetailsOpen && fetchToken === planDetailFetchSeq) {
        context.showToast?.('Não foi possível carregar os detalhes do plano.');
      }
    }
  };


  const shorten = (value, max = 52) => {
    if (!value) {
      return '';
    }
    const text = String(value).trim();
    if (text.length <= max) {
      return text;
    }
    return `${text.slice(0, max - 3).trim()}...`;
  };

  const getFirstAvailable = (source, keys) => {
    if (!source || typeof source !== 'object') {
      return null;
    }
    for (const key of keys) {
      if (!(key in source)) {
        continue;
      }
      const value = source[key];
      if (value === null || value === undefined) {
        continue;
      }
      if (typeof value === 'string') {
        if (!value.trim()) {
          continue;
        }
        return value;
      }
      if (typeof value === 'number') {
        if (Number.isNaN(value)) {
          continue;
        }
        return value;
      }
      return value;
    }
    return null;
  };

  const parseDateValue = (value) => {
    if (!value) {
      return null;
    }
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return value;
    }
    if (typeof value === 'number') {
      const date = new Date(value);
      if (!Number.isNaN(date.getTime())) {
        return date;
      }
    }
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (!trimmed) {
        return null;
      }
      const normalized = trimmed.replace(/ /g, 'T');
      const parsed = new Date(normalized);
      if (!Number.isNaN(parsed.getTime())) {
        return parsed;
      }
    }
    return null;
  };

  const formatAbsoluteDateTime = (value) => {
    const date = parseDateValue(value);
    if (!date) {
      return null;
    }
    try {
      return new Intl.DateTimeFormat('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'America/Sao_Paulo',
      }).format(date);
    } catch (error) {
      console.warn('Falha ao formatar data/hora absoluta.', error);
      return date.toLocaleString('pt-BR');
    }
  };

  const formatRelativeUpdate = (value) => {
    const date = parseDateValue(value);
    if (!date) {
      return null;
    }
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    if (!Number.isFinite(diffMs)) {
      return null;
    }
    const minuteMs = 60 * 1000;
    const hourMs = 60 * minuteMs;
    const dayMs = 24 * hourMs;
    const monthMs = 30 * dayMs;

    if (diffMs < 0) {
      const abs = Math.abs(diffMs);
      if (abs < minuteMs) {
        return 'Atualiza em instantes';
      }
      if (abs < hourMs) {
        const minutes = Math.max(1, Math.round(abs / minuteMs));
        return `Atualiza em ${minutes}min`;
      }
      if (abs < dayMs) {
        const hours = Math.max(1, Math.round(abs / hourMs));
        return `Atualiza em ${hours}h`;
      }
      const days = Math.max(1, Math.round(abs / dayMs));
      return `Atualiza em ${days}d`;
    }

    if (diffMs < minuteMs) {
      return 'Atualizado agora';
    }
    if (diffMs < hourMs) {
      const minutes = Math.max(1, Math.round(diffMs / minuteMs));
      return `Atualizado há ${minutes}min`;
    }
    if (diffMs < dayMs) {
      const hours = Math.max(1, Math.round(diffMs / hourMs));
      return `Atualizado há ${hours}h`;
    }
    if (diffMs < monthMs) {
      const days = Math.max(1, Math.round(diffMs / dayMs));
      return `Atualizado há ${days}d`;
    }
    const months = Math.max(1, Math.round(diffMs / monthMs));
    return `Atualizado há ${months}m`;
  };

  const setFieldValue = (key, rawValue) => {
    const target = fields[key];
    if (!target) {
      return;
    }
    if (rawValue === null || rawValue === undefined) {
      target.textContent = '—';
      return;
    }
    const text = typeof rawValue === 'string' ? rawValue.trim() : String(rawValue);
    target.textContent = text || '—';
  };

  const setFieldWithNote = (key, mainValue, noteValue) => {
    const target = fields[key];
    if (!target) {
      return;
    }
    target.textContent = '';
    if (mainValue === null || mainValue === undefined) {
      target.append('—');
    } else {
      const text = typeof mainValue === 'string' ? mainValue.trim() : String(mainValue);
      target.append(text || '—');
    }
    if (noteValue) {
      const note = document.createElement('span');
      note.className = 'plan-details__value-note';
      note.textContent = noteValue;
      target.appendChild(note);
    }
  };

  const normalizePlanDetails = (plan) => {
    const number = getFirstAvailable(plan, ['number', 'numero', 'plan_number', 'planNumber', 'numero_plano']);
    const identifier = number ? String(number).trim() : '';
    const documentRaw = getFirstAvailable(plan, [
      'document',
      'documento',
      'document_number',
      'documentNumber',
      'numero_inscricao',
      'numeroInscricao',
      'cnpj',
      'cpf',
      'cei',
    ]);
    const companyName = getFirstAvailable(plan, [
      'company_name',
      'companyName',
      'razao_social',
      'razaoSocial',
      'nome_empresa',
      'nomeEmpresa',
    ]);
    const planType = getFirstAvailable(plan, [
      'plan_type',
      'planType',
      'tipo_plano',
      'tipoPlano',
      'tipo',
      'tipoDescricao',
    ]);
    const resolution = getFirstAvailable(plan, [
      'resolucao',
      'resolution',
      'resolucao_codigo',
      'resolucaoCodigo',
      'resolucaoDescricao',
    ]);
    const status = getFirstAvailable(plan, ['status', 'situacao', 'status_label', 'statusLabel']);
    const periodStart = getFirstAvailable(plan, [
      'competencia_ini',
      'competenciaIni',
      'period_start',
      'periodo_inicio',
      'periodoIni',
    ]);
    const periodEnd = getFirstAvailable(plan, [
      'competencia_fim',
      'competenciaFim',
      'period_end',
      'periodo_fim',
      'periodoFim',
    ]);
    const daysOverdue = getFirstAvailable(plan, ['days_overdue', 'dias_em_atraso', 'diasAtraso']);
    const balance = getFirstAvailable(plan, ['balance', 'saldo_total', 'saldoTotal', 'valor_total']);
    const updatedAt = getFirstAvailable(plan, [
      'updated_at',
      'ultima_atualizacao',
      'last_update_at',
      'last_update',
      'lastUpdateAt',
      'status_date',
      'dt_situacao',
      'data_atualizacao',
    ]);
    const rescissionFlag = getFirstAvailable(plan, [
      'rescisao_comunicada',
      'rescisaoComunicada',
      'rescission_notified',
      'rescissionNotified',
      'possui_rescisao',
    ]);
    const rescissionDate = getFirstAvailable(plan, [
      'rescisao_comunicada_em',
      'rescisao_data',
      'rescission_notified_at',
      'data_rescisao',
    ]);

    return {
      raw: plan,
      identifier,
      documentRaw,
      companyName,
      planType,
      resolution,
      status,
      periodStart,
      periodEnd,
      daysOverdue,
      balance,
      updatedAt,
      rescissionFlag,
      rescissionDate,
    };
  };

  const populateFields = (details) => {
    if (!details) {
      return;
    }

    const {
      identifier,
      documentRaw,
      companyName,
      planType,
      resolution,
      status,
      periodStart,
      periodEnd,
      daysOverdue,
      balance,
      updatedAt,
      rescissionFlag,
      rescissionDate,
    } = details;

    if (titleEl) {
      const label = identifier ? `Plano #${identifier}` : 'Plano —';
      titleEl.textContent = label;
    }

    if (subtitleEl) {
      if (companyName) {
        subtitleEl.textContent = shorten(companyName, 64);
        subtitleEl.title = String(companyName);
      } else {
        subtitleEl.textContent = '—';
        subtitleEl.removeAttribute('title');
      }
    }

    const docFormatted = documentRaw ? context.formatDocument?.(documentRaw) ?? String(documentRaw) : null;
    const docTypeRaw = details?.raw ? getFirstAvailable(details.raw, [
      'tipo_doc',
      'document_type',
      'tipoDocumento',
    ]) : null;
    const docTypeLabel = typeof docTypeRaw === 'string' ? docTypeRaw.trim().toUpperCase() : null;
    const statusFormatted = status ? context.formatStatusLabel?.(status) ?? String(status) : null;
    const periodStartFormatted = periodStart ? context.formatDateLabel?.(periodStart) ?? String(periodStart) : null;
    const periodEndFormatted = periodEnd ? context.formatDateLabel?.(periodEnd) ?? String(periodEnd) : null;
    const daysFormatted = context.formatDaysValue?.(daysOverdue) ?? '—';
    const balanceFormatted = context.formatCurrencyValue?.(balance) ?? '—';

    let periodValue = null;
    if (periodStartFormatted && periodEndFormatted) {
      periodValue = `${periodStartFormatted} - ${periodEndFormatted}`;
    } else if (periodStartFormatted) {
      periodValue = periodStartFormatted;
    } else if (periodEndFormatted) {
      periodValue = periodEndFormatted;
    }

    if (documentLabelEl) {
      documentLabelEl.textContent = docTypeLabel || 'Documento';
    }
    setFieldValue('document', docFormatted);
    setFieldValue('type', planType ?? null);
    setFieldValue('resolution', resolution ?? null);
    setFieldValue('status', statusFormatted);
    setFieldValue('period', periodValue);
    setFieldValue('days', daysFormatted);
    setFieldValue('balance', balanceFormatted);

    const absoluteUpdate = formatAbsoluteDateTime(updatedAt);
    const relativeUpdate = formatRelativeUpdate(updatedAt);
    setFieldWithNote('updated', absoluteUpdate ?? null, relativeUpdate);

    const rescissionDateFormatted = rescissionDate
      ? formatAbsoluteDateTime(rescissionDate)
      : null;
    let rescissionValue = null;
    let rescissionBoolean;
    if (typeof rescissionFlag === 'string') {
      const normalized = rescissionFlag.trim().toLowerCase();
      if (['true', 'sim', 's', '1', 'yes', 'y'].includes(normalized)) {
        rescissionBoolean = true;
      } else if (['false', 'nao', 'não', 'n', '0', 'no'].includes(normalized)) {
        rescissionBoolean = false;
      }
    }
    if (rescissionBoolean === undefined) {
      rescissionBoolean = Boolean(rescissionFlag);
    }

    if (rescissionBoolean) {
      rescissionValue = 'Sim';
      if (rescissionDateFormatted) {
        rescissionValue = `Sim - Data da comunicação: ${rescissionDateFormatted}`;
      }
    } else if (rescissionBoolean === false) {
      rescissionValue = 'Não';
    }
    setFieldValue('rescission', rescissionValue);
  };

  const handleOpen = (plan) => {
    if (!panel) {
      return;
    }
    if (!plan) {
      context.showToast?.('Não foi possível carregar os detalhes do plano selecionado.');
      return;
    }
    const normalizedPlan = normalizePlanDetails(plan);
    state.currentPlanDetails = normalizedPlan;
    populateFields(normalizedPlan);

    const cachedDetail = getCachedDetail(plan);
    if (cachedDetail) {
      const normalizedDetail = normalizePlanDetails(cachedDetail);
      state.currentPlanDetails = normalizedDetail;
      populateFields(normalizedDetail);
    } else {
      void loadPlanDetail(plan);
    }
    lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    layer.classList.add('plan-details--visible');
    layer.removeAttribute('hidden');
    layer.setAttribute('aria-hidden', 'false');
    document.body.classList.add('plan-details-open');
    state.isPlanDetailsOpen = true;
    window.requestAnimationFrame(() => {
      panel.focus();
      window.feather?.replace(panel);
    });
    document.addEventListener('keydown', handleKeydown);
  };

  const handleClose = () => {
    if (!layer) {
      return;
    }
    planDetailFetchSeq += 1;
    layer.classList.remove('plan-details--visible');
    layer.setAttribute('hidden', 'hidden');
    layer.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('plan-details-open');
    state.isPlanDetailsOpen = false;
    document.removeEventListener('keydown', handleKeydown);
    state.currentPlanDetails = null;
    if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
      lastFocusedElement.focus();
    }
  };

  const handleKeydown = (event) => {
    if (event.key === 'Escape' && state.isPlanDetailsOpen) {
      event.preventDefault();
      handleClose();
    }
  };

  if (overlay) {
    overlay.addEventListener('click', () => {
      handleClose();
    });
  }

  if (closeButton) {
    closeButton.addEventListener('click', () => {
      handleClose();
    });
  }

  if (panel) {
    panel.addEventListener('click', (event) => {
      const dismiss = event.target instanceof HTMLElement
        ? event.target.closest('[data-plan-details-close]')
        : null;
      if (dismiss) {
        handleClose();
      }
    });
  }

  context.showPlanDetails = handleOpen;
  context.closePlanDetails = handleClose;
}
