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
