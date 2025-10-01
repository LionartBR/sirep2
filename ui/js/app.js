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

  const PIPELINE_ENDPOINT = '/api/pipeline';
  const PLANS_ENDPOINT = '/api/plans';
  const DEFAULT_PLAN_PAGE_SIZE = 50;
  const tableSearchState = {
    plans: '',
    occurrences: '',
  };
  if (lastUpdateLabel) {
    lastUpdateLabel.textContent = 'última atualização em —';
  }
  let currentPlansSearchTerm = '';
  let currentOccurrencesSearchTerm = '';
  let activeTableSearchTarget = 'plans';
  let plansFetchController = null;
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
  let isFetchingPlans = false;
  let plansLoaded = false;
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

  const updateLastUpdateInfo = (state) => {
    if (!lastUpdateLabel) {
      return;
    }
    if (state?.status === 'succeeded' && state?.finished_at) {
      lastSuccessfulFinishedAt = state.finished_at;
    }
    const timestamp = lastSuccessfulFinishedAt ?? null;
    const formatted = formatDateTimeLabel(timestamp);
    lastUpdateLabel.textContent = `última atualização em ${formatted}`;
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

  const buildPlansRequestUrl = () => {
    const baseUrl =
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : window.location.href;
    const url = new URL(PLANS_ENDPOINT, baseUrl);
    url.searchParams.set('limit', String(DEFAULT_PLAN_PAGE_SIZE));
    url.searchParams.set('offset', '0');
    if (currentPlansSearchTerm) {
      url.searchParams.set('q', currentPlansSearchTerm);
    }
    return url.toString();
  };

  const refreshPlans = async ({ showLoading } = {}) => {
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
      const response = await fetch(buildPlansRequestUrl(), {
        headers: requestHeaders,
        signal: plansFetchController.signal,
      });
      if (!response.ok) {
        throw new Error('Não foi possível carregar os planos.');
      }
      const payload = await response.json();
      const items = Array.isArray(payload?.items) ? payload.items : [];
      renderPlanRows(items);
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

  const handleOccurrencesSearch = (term) => {
    const normalized = (term || '').trim();
    currentOccurrencesSearchTerm = normalized;
    tableSearchState.occurrences = normalized;
    applyOccurrencesFilter(normalized);
  };

  const handlePlansSearch = (term, { forceRefresh = false } = {}) => {
    const normalized = (term || '').trim();
    if (!forceRefresh && normalized === currentPlansSearchTerm) {
      return;
    }
    currentPlansSearchTerm = normalized;
    tableSearchState.plans = normalized;
    void refreshPlans({ showLoading: true });
  };

  if (tableSearchForm) {
    tableSearchForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const value = tableSearchInput?.value ?? '';
      if (activeTableSearchTarget === 'occurrences') {
        handleOccurrencesSearch(value);
      } else {
        handlePlansSearch(value, { forceRefresh: true });
      }
    });
  }

  if (tableSearchInput) {
    tableSearchInput.addEventListener('input', (event) => {
      const value = event.target?.value ?? '';
      tableSearchState[activeTableSearchTarget] = value;
      if (activeTableSearchTarget === 'occurrences') {
        handleOccurrencesSearch(value);
        return;
      }
      if (!value.trim() && currentPlansSearchTerm) {
        handlePlansSearch('', { forceRefresh: true });
      }
    });
  }

  const setupOccurrencesSearchObserver = () => {
    const occurrencesPanel = document.getElementById('occurrencesTablePanel');
    if (!occurrencesPanel) {
      return;
    }

    const observer = new MutationObserver(() => {
      if (currentOccurrencesSearchTerm) {
        applyOccurrencesFilter(currentOccurrencesSearchTerm);
      }
    });

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
      const tbody = occurrencesPanel.querySelector('tbody');
      const rows = tbody ? Array.from(tbody.rows ?? []) : [];
      const total = rows.filter((row) => {
        if (row.classList.contains('table__row--empty')) {
          return false;
        }
        if (row.hasAttribute('hidden')) {
          return false;
        }
        return true;
      }).length;

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

    const observer = new MutationObserver(() => {
      scheduleOccurrencesCountUpdate();
    });
    observer.observe(occurrencesPanel, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'hidden'],
    });
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
      if (target === 'occurrences') {
        applyOccurrencesFilter(currentOccurrencesSearchTerm);
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

  const schedulePolling = () => {
    stopPolling();
    pollHandle = window.setInterval(async () => {
      const state = await fetchPipelineState();
      if (state) {
        applyState(state);
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
