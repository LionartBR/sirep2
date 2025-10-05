/* global flatpickr */
import { createAppContext } from './app/context.js';
import { registerHelperModule } from './app/helpers.js';
import { registerProfileModule } from './app/profile.js';

document.addEventListener('DOMContentLoaded', () => {
  if (!window.Auth || !Auth.isAuthenticated()) {
    window.location.replace('/app/login.html');
    return;
  }

  if (window.feather) {
    window.feather.replace();
  }

  const context = createAppContext();

  context.formatDocument = (value) => {
    if (window.SirepUtils?.formatDocument) {
      return window.SirepUtils.formatDocument(value);
    }
    return String(value ?? '');
  };

  registerHelperModule(context);
  registerProfileModule(context);

  context.updateUserName();
  context.setupSignOut();

  const state = context;

  const {
    currentUser,
    statusText,
    btnStart,
    btnPause,
    btnContinue,
    btnCloseTreatment,
    progressContainer,
    progressBar,
    runningPlanNumberEl,
    runningPlanDocumentEl,
    runningPlanCompanyEl,
    runningPlanStatusEl,
    runningPlanStageEl,
    lblLastUpdate,
    lblLastDuration,
    dateFromInput,
    dateToInput,
    openDateFromButton,
    openDateToButton,
    plansTablePanel,
    plansTableElement,
    plansTableBody,
    plansColumnCount,
    plansActionsMenuContainer,
    plansActionsTrigger,
    plansActionsMenu,
    plansSelectAllAction,
    plansSelectAllLabel,
    plansActionsSeparator,
    plansFiltersChipsContainer,
    occFiltersChipsContainer,
    occTablePanel,
    occTableElement,
    occTableBody,
    occColumnCount,
    treatmentPanelEl,
    treatmentTableElement,
    treatmentTableBody,
    treatmentColumnCount,
    treatmentPagerRange,
    treatmentPagerLabel,
    treatmentPagerPrevBtn,
    treatmentPagerNextBtn,
    plansPagerPrevBtn,
    plansPagerNextBtn,
    plansPagerLabel,
    plansPagerRange,
    occPagerPrevBtn,
    occPagerNextBtn,
    occPagerLabel,
    occPagerRange,
    kpiQueueEl,
    kpiRescindedEl,
    kpiFailuresEl,
    PIPELINE_ENDPOINT,
    PLANS_ENDPOINT,
    TREATMENT_ENDPOINT,
    PROFILE_ENDPOINT,
    DEFAULT_PLAN_PAGE_SIZE,
    TREATMENT_GRID,
    FILTER_LABELS,
    plansSelection,
    filtersState,
    tableSearchState,
    currencyFormatter,
    PROGRESS_TOTAL_DURATION_MS,
    PROGRESS_MAX_RATIO_BEFORE_COMPLETION,
  } = context;

  const {
    setStatus,
    formatStatusLabel,
    formatDaysValue,
    formatCurrencyValue,
    formatDateLabel,
    formatDurationLabel,
    formatDateTimeLabel,
    formatDateTime,
    setElementText,
    resolveRunningPlanFromState,
    updateRunningPlanInfo,
    pad2,
    formatDurationText,
    setText,
    showPermissionDeniedToast,
    refreshProfileFromStore,
    applyProfilePermissions,
    refreshUserProfile,
    canAccessBase,
  } = context;

  const refreshPipelineMeta = async () => {
    if (!canAccessBase()) {
      setText(lblLastUpdate, '', null);
      setText(lblLastDuration, '', null);
      return null;
    }
    if (state.isFetchingPipelineMeta) {
      return null;
    }
    state.isFetchingPipelineMeta = true;
    try {
      if (state.pipelineMetaController) {
        state.pipelineMetaController.abort();
      }
      state.pipelineMetaController = new AbortController();
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
        signal: state.pipelineMetaController.signal,
      });
      if (!response.ok) {
        throw new Error('Não foi possível consultar o status da pipeline.');
      }
      const payload = await response.json();
      const lastUpdateAt = payload?.last_update_at ?? null;
      const durationText = payload?.duration_text ?? null;
      const formattedDuration = formatDurationLabel(durationText);
      setText(lblLastUpdate, '', formatDateTime(lastUpdateAt));
      setText(lblLastDuration, '', formattedDuration);
      return payload;
    } catch (error) {
      console.error('Falha ao carregar metadados da pipeline.', error);
      setText(lblLastUpdate, '', null);
      setText(lblLastDuration, '', null);
      return null;
    } finally {
      state.pipelineMetaController = null;
      state.isFetchingPipelineMeta = false;
    }
  };

  const hasActiveFilters = () =>
    filtersState.situacao.length > 0 ||
    filtersState.diasMin !== null ||
    filtersState.saldoMin !== null ||
    Boolean(filtersState.dtRange);

  const resetFiltersState = () => {
    filtersState.situacao = [];
    filtersState.diasMin = null;
    filtersState.saldoMin = null;
    filtersState.dtRange = null;
  };

  const planCheckboxSelector = "input[type='checkbox'][data-plan-checkbox]";

  const getFirstVisiblePlansAction = () => {
    if (!plansActionsMenu) {
      return null;
    }
    const items = plansActionsMenu.querySelectorAll('.table-actions-menu__item');
    for (const item of items) {
      if (!(item instanceof HTMLElement)) {
        continue;
      }
      if (!item.hidden && !item.disabled) {
        return item;
      }
    }
    return null;
  };

  const updatePlansActionsMenuState = () => {
    if (!plansActionsMenu) {
      return;
    }
    const checkboxSelector = planCheckboxSelector;
    const totalEnabledCheckboxes = plansTableBody
      ? plansTableBody.querySelectorAll(`${checkboxSelector}:not(:disabled)`).length
      : 0;
    const checkedEnabledCheckboxes = plansTableBody
      ? plansTableBody.querySelectorAll(`${checkboxSelector}:checked:not(:disabled)`).length
      : 0;
    const hasSelection = plansSelection.size > 0 || checkedEnabledCheckboxes > 0;
    const allSelected =
      totalEnabledCheckboxes > 0 && checkedEnabledCheckboxes === totalEnabledCheckboxes;

    const requiresSelectionItems = plansActionsMenu.querySelectorAll('[data-requires-selection]');
    requiresSelectionItems.forEach((node) => {
      if (!(node instanceof HTMLElement)) {
        return;
      }
      if (hasSelection) {
        node.hidden = false;
        node.removeAttribute('aria-hidden');
      } else {
        node.hidden = true;
        node.setAttribute('aria-hidden', 'true');
      }
    });

    if (plansActionsSeparator instanceof HTMLElement) {
      if (hasSelection) {
        plansActionsSeparator.removeAttribute('hidden');
      } else {
        plansActionsSeparator.setAttribute('hidden', 'hidden');
      }
    }

    if (plansSelectAllAction instanceof HTMLElement) {
      const isDisabled = totalEnabledCheckboxes === 0;
      plansSelectAllAction.disabled = isDisabled;
      plansSelectAllAction.setAttribute('aria-disabled', String(isDisabled));
      plansSelectAllAction.dataset.mode = allSelected ? 'clear' : 'select';
      if (plansSelectAllLabel) {
        plansSelectAllLabel.textContent = allSelected ? 'Desmarcar todos' : 'Selecionar todos';
      }
    }

    if (!hasSelection && state.isPlansActionsMenuOpen && plansActionsMenu) {
      const activeElement = document.activeElement;
      if (
        activeElement instanceof HTMLElement &&
        plansActionsMenu.contains(activeElement) &&
        activeElement !== plansSelectAllAction
      ) {
        const firstItem = getFirstVisiblePlansAction();
        if (firstItem) {
          firstItem.focus();
        }
      }
    }
  };

  const closePlansActionsMenu = (options = {}) => {
    const { focusTrigger = false } = options;
    if (!plansActionsMenu || !plansActionsMenuContainer || !plansActionsTrigger) {
      return;
    }
    plansActionsMenuContainer.classList.remove('table-actions-menu--open');
    plansActionsMenu.setAttribute('hidden', 'hidden');
    plansActionsTrigger.setAttribute('aria-expanded', 'false');
    state.isPlansActionsMenuOpen = false;
    if (focusTrigger) {
      plansActionsTrigger.focus();
    }
  };

  const openPlansActionsMenu = (options = {}) => {
    const { focusFirst = false } = options;
    if (!plansActionsMenu || !plansActionsMenuContainer || !plansActionsTrigger) {
      return;
    }
    updatePlansActionsMenuState();
    plansActionsMenuContainer.classList.add('table-actions-menu--open');
    plansActionsMenu.removeAttribute('hidden');
    plansActionsTrigger.setAttribute('aria-expanded', 'true');
    state.isPlansActionsMenuOpen = true;
    if (focusFirst) {
      const firstItem = getFirstVisiblePlansAction();
      if (firstItem) {
        window.requestAnimationFrame(() => {
          firstItem.focus();
        });
      }
    }
  };

  const togglePlansActionsMenu = () => {
    if (state.isPlansActionsMenuOpen) {
      closePlansActionsMenu();
    } else {
      openPlansActionsMenu();
    }
  };

  const applyPlanRowSelectionState = (row, checked) => {
    if (!row) {
      return;
    }
    row.classList.toggle('table__row--selected', Boolean(checked));
    row.setAttribute('aria-selected', String(Boolean(checked)));
  };

  const setPlanSelection = (planId, checked, { checkbox, row } = {}) => {
    if (checkbox instanceof HTMLInputElement) {
      checkbox.checked = Boolean(checked);
    }
    if (row instanceof HTMLElement) {
      applyPlanRowSelectionState(row, checked);
    }
    const hasIdentifier = typeof planId === 'string' && planId.trim().length > 0;
    if (!hasIdentifier) {
      return;
    }
    if (checked) {
      plansSelection.add(planId);
    } else {
      plansSelection.delete(planId);
    }
  };

  const selectAllPlansOnPage = () => {
    if (!plansTableBody) {
      return;
    }
    const checkboxes = plansTableBody.querySelectorAll(planCheckboxSelector);
    if (!checkboxes.length) {
      return;
    }
    plansSelection.clear();
    checkboxes.forEach((checkbox) => {
      if (!(checkbox instanceof HTMLInputElement)) {
        return;
      }
      if (checkbox.disabled) {
        const row = checkbox.closest('tr');
        applyPlanRowSelectionState(row, false);
        return;
      }
      const row = checkbox.closest('tr');
      const planId = checkbox.dataset.planId ?? row?.dataset.planId ?? '';
      setPlanSelection(planId, true, { checkbox, row });
    });
    updatePlansActionsMenuState();
  };

  const deselectAllPlansOnPage = () => {
    if (!plansTableBody) {
      return;
    }
    const checkboxes = plansTableBody.querySelectorAll(planCheckboxSelector);
    if (!checkboxes.length) {
      plansSelection.clear();
      updatePlansActionsMenuState();
      return;
    }
    checkboxes.forEach((checkbox) => {
      if (!(checkbox instanceof HTMLInputElement)) {
        return;
      }
      const row = checkbox.closest('tr');
      const planId = checkbox.dataset.planId ?? row?.dataset.planId ?? '';
      setPlanSelection(planId, false, { checkbox, row });
    });
    plansSelection.clear();
    updatePlansActionsMenuState();
  };

  if (plansActionsTrigger && plansActionsMenu && plansActionsMenuContainer) {
    plansActionsTrigger.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      togglePlansActionsMenu();
    });

    plansActionsTrigger.addEventListener('keydown', (event) => {
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault();
        if (state.isPlansActionsMenuOpen) {
          closePlansActionsMenu();
        } else {
          openPlansActionsMenu({ focusFirst: true });
        }
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        openPlansActionsMenu({ focusFirst: true });
      } else if (event.key === 'Escape' && state.isPlansActionsMenuOpen) {
        event.preventDefault();
        closePlansActionsMenu();
      }
    });

    plansActionsMenu.addEventListener('click', (event) => {
      const target = event.target instanceof HTMLElement
        ? event.target.closest('.table-actions-menu__item')
        : null;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      const action = target.dataset.action || '';
      if (action === 'select-all') {
        const shouldClear = target.dataset.mode === 'clear';
        if (shouldClear) {
          deselectAllPlansOnPage();
        } else {
          selectAllPlansOnPage();
        }
      }
      updatePlansActionsMenuState();
      closePlansActionsMenu();
    });

    plansActionsMenu.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closePlansActionsMenu({ focusTrigger: true });
      }
    });

    document.addEventListener('click', (event) => {
      if (!state.isPlansActionsMenuOpen) {
        return;
      }
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (plansActionsMenuContainer.contains(target)) {
        return;
      }
      closePlansActionsMenu();
    });

    document.addEventListener('focusin', (event) => {
      if (!state.isPlansActionsMenuOpen) {
        return;
      }
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (plansActionsMenuContainer.contains(target)) {
        return;
      }
      closePlansActionsMenu();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && state.isPlansActionsMenuOpen) {
        event.preventDefault();
        closePlansActionsMenu({ focusTrigger: true });
      }
    });
  }

  updatePlansActionsMenuState();

  const renderPlansPlaceholder = (message, modifier = 'empty') => {
    if (!plansTableBody) {
      return;
    }
    plansSelection.clear();
    updatePlansActionsMenuState();
    closePlansActionsMenu();
    plansTableBody.innerHTML = '';
    const row = document.createElement('tr');
    row.className = 'table__row table__row--empty';
    if (modifier) {
      row.classList.add(`table__row--${modifier}`);
    }
    const cell = document.createElement('td');
    cell.className = 'table__cell table__cell--empty';
    cell.colSpan = plansColumnCount;
    const wrapper = document.createElement('div');
    wrapper.className = 'table-empty';

    const messageEl = document.createElement('p');
    messageEl.className = 'table-empty__message';
    messageEl.textContent = message;
    wrapper.appendChild(messageEl);

    const isEmptyState = modifier === 'empty';
    const showFilterContext = isEmptyState && hasActiveFilters();
    if (showFilterContext) {
      const hint = document.createElement('p');
      hint.className = 'table-empty__hint';
      hint.textContent = 'Os filtros selecionados podem estar escondendo alguns planos.';
      wrapper.appendChild(hint);

      const chipsHolder = document.createElement('div');
      chipsHolder.className = 'table-active-filters table-active-filters--floating';
      chipsHolder.dataset.filterChips = 'plans-empty';
      wrapper.appendChild(chipsHolder);
      attachFilterChipHandler(chipsHolder);

      const actions = document.createElement('div');
      actions.className = 'table-empty__actions';
      const clearButton = document.createElement('button');
      clearButton.type = 'button';
      clearButton.className = 'table-empty__clear';
      clearButton.textContent = 'Limpar filtros';
      clearButton.addEventListener('click', () => {
        clearAllFilters();
      });
      actions.appendChild(clearButton);
      wrapper.appendChild(actions);
    }

    cell.appendChild(wrapper);
    row.appendChild(cell);
    plansTableBody.appendChild(row);
    if (isEmptyState) {
      state.plansHasResults = false;
      renderFilterChips();
    }
  };

  const renderPlanRows = (items) => {
    if (!plansTableBody) {
      return;
    }
    plansTableBody.innerHTML = '';
    plansSelection.clear();
    closePlansActionsMenu();
    const plans = Array.isArray(items) ? items : [];
    if (!plans.length) {
      if (state.currentPlansSearchTerm) {
        renderPlansPlaceholder('nenhum plano encontrado para a busca.', 'empty');
      } else {
        renderPlansPlaceholder('nada a exibir por aqui.');
      }
      return;
    }

    state.plansHasResults = true;
    plans.forEach((item) => {
      const row = document.createElement('tr');
      row.className = 'table__row';
      row.setAttribute('aria-selected', 'false');

      const planNumberRaw = item?.number ?? '';
      const planId =
        typeof planNumberRaw === 'string'
          ? planNumberRaw.trim()
          : typeof planNumberRaw === 'number'
            ? String(planNumberRaw)
            : '';
      if (planId) {
        row.dataset.planId = planId;
      }

      const planCell = document.createElement('td');
      planCell.className = 'table__cell';
      const planNumberText = item?.number ?? '';
      const planNumberSpan = document.createElement('span');
      planNumberSpan.textContent = planNumberText;
      planCell.appendChild(planNumberSpan);

      const queueInfo = item?.treatment_queue ?? null;
      const isQueued = Boolean(queueInfo?.enqueued);
      if (isQueued) {
        row.classList.add('table__row--queued');
        const badge = document.createElement('span');
        badge.className = 'badge badge--queue';
        badge.textContent = 'Em tratamento';
        const badgeDetails = [];
        if (typeof queueInfo?.filas === 'number' && queueInfo.filas > 0) {
          badgeDetails.push(`Filas: ${queueInfo.filas}`);
        }
        if (typeof queueInfo?.users === 'number' && queueInfo.users > 0) {
          badgeDetails.push(`Usuários: ${queueInfo.users}`);
        }
        if (typeof queueInfo?.lotes === 'number' && queueInfo.lotes > 0) {
          badgeDetails.push(`Lotes: ${queueInfo.lotes}`);
        }
        if (badgeDetails.length) {
          badge.title = badgeDetails.join(' • ');
        } else {
          badge.title = 'Plano atualmente enfileirado para tratamento';
        }
        planCell.appendChild(document.createElement('br'));
        planCell.appendChild(badge);
      }
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
      actionsCell.className = 'table__cell table__cell--select';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.dataset.planCheckbox = 'true';
      if (planId) {
        checkbox.dataset.planId = planId;
      }
      checkbox.setAttribute(
        'aria-label',
        planId ? `Selecionar plano ${planId}` : 'Selecionar plano',
      );
      if (isQueued) {
        checkbox.disabled = true;
        checkbox.setAttribute('aria-disabled', 'true');
        const disabledHint = queueInfo?.filas
          ? `Plano em tratamento (${queueInfo.filas} filas ativas)`
          : 'Plano em tratamento';
        checkbox.title = disabledHint;
      }
      checkbox.addEventListener('change', () => {
        if (checkbox.disabled) {
          return;
        }
        const isChecked = checkbox.checked;
        setPlanSelection(planId, isChecked, { checkbox, row });
        updatePlansActionsMenuState();
      });
      actionsCell.appendChild(checkbox);
      row.appendChild(actionsCell);

      plansTableBody.appendChild(row);
    });

    renderFilterChips();
    updatePlansActionsMenuState();
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

    state.occHasResults = true;
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

    renderFilterChips();
  };

  const renderTreatmentPlaceholder = (message = 'nenhum lote aberto. clique em "Migrar planos".', modifier = 'empty') => {
    if (!treatmentTableBody) {
      return;
    }
    treatmentTableBody.innerHTML = '';
    const row = document.createElement('tr');
    row.className = 'table__row table__row--empty';
    if (modifier) {
      row.classList.add(`table__row--${modifier}`);
    }
    const cell = document.createElement('td');
    cell.className = 'table__cell table__cell--empty';
    cell.colSpan = treatmentColumnCount;
    cell.textContent = message;
    row.appendChild(cell);
    treatmentTableBody.appendChild(row);
  };

  const renderTreatmentRows = (items) => {
    if (!treatmentTableBody) {
      return;
    }
    treatmentTableBody.innerHTML = '';
    const plans = Array.isArray(items) ? items : [];
    if (!plans.length) {
      renderTreatmentPlaceholder('nenhum item pendente neste lote.');
      return;
    }
    plans.forEach((item) => {
      const row = document.createElement('tr');
      row.className = 'table__row';
      if (item?.plano_id) {
        row.dataset.planId = String(item.plano_id);
      }

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

      const balanceCell = document.createElement('td');
      balanceCell.className = 'table__cell';
      balanceCell.textContent = formatCurrencyValue(item?.balance);
      row.appendChild(balanceCell);

      const statusDateCell = document.createElement('td');
      statusDateCell.className = 'table__cell';
      statusDateCell.textContent = formatDateLabel(item?.status_date);
      row.appendChild(statusDateCell);

      const actionsCell = document.createElement('td');
      actionsCell.className = 'table__cell table__cell--actions';
      const actionsWrapper = document.createElement('div');
      actionsWrapper.className = 'table-actions';

      const rescindButton = document.createElement('button');
      rescindButton.type = 'button';
      rescindButton.className = 'btn btn--ghost';
      rescindButton.textContent = 'Rescindir';
      rescindButton.addEventListener('click', () => {
        void handleRescind(item, rescindButton);
      });
      actionsWrapper.appendChild(rescindButton);

      const skipButton = document.createElement('button');
      skipButton.type = 'button';
      skipButton.className = 'btn btn--ghost';
      skipButton.textContent = 'Pular';
      skipButton.addEventListener('click', () => {
        void handleSkip(item, skipButton);
      });
      actionsWrapper.appendChild(skipButton);

      actionsCell.appendChild(actionsWrapper);
      row.appendChild(actionsCell);

      treatmentTableBody.appendChild(row);
    });
  };

  const resetTreatmentPagination = () => {
    treatmentPager.page = 1;
    treatmentPager.nextCursor = null;
    treatmentPager.prevCursor = null;
    treatmentPager.hasMoreNext = false;
    treatmentPager.hasMorePrev = false;
    treatmentPager.lastCount = 0;
    treatmentPager.currentCursor = null;
    treatmentPager.currentDirection = 'next';
  };

  const setTreatmentTotals = (totals) => {
    const pending = Number(totals?.pending) || 0;
    const processed = Number(totals?.processed) || 0;
    const skipped = Number(totals?.skipped) || 0;
    state.treatmentTotals = {
      pending: pending < 0 ? 0 : pending,
      processed: processed < 0 ? 0 : processed,
      skipped: skipped < 0 ? 0 : skipped,
    };
    updateTreatmentKpis();
  };

  const getTreatmentTotalForStatus = (status) => {
    const normalized = typeof status === 'string' ? status.trim().toLowerCase() : 'pending';
    if (normalized === 'processed') {
      return Math.max(0, Number(state.treatmentTotals.processed) || 0);
    }
    if (normalized === 'skipped') {
      return Math.max(0, Number(state.treatmentTotals.skipped) || 0);
    }
    return Math.max(0, Number(state.treatmentTotals.pending) || 0);
  };

  const buildTreatmentFilters = () => {
    const filters = {};
    if (Array.isArray(filtersState.situacao) && filtersState.situacao.length) {
      filters.situacao = filtersState.situacao;
    }
    if (typeof filtersState.diasMin === 'number' && Number.isFinite(filtersState.diasMin)) {
      filters.dias_min = filtersState.diasMin;
    }
    if (typeof filtersState.saldoMin === 'number' && Number.isFinite(filtersState.saldoMin)) {
      filters.saldo_min = filtersState.saldoMin;
    }
    if (filtersState.dtRange) {
      filters.dt_sit_range = filtersState.dtRange;
    }
    return Object.keys(filters).length ? filters : null;
  };

  function updateTreatmentKpis() {
    if (kpiQueueEl) {
      kpiQueueEl.textContent = formatIntCount(state.treatmentTotals.pending ?? 0);
    }
    if (kpiRescindedEl) {
      kpiRescindedEl.textContent = formatIntCount(state.treatmentTotals.processed ?? 0);
    }
    if (kpiFailuresEl) {
      kpiFailuresEl.textContent = formatIntCount(state.treatmentTotals.skipped ?? 0);
    }
  }

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
    cell.className = 'table__cell table__cell--empty';
    cell.colSpan = occColumnCount;
    const wrapper = document.createElement('div');
    wrapper.className = 'table-empty';

    const messageEl = document.createElement('p');
    messageEl.className = 'table-empty__message';
    messageEl.textContent = message;
    wrapper.appendChild(messageEl);

    const isEmptyState = modifier === 'empty';
    const showFilterContext = isEmptyState && hasActiveFilters();
    if (showFilterContext) {
      const hint = document.createElement('p');
      hint.className = 'table-empty__hint';
      hint.textContent = 'Os filtros selecionados podem estar ocultando as ocorrências recentes.';
      wrapper.appendChild(hint);

      const chipsHolder = document.createElement('div');
      chipsHolder.className = 'table-active-filters table-active-filters--floating';
      chipsHolder.dataset.filterChips = 'occ-empty';
      wrapper.appendChild(chipsHolder);
      attachFilterChipHandler(chipsHolder);

      const actions = document.createElement('div');
      actions.className = 'table-empty__actions';
      const clearButton = document.createElement('button');
      clearButton.type = 'button';
      clearButton.className = 'table-empty__clear';
      clearButton.textContent = 'Limpar filtros';
      clearButton.addEventListener('click', () => {
        clearAllFilters();
      });
      actions.appendChild(clearButton);
      wrapper.appendChild(actions);
    }

    cell.appendChild(wrapper);
    row.appendChild(cell);
    occTableBody.appendChild(row);
    if (isEmptyState) {
      state.occHasResults = false;
      renderFilterChips();
    }
  };

  const resetPlansPagination = () => {
    plansPager.page = 1;
    plansPager.nextCursor = null;
    plansPager.prevCursor = null;
    plansPager.hasMore = false;
    plansPager.showingFrom = 0;
    plansPager.showingTo = 0;
    plansPager.totalCount = null;
    plansPager.totalPages = null;
  };

  const resetOccurrencesPagination = () => {
    occPager.page = 1;
    occPager.nextCursor = null;
    occPager.prevCursor = null;
    occPager.hasMore = false;
    occPager.showingFrom = 0;
    occPager.showingTo = 0;
    occPager.totalCount = null;
    occPager.totalPages = null;
  };

  const getFilterLabel = (filterKey, value) => {
    const labels = FILTER_LABELS[filterKey];
    if (!labels) {
      return String(value);
    }
    const stringValue = String(value);
    return labels[stringValue] ?? labels[value] ?? String(value);
  };

  const renderFilterChips = () => {
    const containers = Array.from(document.querySelectorAll('[data-filter-chips]')).filter(
      (node) => node instanceof HTMLElement,
    );
    if (!containers.length) {
      return;
    }

    const chips = [];
    filtersState.situacao.forEach((value) => {
      chips.push({ type: 'situacao', value });
    });
    if (filtersState.diasMin !== null) {
      chips.push({ type: 'diasMin', value: String(filtersState.diasMin) });
    }
    if (filtersState.saldoMin !== null) {
      chips.push({ type: 'saldoMin', value: String(filtersState.saldoMin) });
    }
    if (filtersState.dtRange) {
      chips.push({ type: 'dtRange', value: filtersState.dtRange });
    }

    const hasChips = chips.length > 0;

    containers.forEach((container) => {
      const scope = container.getAttribute('data-filter-chips') ?? '';
      const isPlanContainer = scope.startsWith('plans');
      const isPlanEmptyContainer = scope === 'plans-empty';
      const isOccContainer = scope.startsWith('occ');
      const isOccEmptyContainer = scope === 'occ-empty';

      let shouldShow = hasChips;

      if (isPlanContainer) {
        shouldShow =
          hasChips &&
          ((state.plansHasResults && !isPlanEmptyContainer) || (!state.plansHasResults && isPlanEmptyContainer));
      } else if (isOccContainer) {
        shouldShow =
          hasChips &&
          ((state.occHasResults && !isOccEmptyContainer) || (!state.occHasResults && isOccEmptyContainer));
      }

      if (!shouldShow) {
        container.hidden = true;
        container.innerHTML = '';
        return;
      }

      container.hidden = false;
      container.innerHTML = '';

      chips.forEach(({ type, value }) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'filter-chip';
        button.dataset.filterType = type;
        button.dataset.filterValue = value;
        const label = getFilterLabel(type, value);
        button.setAttribute('aria-label', `Remover filtro ${label}`);
        button.innerHTML = `
          <span class="filter-chip__label">${label}</span>
          <span class="filter-chip__remove" aria-hidden="true">×</span>
          <span class="sr-only">Remover filtro ${label}</span>
        `;
        container.appendChild(button);
      });
    });
  };

  const syncFilterInputs = () => {
    const inputs = document.querySelectorAll('[data-filter-input]');
    inputs.forEach((input) => {
      const filterType = input.dataset.filterInput;
      const value = input.value;
      if (!filterType) {
        return;
      }
      switch (filterType) {
        case 'situacao':
          input.checked = filtersState.situacao.includes(value);
          break;
        case 'dias':
          input.checked =
            filtersState.diasMin !== null && Number(value) === Number(filtersState.diasMin);
          break;
        case 'saldo':
          input.checked =
            filtersState.saldoMin !== null && Number(value) === Number(filtersState.saldoMin);
          break;
        case 'dt':
          input.checked = filtersState.dtRange === value;
          break;
        default:
          break;
      }
    });
  };

  const closeAllFilterDropdowns = () => {
    state.filterWrappers.forEach((wrapper) => {
      wrapper.classList.remove('table-filter--open');
      const trigger = wrapper.querySelector('.table-filter__trigger');
      if (trigger) {
        trigger.setAttribute('aria-expanded', 'false');
      }
    });
  };

  const clearFilter = (filterType) => {
    switch (filterType) {
      case 'situacao':
        filtersState.situacao = [];
        break;
      case 'dias':
        filtersState.diasMin = null;
        break;
      case 'saldo':
        filtersState.saldoMin = null;
        break;
      case 'dt':
        filtersState.dtRange = null;
        break;
      default:
        break;
    }
  };

  const applyFilters = ({ closeDropdown = false } = {}) => {
    resetPlansPagination();
    resetOccurrencesPagination();
    syncFilterInputs();
    renderFilterChips();
    void refreshPlans({ showLoading: true });
    void refreshOccurrences({ showLoading: true });
    if (closeDropdown) {
      closeAllFilterDropdowns();
    }
  };

  const clearAllFilters = ({ closeDropdown = true } = {}) => {
    resetFiltersState();
    applyFilters({ closeDropdown });
  };

  const setupFilters = () => {
    state.filterWrappers = Array.from(document.querySelectorAll('[data-filter-group]'));
    if (!state.filterWrappers.length) {
      return;
    }

    state.filterWrappers.forEach((wrapper) => {
      const trigger = wrapper.querySelector('.table-filter__trigger');
      const dropdown = wrapper.querySelector('.table-filter__dropdown');
      if (!trigger || !dropdown) {
        return;
      }

      trigger.addEventListener('click', (event) => {
        event.stopPropagation();
        const isOpen = wrapper.classList.toggle('table-filter--open');
        state.filterWrappers.forEach((other) => {
          if (other !== wrapper) {
            other.classList.remove('table-filter--open');
            const otherTrigger = other.querySelector('.table-filter__trigger');
            if (otherTrigger) {
              otherTrigger.setAttribute('aria-expanded', 'false');
            }
          }
        });
        trigger.setAttribute('aria-expanded', String(isOpen));
      });

      dropdown.addEventListener('click', (event) => {
        event.stopPropagation();
      });

      const inputs = dropdown.querySelectorAll('[data-filter-input]');
      inputs.forEach((input) => {
        input.addEventListener('change', (event) => {
          const target = event.currentTarget;
          if (!(target instanceof HTMLInputElement)) {
            return;
          }
          const filterType = target.dataset.filterInput;
          if (!filterType) {
            return;
          }

          if (filterType === 'situacao') {
            const value = target.value;
            if (target.checked) {
              if (!filtersState.situacao.includes(value)) {
                filtersState.situacao.push(value);
              }
            } else {
              filtersState.situacao = filtersState.situacao.filter((item) => item !== value);
            }
            applyFilters();
            return;
          }

          if (filterType === 'dias') {
            filtersState.diasMin = Number(target.value);
            applyFilters({ closeDropdown: true });
            return;
          }

          if (filterType === 'saldo') {
            filtersState.saldoMin = Number(target.value);
            applyFilters({ closeDropdown: true });
            return;
          }

          if (filterType === 'dt') {
            filtersState.dtRange = target.value;
            applyFilters({ closeDropdown: true });
          }
        });
      });

      const clearButton = dropdown.querySelector('[data-filter-clear]');
      if (clearButton) {
        clearButton.addEventListener('click', (event) => {
          event.preventDefault();
          const filterType = clearButton.getAttribute('data-filter-clear');
          if (!filterType) {
            return;
          }
          clearFilter(filterType);
          applyFilters({ closeDropdown: true });
        });
      }
    });

    document.addEventListener('click', () => {
      closeAllFilterDropdowns();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        closeAllFilterDropdowns();
      }
    });

    syncFilterInputs();
    renderFilterChips();
  };

  const attachFilterChipHandler = (container) => {
    if (!container) {
      return;
    }
    container.addEventListener('click', (event) => {
      const target = event.target instanceof Element ? event.target.closest('.filter-chip') : null;
      if (!target) {
        return;
      }
      event.preventDefault();
      const filterType = target.getAttribute('data-filter-type');
      const filterValue = target.getAttribute('data-filter-value');
      if (!filterType) {
        return;
      }

      switch (filterType) {
        case 'situacao':
          if (filterValue) {
            filtersState.situacao = filtersState.situacao.filter((item) => item !== filterValue);
          }
          break;
        case 'diasMin':
          filtersState.diasMin = null;
          break;
        case 'saldoMin':
          filtersState.saldoMin = null;
          break;
        case 'dtRange':
          filtersState.dtRange = null;
          break;
        default:
          break;
      }

      applyFilters();
    });
  };

  attachFilterChipHandler(plansFiltersChipsContainer);
  attachFilterChipHandler(occFiltersChipsContainer);

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

  const treatmentPager = {
    page: 1,
    pageSize: DEFAULT_PLAN_PAGE_SIZE,
    nextCursor: null,
    prevCursor: null,
    hasMoreNext: false,
    hasMorePrev: false,
    lastCount: 0,
    currentCursor: null,
    currentDirection: 'next',
  };
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
      const totalPagesRaw = plansPager.totalPages ?? null;
      const totalPagesNumber =
        totalPagesRaw && Number.isFinite(totalPagesRaw) && totalPagesRaw > 0
          ? Number(totalPagesRaw)
          : 1;
      const currentPage = Math.max(1, plansPager.page || 1);
      plansPagerLabel.textContent = `pág. ${currentPage} de ${totalPagesNumber}`;
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

  const updateTreatmentPagerUI = () => {
    const pageSize = Number(treatmentPager.pageSize) || DEFAULT_PLAN_PAGE_SIZE;
    const totalForStatus = getTreatmentTotalForStatus(state.treatmentStatusFilter);
    const totalValue = Number.isFinite(totalForStatus) ? totalForStatus : 0;
    const totalPages = totalValue > 0 ? Math.ceil(totalValue / pageSize) : 1;
    let currentPage = Math.max(1, Number(treatmentPager.page) || 1);
    if (currentPage > totalPages) {
      currentPage = totalPages;
      treatmentPager.page = currentPage;
    }

    if (treatmentPagerLabel) {
      treatmentPagerLabel.textContent = `pág. ${currentPage} de ${totalPages}`;
    }

    if (treatmentPagerRange) {
      const rowsOnPage = Math.max(0, Number(treatmentPager.lastCount) || 0);
      const showingFrom = rowsOnPage ? (currentPage - 1) * pageSize + 1 : 0;
      const showingTo = rowsOnPage
        ? Math.min(totalValue, showingFrom + rowsOnPage - 1)
        : 0;
      const totalLabel = totalValue.toLocaleString('pt-BR');
      treatmentPagerRange.textContent = `exibindo ${showingFrom}–${showingTo} de ${totalLabel} planos para rescisão`;
    }

    if (treatmentPagerPrevBtn) {
      const canGoPrev = currentPage > 1 && Boolean(treatmentPager.prevCursor);
      treatmentPagerPrevBtn.disabled = !canGoPrev;
      treatmentPagerPrevBtn.setAttribute('aria-disabled', String(!canGoPrev));
    }

    if (treatmentPagerNextBtn) {
      const canGoNext =
        currentPage < totalPages && Boolean(treatmentPager.hasMoreNext && treatmentPager.nextCursor);
      treatmentPagerNextBtn.disabled = !canGoNext;
      treatmentPagerNextBtn.setAttribute('aria-disabled', String(!canGoNext));
    }
  };

  const updateOccPagerUI = () => {
    if (occPagerLabel) {
      const totalPagesRaw = occPager.totalPages ?? null;
      const totalPagesNumber =
        totalPagesRaw && Number.isFinite(totalPagesRaw) && totalPagesRaw > 0
          ? Number(totalPagesRaw)
          : 1;
      const currentPage = Math.max(1, occPager.page || 1);
      occPagerLabel.textContent = `pág. ${currentPage} de ${totalPagesNumber}`;
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
    if (state.currentPlansSearchTerm) {
      url.searchParams.set('q', state.currentPlansSearchTerm);
    }
    if (filtersState.situacao.length) {
      filtersState.situacao.forEach((value) => {
        url.searchParams.append('situacao', value);
      });
    }
    if (filtersState.diasMin !== null) {
      url.searchParams.set('dias_min', String(filtersState.diasMin));
    }
    if (filtersState.saldoMin !== null) {
      url.searchParams.set('saldo_min', String(filtersState.saldoMin));
    }
    if (filtersState.dtRange) {
      url.searchParams.set('dt_sit_range', filtersState.dtRange);
    }
    return url.toString();
  };

  const refreshPlans = async ({ showLoading, direction = null } = {}) => {
    if (!canAccessBase()) {
      state.plansLoaded = true;
      if (plansTableBody) {
        renderPlansPlaceholder('Área disponível apenas para perfil Gestor.', 'empty');
      }
      return;
    }

    if (!plansTableBody || state.isFetchingPlans) {
      return;
    }
    const shouldShowLoading = showLoading ?? !state.plansLoaded;
    if (shouldShowLoading) {
      renderPlansPlaceholder('carregando planos...', 'loading');
    }

    state.isFetchingPlans = true;
    try {
      if (state.plansFetchController) {
        state.plansFetchController.abort();
      }
      state.plansFetchController = new AbortController();
      const requestHeaders = new Headers({ Accept: 'application/json' });
      const matricula = currentUser?.username?.trim();
      if (matricula) {
        requestHeaders.set('X-User-Registration', matricula);
      }
      const response = await fetch(buildPlansRequestUrl({ direction }), {
        headers: requestHeaders,
        signal: state.plansFetchController.signal,
      });
      if (!response.ok) {
        throw new Error('Não foi possível carregar os planos.');
      }
      const payload = await response.json();
      const items = Array.isArray(payload?.items) ? payload.items : [];
      renderPlanRows(items);
      const filtersResponse = payload?.filters ?? null;
      if (filtersResponse) {
        filtersState.situacao = Array.isArray(filtersResponse.situacao)
          ? [...filtersResponse.situacao]
          : [];
        filtersState.diasMin =
          typeof filtersResponse.dias_min === 'number' ? filtersResponse.dias_min : null;
        filtersState.saldoMin =
          typeof filtersResponse.saldo_min === 'number' ? filtersResponse.saldo_min : null;
        filtersState.dtRange = filtersResponse.dt_sit_range || null;
      } else {
        filtersState.situacao = [];
        filtersState.diasMin = null;
        filtersState.saldoMin = null;
        filtersState.dtRange = null;
      }
      syncFilterInputs();
      renderFilterChips();
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
      state.plansLoaded = true;
    } catch (error) {
      if (error?.name === 'AbortError') {
        return;
      }
      console.error('Erro ao carregar planos.', error);
      if (!state.plansLoaded) {
        renderPlansPlaceholder('Não foi possível carregar os planos.', 'error');
      }
    } finally {
      state.plansFetchController = null;
      state.isFetchingPlans = false;
    }
  };

  const toggleButtons = ({ start, pause, cont }) => {
    if (!canAccessBase()) {
      [btnStart, btnPause, btnContinue].forEach((btn) => {
        if (!btn) {
          return;
        }
        btn.disabled = true;
        btn.classList.add('btn--disabled');
        btn.setAttribute('aria-disabled', 'true');
      });
      return;
    }
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
    if (state.pollHandle !== null) {
      window.clearInterval(state.pollHandle);
      state.pollHandle = null;
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
    if (state.progressIntervalHandle !== null) {
      window.clearInterval(state.progressIntervalHandle);
      state.progressIntervalHandle = null;
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
    if (!progressBar || state.progressStartTimestamp === null) {
      return;
    }

    const elapsed = Math.max(0, Date.now() - state.progressStartTimestamp);
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

    state.progressStartTimestamp = normalizedTimestamp;
    progressBar.classList.remove('progress__bar--complete');
    setProgressVisibility(true);
    tickProgress();
    stopProgressTimer();
    state.progressIntervalHandle = window.setInterval(tickProgress, 1000);
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
    state.progressStartTimestamp = null;

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
        startedTimestamp ?? state.progressStartTimestamp ?? Date.now();
      beginProgressTracking(effectiveStart);
      return;
    }

    if (status === 'succeeded') {
      if (startedTimestamp && state.progressStartTimestamp === null) {
        state.progressStartTimestamp = startedTimestamp;
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
    state.activeTableSearchTarget = target;
    if (tableSearchForm) {
      tableSearchForm.dataset.activeTable = target;
    }
    if (tableSearchInput) {
      const controlsTarget =
        target === 'occurrences' ? 'occurrencesTablePanel' : 'plansTablePanel';
      tableSearchInput.setAttribute('aria-controls', controlsTarget);
    }
  };

  state.scheduleOccurrencesCountUpdate = () => {};

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

    state.scheduleOccurrencesCountUpdate();
  };

  const handleOccurrencesSearch = (term, { forceRefresh = false } = {}) => {
    const normalized = (term || '').trim();
    if (!forceRefresh && normalized === state.currentOccurrencesSearchTerm) {
      return;
    }
    state.currentOccurrencesSearchTerm = normalized;
    tableSearchState.occurrences = normalized;
    // Reset pager when the search changes
    occPager.page = 1;
    occPager.nextCursor = null;
    occPager.prevCursor = null;
    void refreshOccurrences({ showLoading: true });
  };

  const handlePlansSearch = (term, { forceRefresh = false } = {}) => {
    const normalized = (term || '').trim();
    if (!forceRefresh && normalized === state.currentPlansSearchTerm) {
      return;
    }
    state.currentPlansSearchTerm = normalized;
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
      if (state.activeTableSearchTarget === 'occurrences') {
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
      tableSearchState[state.activeTableSearchTarget] = value;
      if (searchDebounceHandle !== null) {
        window.clearTimeout(searchDebounceHandle);
      }
      searchDebounceHandle = window.setTimeout(() => {
        searchDebounceHandle = null;
        if (state.activeTableSearchTarget === 'occurrences') {
          handleOccurrencesSearch(value);
          return;
        }
        if (value.trim()) {
          handlePlansSearch(value);
        } else if (state.currentPlansSearchTerm) {
          // Clear search resets pager and reloads first page
          plansPager.page = 1;
          plansPager.nextCursor = null;
          plansPager.prevCursor = null;
          handlePlansSearch('', { forceRefresh: true });
        }
        if (!value.trim() && state.currentOccurrencesSearchTerm) {
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

  if (treatmentPagerPrevBtn) {
    treatmentPagerPrevBtn.addEventListener('click', () => {
      if (treatmentPager.page <= 1 || !treatmentPager.prevCursor) {
        return;
      }
      void refreshTreatment({ direction: 'prev', cursor: treatmentPager.prevCursor });
    });
  }
  if (treatmentPagerNextBtn) {
    treatmentPagerNextBtn.addEventListener('click', () => {
      if (!treatmentPager.hasMoreNext || !treatmentPager.nextCursor) {
        return;
      }
      void refreshTreatment({ direction: 'next', cursor: treatmentPager.nextCursor });
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
    if (state.currentOccurrencesSearchTerm) {
      url.searchParams.set('q', state.currentOccurrencesSearchTerm);
    }
    if (filtersState.situacao.length) {
      filtersState.situacao.forEach((value) => {
        url.searchParams.append('situacao', value);
      });
    }
    if (filtersState.diasMin !== null) {
      url.searchParams.set('dias_min', String(filtersState.diasMin));
    }
    if (filtersState.saldoMin !== null) {
      url.searchParams.set('saldo_min', String(filtersState.saldoMin));
    }
    if (filtersState.dtRange) {
      url.searchParams.set('dt_sit_range', filtersState.dtRange);
    }
    return url.toString();
  };

  const refreshOccurrences = async ({ showLoading, direction = null } = {}) => {
    if (!canAccessBase()) {
      state.occurrencesLoaded = true;
      if (occTableBody) {
        renderOccurrencesPlaceholder('Área disponível apenas para perfil Gestor.', 'empty');
      }
      return;
    }

    if (!occTableBody || state.isFetchingOccurrences) {
      return;
    }
    const shouldShowLoading = showLoading ?? !state.occurrencesLoaded;
    if (shouldShowLoading) {
      renderOccurrencesPlaceholder('carregando ocorrências...', 'loading');
    }

    state.isFetchingOccurrences = true;
    try {
      if (state.occFetchController) {
        state.occFetchController.abort();
      }
      state.occFetchController = new AbortController();
      const requestHeaders = new Headers({ Accept: 'application/json' });
      const matricula = currentUser?.username?.trim();
      if (matricula) {
        requestHeaders.set('X-User-Registration', matricula);
      }
      const response = await fetch(buildOccurrencesRequestUrl({ direction }), {
        headers: requestHeaders,
        signal: state.occFetchController.signal,
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

      state.occurrencesLoaded = true;
    } catch (error) {
      if (error?.name === 'AbortError') {
        return;
      }
      console.error('Erro ao carregar ocorrências.', error);
      if (!state.occurrencesLoaded) {
        renderOccurrencesPlaceholder('Não foi possível carregar as ocorrências.', 'error');
      }
    } finally {
      state.occFetchController = null;
      state.isFetchingOccurrences = false;
    }
  };

  const fetchTreatmentState = async ({ refreshItems = true } = {}) => {
    if (state.isFetchingTreatmentState) {
      return null;
    }
    state.isFetchingTreatmentState = true;
    const baseUrl =
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : window.location.href;
    const url = new URL(`${TREATMENT_ENDPOINT}/state`, baseUrl);
    url.searchParams.set('grid', TREATMENT_GRID);
    const headers = new Headers({ Accept: 'application/json' });
    const matricula = currentUser?.username?.trim();
    if (matricula) {
      headers.set('X-User-Registration', matricula);
    }

    try {
      const response = await fetch(url.toString(), { headers });
      if (!response.ok) {
        throw new Error('Falha ao obter estado do tratamento.');
      }
      const payload = await response.json();
      const hasOpen = Boolean(payload?.has_open);
      const loteIdRaw = hasOpen ? payload?.lote_id ?? null : null;
      const loteId = loteIdRaw ? String(loteIdRaw) : null;
      setTreatmentTotals(payload?.totals ?? {});

      if (btnCloseTreatment) {
        const disable = !hasOpen || !loteId;
        btnCloseTreatment.disabled = disable;
        btnCloseTreatment.setAttribute('aria-disabled', String(disable));
      }

      if (!hasOpen || !loteId) {
        state.treatmentBatchId = null;
        resetTreatmentPagination();
        updateTreatmentPagerUI();
        renderTreatmentPlaceholder();
        state.treatmentLoaded = true;
        return payload;
      }

      const batchChanged = state.treatmentBatchId !== loteId;
      state.treatmentBatchId = loteId;
      if (batchChanged) {
        resetTreatmentPagination();
      }
      if (refreshItems || batchChanged) {
        await refreshTreatment({ reset: batchChanged, showLoading: !state.treatmentLoaded });
      } else {
        updateTreatmentPagerUI();
      }
      return payload;
    } catch (error) {
      console.error('Erro ao carregar o estado do tratamento.', error);
      state.treatmentBatchId = null;
      setTreatmentTotals({ pending: 0, processed: 0, skipped: 0 });
      resetTreatmentPagination();
      updateTreatmentPagerUI();
      if (btnCloseTreatment) {
        btnCloseTreatment.disabled = true;
        btnCloseTreatment.setAttribute('aria-disabled', 'true');
      }
      if (!state.treatmentLoaded) {
        renderTreatmentPlaceholder('Não foi possível carregar os planos.', 'error');
      }
      return null;
    } finally {
      state.isFetchingTreatmentState = false;
    }
  };

  const refreshTreatment = async ({
    cursor,
    direction,
    reset = false,
    showLoading,
  } = {}) => {
    if (!treatmentTableBody || state.isFetchingTreatment) {
      return;
    }
    if (!state.treatmentBatchId) {
      resetTreatmentPagination();
      updateTreatmentPagerUI();
      renderTreatmentPlaceholder();
      return;
    }

    const hasCursorParam = cursor !== undefined;
    let normalizedDirection;
    if (hasCursorParam || typeof direction === 'string') {
      normalizedDirection = direction === 'prev' ? 'prev' : 'next';
    } else {
      normalizedDirection = treatmentPager.currentDirection || 'next';
    }

    if (reset) {
      resetTreatmentPagination();
      treatmentPager.currentDirection = normalizedDirection;
    }

    let requestCursor;
    if (hasCursorParam) {
      requestCursor = cursor;
    } else if (reset) {
      requestCursor = null;
    } else {
      requestCursor = treatmentPager.currentCursor;
    }

    const shouldShowLoading = showLoading ?? !state.treatmentLoaded;
    if (shouldShowLoading) {
      renderTreatmentPlaceholder('carregando planos...', 'loading');
    }

    state.isFetchingTreatment = true;
    try {
      const baseUrl =
        window.location.origin && window.location.origin !== 'null'
          ? window.location.origin
          : window.location.href;
      const url = new URL(`${TREATMENT_ENDPOINT}/items`, baseUrl);
      url.searchParams.set('lote_id', String(state.treatmentBatchId));
      url.searchParams.set('status', state.treatmentStatusFilter);
      url.searchParams.set('page_size', String(treatmentPager.pageSize || DEFAULT_PLAN_PAGE_SIZE));
      url.searchParams.set('direction', normalizedDirection);
      if (requestCursor) {
        url.searchParams.set('cursor', requestCursor);
      }

      const headers = new Headers({ Accept: 'application/json' });
      const matricula = currentUser?.username?.trim();
      if (matricula) {
        headers.set('X-User-Registration', matricula);
      }

      const response = await fetch(url.toString(), { headers });
      if (!response.ok) {
        throw new Error('Não foi possível carregar os itens do tratamento.');
      }

      const payload = await response.json();
      const items = Array.isArray(payload?.items) ? payload.items : [];
      renderTreatmentRows(items);

      const paging = payload?.paging || {};
      const pageSizeValue = Number(paging.page_size);
      if (Number.isFinite(pageSizeValue) && pageSizeValue > 0) {
        treatmentPager.pageSize = pageSizeValue;
      }
      treatmentPager.nextCursor = paging?.next_cursor || null;
      treatmentPager.prevCursor = paging?.prev_cursor || null;
      treatmentPager.lastCount = items.length;

      const hasResults = items.length > 0;

      if (reset) {
        treatmentPager.page = 1;
      } else if (hasCursorParam && requestCursor && hasResults) {
        if (normalizedDirection === 'next') {
          treatmentPager.page += 1;
        } else if (normalizedDirection === 'prev') {
          treatmentPager.page = Math.max(1, treatmentPager.page - 1);
        }
      } else if (!hasCursorParam) {
        treatmentPager.page = Math.max(1, treatmentPager.page);
      }

      if (reset) {
        treatmentPager.currentCursor = requestCursor ?? null;
        treatmentPager.currentDirection = normalizedDirection;
      } else if (hasCursorParam) {
        if (hasResults) {
          treatmentPager.currentCursor = requestCursor ?? null;
          treatmentPager.currentDirection = normalizedDirection;
        }
      } else {
        if (requestCursor !== undefined) {
          treatmentPager.currentCursor = requestCursor ?? null;
        }
        treatmentPager.currentDirection = normalizedDirection;
      }

      const totalForStatus = getTreatmentTotalForStatus(state.treatmentStatusFilter);
      const totalPages = totalForStatus > 0 ? Math.ceil(totalForStatus / treatmentPager.pageSize) : 1;
      if (treatmentPager.page > totalPages) {
        treatmentPager.page = totalPages;
      }
      treatmentPager.page = Math.max(1, treatmentPager.page);

      const hasMorePrev =
        (normalizedDirection === 'prev' && hasCursorParam)
          ? Boolean(paging?.has_more)
          : treatmentPager.page > 1;
      const hasMoreNext =
        (normalizedDirection === 'next' && hasCursorParam)
          ? Boolean(paging?.has_more)
          : treatmentPager.page < totalPages;

      treatmentPager.hasMorePrev = hasMorePrev && Boolean(treatmentPager.prevCursor);
      treatmentPager.hasMoreNext = hasMoreNext && Boolean(treatmentPager.nextCursor);

      if (treatmentPager.page <= 1) {
        treatmentPager.hasMorePrev = false;
      }

      updateTreatmentPagerUI();
      state.treatmentLoaded = true;
    } catch (error) {
      console.error('Erro ao carregar planos de tratamento.', error);
      if (!state.treatmentLoaded) {
        renderTreatmentPlaceholder('Não foi possível carregar os planos.', 'error');
      }
    } finally {
      state.isFetchingTreatment = false;
    }
  };

  async function handleRescind(item, button) {
    if (!state.treatmentBatchId || !item?.plano_id) {
      return;
    }
    const targetButton = button ?? null;
    if (targetButton) {
      targetButton.disabled = true;
      targetButton.setAttribute('aria-disabled', 'true');
    }
    try {
      const baseUrl =
        window.location.origin && window.location.origin !== 'null'
          ? window.location.origin
          : window.location.href;
      const url = new URL(`${TREATMENT_ENDPOINT}/rescind`, baseUrl);
      const headers = new Headers({ Accept: 'application/json', 'Content-Type': 'application/json' });
      const matricula = currentUser?.username?.trim();
      if (matricula) {
        headers.set('X-User-Registration', matricula);
      }
      const payload = {
        lote_id: state.treatmentBatchId,
        plano_id: item.plano_id,
        data_rescisao: new Date().toISOString(),
      };
      const response = await fetch(url.toString(), {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error('Falha ao rescindir o plano.');
      }
      await fetchTreatmentState({ refreshItems: true });
    } catch (error) {
      console.error('Erro ao rescindir plano.', error);
    } finally {
      if (targetButton) {
        targetButton.disabled = false;
        targetButton.setAttribute('aria-disabled', 'false');
      }
    }
  }

  async function handleSkip(item, button) {
    if (!state.treatmentBatchId || !item?.plano_id) {
      return;
    }
    const targetButton = button ?? null;
    if (targetButton) {
      targetButton.disabled = true;
      targetButton.setAttribute('aria-disabled', 'true');
    }
    try {
      const baseUrl =
        window.location.origin && window.location.origin !== 'null'
          ? window.location.origin
          : window.location.href;
      const url = new URL(`${TREATMENT_ENDPOINT}/skip`, baseUrl);
      const headers = new Headers({ Accept: 'application/json', 'Content-Type': 'application/json' });
      const matricula = currentUser?.username?.trim();
      if (matricula) {
        headers.set('X-User-Registration', matricula);
      }
      const payload = {
        lote_id: state.treatmentBatchId,
        plano_id: item.plano_id,
      };
      const response = await fetch(url.toString(), {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error('Falha ao ignorar o item.');
      }
      await fetchTreatmentState({ refreshItems: true });
    } catch (error) {
      console.error('Erro ao ignorar item de tratamento.', error);
    } finally {
      if (targetButton) {
        targetButton.disabled = false;
        targetButton.setAttribute('aria-disabled', 'false');
      }
    }
  }

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
    const formatted = context.formatDocument(current);
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
      state.scheduleOccurrencesCountUpdate = () => {};
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

    state.scheduleOccurrencesCountUpdate = () => {
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
      if (target === 'occurrences' && !state.occurrencesLoaded) {
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

  // --- KPI helpers ---
  const formatIntCount = (value) => {
    const n = Number(value);
    if (!Number.isFinite(n) || n < 0) return '0';
    if (n >= 1000) return n.toLocaleString('pt-BR');
    return String(Math.trunc(n));
  };

  const updateKpiCounts = ({ queueCount, rescindedCount, remainingCount }) => {
    if (kpiQueueEl) {
      kpiQueueEl.textContent = formatIntCount(queueCount ?? 0);
    }
    if (kpiRescindedEl) {
      kpiRescindedEl.textContent = formatIntCount(rescindedCount ?? 0);
    }
    if (kpiFailuresEl) {
      kpiFailuresEl.textContent = formatIntCount(remainingCount ?? 0);
    }
  };

  const setupMainTabsSwitching = () => {
    const baseTab = document.getElementById('tab-base');
    const treatmentTab = document.getElementById('tab-treatment');
    const basePanel = document.getElementById('panel-base');
    const treatmentPanel = document.getElementById('panel-treatment');

    if (!baseTab || !treatmentTab || !basePanel || !treatmentPanel) {
      return;
    }

    const activate = (target) => {
      let desired = target;
      if (desired === 'base' && !canAccessBase()) {
        desired = 'treatment';
      }

      const isBase = desired === 'base';
      baseTab.classList.toggle('tabs__item--active', isBase);
      treatmentTab.classList.toggle('tabs__item--active', !isBase);
      baseTab.setAttribute('aria-selected', String(isBase));
      baseTab.setAttribute('tabindex', isBase ? '0' : canAccessBase() ? '0' : '-1');
      treatmentTab.setAttribute('aria-selected', String(!isBase));
      treatmentTab.setAttribute('tabindex', isBase ? '-1' : '0');

      basePanel.classList.toggle('card__panel--hidden', !isBase);
      treatmentPanel.classList.toggle('card__panel--hidden', isBase);
      if (isBase) {
        basePanel.removeAttribute('hidden');
        treatmentPanel.setAttribute('hidden', 'hidden');
      } else {
        treatmentPanel.removeAttribute('hidden');
        basePanel.setAttribute('hidden', 'hidden');
        void fetchTreatmentState({ refreshItems: !state.treatmentLoaded });
      }
    };

    const handleBaseClick = (event) => {
      event.preventDefault();
      if (!canAccessBase()) {
        return;
      }
      activate('base');
    };

    const handleTreatmentClick = (event) => {
      event.preventDefault();
      activate('treatment');
    };

    baseTab.addEventListener('click', handleBaseClick);
    treatmentTab.addEventListener('click', handleTreatmentClick);

    const handleKeyNav = (event) => {
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        treatmentTab.focus();
        activate('treatment');
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        if (!canAccessBase()) {
          return;
        }
        baseTab.focus();
        activate('base');
      }
    };
    baseTab.addEventListener('keydown', handleKeyNav);
    treatmentTab.addEventListener('keydown', handleKeyNav);

    applyProfilePermissions();
    const isBaseInitiallyActive = baseTab.classList.contains('tabs__item--active');
    const initialTarget = canAccessBase() && isBaseInitiallyActive ? 'base' : 'treatment';
    activate(initialTarget);
  };

  refreshProfileFromStore();
  applyProfilePermissions();
  setupFilters();
  toggleButtons({ start: true, pause: false, cont: false });
  setStatus(defaultMessages.idle);
  void refreshPlans();
  void refreshOccurrences();
  void fetchTreatmentState({ refreshItems: true });
  // Initialize KPI values with zeros; backend wiring can update these later
  updateKpiCounts({ queueCount: 0, rescindedCount: 0, remainingCount: 0 });
  void refreshUserProfile();

  const schedulePolling = () => {
    if (!canAccessBase()) {
      stopPolling();
      return;
    }
    stopPolling();
    state.pollHandle = window.setInterval(async () => {
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
    const runningPlan = resolveRunningPlanFromState(state);
    updateRunningPlanInfo(runningPlan);
    switch (state.status) {
      case 'running':
        toggleButtons({ start: false, pause: true, cont: false });
        state.shouldRefreshPlansAfterRun = true;
        break;
      case 'succeeded':
      case 'failed':
      case 'idle':
      default:
        toggleButtons({ start: true, pause: false, cont: false });
        if (state.shouldRefreshPlansAfterRun) {
          state.shouldRefreshPlansAfterRun = false;
          void refreshPlans({ showLoading: false });
          void refreshOccurrences({ showLoading: false });
        }
        break;
    }
    setStatus(message);
  };

  const fetchPipelineState = async () => {
    if (!canAccessBase()) {
      return null;
    }
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
    if (!canAccessBase()) {
      showPermissionDeniedToast();
      return;
    }
    toggleButtons({ start: false, pause: false, cont: false });
    setStatus('Iniciando...');

    try {
      const payload = {};
      if (currentUser?.username) {
        payload.matricula = currentUser.username;
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

  const btnMigratePlans = document.getElementById('btnMigratePlans');
  if (btnMigratePlans) {
    btnMigratePlans.addEventListener('click', async () => {
      try {
        const baseUrl =
          window.location.origin && window.location.origin !== 'null'
            ? window.location.origin
            : window.location.href;
        const url = new URL(`${TREATMENT_ENDPOINT}/migrate`, baseUrl);
        const headers = new Headers({ 'Accept': 'application/json', 'Content-Type': 'application/json' });
        const matricula = currentUser?.username?.trim();
        if (matricula) {
          headers.set('X-User-Registration', matricula);
        }
        const payload = { grid: TREATMENT_GRID };
        const filtersPayload = buildTreatmentFilters();
        if (filtersPayload) {
          payload.filters = filtersPayload;
        }
        const response = await fetch(url.toString(), {
          method: 'POST',
          headers,
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          throw new Error('Falha ao migrar planos.');
        }
        await response.json().catch(() => null);
        await fetchTreatmentState({ refreshItems: true });
      } catch (error) {
        console.error('Erro ao migrar planos para tratamento.', error);
      }
    });
  }

  if (btnCloseTreatment) {
    btnCloseTreatment.addEventListener('click', async () => {
      if (!state.treatmentBatchId) {
        return;
      }
      btnCloseTreatment.disabled = true;
      btnCloseTreatment.setAttribute('aria-disabled', 'true');

      try {
        const baseUrl =
          window.location.origin && window.location.origin !== 'null'
            ? window.location.origin
            : window.location.href;
        const url = new URL(`${TREATMENT_ENDPOINT}/close`, baseUrl);
        const headers = new Headers({ 'Accept': 'application/json', 'Content-Type': 'application/json' });
        const matricula = currentUser?.username?.trim();
        if (matricula) {
          headers.set('X-User-Registration', matricula);
        }
        const payload = { lote_id: state.treatmentBatchId };
        const response = await fetch(url.toString(), {
          method: 'POST',
          headers,
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          throw new Error('Falha ao encerrar o lote.');
        }
        await response.json().catch(() => null);
        await fetchTreatmentState({ refreshItems: true });
      } catch (error) {
        console.error('Erro ao encerrar lote de tratamento.', error);
        if (state.treatmentBatchId) {
          btnCloseTreatment.disabled = false;
          btnCloseTreatment.setAttribute('aria-disabled', 'false');
        }
      }
    });
  }

  (async () => {
    if (!canAccessBase()) {
      toggleButtons({ start: true, pause: false, cont: false });
      setStatus(defaultMessages.idle);
      return;
    }
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
    if (!canAccessBase()) {
      return;
    }
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
  setupMainTabsSwitching();
});
