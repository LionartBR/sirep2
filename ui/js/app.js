/* global flatpickr */
document.addEventListener('DOMContentLoaded', () => {
  if (!window.Auth || !Auth.isAuthenticated()) {
    window.location.replace('/app/login.html');
    return;
  }

  if (window.feather) {
    window.feather.replace();
  }

  const currentUser = Auth.getUser();
  const userNameLabel = document.getElementById('currentUserName');
  if (userNameLabel) {
    const displayName = currentUser?.name || currentUser?.username || 'Operador';
    userNameLabel.textContent = displayName;
  }

  const signOutLink = document.querySelector('.topbar__signout');
  if (signOutLink) {
    signOutLink.addEventListener('click', (event) => {
      event.preventDefault();
      Auth.logout();
      window.location.replace('/app/login.html');
    });
  }

  const statusText = document.getElementById('statusText');
  const btnStart = document.getElementById('btnStart');
  const btnPause = document.getElementById('btnPause');
  const btnContinue = document.getElementById('btnContinue');
  const progressContainer = document.querySelector('.progress');
  const progressBar = progressContainer?.querySelector('.progress__bar');
  // Pipeline meta labels
  const lblLastUpdate = document.getElementById('lbl-last-update');
  const lblLastDuration = document.getElementById('lbl-last-duration');
  const dateFromInput = document.getElementById('date-from');
  const dateToInput = document.getElementById('date-to');
  const openDateFromButton = document.getElementById('open-date-from');
  const openDateToButton = document.getElementById('open-date-to');
  const plansTablePanel = document.getElementById('plansTablePanel');
  const plansTableElement = plansTablePanel?.querySelector('table') ?? null;
  const plansTableBody = plansTableElement?.tBodies?.[0] ?? null;
  const plansColumnCount =
    plansTableElement?.tHead?.rows?.[0]?.cells?.length ??
    plansTableElement?.rows?.[0]?.cells?.length ??
    8;
  const lastUpdateLabel = document.getElementById('lastUpdateInfo');

  // Occurrences table elements
  const occTablePanel = document.getElementById('occurrencesTablePanel');
  const occTableElement = occTablePanel?.querySelector('table') ?? null;
  const occTableBody = occTableElement?.tBodies?.[0] ?? null;
  const occColumnCount =
    occTableElement?.tHead?.rows?.[0]?.cells?.length ??
    occTableElement?.rows?.[0]?.cells?.length ??
    8;

  const PIPELINE_ENDPOINT = '/api/pipeline';
  const PLANS_ENDPOINT = '/api/plans';
  const DEFAULT_PLAN_PAGE_SIZE = 10;
  const tableSearchState = {
    plans: '',
    occurrences: '',
  };
  if (lastUpdateLabel) {
    lastUpdateLabel.textContent = 'Última atualização em: —';
  }
  let currentPlansSearchTerm = '';
  let currentOccurrencesSearchTerm = '';
  let activeTableSearchTarget = 'plans';
  let plansFetchController = null;
  let occFetchController = null;
  const currencyFormatter = new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
  });

  const PROGRESS_TOTAL_DURATION_MS = 15 * 60 * 1000;
  const PROGRESS_MAX_RATIO_BEFORE_COMPLETION = 0.99;
  let progressStartTimestamp = null;
  let progressIntervalHandle = null;

  let pollHandle = null;
  let pipelineMetaController = null;
  let isFetchingPipelineMeta = false;
  let isFetchingPlans = false;
  let isFetchingOccurrences = false;
  let plansLoaded = false;
  let occurrencesLoaded = false;
  let shouldRefreshPlansAfterRun = false;
  let lastSuccessfulFinishedAt = null;

  const setStatus = (text) => {
    statusText.textContent = `Estado: ${text}`;
  };

  const formatStatusLabel = (value) => {
    if (!value) {
      return '—';
    }
    const text = String(value).trim();
    if (!text) {
      return '—';
    }
    return text.replace(/_/g, ' ');
  };

  const formatDaysValue = (value) => {
    if (value === null || value === undefined) {
      return '—';
    }
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return '—';
    }
    return String(Math.max(0, Math.trunc(number)));
  };

  const formatCurrencyValue = (value) => {
    if (value === null || value === undefined) {
      return '—';
    }
    const number = typeof value === 'number' ? value : Number(value);
    if (!Number.isFinite(number)) {
      return '—';
    }
    try {
      return currencyFormatter.format(number);
    } catch (error) {
      console.warn('Falha ao formatar valor monetário.', error);
      return number.toFixed(2);
    }
  };

  const formatDateLabel = (value) => {
    if (!value) {
      return '—';
    }
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return value.toLocaleDateString('pt-BR');
    }
    const text = String(value).trim();
    if (!text) {
      return '—';
    }
    const isoMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (isoMatch) {
      const [, year, month, day] = isoMatch;
      return `${day}/${month}/${year}`;
    }
    const parsed = new Date(text);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed.toLocaleDateString('pt-BR');
    }
    return text;
  };

  const formatDateTimeLabel = (value) => {
    if (!value) {
      return '—';
    }
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) {
      return '—';
    }
    return date.toLocaleString('pt-BR', {
      dateStyle: 'short',
      timeStyle: 'short',
    });
  };

  const formatDateTime = (value) => {
    if (!value) {
      return '—';
    }
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) {
      return '—';
    }
    try {
      return new Intl.DateTimeFormat('pt-BR', {
        dateStyle: 'short',
        timeStyle: 'medium',
        timeZone: 'America/Sao_Paulo',
      }).format(date);
    } catch (error) {
      return date.toLocaleString('pt-BR');
    }
  };

  const pad2 = (n) => String(Math.trunc(Math.max(0, n))).padStart(2, '0');
  const formatDurationText = (ms) => {
    if (!Number.isFinite(ms) || ms < 0) {
      return '—';
    }
    const totalSeconds = Math.trunc(ms / 1000);
    const hours = Math.trunc(totalSeconds / 3600);
    const minutes = Math.trunc((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours}h ${pad2(minutes)}m ${pad2(seconds)}s`;
  };

  const setText = (el, prefix, value) => {
    if (!el) return;
    const text = value ? value : '—';
    el.textContent = `${prefix} ${text}`;
  };

  const updateLastUpdateInfo = (state) => {
    if (!lastUpdateLabel) {
      return;
    }
    if (state?.status === 'succeeded' && state?.finished_at) {
      lastSuccessfulFinishedAt = state.finished_at;
    }
    const timestamp = lastSuccessfulFinishedAt ?? null;
    const formatted = formatDateTimeLabel(timestamp);
    lastUpdateLabel.textContent = `Última atualização em: ${formatted}`;
  };

  const refreshPipelineMeta = async () => {
    if (isFetchingPipelineMeta) {
      return null;
    }
    isFetchingPipelineMeta = true;
    try {
      if (pipelineMetaController) {
        pipelineMetaController.abort();
      }
      pipelineMetaController = new AbortController();
      const baseUrl =
        window.location.origin && window.location.origin !== 'null'
          ? window.location.origin
          : window.location.href;
      const url = new URL(`${PIPELINE_ENDPOINT}/status`, baseUrl);
      url.searchParams.set('job_name', 'gestao_base');
      const headers = new Headers({ Accept: 'application/json' });
      const matricula = currentUser?.username?.trim();
      if (matricula) {
        headers.set('X-User-Registration', matricula);
      }
      const response = await fetch(url.toString(), {
        headers,
        signal: pipelineMetaController.signal,
      });
      if (!response.ok) {
        throw new Error('Não foi possível consultar o status da pipeline.');
      }
      const payload = await response.json();
      const lastUpdateAt = payload?.last_update_at ?? null;
      const durationText = payload?.duration_text ?? null;
      setText(lblLastUpdate, 'Última atualização em:', formatDateTime(lastUpdateAt));
      setText(lblLastDuration, 'Duração da última atualização:', durationText);
      return payload;
    } catch (error) {
      console.error('Falha ao carregar metadados da pipeline.', error);
      setText(lblLastUpdate, 'Última atualização em:', null);
      setText(lblLastDuration, 'Duração da última atualização:', null);
      return null;
    } finally {
      pipelineMetaController = null;
      isFetchingPipelineMeta = false;
    }
  };

  const renderPlansPlaceholder = (message, modifier = 'empty') => {
    if (!plansTableBody) {
      return;
    }
    plansTableBody.innerHTML = '';
    const row = document.createElement('tr');
    row.className = 'table__row table__row--empty';
    if (modifier) {
      row.classList.add(`table__row--${modifier}`);
    }
    const cell = document.createElement('td');
    cell.className = 'table__cell';
    cell.colSpan = plansColumnCount;
    cell.textContent = message;
    row.appendChild(cell);
    plansTableBody.appendChild(row);
  };

  const renderPlanRows = (items) => {
    if (!plansTableBody) {
      return;
    }
    plansTableBody.innerHTML = '';
    const plans = Array.isArray(items) ? items : [];
    if (!plans.length) {
      if (currentPlansSearchTerm) {
        renderPlansPlaceholder('nenhum plano encontrado para a busca.', 'empty');
      } else {
        renderPlansPlaceholder('nada a exibir por aqui.');
      }
      return;
    }

    plans.forEach((item) => {
      const row = document.createElement('tr');
      row.className = 'table__row';

      const planCell = document.createElement('td');
      planCell.className = 'table__cell';
      planCell.textContent = item?.number ?? '';
      row.appendChild(planCell);

      const documentCell = document.createElement('td');
      documentCell.className = 'table__cell';
      documentCell.textContent = item?.document ?? '';
      row.appendChild(documentCell);

      const companyCell = document.createElement('td');
      companyCell.className = 'table__cell';
      companyCell.textContent = item?.company_name ?? '';
      row.appendChild(companyCell);

      const statusCell = document.createElement('td');
      statusCell.className = 'table__cell';
      statusCell.textContent = formatStatusLabel(item?.status);
      row.appendChild(statusCell);

      const daysCell = document.createElement('td');
      daysCell.className = 'table__cell';
      daysCell.textContent = formatDaysValue(item?.days_overdue);
      row.appendChild(daysCell);

      const balanceCell = document.createElement('td');
      balanceCell.className = 'table__cell';
      balanceCell.textContent = formatCurrencyValue(item?.balance);
      row.appendChild(balanceCell);

      const statusDateCell = document.createElement('td');
      statusDateCell.className = 'table__cell';
      statusDateCell.textContent = formatDateLabel(item?.status_date);
      row.appendChild(statusDateCell);

      const actionsCell = document.createElement('td');
      actionsCell.className = 'table__cell';
      actionsCell.textContent = '—';
      row.appendChild(actionsCell);

      plansTableBody.appendChild(row);
    });
  };

  const renderOccurrenceRows = (items) => {
    if (!occTableBody) {
      return;
    }
    occTableBody.innerHTML = '';
    const rows = Array.isArray(items) ? items : [];
    if (!rows.length) {
      renderOccurrencesPlaceholder('nenhuma ocorrência por aqui.');
      return;
    }

    rows.forEach((item) => {
      const row = document.createElement('tr');
      row.className = 'table__row';

      const planCell = document.createElement('td');
      planCell.className = 'table__cell';
      planCell.textContent = item?.number ?? '';
      row.appendChild(planCell);

      const documentCell = document.createElement('td');
      documentCell.className = 'table__cell';
      documentCell.textContent = item?.document ?? '';
      row.appendChild(documentCell);

      const companyCell = document.createElement('td');
      companyCell.className = 'table__cell';
      companyCell.textContent = item?.company_name ?? '';
      row.appendChild(companyCell);

      const statusCell = document.createElement('td');
      statusCell.className = 'table__cell';
      statusCell.textContent = formatStatusLabel(item?.status);
      row.appendChild(statusCell);

      const daysCell = document.createElement('td');
      daysCell.className = 'table__cell';
      daysCell.textContent = formatDaysValue(item?.days_overdue);
      row.appendChild(daysCell);

      const balanceCell = document.createElement('td');
      balanceCell.className = 'table__cell';
      balanceCell.textContent = formatCurrencyValue(item?.balance);
      row.appendChild(balanceCell);

      const statusDateCell = document.createElement('td');
      statusDateCell.className = 'table__cell';
      statusDateCell.textContent = formatDateLabel(item?.status_date);
      row.appendChild(statusDateCell);

      const actionsCell = document.createElement('td');
      actionsCell.className = 'table__cell';
      actionsCell.textContent = '—';
      row.appendChild(actionsCell);

      occTableBody.appendChild(row);
    });
  };

  const renderOccurrencesPlaceholder = (message, modifier = 'empty') => {
    if (!occTableBody) {
      return;
    }
    occTableBody.innerHTML = '';
    const row = document.createElement('tr');
    row.className = 'table__row table__row--empty';
    if (modifier) {
      row.classList.add(`table__row--${modifier}`);
    }
    const cell = document.createElement('td');
    cell.className = 'table__cell';
    cell.colSpan = occColumnCount;
    cell.textContent = message;
    row.appendChild(cell);
    occTableBody.appendChild(row);
  };

  // --- Keyset pagination state (client-side) ---
  const plansPager = {
    page: 1,
    pageSize: DEFAULT_PLAN_PAGE_SIZE,
    nextCursor: null,
    prevCursor: null,
    hasMore: false,
    totalCount: null,
    totalPages: null,
    showingFrom: 0,
    showingTo: 0,
  };

  const plansPagerPrevBtn = document.getElementById('plansPagerPrev');
  const plansPagerNextBtn = document.getElementById('plansPagerNext');
  const plansPagerLabel = document.getElementById('plansPagerLabel');
  const plansPagerRange = document.getElementById('plansPagerRange');

  // Occurrences pager UI elements
  const occPagerPrevBtn = document.getElementById('occPagerPrev');
  const occPagerNextBtn = document.getElementById('occPagerNext');
  const occPagerLabel = document.getElementById('occPagerLabel');
  const occPagerRange = document.getElementById('occPagerRange');

  // Independent keyset pager for occurrences
  const occPager = {
    page: 1,
    pageSize: DEFAULT_PLAN_PAGE_SIZE,
    nextCursor: null,
    prevCursor: null,
    hasMore: false,
    totalCount: null,
    totalPages: null,
    showingFrom: 0,
    showingTo: 0,
  };

  const updatePlansPagerUI = () => {
    if (plansPagerLabel) {
      const totalPages = plansPager.totalPages ?? null;
      const totalPagesLabel = totalPages && Number.isFinite(totalPages) ? String(totalPages) : '?';
      plansPagerLabel.textContent = `pág. ${plansPager.page} de ${totalPagesLabel}`;
    }
    if (plansPagerRange) {
      const totalKnown = plansPager.totalCount !== null && plansPager.totalCount !== undefined;
      const totalLabel = totalKnown ? String(plansPager.totalCount) : `~${Math.max(plansPager.showingTo, 0)}`;
      const from = plansPager.showingFrom || 0;
      const to = plansPager.showingTo || 0;
      plansPagerRange.textContent = `exibindo ${from}–${to} de ${totalLabel} planos`;
    }
    if (plansPagerPrevBtn) {
      const canGoPrev = plansPager.page > 1;
      plansPagerPrevBtn.disabled = !canGoPrev;
      plansPagerPrevBtn.setAttribute('aria-disabled', String(!canGoPrev));
    }
    if (plansPagerNextBtn) {
      const canGoNext = !!plansPager.hasMore;
      plansPagerNextBtn.disabled = !canGoNext;
      plansPagerNextBtn.setAttribute('aria-disabled', String(!canGoNext));
    }
  };

  const updateOccPagerUI = () => {
    if (occPagerLabel) {
      const totalPages = occPager.totalPages ?? null;
      const totalPagesLabel = totalPages && Number.isFinite(totalPages) ? String(totalPages) : '?';
      occPagerLabel.textContent = `pág. ${occPager.page} de ${totalPagesLabel}`;
    }
    if (occPagerRange) {
      const totalKnown = occPager.totalCount !== null && occPager.totalCount !== undefined;
      const totalLabel = totalKnown ? String(occPager.totalCount) : `~${Math.max(occPager.showingTo, 0)}`;
      const from = occPager.showingFrom || 0;
      const to = occPager.showingTo || 0;
      occPagerRange.textContent = `exibindo ${from}–${to} de ${totalLabel} planos para tratamento manual`;
    }
    if (occPagerPrevBtn) {
      const canGoPrev = occPager.page > 1;
      occPagerPrevBtn.disabled = !canGoPrev;
      occPagerPrevBtn.setAttribute('aria-disabled', String(!canGoPrev));
    }
    if (occPagerNextBtn) {
      const canGoNext = !!occPager.hasMore;
      occPagerNextBtn.disabled = !canGoNext;
      occPagerNextBtn.setAttribute('aria-disabled', String(!canGoNext));
    }
  };

  const buildPlansRequestUrl = ({ direction = null } = {}) => {
    const baseUrl =
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : window.location.href;
    const url = new URL(PLANS_ENDPOINT, baseUrl);
    // Keyset pagination params
    url.searchParams.set('page', String(plansPager.page));
    url.searchParams.set('page_size', String(plansPager.pageSize));
    if (direction === 'next' && plansPager.nextCursor) {
      url.searchParams.set('cursor', plansPager.nextCursor);
      url.searchParams.set('direction', 'next');
    } else if (direction === 'prev' && plansPager.prevCursor) {
      url.searchParams.set('cursor', plansPager.prevCursor);
      url.searchParams.set('direction', 'prev');
    }
    if (currentPlansSearchTerm) {
      url.searchParams.set('q', currentPlansSearchTerm);
    }
    return url.toString();
  };

  const refreshPlans = async ({ showLoading, direction = null } = {}) => {
    if (!plansTableBody || isFetchingPlans) {
      return;
    }
    const shouldShowLoading = showLoading ?? !plansLoaded;
    if (shouldShowLoading) {
      renderPlansPlaceholder('carregando planos...', 'loading');
    }

    isFetchingPlans = true;
    try {
      if (plansFetchController) {
        plansFetchController.abort();
      }
      plansFetchController = new AbortController();
      const requestHeaders = new Headers({ Accept: 'application/json' });
      const matricula = currentUser?.username?.trim();
      if (matricula) {
        requestHeaders.set('X-User-Registration', matricula);
      }
      const response = await fetch(buildPlansRequestUrl({ direction }), {
        headers: requestHeaders,
        signal: plansFetchController.signal,
      });
      if (!response.ok) {
        throw new Error('Não foi possível carregar os planos.');
      }
      const payload = await response.json();
      const items = Array.isArray(payload?.items) ? payload.items : [];
      renderPlanRows(items);
      // Occurrences are now fetched independently
      // Update pager state from response
      const paging = payload?.paging || {};
      if (paging && typeof paging === 'object') {
        plansPager.page = Number(paging.page) || plansPager.page;
        plansPager.pageSize = Number(paging.page_size) || plansPager.pageSize;
        plansPager.hasMore = Boolean(paging.has_more);
        plansPager.nextCursor = paging.next_cursor || null;
        plansPager.prevCursor = paging.prev_cursor || null;
        plansPager.showingFrom = Number(paging.showing_from) || (items.length ? 1 : 0);
        plansPager.showingTo = Number(paging.showing_to) || (items.length ? items.length : 0);
        plansPager.totalCount = typeof paging.total_count === 'number' ? paging.total_count : null;
        plansPager.totalPages = typeof paging.total_pages === 'number' ? paging.total_pages : null;
        // When navigating backward, server's has_more may reference the previous direction.
        // Ensure the Next button remains available after going back a page.
        if (direction === 'prev') {
          plansPager.hasMore = true;
        }
      } else {
        // Fallback when server doesn't send paging (legacy path)
        plansPager.page = 1;
        plansPager.pageSize = DEFAULT_PLAN_PAGE_SIZE;
        plansPager.hasMore = false;
        plansPager.nextCursor = null;
        plansPager.prevCursor = null;
        plansPager.showingFrom = items.length ? 1 : 0;
        plansPager.showingTo = items.length;
        plansPager.totalCount = typeof payload?.total === 'number' ? payload.total : null;
        plansPager.totalPages = plansPager.totalCount ? 1 : null;
      }
      updatePlansPagerUI();
      // Occurrences pager updated via refreshOccurrences()
      plansLoaded = true;
    } catch (error) {
      if (error?.name === 'AbortError') {
        return;
      }
      console.error('Erro ao carregar planos.', error);
      if (!plansLoaded) {
        renderPlansPlaceholder('Não foi possível carregar os planos.', 'error');
      }
    } finally {
      plansFetchController = null;
      isFetchingPlans = false;
    }
  };

  const toggleButtons = ({ start, pause, cont }) => {
    btnStart.disabled = !start;
    btnPause.disabled = !pause;
    btnContinue.disabled = !cont;

    btnStart.classList.toggle('btn--disabled', btnStart.disabled);
    btnPause.classList.toggle('btn--disabled', btnPause.disabled);
    btnContinue.classList.toggle('btn--disabled', btnContinue.disabled);

    btnPause.classList.toggle('btn--ghost', true);
    btnContinue.classList.toggle('btn--ghost', true);
  };

  const stopPolling = () => {
    if (pollHandle !== null) {
      window.clearInterval(pollHandle);
      pollHandle = null;
    }
  };

  const setProgressVisibility = (visible) => {
    if (!progressContainer) {
      return;
    }

    progressContainer.classList.toggle('progress--hidden', !visible);
    progressContainer.setAttribute('aria-hidden', visible ? 'false' : 'true');
  };

  const stopProgressTimer = () => {
    if (progressIntervalHandle !== null) {
      window.clearInterval(progressIntervalHandle);
      progressIntervalHandle = null;
    }
  };

  const setProgressWidth = (ratio) => {
    if (!progressBar) {
      return;
    }

    const boundedRatio = Math.max(0, Math.min(ratio, 1));
    progressBar.style.width = `${(boundedRatio * 100).toFixed(2)}%`;
  };

  const tickProgress = () => {
    if (!progressBar || progressStartTimestamp === null) {
      return;
    }

    const elapsed = Math.max(0, Date.now() - progressStartTimestamp);
    const ratio = Math.min(
      elapsed / PROGRESS_TOTAL_DURATION_MS,
      PROGRESS_MAX_RATIO_BEFORE_COMPLETION,
    );
    setProgressWidth(ratio);
  };

  const beginProgressTracking = (startTimestamp) => {
    if (!progressBar) {
      return;
    }

    const normalizedTimestamp =
      typeof startTimestamp === 'number' && !Number.isNaN(startTimestamp)
        ? startTimestamp
        : Date.now();

    progressStartTimestamp = normalizedTimestamp;
    progressBar.classList.remove('progress__bar--complete');
    setProgressVisibility(true);
    tickProgress();
    stopProgressTimer();
    progressIntervalHandle = window.setInterval(tickProgress, 1000);
  };

  const completeProgressTracking = () => {
    if (!progressBar) {
      return;
    }

    setProgressVisibility(true);
    stopProgressTimer();
    progressBar.classList.add('progress__bar--complete');
    setProgressWidth(1);
  };

  const resetProgress = () => {
    stopProgressTimer();
    progressStartTimestamp = null;

    if (progressBar) {
      progressBar.classList.remove('progress__bar--complete');
      setProgressWidth(0);
    }

    setProgressVisibility(false);
  };

  const parseTimestamp = (value) => {
    if (!value) {
      return null;
    }

    if (value instanceof Date) {
      return value.getTime();
    }

    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }

    if (typeof value === 'string') {
      const timestamp = Date.parse(value);
      return Number.isNaN(timestamp) ? null : timestamp;
    }

    return null;
  };

  const updateProgressFromState = (state) => {
    if (!progressContainer || !progressBar) {
      return;
    }

    const status = state.status;
    const startedTimestamp = parseTimestamp(state.started_at);

    if (status === 'running') {
      const effectiveStart =
        startedTimestamp ?? progressStartTimestamp ?? Date.now();
      beginProgressTracking(effectiveStart);
      return;
    }

    if (status === 'succeeded') {
      if (startedTimestamp && progressStartTimestamp === null) {
        progressStartTimestamp = startedTimestamp;
      }
      completeProgressTracking();
      return;
    }

    resetProgress();
  };

  if (progressContainer && progressBar) {
    resetProgress();
  }

  const defaultMessages = {
    idle: 'Ocioso',
    running: 'Executando',
    succeeded: 'Concluída',
    failed: 'Falha',
  };

  const formatDocument = (value) => {
    if (window.SirepUtils?.formatDocument) {
      return window.SirepUtils.formatDocument(value);
    }
    return String(value ?? '');
  };

  const stripDigits = (value) => {
    if (typeof value !== 'string') {
      return '';
    }
    return value.replace(/\D+/g, '');
  };

  const tableSearchForm = document.getElementById('tableSearchForm');
  const tableSearchInput = document.getElementById('tableSearchInput');
  const SEARCH_DEBOUNCE_MS = 350;
  let searchDebounceHandle = null;

  const syncSearchInputValue = (target) => {
    if (!target || !tableSearchInput) {
      return;
    }
    const value = tableSearchState[target] ?? '';
    if (tableSearchInput.value !== value) {
      tableSearchInput.value = value;
    }
  };

  const setActiveSearchTarget = (target) => {
    if (!target) {
      return;
    }
    activeTableSearchTarget = target;
    if (tableSearchForm) {
      tableSearchForm.dataset.activeTable = target;
    }
    if (tableSearchInput) {
      const controlsTarget =
        target === 'occurrences' ? 'occurrencesTablePanel' : 'plansTablePanel';
      tableSearchInput.setAttribute('aria-controls', controlsTarget);
    }
  };

  let scheduleOccurrencesCountUpdate = () => {};

  const resolveTableSearchIntent = (term) => {
    const normalized = (term || '').trim();
    if (!normalized) {
      return {
        normalized,
        digits: '',
        intent: 'none',
      };
    }

    const digits = stripDigits(normalized);
    const isDigitsOnly = /^\d+$/.test(normalized);

    if ([11, 12, 14].includes(digits.length)) {
      return {
        normalized,
        digits,
        intent: 'document',
      };
    }

    if (isDigitsOnly) {
      return {
        normalized,
        digits: normalized,
        intent: 'plan-number',
      };
    }

    return {
      normalized,
      digits,
      intent: 'text',
    };
  };

  const applyOccurrencesFilter = (term) => {
    const occurrencesPanel = document.getElementById('occurrencesTablePanel');
    if (!occurrencesPanel) {
      return;
    }

    const tbody = occurrencesPanel.querySelector('tbody');
    if (!tbody) {
      return;
    }

    const { normalized, digits, intent } = resolveTableSearchIntent(term);
    const normalizedLower = normalized.toLowerCase();

    const rows = Array.from(tbody.rows ?? []);
    let visibleRows = 0;

    rows.forEach((row) => {
      if (!row || row.classList.contains('table__row--empty')) {
        return;
      }

      const planCell = row.cells?.[0];
      const documentCell = row.cells?.[1];
      const nameCell = row.cells?.[2];

      const planDigits = stripDigits(planCell?.textContent ?? '');
      const documentDigits = stripDigits(documentCell?.textContent ?? '');
      const nameText = (nameCell?.textContent ?? '').toLowerCase();

      let matches = true;
      if (normalized) {
        if (intent === 'document') {
          matches = documentDigits === digits;
        } else if (intent === 'plan-number') {
          matches = planDigits.startsWith(digits);
        } else if (intent === 'text') {
          matches = nameText.includes(normalizedLower);
        }
      }

      row.hidden = !matches;
      if (matches) {
        visibleRows += 1;
      }
    });

    const placeholderRow = rows.find((row) => row.classList.contains('table__row--empty'));
    if (placeholderRow) {
      const placeholderCell = placeholderRow.cells?.[0];
      if (placeholderCell) {
        placeholderCell.textContent =
          visibleRows > 0 || !normalized
            ? 'nenhuma ocorrência por aqui.'
            : 'nenhuma ocorrência encontrada para a busca.';
      }
      placeholderRow.hidden = visibleRows > 0;
    }

    scheduleOccurrencesCountUpdate();
  };

  const handleOccurrencesSearch = (term, { forceRefresh = false } = {}) => {
    const normalized = (term || '').trim();
    if (!forceRefresh && normalized === currentOccurrencesSearchTerm) {
      return;
    }
    currentOccurrencesSearchTerm = normalized;
    tableSearchState.occurrences = normalized;
    // Reset pager when the search changes
    occPager.page = 1;
    occPager.nextCursor = null;
    occPager.prevCursor = null;
    void refreshOccurrences({ showLoading: true });
  };

  const handlePlansSearch = (term, { forceRefresh = false } = {}) => {
    const normalized = (term || '').trim();
    if (!forceRefresh && normalized === currentPlansSearchTerm) {
      return;
    }
    currentPlansSearchTerm = normalized;
    tableSearchState.plans = normalized;
    // Reset pager when the search changes
    plansPager.page = 1;
    plansPager.nextCursor = null;
    plansPager.prevCursor = null;
    void refreshPlans({ showLoading: true });
  };

  if (tableSearchForm) {
    tableSearchForm.addEventListener('submit', (event) => {
      event.preventDefault();
      if (searchDebounceHandle !== null) {
        window.clearTimeout(searchDebounceHandle);
        searchDebounceHandle = null;
      }
      const value = tableSearchInput?.value ?? '';
      if (activeTableSearchTarget === 'occurrences') {
        handleOccurrencesSearch(value);
      } else {
        // On submit, start from first page
        plansPager.page = 1;
        plansPager.nextCursor = null;
        plansPager.prevCursor = null;
        handlePlansSearch(value, { forceRefresh: true });
      }
    });
  }

  if (tableSearchInput) {
    tableSearchInput.addEventListener('input', (event) => {
      const value = event.target?.value ?? '';
      tableSearchState[activeTableSearchTarget] = value;
      if (searchDebounceHandle !== null) {
        window.clearTimeout(searchDebounceHandle);
      }
      searchDebounceHandle = window.setTimeout(() => {
        searchDebounceHandle = null;
        if (activeTableSearchTarget === 'occurrences') {
          handleOccurrencesSearch(value);
          return;
        }
        if (value.trim()) {
          handlePlansSearch(value);
        } else if (currentPlansSearchTerm) {
          // Clear search resets pager and reloads first page
          plansPager.page = 1;
          plansPager.nextCursor = null;
          plansPager.prevCursor = null;
          handlePlansSearch('', { forceRefresh: true });
        }
        if (!value.trim() && currentOccurrencesSearchTerm) {
          handleOccurrencesSearch('', { forceRefresh: true });
        }
      }, SEARCH_DEBOUNCE_MS);
    });
  }

  // Pager buttons behavior
  if (plansPagerPrevBtn) {
    plansPagerPrevBtn.addEventListener('click', () => {
      if (plansPager.page <= 1) {
        return;
      }
      plansPager.page = Math.max(1, plansPager.page - 1);
      void refreshPlans({ showLoading: true, direction: 'prev' });
    });
  }
  if (plansPagerNextBtn) {
    plansPagerNextBtn.addEventListener('click', () => {
      if (!plansPager.hasMore) {
        return;
      }
      plansPager.page = plansPager.page + 1;
      void refreshPlans({ showLoading: true, direction: 'next' });
    });
  }

  if (occPagerPrevBtn) {
    occPagerPrevBtn.addEventListener('click', () => {
      if (occPager.page <= 1) {
        return;
      }
      occPager.page = Math.max(1, occPager.page - 1);
      void refreshOccurrences({ showLoading: true, direction: 'prev' });
    });
  }
  if (occPagerNextBtn) {
    occPagerNextBtn.addEventListener('click', () => {
      if (!occPager.hasMore) {
        return;
      }
      occPager.page = occPager.page + 1;
      void refreshOccurrences({ showLoading: true, direction: 'next' });
    });
  }

  const buildOccurrencesRequestUrl = ({ direction = null } = {}) => {
    const baseUrl =
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : window.location.href;
    const url = new URL(PLANS_ENDPOINT, baseUrl);
    url.searchParams.set('occurrences_only', 'true');
    url.searchParams.set('page', String(occPager.page));
    url.searchParams.set('page_size', String(occPager.pageSize));
    if (direction === 'next' && occPager.nextCursor) {
      url.searchParams.set('cursor', occPager.nextCursor);
      url.searchParams.set('direction', 'next');
    } else if (direction === 'prev' && occPager.prevCursor) {
      url.searchParams.set('cursor', occPager.prevCursor);
      url.searchParams.set('direction', 'prev');
    }
    if (currentOccurrencesSearchTerm) {
      url.searchParams.set('q', currentOccurrencesSearchTerm);
    }
    return url.toString();
  };

  const refreshOccurrences = async ({ showLoading, direction = null } = {}) => {
    if (!occTableBody || isFetchingOccurrences) {
      return;
    }
    const shouldShowLoading = showLoading ?? !occurrencesLoaded;
    if (shouldShowLoading) {
      renderOccurrencesPlaceholder('carregando ocorrências...', 'loading');
    }

    isFetchingOccurrences = true;
    try {
      if (occFetchController) {
        occFetchController.abort();
      }
      occFetchController = new AbortController();
      const requestHeaders = new Headers({ Accept: 'application/json' });
      const matricula = currentUser?.username?.trim();
      if (matricula) {
        requestHeaders.set('X-User-Registration', matricula);
      }
      const response = await fetch(buildOccurrencesRequestUrl({ direction }), {
        headers: requestHeaders,
        signal: occFetchController.signal,
      });
      if (!response.ok) {
        throw new Error('Não foi possível carregar as ocorrências.');
      }
      const payload = await response.json();
      const items = Array.isArray(payload?.items) ? payload.items : [];
      renderOccurrenceRows(items);

      const paging = payload?.paging || {};
      if (paging && typeof paging === 'object') {
        occPager.page = Number(paging.page) || occPager.page;
        occPager.pageSize = Number(paging.page_size) || occPager.pageSize;
        occPager.hasMore = Boolean(paging.has_more);
        occPager.nextCursor = paging.next_cursor || null;
        occPager.prevCursor = paging.prev_cursor || null;
        occPager.showingFrom = Number(paging.showing_from) || (items.length ? 1 : 0);
        occPager.showingTo = Number(paging.showing_to) || (items.length ? items.length : 0);
        occPager.totalCount = typeof paging.total_count === 'number' ? paging.total_count : null;
        occPager.totalPages = typeof paging.total_pages === 'number' ? paging.total_pages : null;
        if (direction === 'prev') {
          occPager.hasMore = true;
        }
      } else {
        occPager.page = 1;
        occPager.pageSize = DEFAULT_PLAN_PAGE_SIZE;
        occPager.hasMore = false;
        occPager.nextCursor = null;
        occPager.prevCursor = null;
        occPager.showingFrom = items.length ? 1 : 0;
        occPager.showingTo = items.length;
        occPager.totalCount = typeof payload?.total === 'number' ? payload.total : null;
        occPager.totalPages = occPager.totalCount ? 1 : null;
      }
      updateOccPagerUI();

      // Update occurrences badge with total count (not visible rows)
      const countElement = document.getElementById('occurrencesCount');
      if (countElement) {
        const total = typeof occPager.totalCount === 'number' ? occPager.totalCount : items.length;
        countElement.textContent = `(${total})`;
        countElement.classList.toggle('section-switch__count--alert', total > 0);
      }

      occurrencesLoaded = true;
    } catch (error) {
      if (error?.name === 'AbortError') {
        return;
      }
      console.error('Erro ao carregar ocorrências.', error);
      if (!occurrencesLoaded) {
        renderOccurrencesPlaceholder('Não foi possível carregar as ocorrências.', 'error');
      }
    } finally {
      occFetchController = null;
      isFetchingOccurrences = false;
    }
  };

  const setupOccurrencesSearchObserver = () => {
    const occurrencesPanel = document.getElementById('occurrencesTablePanel');
    if (!occurrencesPanel) {
      return;
    }

    // Server-side filtering handles occurrences; no client observer needed.
    const observer = new MutationObserver(() => {});

    observer.observe(occurrencesPanel, {
      childList: true,
      subtree: true,
    });
  };

  const tooltipTimeouts = new WeakMap();

  const showCopyTooltip = (button) => {
    if (!button) {
      return;
    }

    const previousTimeout = tooltipTimeouts.get(button);
    if (typeof previousTimeout === 'number') {
      window.clearTimeout(previousTimeout);
    }

    button.setAttribute('data-tooltip-visible', 'true');

    const timeoutHandle = window.setTimeout(() => {
      button.removeAttribute('data-tooltip-visible');
      tooltipTimeouts.delete(button);
    }, 1500);

    tooltipTimeouts.set(button, timeoutHandle);
  };

  const copyToClipboard = async (value) => {
    if (!value) {
      return false;
    }

    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
        return true;
      }
    } catch (error) {
      console.warn('Falha ao copiar usando clipboard API.', error);
    }

    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', 'true');
    textarea.style.position = 'absolute';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();

    try {
      const success = document.execCommand('copy');
      return success;
    } catch (error) {
      console.error('Não foi possível copiar o valor.', error);
      return false;
    } finally {
      document.body.removeChild(textarea);
    }
  };

  const enhanceCopyableCell = (cell, { label }) => {
    if (!cell) {
      return;
    }

    const existingButton = cell.querySelector('.table__copy-trigger');
    const target = existingButton ?? cell;
    const currentText = target.textContent?.trim() ?? '';
    if (!currentText) {
      return;
    }

    const digits = stripDigits(currentText);
    if (!digits) {
      return;
    }

    const ariaLabel = `${label} ${digits}. Clique para copiar.`;

    if (!existingButton) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'table__copy-trigger';
      button.dataset.copyValue = digits;
      button.dataset.tooltip = 'Item copiado';
      button.setAttribute('aria-label', ariaLabel);
      button.textContent = currentText;

      cell.classList.add('table__cell--copyable');
      cell.textContent = '';
      cell.appendChild(button);
      return;
    }

    existingButton.dataset.copyValue = digits;
    existingButton.setAttribute('aria-label', ariaLabel);
    if (!existingButton.dataset.tooltip) {
      existingButton.dataset.tooltip = 'Item copiado';
    }
    if (existingButton.textContent !== currentText) {
      existingButton.textContent = currentText;
    }
  };

  const setupCopyableCells = () => {
    const tables = document.querySelectorAll('.data-table');
    if (!tables.length) {
      return;
    }

    const processRow = (row) => {
      if (!row || row.classList.contains('table__row--empty')) {
        return;
      }

      const planCell = row.cells?.[0];
      const documentCell = row.cells?.[1];

      if (planCell) {
        enhanceCopyableCell(planCell, { label: 'Copiar número do plano' });
      }
      if (documentCell) {
        enhanceCopyableCell(documentCell, { label: 'Copiar CNPJ' });
      }
    };

    tables.forEach((table) => {
      const tbody = table.tBodies?.[0];
      if (!tbody) {
        return;
      }

      Array.from(tbody.rows).forEach(processRow);

      const observer = new MutationObserver(() => {
        Array.from(tbody.rows).forEach(processRow);
      });

      observer.observe(tbody, {
        childList: true,
        subtree: true,
        characterData: true,
      });

      tbody.addEventListener('click', async (event) => {
        const targetElement = event.target;
        if (!(targetElement instanceof Element)) {
          return;
        }

        const button = targetElement.closest('.table__copy-trigger');
        if (!button) {
          return;
        }

        event.preventDefault();
        const value = button.dataset.copyValue ?? '';
        const success = await copyToClipboard(value);
        if (success) {
          showCopyTooltip(button);
        }
      });
    });
  };

  const applyDocumentFormatting = (row) => {
    if (!row || row.classList.contains('table__row--empty')) {
      return;
    }

    const documentCell = row.cells?.[1];
    if (!documentCell) {
      return;
    }

    const target = documentCell.querySelector('.table__copy-trigger') ?? documentCell;
    const current = target.textContent ?? '';
    const formatted = formatDocument(current);
    if (formatted && current.trim() !== formatted) {
      target.textContent = formatted;
    }

    if (target.classList.contains('table__copy-trigger')) {
      target.dataset.copyValue = stripDigits(target.textContent ?? '');
    }
  };

  const setupDocumentObserver = () => {
    const tables = document.querySelectorAll('.data-table');
    if (!tables.length) {
      return;
    }

    tables.forEach((table) => {
      const tbody = table.tBodies?.[0];
      if (!tbody) {
        return;
      }

      const formatAllRows = () => {
        Array.from(tbody.rows).forEach((row) => applyDocumentFormatting(row));
      };

      formatAllRows();

      const observer = new MutationObserver(() => {
        formatAllRows();
      });

      observer.observe(tbody, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    });
  };

  const setupOccurrencesCounter = () => {
    const countElement = document.getElementById('occurrencesCount');
    const occurrencesPanel = document.getElementById('occurrencesTablePanel');

    if (!countElement || !occurrencesPanel) {
      scheduleOccurrencesCountUpdate = () => {};
      return;
    }

    const updateCount = () => {
      const total = typeof occPager.totalCount === 'number' ? occPager.totalCount : 0;
      countElement.textContent = `(${total})`;
      countElement.classList.toggle('section-switch__count--alert', total > 0);
    };

    let pendingHandle = null;
    const supportsAnimationFrame = typeof window.requestAnimationFrame === 'function';

    const runPendingUpdate = () => {
      pendingHandle = null;
      updateCount();
    };

    const cancelScheduledUpdate = () => {
      if (pendingHandle === null) {
        return;
      }

      if (supportsAnimationFrame) {
        window.cancelAnimationFrame(pendingHandle);
      } else {
        window.clearTimeout(pendingHandle);
      }

      pendingHandle = null;
    };

    scheduleOccurrencesCountUpdate = () => {
      if (pendingHandle !== null) {
        return;
      }

      if (supportsAnimationFrame) {
        pendingHandle = window.requestAnimationFrame(runPendingUpdate);
        return;
      }

      pendingHandle = window.setTimeout(runPendingUpdate, 0);
    };

    const forceUpdateCount = () => {
      cancelScheduledUpdate();
      updateCount();
    };

    forceUpdateCount();

    // No observers needed: the total comes from the API via occPager
  };

  const setupTableSwitching = () => {
    const tabs = Array.from(document.querySelectorAll('[data-table-target]'));
    const panels = Array.from(document.querySelectorAll('[data-table-panel]'));

    if (!tabs.length || !panels.length) {
      return;
    }

    const activateTable = (target) => {
      if (!target) {
        return;
      }

      tabs.forEach((tab) => {
        const isActive = tab.dataset.tableTarget === target;
        tab.classList.toggle('section-switch--active', isActive);
        tab.setAttribute('aria-selected', String(isActive));
        tab.setAttribute('tabindex', isActive ? '0' : '-1');
      });

      panels.forEach((panel) => {
        const isActive = panel.dataset.tablePanel === target;
        panel.classList.toggle('table-panel--hidden', !isActive);
        if (isActive) {
          panel.removeAttribute('hidden');
        } else {
          panel.setAttribute('hidden', 'hidden');
        }
      });

      setActiveSearchTarget(target);
      syncSearchInputValue(target);
      if (target === 'occurrences' && !occurrencesLoaded) {
        void refreshOccurrences({ showLoading: true });
      }
    };

    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => {
        activateTable(tab.dataset.tableTarget);
      });

      tab.addEventListener('keydown', (event) => {
        if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
          event.preventDefault();
          const direction = event.key === 'ArrowRight' ? 1 : -1;
          const nextIndex = (index + direction + tabs.length) % tabs.length;
          const nextTab = tabs[nextIndex];
          activateTable(nextTab.dataset.tableTarget);
          nextTab.focus();
        }
      });
    });

    const activeTab = tabs.find((tab) => tab.classList.contains('section-switch--active'));
    const initialTarget = activeTab?.dataset.tableTarget || tabs[0].dataset.tableTarget;
    activateTable(initialTarget);
  };

  toggleButtons({ start: true, pause: false, cont: false });
  setStatus(defaultMessages.idle);
  void refreshPlans();
  void refreshOccurrences();

  const schedulePolling = () => {
    stopPolling();
    pollHandle = window.setInterval(async () => {
      const state = await fetchPipelineState();
      if (state) {
        applyState(state);
        // also refresh pipeline meta while running
        await refreshPipelineMeta();
        if (state.status !== 'running') {
          stopPolling();
        }
      }
    }, 5000);
  };

  const applyState = (state) => {
    const message = state.message || defaultMessages[state.status] || defaultMessages.idle;
    updateProgressFromState(state);
    updateLastUpdateInfo(state);
    switch (state.status) {
      case 'running':
        toggleButtons({ start: false, pause: true, cont: false });
        shouldRefreshPlansAfterRun = true;
        break;
      case 'succeeded':
      case 'failed':
      case 'idle':
      default:
        toggleButtons({ start: true, pause: false, cont: false });
        if (shouldRefreshPlansAfterRun) {
          shouldRefreshPlansAfterRun = false;
          void refreshPlans({ showLoading: false });
          void refreshOccurrences({ showLoading: false });
        }
        break;
    }
    setStatus(message);
  };

  const fetchPipelineState = async () => {
    try {
      const response = await fetch(`${PIPELINE_ENDPOINT}/state`, { headers: { 'Accept': 'application/json' } });
      if (!response.ok) {
        throw new Error('Não foi possível consultar o estado da pipeline.');
      }
      return await response.json();
    } catch (error) {
      console.error(error);
      return null;
    }
  };

  const startPipeline = async () => {
    toggleButtons({ start: false, pause: false, cont: false });
    setStatus('Iniciando...');

    try {
      const payload = {};
      if (currentUser?.username) {
        payload.matricula = currentUser.username;
      }
      if (window.Auth?.getPassword) {
        const senha = Auth.getPassword();
        if (senha) {
          payload.senha = senha;
        }
      }

      const response = await fetch(`${PIPELINE_ENDPOINT}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({ detail: 'Erro desconhecido.' }));
        throw new Error(payload.detail || 'Não foi possível iniciar a pipeline.');
      }

      const state = await response.json();
      applyState(state);
      void refreshPipelineMeta();
      if (state.status === 'running') {
        schedulePolling();
      }
    } catch (error) {
      console.error(error);
      setStatus(`Erro: ${error.message}`);
      toggleButtons({ start: true, pause: false, cont: false });
      resetProgress();
    }
  };

  btnStart.addEventListener('click', () => {
    startPipeline();
  });

  btnPause.addEventListener('click', () => {
    toggleButtons({ start: false, pause: false, cont: true });
    setStatus('Pausado');
  });

  btnContinue.addEventListener('click', () => {
    toggleButtons({ start: false, pause: true, cont: false });
    setStatus('Executando');
  });

  (async () => {
    void refreshPipelineMeta();
    const state = await fetchPipelineState();
    if (state) {
      applyState(state);
      if (state.status === 'running') {
        schedulePolling();
      }
    } else {
      toggleButtons({ start: true, pause: false, cont: false });
      setStatus(defaultMessages.idle);
    }
  })();

  document.addEventListener('visibilitychange', async () => {
    if (document.hidden) {
      stopPolling();
      return;
    }
    // On resume, refetch state and meta
    const state = await fetchPipelineState();
    if (state) {
      applyState(state);
      await refreshPipelineMeta();
      if (state.status === 'running') {
        schedulePolling();
      }
    }
  });

  const disableCalendarButton = (button) => {
    if (!button) {
      return;
    }
    button.disabled = true;
    button.setAttribute('aria-disabled', 'true');
    if (!button.title) {
      button.title = 'Calendário indisponível';
    }
  };

  const enableManualDateInput = (input) => {
    if (!input) {
      return;
    }
    input.readOnly = false;
    const manualHint = 'digite a data manualmente';
    const label = input.getAttribute('aria-label');
    if (label && !label.toLowerCase().includes(manualHint)) {
      input.setAttribute('aria-label', `${label} (digite a data manualmente)`);
    }
    if (!input.title) {
      input.title = 'Digite a data no formato dd/mm/aaaa';
    }
  };

  const fallbackDateInput = (input, button) => {
    enableManualDateInput(input);
    disableCalendarButton(button);
  };

  const registerPickerTriggers = (picker, input, button) => {
    if (!picker) {
      return;
    }

    const open = () => picker.open();
    if (input) {
      input.addEventListener('click', open);
    }
    if (button) {
      button.addEventListener('click', open);
    }
  };

  const initializeDatePicker = (input, button, options) => {
    if (!input) {
      disableCalendarButton(button);
      return null;
    }

    try {
      const picker = window.flatpickr(input, options);
      registerPickerTriggers(picker, input, button);
      return picker;
    } catch (error) {
      console.error('Não foi possível inicializar o calendário de data.', error);
      return null;
    }
  };

  const initializeDatePickers = () => {
    if (!dateFromInput && !dateToInput) {
      return;
    }

    if (typeof window.flatpickr !== 'function') {
      console.warn('flatpickr indisponível; habilitando entrada manual de datas.');
      fallbackDateInput(dateFromInput, openDateFromButton);
      fallbackDateInput(dateToInput, openDateToButton);
      return;
    }

    const options = {
      locale: window.flatpickr.l10ns?.pt ?? undefined,
      dateFormat: 'd/m/Y',
      allowInput: false,
    };

    const fromPicker = initializeDatePicker(dateFromInput, openDateFromButton, options);
    const toPicker = initializeDatePicker(dateToInput, openDateToButton, options);

    if (!fromPicker) {
      fallbackDateInput(dateFromInput, openDateFromButton);
    }
    if (!toPicker) {
      fallbackDateInput(dateToInput, openDateToButton);
    }
  };

  initializeDatePickers();

  const logsToggle = document.getElementById('logsToggle');
  const logsPanel = document.getElementById('logsPanel');
  const accordion = logsToggle.closest('.accordion');

  const updateAccordionState = (isOpen) => {
    logsToggle.setAttribute('aria-expanded', String(isOpen));
    if (isOpen) {
      logsPanel.classList.add('is-open');
      accordion.classList.add('is-open');
    } else {
      logsPanel.classList.remove('is-open');
      accordion.classList.remove('is-open');
    }
  };

  logsToggle.addEventListener('click', () => {
    const isOpen = logsToggle.getAttribute('aria-expanded') === 'true';
    updateAccordionState(!isOpen);
  });

  logsToggle.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      const isOpen = logsToggle.getAttribute('aria-expanded') === 'true';
      updateAccordionState(!isOpen);
    }
  });

  updateAccordionState(false);
  setupCopyableCells();
  setupDocumentObserver();
  setupOccurrencesSearchObserver();
  setupOccurrencesCounter();
  setupTableSwitching();
});
