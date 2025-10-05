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

  if (!(context.lockedPlans instanceof Set)) {
    context.lockedPlans = new Set();
  }
  if (typeof context.onLockPlans !== 'function') {
    context.onLockPlans = async () => false;
  }

  state.planRecords = state.planRecords instanceof Map ? state.planRecords : new Map();

  const detailsIconTemplate = (() => {
    if (typeof window === 'undefined') {
      return null;
    }
    try {
      return window.feather?.icons?.['external-link']?.toSvg({ 'aria-hidden': 'true' }) ?? null;
    } catch (error) {
      console.error('Falha ao gerar ícone de detalhes.', error);
      return null;
    }
  })();

  const lockIconTemplate = (() => {
    if (typeof window === 'undefined') {
      return null;
    }
    try {
      return window.feather?.icons?.lock?.toSvg({ 'aria-hidden': 'true' }) ?? null;
    } catch (error) {
      console.error('Falha ao gerar ícone de bloqueio.', error);
      return null;
    }
  })();

  const unlockIconTemplate = (() => {
    if (typeof window === 'undefined') {
      return null;
    }
    try {
      return window.feather?.icons?.unlock?.toSvg({ 'aria-hidden': 'true' }) ?? null;
    } catch (error) {
      console.error('Falha ao gerar ícone de desbloqueio.', error);
      return null;
    }
  })();

  const findPlanRow = (planId) => {
    if (!plansTableBody || !planId) {
      return null;
    }
    const selectorId = typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(planId) : planId.replace(/"/g, '\\"');
    return plansTableBody.querySelector(`[data-plan-id="${selectorId}"]`);
  };

  const applyPlanLockedState = (row, locked) => {
    if (!row) {
      return;
    }
    row.classList.toggle('table__row--locked', locked);
    row.dataset.planLocked = locked ? 'true' : 'false';

    const checkbox = row.querySelector(planCheckboxSelector);
    if (checkbox instanceof HTMLInputElement) {
      if (locked) {
        checkbox.dataset.lockPrevDisabled = checkbox.disabled ? 'true' : 'false';
        if (checkbox.disabled) {
          checkbox.dataset.lockPrevDisabledTitle = checkbox.title || '';
        } else if (checkbox.dataset.lockPrevDisabledTitle === undefined) {
          checkbox.dataset.lockPrevDisabledTitle = checkbox.dataset.defaultTitle || checkbox.title || '';
        }
        if (checkbox.dataset.lockPrevDisabled !== 'true') {
          checkbox.disabled = false;
          checkbox.removeAttribute('aria-disabled');
        }
        checkbox.title = 'Plano bloqueado';
      } else if (checkbox.dataset.lockPrevDisabled !== undefined) {
        const wasDisabled = checkbox.dataset.lockPrevDisabled === 'true';
        if (wasDisabled) {
          checkbox.disabled = true;
          checkbox.setAttribute('aria-disabled', 'true');
          if (checkbox.dataset.lockPrevDisabledTitle) {
            checkbox.title = checkbox.dataset.lockPrevDisabledTitle;
          }
        } else {
          checkbox.disabled = false;
          checkbox.removeAttribute('aria-disabled');
          if (checkbox.dataset.defaultTitle) {
            checkbox.title = checkbox.dataset.defaultTitle;
          }
        }
        delete checkbox.dataset.lockPrevDisabled;
        delete checkbox.dataset.lockPrevDisabledTitle;
      }
    }

    const lockButton = row.querySelector('.table__row-action--lock');
    if (lockButton instanceof HTMLButtonElement) {
      if (locked) {
        lockButton.disabled = false;
        lockButton.removeAttribute('aria-disabled');
        const labelTarget = lockButton.dataset.planLabel || '';
        const unlockLabel = labelTarget
          ? `Desbloquear plano ${labelTarget}`
          : 'Desbloquear plano';
        lockButton.setAttribute('aria-label', unlockLabel);
        lockButton.title = unlockLabel;
        lockButton.innerHTML =
          unlockIconTemplate ?? '<span class="table__row-action-fallback" aria-hidden="true">🔓</span>';
        lockButton.dataset.locked = 'true';
      } else {
        lockButton.disabled = false;
        lockButton.removeAttribute('aria-disabled');
        const labelTarget = lockButton.dataset.planLabel || '';
        const lockLabel = labelTarget
          ? `Bloquear plano ${labelTarget}`
          : 'Bloquear plano';
        lockButton.setAttribute('aria-label', lockLabel);
        lockButton.title = lockLabel;
        lockButton.dataset.defaultTitle = lockLabel;
        lockButton.innerHTML =
          lockIconTemplate ?? '<span class="table__row-action-fallback" aria-hidden="true">🔒</span>';
        lockButton.dataset.locked = 'false';
      }
    }
  };

  const requestPlanDetails = (details) => {
    let handled = false;
    try {
      handled = context.onViewPlanDetails?.(details) === true;
    } catch (error) {
      console.error('Erro ao executar callback de detalhes do plano.', error);
    }
    if (handled) {
      return;
    }
    if (
      typeof window !== 'undefined' &&
      typeof window.SirepUtils?.openPlanDetails === 'function'
    ) {
      try {
        window.SirepUtils.openPlanDetails(details);
        return;
      } catch (error) {
        console.error('Falha ao abrir detalhes do plano via SirepUtils.', error);
      }
    }
    document.dispatchEvent(
      new CustomEvent('sirep:view-plan-details', {
        detail: details,
      }),
    );
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
    const totalEnabledCheckboxes = plansTableBody
      ? plansTableBody.querySelectorAll(`${planCheckboxSelector}:not(:disabled)`).length
      : 0;
    const checkedEnabledCheckboxes = plansTableBody
      ? plansTableBody.querySelectorAll(`${planCheckboxSelector}:checked:not(:disabled)`).length
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

    if (plansActionsMenu) {
      const lockMenuAction = plansActionsMenu.querySelector('[data-action="lock"]');
      if (lockMenuAction instanceof HTMLElement) {
        const selectedIds = new Set(plansSelection);
        if (plansTableBody) {
          const checkedBoxes = plansTableBody.querySelectorAll(`${planCheckboxSelector}:checked`);
          checkedBoxes.forEach((checkbox) => {
            if (!(checkbox instanceof HTMLInputElement)) {
              return;
            }
            const row = checkbox.closest('tr');
            const planId = checkbox.dataset.planId ?? row?.dataset.planId ?? '';
            if (planId) {
              selectedIds.add(planId);
            }
          });
        }
        let hasLockedSelected = false;
        selectedIds.forEach((planId) => {
          if (context.lockedPlans.has(planId)) {
            hasLockedSelected = true;
          }
        });
        const labelSpan = lockMenuAction.querySelector('span');
        const mode = hasLockedSelected ? 'unlock' : 'lock';
        const ariaLabel = hasLockedSelected
          ? 'Desbloquear selecionados'
          : 'Bloquear selecionados';
        if (labelSpan) {
          labelSpan.textContent = hasLockedSelected ? 'Desbloquear' : 'Bloquear';
        }
        lockMenuAction.dataset.mode = mode;
        lockMenuAction.setAttribute('aria-label', ariaLabel);
        lockMenuAction.title = ariaLabel;
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

  const setPlansLocked = (planIds, locked = true) => {
    if (!Array.isArray(planIds) || planIds.length === 0) {
      return;
    }
    const normalized = planIds
      .map((value) => (typeof value === 'string' ? value.trim() : ''))
      .filter((value, index, array) => value.length > 0 && array.indexOf(value) === index);
    if (!normalized.length) {
      return;
    }

    normalized.forEach((planId) => {
      if (locked) {
        context.lockedPlans.add(planId);
      } else {
        context.lockedPlans.delete(planId);
      }
      const record = state.planRecords.get(planId);
      if (record) {
        record.locked = locked;
      }
      const row = findPlanRow(planId);
      applyPlanLockedState(row, locked);
    });

    updatePlansActionsMenuState();
  };

  const ensurePlansEndpoint = () => context.PLANS_ENDPOINT || '/api/plans';

  const buildAuthHeaders = () => {
    const headers = new Headers({
      Accept: 'application/json',
      'Content-Type': 'application/json',
    });
    const matricula = state.currentUser?.username?.trim();
    if (matricula) {
      headers.set('X-User-Registration', matricula);
    }
    return headers;
  };

  const performPlanBlock = async (record) => {
    if (!record?.uuid) {
      return false;
    }
    const response = await fetch(`${ensurePlansEndpoint()}/block`, {
      method: 'POST',
      headers: buildAuthHeaders(),
      body: JSON.stringify({
        plano_id: record.uuid,
        motivo: record.lockReason ?? null,
        expires_at: record.expiresAt ?? null,
      }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const detail = payload?.detail || 'Não foi possível bloquear o plano.';
      throw new Error(detail);
    }
    await response.json().catch(() => null);
    return true;
  };

  const performPlanUnblock = async (record) => {
    if (!record?.uuid) {
      return false;
    }
    const response = await fetch(`${ensurePlansEndpoint()}/unblock`, {
      method: 'POST',
      headers: buildAuthHeaders(),
      body: JSON.stringify({ plano_id: record.uuid }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const detail = payload?.detail || 'Não foi possível desbloquear o plano.';
      throw new Error(detail);
    }
    await response.json().catch(() => null);
    return true;
  };

  const resolvePlanEntries = (planIds) => {
    if (!Array.isArray(planIds)) {
      return [];
    }
    return planIds
      .map((value) => (typeof value === 'string' ? value.trim() : ''))
      .filter((value, index, array) => value.length > 0 && array.indexOf(value) === index)
      .map((key) => ({ key, record: state.planRecords.get(key) }))
      .filter((entry) => Boolean(entry.record && entry.record.uuid));
  };

  const lockPlansRemotely = async (entries) => {
    const successes = [];
    for (const entry of entries) {
      const { key, record } = entry;
      if (!record || record.locked) {
        continue;
      }
      try {
        await performPlanBlock(record);
        record.locked = true;
        successes.push(key);
      } catch (error) {
        console.error('Falha ao bloquear plano.', error);
        if (typeof context.showToast === 'function') {
          const label = record.displayNumber || record.number || record.numero_plano || key;
          context.showToast(`Não foi possível bloquear o plano ${label}.`);
        }
      }
    }
    return successes;
  };

  const unlockPlansRemotely = async (entries) => {
    const successes = [];
    for (const entry of entries) {
      const { key, record } = entry;
      if (!record || !record.locked) {
        continue;
      }
      try {
        await performPlanUnblock(record);
        record.locked = false;
        successes.push(key);
      } catch (error) {
        console.error('Falha ao desbloquear plano.', error);
        if (typeof context.showToast === 'function') {
          const label = record.displayNumber || record.number || record.numero_plano || key;
          context.showToast(`Não foi possível desbloquear o plano ${label}.`);
        }
      }
    }
    return successes;
  };

  const lockPlans = async (planIds) => {
    const entries = resolvePlanEntries(planIds).filter((entry) => !entry.record.locked);
    if (!entries.length) {
      return;
    }
    const successes = await lockPlansRemotely(entries);
    if (successes.length) {
      setPlansLocked(successes, true);
      if (typeof document !== 'undefined' && typeof document.dispatchEvent === 'function') {
        document.dispatchEvent(
          new CustomEvent('sirep:lock-plans', {
            detail: {
              planIds: successes,
              locked: true,
            },
          }),
        );
      }
    }
  };

  const unlockPlans = async (planIds) => {
    const entries = resolvePlanEntries(planIds).filter((entry) => entry.record.locked);
    if (!entries.length) {
      return;
    }
    const successes = await unlockPlansRemotely(entries);
    if (successes.length) {
      setPlansLocked(successes, false);
      if (typeof document !== 'undefined' && typeof document.dispatchEvent === 'function') {
        document.dispatchEvent(
          new CustomEvent('sirep:unlock-plans', {
            detail: {
              planIds: successes,
              locked: false,
            },
          }),
        );
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
    const previousLockedPlans =
      context.lockedPlans instanceof Set ? new Set(context.lockedPlans) : new Set();
    state.planRecords = new Map();
    const lockedPlans = new Set();
    context.lockedPlans = lockedPlans;
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

      const planUuidRaw = item?.plan_id ?? item?.plan_uuid ?? item?.id ?? null;
      const planUuid = planUuidRaw ? String(planUuidRaw).trim() : '';
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
      if (planUuid) {
        row.dataset.planUuid = planUuid;
      }

      const planCell = document.createElement('td');
      planCell.className = 'table__cell';
      const planNumberText = item?.number ?? '';
      const planNumberSpan = document.createElement('span');
      planNumberSpan.textContent = planNumberText;
      planNumberSpan.dataset.copySource = 'plan-number';
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
      const documentSpan = document.createElement('span');
      documentSpan.textContent = context.formatDocument?.(item?.document ?? '') ?? '';
      documentSpan.dataset.copySource = 'plan-document';
      documentCell.appendChild(documentSpan);
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

      const actionsCell = document.createElement('td');
      actionsCell.className = 'table__cell table__cell--select';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.dataset.planCheckbox = 'true';
      if (planId) {
        checkbox.dataset.planId = planId;
      }
      if (planUuid) {
        checkbox.dataset.planUuid = planUuid;
      }
      checkbox.setAttribute(
        'aria-label',
        planId ? `Selecionar plano ${planId}` : 'Selecionar plano',
      );
      const checkboxDefaultTitle = planId ? `Selecionar plano ${planId}` : 'Selecionar plano';
      checkbox.title = checkboxDefaultTitle;
      checkbox.dataset.defaultTitle = checkboxDefaultTitle;
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

      const lockButton = document.createElement('button');
      lockButton.type = 'button';
      lockButton.className = 'table__row-action table__row-action--lock';
      if (planId) {
        lockButton.dataset.planId = planId;
      }
      if (planUuid) {
        lockButton.dataset.planUuid = planUuid;
      }
      const lockLabelTarget =
        (planId && planId.trim()) ||
        (typeof planNumberText === 'string' && planNumberText.trim()) ||
        (typeof planNumberRaw === 'number' ? String(planNumberRaw) : '');
      const lockLabel = lockLabelTarget
        ? `Bloquear plano ${lockLabelTarget}`
        : 'Bloquear plano';
      lockButton.dataset.planLabel = lockLabelTarget;
      lockButton.setAttribute('aria-label', lockLabel);
      lockButton.title = lockLabel;
      lockButton.dataset.defaultTitle = lockLabel;
      lockButton.innerHTML =
        lockIconTemplate ?? '<span class="table__row-action-fallback" aria-hidden="true">🔒</span>';

      if (!planId) {
        lockButton.disabled = true;
        lockButton.setAttribute('aria-disabled', 'true');
      }

      lockButton.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (!planId) {
          return;
        }
        const currentlyLocked = context.lockedPlans instanceof Set && context.lockedPlans.has(planId);
        if (currentlyLocked) {
          void unlockPlans([planId]);
        } else {
          void lockPlans([planId]);
        }
      });

      const detailsButton = document.createElement('button');
      detailsButton.type = 'button';
      detailsButton.className = 'table__row-action table__row-action--details';
      if (planId) {
        detailsButton.dataset.planId = planId;
      }
      const detailsLabelTarget =
        (planId && planId.trim()) ||
        (typeof planNumberText === 'string' && planNumberText.trim()) ||
        (typeof planNumberRaw === 'number' ? String(planNumberRaw) : '');
      const detailsLabel = detailsLabelTarget
        ? `Ver detalhes do plano ${detailsLabelTarget}`
        : 'Ver detalhes do plano';
      detailsButton.setAttribute('aria-label', detailsLabel);
      detailsButton.title = detailsLabel;
      detailsButton.innerHTML =
        detailsIconTemplate ?? '<span class="table__row-action-fallback" aria-hidden="true">↗</span>';

      const planDetails = {
        uuid: planUuid,
        planKey: planId,
        number: planId,
        displayNumber: planNumberText,
        document: item?.document ?? '',
        companyName: item?.company_name ?? '',
        status: item?.status ?? '',
        daysOverdue: item?.days_overdue ?? null,
        balance: item?.balance ?? null,
        statusDate: item?.status_date ?? null,
        treatmentQueue: queueInfo,
      };
      if (!planDetails.number) {
        planDetails.number = typeof planNumberRaw === 'number'
          ? String(planNumberRaw)
          : (planNumberRaw || '').toString().trim();
      }
      planDetails.displayNumber = planDetails.displayNumber
        ? String(planDetails.displayNumber)
        : planDetails.number;

      let isLocked = false;
      if (typeof item?.blocked === 'boolean') {
        isLocked = item.blocked;
      } else if (planId) {
        isLocked = previousLockedPlans.has(planId);
      }
      if (planId && isLocked) {
        lockedPlans.add(planId);
      }
      planDetails.locked = isLocked;
      if (planId) {
        state.planRecords.set(planId, planDetails);
      }

      detailsButton.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        requestPlanDetails(planDetails);
      });

      const actionsWrapper = document.createElement('div');
      actionsWrapper.className = 'table__row-actions';
      actionsWrapper.appendChild(checkbox);
      actionsWrapper.appendChild(lockButton);
      actionsWrapper.appendChild(detailsButton);
      actionsCell.appendChild(actionsWrapper);
      row.appendChild(actionsCell);

      plansTableBody.appendChild(row);

      if (isLocked) {
        context.lockedPlans.add(planId);
      } else {
        context.lockedPlans.delete(planId);
      }

      applyPlanLockedState(row, isLocked);
    });

    context.planRecords = state.planRecords;

    if (typeof context.renderFilterChips === 'function') {
      context.renderFilterChips();
    }
    updatePlansActionsMenuState();
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

  const buildPlansRequestUrl = ({ direction = null } = {}) => {
    const baseUrl =
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : window.location.href;
    const url = new URL(PLANS_ENDPOINT, baseUrl);
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
      updatePlansPagerUI();
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

    plansActionsMenu.addEventListener('click', async (event) => {
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
      } else if (action === 'lock') {
        const selected = new Set(plansSelection);
        if (selected.size === 0 && plansTableBody) {
          const checkedBoxes = plansTableBody.querySelectorAll(`${planCheckboxSelector}:checked`);
          checkedBoxes.forEach((checkbox) => {
            if (!(checkbox instanceof HTMLInputElement)) {
              return;
            }
            const row = checkbox.closest('tr');
            const planId = checkbox.dataset.planId ?? row?.dataset.planId ?? '';
            if (planId) {
              selected.add(planId);
            }
          });
        }
        if (selected.size > 0) {
          const ids = Array.from(selected);
          if (target.dataset.mode === 'unlock') {
            const lockedSelectedCount = ids.filter((planId) => context.lockedPlans.has(planId)).length;
            await unlockPlans(ids);
            if (lockedSelectedCount > 1) {
              ids.forEach((planId) => {
                const row = findPlanRow(planId);
                const checkbox = row?.querySelector(planCheckboxSelector);
                setPlanSelection(planId, false, { checkbox, row });
              });
            }
          } else {
            await lockPlans(ids);
          }
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
  context.requestPlanDetails = requestPlanDetails;
  context.planRecords = state.planRecords;
  context.lockPlans = lockPlans;
  context.unlockPlans = unlockPlans;
  context.onLockPlans = async ({ planIds } = {}) => {
    await lockPlans(planIds ?? []);
    return true;
  };
  context.onUnlockPlans = async ({ planIds } = {}) => {
    await unlockPlans(planIds ?? []);
    return true;
  };
  context.setPlansLocked = setPlansLocked;
  context.setPlanLocked = (planId, locked = true) => setPlansLocked([planId], locked);
  context.isPlanLocked = (planId) =>
    typeof planId === 'string' ? context.lockedPlans.has(planId.trim()) : false;
}
