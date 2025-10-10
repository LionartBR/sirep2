export function registerPlansModule(context) {
  const state = context;
  const {
    plansSelection,
    plansTableBody,
    plansColumnCount,
    plansActionsMenuContainer,
    plansActionsTrigger,
    plansActionsMenu,
    plansSelectAllAction,
    plansSelectAllLabel,
    plansLockAction,
    plansLockActionLabel,
    plansActionsSeparator,
    filtersState,
    plansPagerPrevBtn,
    plansPagerNextBtn,
    plansPagerLabel,
    plansPagerRange,
    PLANS_ENDPOINT,
    DEFAULT_PLAN_PAGE_SIZE,
  } = context;

  const plansPager = context.plansPager;
  const planCheckboxSelector = "input[type='checkbox'][data-plan-checkbox]";
  const occurrenceSituacaoCodes =
    Array.isArray(context.OCCURRENCE_SITUATION_CODES) && context.OCCURRENCE_SITUATION_CODES.length
      ? [...context.OCCURRENCE_SITUATION_CODES]
      : ['SIT_ESPECIAL', 'GRDE_EMITIDA'];

  state.isProcessingPlanLock = false;
  if (!(state.planMetadata instanceof Map)) {
    state.planMetadata = new Map();
  }

  const getPlanRowById = (planId) => {
    if (!plansTableBody || !planId) {
      return null;
    }
    const rows = plansTableBody.querySelectorAll('tr[data-plan-id]');
    for (const row of rows) {
      if (row instanceof HTMLElement && row.dataset.planId === planId) {
        return row;
      }
    }
    return null;
  };

  const selectionHasBlockedRows = () => {
    if (!plansSelection.size || !plansTableBody) {
      return false;
    }
    for (const planId of plansSelection) {
      const row = getPlanRowById(planId);
      if (row?.dataset.planBlocked === 'true') {
        return true;
      }
    }
    return false;
  };

  const selectionHasQueuedRows = () => {
    if (!plansSelection.size) {
      return false;
    }
    if (!(state.planMetadata instanceof Map)) {
      return false;
    }
    for (const planId of plansSelection) {
      const metadata = state.planMetadata.get(planId);
      if (metadata?.queued) {
        return true;
      }
    }
    return false;
  };

  const selectionHasTreatmentStatus = () => {
    if (!plansSelection.size) {
      return false;
    }
    if (!(state.planMetadata instanceof Map)) {
      return false;
    }
    for (const planId of plansSelection) {
      const metadata = state.planMetadata.get(planId);
      if (metadata?.statusInTreatment) {
        return true;
      }
    }
    return false;
  };

  const isStatusInTreatment = (value) => {
    if (!value) {
      return false;
    }
    const text = String(value).trim().toLowerCase();
    if (!text) {
      return false;
    }
    const compact = text.replace(/\s+/g, ' ');
    if (compact === 'em tratamento' || compact === 'in treatment') {
      return true;
    }
    return compact.includes('tratamento') || compact.includes('treatment');
  };

  const buildPlansActionUrl = (path) => {
    const baseUrl =
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : window.location.href;
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return new URL(`${PLANS_ENDPOINT}${normalizedPath}`, baseUrl);
  };

  const performPlansMutation = async (path, body) => {
    const url = buildPlansActionUrl(path);
    const headers = new Headers({ Accept: 'application/json', 'Content-Type': 'application/json' });
    const matricula = state.currentUser?.username?.trim();
    if (matricula) {
      headers.set('X-User-Registration', matricula);
    }
    const response = await fetch(url.toString(), {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error('Falha ao atualizar o bloqueio dos planos.');
    }
    return response.json().catch(() => null);
  };

  const requestBlockPlans = (planIds, { motivo = null, expiresAt = null } = {}) =>
    performPlansMutation('/block', {
      plano_ids: planIds,
      motivo,
      expires_at: expiresAt,
    });

  const requestUnblockPlans = (planIds) =>
    performPlansMutation('/unblock', {
      plano_ids: planIds,
    });

  const updateLockButtonIcon = (button, { locked, planNumber, planId }) => {
    if (!(button instanceof HTMLElement)) {
      return;
    }
    let icon = button.querySelector('i');
    if (!(icon instanceof HTMLElement)) {
      icon = document.createElement('i');
      icon.setAttribute('aria-hidden', 'true');
      button.appendChild(icon);
    }
    icon.setAttribute('data-feather', locked ? 'unlock' : 'lock');
    button.dataset.locked = locked ? 'true' : 'false';
    button.setAttribute('aria-pressed', locked ? 'true' : 'false');
    const identifier = planNumber || planId || '';
    const actionLabel = locked ? 'Desbloquear plano' : 'Bloquear plano';
    const label = identifier ? `${actionLabel} ${identifier}` : actionLabel;
    button.setAttribute('aria-label', label);
    button.title = label;
  };

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
    const allCheckboxes = plansTableBody
      ? plansTableBody.querySelectorAll(`${planCheckboxSelector}`)
      : [];
    const totalCheckboxes = allCheckboxes.length;
    const checkedCheckboxes = plansTableBody
      ? plansTableBody.querySelectorAll(`${planCheckboxSelector}:checked`)
      : [];
    const checkedCount = checkedCheckboxes.length;
    const selectionCount = Math.max(plansSelection.size, checkedCount);
    const hasSelection = selectionCount > 0;
    const allSelected = totalCheckboxes > 0 && checkedCount === totalCheckboxes;

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
      const isDisabled = totalCheckboxes === 0;
      plansSelectAllAction.disabled = isDisabled;
      plansSelectAllAction.setAttribute('aria-disabled', String(isDisabled));
      plansSelectAllAction.dataset.mode = allSelected ? 'clear' : 'select';
      if (plansSelectAllLabel) {
        plansSelectAllLabel.textContent = allSelected ? 'Desmarcar todos' : 'Selecionar todos';
      }
    }

    const viewDetailsAction = plansActionsMenu.querySelector('[data-action="view-details"]');
    if (viewDetailsAction instanceof HTMLElement) {
      const isExactlyOneSelected = selectionCount === 1;
      viewDetailsAction.disabled = !isExactlyOneSelected;
      viewDetailsAction.setAttribute('aria-disabled', String(!isExactlyOneSelected));
      if (!isExactlyOneSelected) {
        viewDetailsAction.title = 'Selecione apenas um plano para ver os detalhes';
      } else {
        viewDetailsAction.removeAttribute('title');
      }
    }

    if (plansLockAction instanceof HTMLElement) {
      const intent = selectionHasBlockedRows() ? 'unblock' : 'block';
      const hasQueuedSelection = selectionHasQueuedRows();
      const hasTreatmentSelection = selectionHasTreatmentStatus();
      const shouldDisable =
        !hasSelection ||
        state.isProcessingPlanLock ||
        (intent === 'block' && (hasQueuedSelection || hasTreatmentSelection));
      plansLockAction.dataset.intent = intent;
      plansLockAction.disabled = shouldDisable;
      plansLockAction.setAttribute('aria-disabled', String(shouldDisable));
      plansLockAction.removeAttribute('title');
      if (plansLockActionLabel) {
        plansLockActionLabel.textContent = intent === 'unblock' ? 'Desbloquear' : 'Bloquear';
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

  const closePlansActionsMenu = ({ focusTrigger = false } = {}) => {
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

  const openPlansActionsMenu = ({ focusFirst = false } = {}) => {
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
    let normalizedId = '';
    if (typeof planId === 'string') {
      normalizedId = planId.trim();
    } else if (typeof planId === 'number') {
      normalizedId = String(planId);
    } else if (planId && typeof planId === 'object' && 'toString' in planId) {
      normalizedId = String(planId).trim();
    }
    if (!normalizedId) {
      return;
    }
    if (checked) {
      plansSelection.add(normalizedId);
    } else {
      plansSelection.delete(normalizedId);
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

  const renderPlansPlaceholder = (message, modifier = 'empty') => {
    if (!plansTableBody) {
      return;
    }
    plansSelection.clear();
    if (state.planMetadata instanceof Map) {
      state.planMetadata.clear();
    }
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
    const hasActiveFilters = typeof context.hasActiveFilters === 'function' && context.hasActiveFilters();
    const showFilterContext = isEmptyState && hasActiveFilters;
    if (showFilterContext) {
      const hint = document.createElement('p');
      hint.className = 'table-empty__hint';
      hint.textContent = 'Os filtros selecionados podem estar escondendo alguns planos.';
      wrapper.appendChild(hint);

      const chipsHolder = document.createElement('div');
      chipsHolder.className = 'table-active-filters table-active-filters--floating';
      chipsHolder.dataset.filterChips = 'plans-empty';
      wrapper.appendChild(chipsHolder);
      if (typeof context.attachFilterChipHandler === 'function') {
        context.attachFilterChipHandler(chipsHolder);
      }

      const actions = document.createElement('div');
      actions.className = 'table-empty__actions';
      const clearButton = document.createElement('button');
      clearButton.type = 'button';
      clearButton.className = 'table-empty__clear';
      clearButton.textContent = 'Limpar filtros';
      clearButton.addEventListener('click', () => {
        if (typeof context.clearAllFilters === 'function') {
          context.clearAllFilters();
        }
      });
      actions.appendChild(clearButton);
      wrapper.appendChild(actions);
    }

    cell.appendChild(wrapper);
    row.appendChild(cell);
    plansTableBody.appendChild(row);
    if (isEmptyState) {
      state.plansHasResults = false;
      if (typeof context.renderFilterChips === 'function') {
        context.renderFilterChips();
      }
    }
  };

  const renderPlanRows = (items) => {
    if (!plansTableBody) {
      return;
    }
    plansTableBody.innerHTML = '';
    plansSelection.clear();
    closePlansActionsMenu();
    if (!(state.planMetadata instanceof Map)) {
      state.planMetadata = new Map();
    } else {
      state.planMetadata.clear();
    }
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
      const planNumber =
        typeof planNumberRaw === 'string'
          ? planNumberRaw.trim()
          : typeof planNumberRaw === 'number'
            ? String(planNumberRaw)
            : '';
      const planIdRaw = item?.plan_id ?? item?.planId ?? '';
      let planId = '';
      if (typeof planIdRaw === 'string') {
        planId = planIdRaw.trim();
      } else if (planIdRaw && typeof planIdRaw === 'object' && 'toString' in planIdRaw) {
        planId = String(planIdRaw).trim();
      }
      if (!planId && planNumber) {
        planId = planNumber;
      }
      if (planId) {
        row.dataset.planId = planId;
      }
      if (planNumber) {
        row.dataset.planNumber = planNumber;
      }

      const queueInfo = item?.treatment_queue ?? null;
      const isQueued = Boolean(queueInfo?.enqueued);
      const isBlocked = Boolean(item?.blocked);
      row.dataset.planBlocked = isBlocked ? 'true' : 'false';
      row.dataset.planQueued = isQueued ? 'true' : 'false';
      const rawStatus = typeof item?.status === 'string' ? item.status : '';
      const formattedStatus = context.formatStatusLabel(item?.status);
      const normalizedStatus = String(formattedStatus || rawStatus || '')
        .trim()
        .toLowerCase();
      const serverInTreatment = item?.em_tratamento === true;
      const statusInTreatment = serverInTreatment || isStatusInTreatment(normalizedStatus);
      row.dataset.planStatus = normalizedStatus || '';
      row.dataset.planInTreatment = statusInTreatment ? 'true' : 'false';
      if (isBlocked) {
        row.classList.add('table__row--blocked');
      }
      if (statusInTreatment) {
        row.classList.add('table__row--in-treatment');
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

      const statusCell = document.createElement('td');
      statusCell.className = 'table__cell';
      statusCell.textContent = context.formatStatusLabel(item?.status);
      row.appendChild(statusCell);

      const daysCell = document.createElement('td');
      daysCell.className = 'table__cell';
      daysCell.textContent = context.formatDaysValue(item?.days_overdue);
      row.appendChild(daysCell);

      const balanceCell = document.createElement('td');
      balanceCell.className = 'table__cell';
      balanceCell.textContent = context.formatCurrencyValue(item?.balance);
      row.appendChild(balanceCell);

      const statusDateCell = document.createElement('td');
      statusDateCell.className = 'table__cell';
      statusDateCell.textContent = context.formatDateLabel(item?.status_date);
      row.appendChild(statusDateCell);

      if (typeof context.applyCopyBehaviorToRow === 'function') {
        context.applyCopyBehaviorToRow(row);
      }

      if (isQueued) {
        row.classList.add('table__row--queued');
      }

      const actionsCell = document.createElement('td');
      actionsCell.className = 'table__cell table__cell--select';

      const actionsWrapper = document.createElement('div');
      actionsWrapper.className = 'table__select-actions';

      const selectWrapper = document.createElement('span');
      selectWrapper.className = 'table__select-wrapper';

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.dataset.planCheckbox = 'true';
      if (planId) {
        checkbox.dataset.planId = planId;
      }
      if (planNumber) {
        checkbox.dataset.planNumber = planNumber;
      }
      checkbox.dataset.planQueued = isQueued ? 'true' : 'false';
      const labelIdentifier = planNumber || planId;
      checkbox.setAttribute(
        'aria-label',
        labelIdentifier ? `Selecionar plano ${labelIdentifier}` : 'Selecionar plano',
      );
      if (isBlocked) {
        checkbox.title = 'Plano bloqueado';
      } else {
        checkbox.removeAttribute('title');
      }
      checkbox.addEventListener('change', () => {
        const isChecked = checkbox.checked;
        setPlanSelection(planId, isChecked, { checkbox, row });
        updatePlansActionsMenuState();
      });
      selectWrapper.appendChild(checkbox);
      actionsWrapper.appendChild(selectWrapper);

      const lockButton = document.createElement('button');
      lockButton.type = 'button';
      lockButton.className = 'table__lock-toggle';
      if (planId) {
        lockButton.dataset.planId = planId;
      }
      if (planNumber) {
        lockButton.dataset.planNumber = planNumber;
      }
      lockButton.dataset.planQueued = isQueued ? 'true' : 'false';
      updateLockButtonIcon(lockButton, {
        locked: isBlocked,
        planNumber,
        planId,
      });
      lockButton.dataset.statusInTreatment = statusInTreatment ? 'true' : 'false';
      if (!planId || statusInTreatment) {
        lockButton.disabled = true;
        lockButton.setAttribute('aria-disabled', 'true');
        lockButton.removeAttribute('title');
      } else {
        lockButton.disabled = false;
        lockButton.setAttribute('aria-disabled', 'false');
        lockButton.removeAttribute('title');
      }
      lockButton.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (!planId) {
          return;
        }
        const statusLocked = lockButton.dataset.locked === 'true';
        const statusInTreatmentButton = lockButton.dataset.statusInTreatment === 'true';
        if (!statusLocked && statusInTreatmentButton) {
          context.showToast?.('Plans in treatment cannot be locked');
          return;
        }
        const locked = lockButton.dataset.locked === 'true';
        void handlePlanLockToggle({
          planId,
          planNumber,
          button: lockButton,
          currentlyLocked: locked,
        });
      });
      actionsWrapper.appendChild(lockButton);

      const refreshButton = document.createElement('button');
      refreshButton.type = 'button';
      refreshButton.className = 'table__refresh-toggle';
      if (planId) {
        refreshButton.dataset.planId = planId;
      }
      if (planNumber) {
        refreshButton.dataset.planNumber = planNumber;
      }
      const refreshIcon = document.createElement('i');
      refreshIcon.setAttribute('data-feather', 'refresh-cw');
      refreshIcon.setAttribute('aria-hidden', 'true');
      refreshButton.appendChild(refreshIcon);
      const refreshIdentifier = planNumber || planId || '';
      const refreshLabel = refreshIdentifier
        ? `Atualizar plano ${refreshIdentifier}`
        : 'Atualizar plano';
      refreshButton.setAttribute('aria-label', refreshLabel);
      refreshButton.title = refreshLabel;
      refreshButton.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
      });
      actionsWrapper.appendChild(refreshButton);

      actionsCell.appendChild(actionsWrapper);

      row.appendChild(actionsCell);
      plansTableBody.appendChild(row);

      row.addEventListener('dblclick', (event) => {
        const interactive = event.target instanceof HTMLElement
          ? event.target.closest('button, input, a')
          : null;
        if (interactive) {
          return;
        }
        event.preventDefault();
        if (typeof context.showPlanDetails === 'function') {
          let planData = item;
          if (state.planMetadata instanceof Map) {
            const metadataEntry = state.planMetadata.get(planId) ??
              (planNumber ? state.planMetadata.get(planNumber) : null);
            if (metadataEntry?.detail) {
              planData = metadataEntry.detail;
            }
          }
          context.showPlanDetails(planData);
        }
      });

      if (planId && state.planMetadata instanceof Map) {
        const previous = state.planMetadata.get(planId) ?? {};
        state.planMetadata.set(planId, {
          ...previous,
          queued: isQueued,
          statusInTreatment,
          summary: item,
        });
      }
      if (planNumber && state.planMetadata instanceof Map) {
        const previousNumberEntry = state.planMetadata.get(planNumber) ?? {};
        state.planMetadata.set(planNumber, {
          ...previousNumberEntry,
          summary: item,
        });
      }
    });

    if (typeof context.renderFilterChips === 'function') {
      context.renderFilterChips();
    }
    updatePlansActionsMenuState();
    window.feather?.replace();
  };

  const mutatePlanLockState = async ({ planIds, unblock, disableMenu = true }) => {
    if (!Array.isArray(planIds) || !planIds.length) {
      return false;
    }

    const ids = planIds.filter((value) => typeof value === 'string' && value.trim().length > 0);
    if (!ids.length) {
      return false;
    }

    const shouldDisableMenu = disableMenu;
    if (shouldDisableMenu) {
      state.isProcessingPlanLock = true;
      updatePlansActionsMenuState();
    }

    let success = false;
    try {
      if (unblock) {
        await requestUnblockPlans(ids);
      } else {
        await requestBlockPlans(ids);
      }
      const successMessage = unblock
        ? (ids.length > 1 ? 'Planos desbloqueados com sucesso.' : 'Plano desbloqueado.')
        : (ids.length > 1 ? 'Planos bloqueados com sucesso.' : 'Plano bloqueado.');
      context.showToast?.(successMessage);
      ids.forEach((id) => plansSelection.delete(id));
      success = true;
      await refreshPlans({ showLoading: false });
    } catch (error) {
      console.error('Erro ao atualizar bloqueio dos planos.', error);
      const failureMessage = unblock
        ? (ids.length > 1
            ? 'Não foi possível desbloquear os planos selecionados.'
            : 'Não foi possível desbloquear o plano.')
        : (ids.length > 1
            ? 'Não foi possível bloquear os planos selecionados.'
            : 'Não foi possível bloquear o plano.');
      context.showToast?.(failureMessage);
    } finally {
      if (shouldDisableMenu) {
        state.isProcessingPlanLock = false;
      }
      updatePlansActionsMenuState();
    }

    return success;
  };

  const handlePlanLockToggle = async ({ planId, planNumber, button, currentlyLocked }) => {
    if (!planId || !(button instanceof HTMLElement)) {
      return;
    }
    button.disabled = true;
    button.setAttribute('aria-disabled', 'true');
    const success = await mutatePlanLockState({
      planIds: [planId],
      unblock: currentlyLocked,
      disableMenu: false,
    });
    if (!success) {
      button.disabled = false;
      button.setAttribute('aria-disabled', 'false');
      updateLockButtonIcon(button, {
        locked: currentlyLocked,
        planNumber,
        planId,
      });
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
    plansPager.currentCursor = null;
    plansPager.currentDirection = null;
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

  const resolvePlansCursorForRequest = (direction) => {
    let requestDirection = direction;
    let cursorToken = null;

    if (requestDirection === 'next' && plansPager.nextCursor) {
      cursorToken = plansPager.nextCursor;
    } else if (requestDirection === 'prev' && plansPager.prevCursor) {
      cursorToken = plansPager.prevCursor;
    } else if (!requestDirection) {
      const hasStoredCursor = plansPager.currentCursor && plansPager.currentDirection;
      if (plansPager.page > 1 && hasStoredCursor) {
        requestDirection = plansPager.currentDirection;
        cursorToken = plansPager.currentCursor;
      }
    }

    if (!cursorToken) {
      requestDirection = null;
    }

    return { cursor: cursorToken, direction: requestDirection };
  };

  const buildPlansRequest = ({ direction = null } = {}) => {
    const baseUrl =
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : window.location.href;
    const url = new URL(PLANS_ENDPOINT, baseUrl);
    url.searchParams.set('page', String(plansPager.page));
    url.searchParams.set('page_size', String(plansPager.pageSize));

    const { cursor, direction: requestDirection } = resolvePlansCursorForRequest(direction);
    if (cursor && requestDirection) {
      url.searchParams.set('cursor', cursor);
      url.searchParams.set('direction', requestDirection);
    }

    if (state.currentPlansSearchTerm) {
      url.searchParams.set('q', state.currentPlansSearchTerm);
    }
    if (typeof context.getPlansSearchConfig === 'function') {
      const searchConfig = context.getPlansSearchConfig();
      if (searchConfig?.tipoDoc) {
        url.searchParams.set('tipo_doc', searchConfig.tipoDoc);
      }
    }
    if (filtersState.situacao.length) {
      filtersState.situacao.forEach((value) => {
        url.searchParams.append('situacao', value);
      });
    }
    if (filtersState.diasRange) {
      url.searchParams.set('dias_range', filtersState.diasRange);
    }
    if (typeof filtersState.saldoBucket === 'string' && filtersState.saldoBucket) {
      url.searchParams.set('saldo_bucket', filtersState.saldoBucket);
    }
    // dt_sit_range filter removed

    if (occurrenceSituacaoCodes.length) {
      const matchesOccurrenceFilter =
        Array.isArray(filtersState.situacao) &&
        filtersState.situacao.length === occurrenceSituacaoCodes.length &&
        occurrenceSituacaoCodes.every((code) => filtersState.situacao.includes(code));
      if (matchesOccurrenceFilter) {
        url.searchParams.set('occurrences_only', 'true');
      }
    }

    return {
      url: url.toString(),
      cursor,
      direction: requestDirection,
    };
  };

  const refreshPlans = async ({ showLoading, direction = null } = {}) => {
    if (!plansTableBody || state.isFetchingPlans) {
      return;
    }
    if (!context.canAccessBase?.()) {
      state.plansLoaded = true;
      renderPlansPlaceholder('Área disponível apenas para perfil Gestor.', 'empty');
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
      const matricula = state.currentUser?.username?.trim();
      if (matricula) {
        requestHeaders.set('X-User-Registration', matricula);
      }
      const requestConfig = buildPlansRequest({ direction });
      const response = await fetch(requestConfig.url, {
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
        filtersState.diasRange =
          typeof filtersResponse.dias_range === 'string' ? filtersResponse.dias_range : null;
        filtersState.saldoBucket =
          typeof filtersResponse.saldo_bucket === 'string' ? filtersResponse.saldo_bucket : null;
      } else {
        filtersState.situacao = [];
        filtersState.diasRange = null;
        filtersState.saldoBucket = null;
      }
      if (typeof context.syncFilterInputs === 'function') {
        context.syncFilterInputs();
      }
      if (typeof context.renderFilterChips === 'function') {
        context.renderFilterChips();
      }

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
        if (direction === 'prev') {
          plansPager.hasMore = true;
        }
      } else {
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
      if (requestConfig.direction && requestConfig.cursor) {
        plansPager.currentCursor = requestConfig.cursor;
        plansPager.currentDirection = requestConfig.direction;
      } else {
        plansPager.currentCursor = null;
        plansPager.currentDirection = null;
      }
      updatePlansPagerUI();
      if (typeof context.scheduleOccurrencesCountUpdate === 'function') {
        context.scheduleOccurrencesCountUpdate();
      }
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
      if (target.getAttribute('aria-disabled') === 'true' || target.disabled) {
        event.preventDefault();
        event.stopPropagation();
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
        updatePlansActionsMenuState();
        closePlansActionsMenu();
        return;
      }
      if (action === 'lock') {
        const intent = target.dataset.intent === 'unblock' ? 'unblock' : 'block';
        if (intent === 'block') {
          const hasQueuedSelection = selectionHasQueuedRows();
          const hasTreatmentSelection = selectionHasTreatmentStatus();
          if (hasQueuedSelection || hasTreatmentSelection) {
            closePlansActionsMenu();
            context.showToast?.('Plans in treatment cannot be locked');
            return;
          }
        }

        const selectedIds = Array.from(plansSelection);
        closePlansActionsMenu();
        if (!selectedIds.length) {
          return;
        }
        if (intent === 'unblock') {
          void mutatePlanLockState({ planIds: selectedIds, unblock: true });
        } else {
          void mutatePlanLockState({ planIds: selectedIds, unblock: false });
        }
        return;
      }
      if (action === 'view-details') {
        const selectedIds = Array.from(plansSelection);
        closePlansActionsMenu();
        if (selectedIds.length !== 1) {
          context.showToast?.('Selecione apenas um plano para ver os detalhes.');
          return;
        }
        const selectedId = selectedIds[0];
        let metadataEntry = null;
        if (state.planMetadata instanceof Map) {
          metadataEntry = state.planMetadata.get(selectedId) ?? null;
          if (!metadataEntry) {
            for (const [key, value] of state.planMetadata.entries()) {
              if (key === selectedId) {
                metadataEntry = value;
                break;
              }
              const candidateNumber = value?.summary?.number ?? value?.summary?.plan_number;
              if (candidateNumber && String(candidateNumber) === selectedId) {
                metadataEntry = value;
                break;
              }
            }
          }
        }
        const detailPlan = metadataEntry?.detail ?? metadataEntry?.summary ?? null;
        if (!detailPlan) {
          context.showToast?.('Detalhes indisponíveis para o plano selecionado.');
          return;
        }
        context.showPlanDetails?.(detailPlan);
        return;
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

  context.updatePlansActionsMenuState = updatePlansActionsMenuState;
  context.openPlansActionsMenu = openPlansActionsMenu;
  context.closePlansActionsMenu = closePlansActionsMenu;
  context.selectAllPlansOnPage = selectAllPlansOnPage;
  context.deselectAllPlansOnPage = deselectAllPlansOnPage;
  context.renderPlansPlaceholder = renderPlansPlaceholder;
  context.renderPlanRows = renderPlanRows;
  context.resetPlansPagination = resetPlansPagination;
  context.updatePlansPagerUI = updatePlansPagerUI;
  context.refreshPlans = refreshPlans;
}
