export function registerOccurrencesModule(context) {
  const OCCURRENCE_ALLOWED_STATUSES = ['SIT_ESPECIAL', 'GRDE_EMITIDA'];
  const OCCURRENCE_DEFAULT_STATUSES = [...OCCURRENCE_ALLOWED_STATUSES];

  const state = context;
  const {
    occTableBody,
    occColumnCount,
    filtersState,
    occPagerPrevBtn,
    occPagerNextBtn,
    occPagerLabel,
    occPagerRange,
    occActionsMenuContainer,
    occActionsTrigger,
    occActionsMenu,
    occSelectAllAction,
    occSelectAllLabel,
    occActionsSeparator,
    PLANS_ENDPOINT,
    DEFAULT_PLAN_PAGE_SIZE,
  } = context;

  const occPager = context.occPager;
  const occSelection = context.occSelection instanceof Set ? context.occSelection : new Set();
  context.occSelection = occSelection;

  state.occurrenceRecords = state.occurrenceRecords instanceof Map ? state.occurrenceRecords : new Map();
  context.occurrenceRecords = state.occurrenceRecords;

  const ensurePlanRecords = () => {
    if (!(context.planRecords instanceof Map)) {
      context.planRecords = new Map();
    }
    return context.planRecords;
  };

  if (!(context.lockedPlans instanceof Set)) {
    context.lockedPlans = new Set();
  }

  const occCheckboxSelector = "input[type='checkbox'][data-occ-checkbox]";

  const detailsIconTemplate = (() => {
    if (typeof window === 'undefined') {
      return null;
    }
    try {
      return window.feather?.icons?.['external-link']?.toSvg({ 'aria-hidden': 'true' }) ?? null;
    } catch (error) {
      console.error('Falha ao gerar ícone de detalhes de ocorrência.', error);
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
      console.error('Falha ao gerar ícone de bloqueio de ocorrência.', error);
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
      console.error('Falha ao gerar ícone de desbloqueio de ocorrência.', error);
      return null;
    }
  })();

  const findOccurrenceRow = (planId) => {
    if (!occTableBody || !planId) {
      return null;
    }
    const selectorId = typeof CSS !== 'undefined' && CSS.escape
      ? CSS.escape(planId)
      : planId.replace(/"/g, '\\"');
    return occTableBody.querySelector(`[data-plan-id="${selectorId}"]`);
  };

  const applyOccurrenceLockedState = (row, locked) => {
    if (!row) {
      return;
    }
    row.classList.toggle('table__row--locked', locked);
    row.dataset.planLocked = locked ? 'true' : 'false';

    const checkbox = row.querySelector(occCheckboxSelector);
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

  const applyOccurrenceRowSelectionState = (row, checked) => {
    if (!row) {
      return;
    }
    row.classList.toggle('table__row--selected', Boolean(checked));
    row.setAttribute('aria-selected', String(Boolean(checked)));
  };

  const getFirstVisibleOccurrenceAction = () => {
    if (!occActionsMenu) {
      return null;
    }
    const items = occActionsMenu.querySelectorAll('.table-actions-menu__item');
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

  const updateOccActionsMenuState = () => {
    if (!occActionsMenu) {
      return;
    }
    const totalEnabledCheckboxes = occTableBody
      ? occTableBody.querySelectorAll(`${occCheckboxSelector}:not(:disabled)`).length
      : 0;
    const checkedEnabledCheckboxes = occTableBody
      ? occTableBody.querySelectorAll(`${occCheckboxSelector}:checked:not(:disabled)`).length
      : 0;
    const hasSelection = occSelection.size > 0 || checkedEnabledCheckboxes > 0;
    const allSelected =
      totalEnabledCheckboxes > 0 && checkedEnabledCheckboxes === totalEnabledCheckboxes;

    const requiresSelectionItems = occActionsMenu.querySelectorAll('[data-requires-selection]');
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

    if (occActionsSeparator instanceof HTMLElement) {
      if (hasSelection) {
        occActionsSeparator.removeAttribute('hidden');
      } else {
        occActionsSeparator.setAttribute('hidden', 'hidden');
      }
    }

    if (occSelectAllAction instanceof HTMLElement) {
      const isDisabled = totalEnabledCheckboxes === 0;
      occSelectAllAction.disabled = isDisabled;
      occSelectAllAction.setAttribute('aria-disabled', String(isDisabled));
      occSelectAllAction.dataset.mode = allSelected ? 'clear' : 'select';
      if (occSelectAllLabel) {
        occSelectAllLabel.textContent = allSelected ? 'Desmarcar todos' : 'Selecionar todos';
      }
    }

    const lockMenuAction = occActionsMenu.querySelector('[data-action="lock"]');
    if (lockMenuAction instanceof HTMLElement) {
      const selectedIds = new Set(occSelection);
      if (occTableBody) {
        const checkedBoxes = occTableBody.querySelectorAll(`${occCheckboxSelector}:checked`);
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
      if (context.lockedPlans instanceof Set) {
        selectedIds.forEach((planId) => {
          if (context.lockedPlans.has(planId)) {
            hasLockedSelected = true;
          }
        });
      }
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

    if (!hasSelection && state.isOccActionsMenuOpen && occActionsMenu) {
      const activeElement = document.activeElement;
      if (
        activeElement instanceof HTMLElement &&
        occActionsMenu.contains(activeElement) &&
        activeElement !== occSelectAllAction
      ) {
        const firstItem = getFirstVisibleOccurrenceAction();
        if (firstItem) {
          firstItem.focus();
        }
      }
    }
  };

  const setOccurrenceSelection = (planId, checked, { checkbox, row } = {}) => {
    if (checkbox instanceof HTMLInputElement) {
      checkbox.checked = Boolean(checked);
    }
    if (row instanceof HTMLElement) {
      applyOccurrenceRowSelectionState(row, checked);
    }
    const hasIdentifier = typeof planId === 'string' && planId.trim().length > 0;
    if (!hasIdentifier) {
      return;
    }
    if (checked) {
      occSelection.add(planId);
    } else {
      occSelection.delete(planId);
    }
  };

  const selectAllOccurrencesOnPage = () => {
    if (!occTableBody) {
      return;
    }
    const checkboxes = occTableBody.querySelectorAll(occCheckboxSelector);
    if (!checkboxes.length) {
      return;
    }
    occSelection.clear();
    checkboxes.forEach((checkbox) => {
      if (!(checkbox instanceof HTMLInputElement)) {
        return;
      }
      const row = checkbox.closest('tr');
      if (!row) {
        return;
      }
      if (checkbox.disabled) {
        applyOccurrenceRowSelectionState(row, false);
        return;
      }
      const planId = checkbox.dataset.planId ?? row.dataset.planId ?? '';
      setOccurrenceSelection(planId, true, { checkbox, row });
    });
    updateOccActionsMenuState();
  };

  const deselectAllOccurrencesOnPage = () => {
    if (!occTableBody) {
      return;
    }
    const checkboxes = occTableBody.querySelectorAll(occCheckboxSelector);
    if (!checkboxes.length) {
      occSelection.clear();
      updateOccActionsMenuState();
      return;
    }
    checkboxes.forEach((checkbox) => {
      if (!(checkbox instanceof HTMLInputElement)) {
        return;
      }
      const row = checkbox.closest('tr');
      const planId = checkbox.dataset.planId ?? row?.dataset.planId ?? '';
      setOccurrenceSelection(planId, false, { checkbox, row });
    });
    occSelection.clear();
    updateOccActionsMenuState();
  };

  const closeOccActionsMenu = ({ focusTrigger = false } = {}) => {
    if (!occActionsMenu || !occActionsMenuContainer || !occActionsTrigger) {
      return;
    }
    occActionsMenuContainer.classList.remove('table-actions-menu--open');
    occActionsMenu.setAttribute('hidden', 'hidden');
    occActionsTrigger.setAttribute('aria-expanded', 'false');
    state.isOccActionsMenuOpen = false;
    if (focusTrigger) {
      occActionsTrigger.focus();
    }
  };

  const openOccActionsMenu = ({ focusFirst = false } = {}) => {
    if (!occActionsMenu || !occActionsMenuContainer || !occActionsTrigger) {
      return;
    }
    updateOccActionsMenuState();
    occActionsMenuContainer.classList.add('table-actions-menu--open');
    occActionsMenu.removeAttribute('hidden');
    occActionsTrigger.setAttribute('aria-expanded', 'true');
    state.isOccActionsMenuOpen = true;
    if (focusFirst) {
      const firstItem = getFirstVisibleOccurrenceAction();
      if (firstItem) {
        window.requestAnimationFrame(() => {
          firstItem.focus();
        });
      }
    }
  };

  const toggleOccActionsMenu = () => {
    if (state.isOccActionsMenuOpen) {
      closeOccActionsMenu();
    } else {
      openOccActionsMenu();
    }
  };

  const renderOccurrencesPlaceholder = (message, modifier = 'empty') => {
    if (!occTableBody) {
      return;
    }
    occSelection.clear();
    state.occurrenceRecords.clear();
    closeOccActionsMenu();
    updateOccActionsMenuState();
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
    const hasActiveFilters = typeof context.hasActiveFilters === 'function' && context.hasActiveFilters();
    const showFilterContext = isEmptyState && hasActiveFilters;
    if (showFilterContext) {
      const hint = document.createElement('p');
      hint.className = 'table-empty__hint';
      hint.textContent = 'Os filtros selecionados podem estar ocultando as ocorrências recentes.';
      wrapper.appendChild(hint);

      const chipsHolder = document.createElement('div');
      chipsHolder.className = 'table-active-filters table-active-filters--floating';
      chipsHolder.dataset.filterChips = 'occ-empty';
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
    occTableBody.appendChild(row);
    if (isEmptyState) {
      state.occHasResults = false;
      if (typeof context.renderFilterChips === 'function') {
        context.renderFilterChips();
      }
    }
  };

  const renderOccurrenceRows = (items) => {
    if (!occTableBody) {
      return;
    }
    occSelection.clear();
    state.occurrenceRecords.clear();
    closeOccActionsMenu();
    occTableBody.innerHTML = '';
    const rows = Array.isArray(items) ? items : [];
    if (!rows.length) {
      const hasActiveFilters =
        typeof context.hasActiveFilters === 'function' && context.hasActiveFilters();
      const emptyMessage = hasActiveFilters
        ? 'nenhuma ocorrência encontrada para os filtros aplicados.'
        : 'nenhuma ocorrência por aqui.';
      renderOccurrencesPlaceholder(emptyMessage);
      return;
    }

    state.occHasResults = true;
    const lockedPlansSet =
      context.lockedPlans instanceof Set ? context.lockedPlans : new Set();
    if (!(context.lockedPlans instanceof Set)) {
      context.lockedPlans = lockedPlansSet;
    }

    rows.forEach((item) => {
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

      const planRecords = ensurePlanRecords();
      const existingRecord = planId ? planRecords.get(planId) ?? {} : {};
      const planUuidRaw = item?.plan_id ?? item?.plan_uuid ?? item?.id ?? null;
      const existingUuid =
        typeof existingRecord.uuid === 'string' && existingRecord.uuid.trim().length > 0
          ? existingRecord.uuid.trim()
          : '';
      const planUuid = planUuidRaw ? String(planUuidRaw).trim() : existingUuid;

      if (planId) {
        row.dataset.planId = planId;
      }
      if (planUuid) {
        row.dataset.planUuid = planUuid;
      } else if (row.dataset.planUuid) {
        delete row.dataset.planUuid;
      }

      const planCell = document.createElement('td');
      planCell.className = 'table__cell';
      const planNumberText = item?.number ?? '';
      const occPlanSpan = document.createElement('span');
      occPlanSpan.textContent = planNumberText;
      occPlanSpan.dataset.copySource = 'occ-plan-number';
      planCell.appendChild(occPlanSpan);
      row.appendChild(planCell);

      const queueInfo = item?.treatment_queue ?? null;
      const isQueued = Boolean(queueInfo?.enqueued);
      const isMarkedInTreatment = Boolean(
        item?.in_treatment ?? item?.em_tratamento ?? false,
      );
      if (isQueued || isMarkedInTreatment) {
        row.classList.add('table__row--queued');
      } else {
        row.classList.remove('table__row--queued');
      }

      const documentCell = document.createElement('td');
      documentCell.className = 'table__cell';
      const occDocumentSpan = document.createElement('span');
      occDocumentSpan.textContent = context.formatDocument?.(item?.document ?? '') ?? '';
      occDocumentSpan.dataset.copySource = 'occ-document';
      documentCell.appendChild(occDocumentSpan);
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
      checkbox.dataset.occCheckbox = 'true';
      if (planId) {
        checkbox.dataset.planId = planId;
      }
      if (planUuid) {
        checkbox.dataset.planUuid = planUuid;
      } else if (checkbox.dataset.planUuid) {
        delete checkbox.dataset.planUuid;
      }
      const checkboxLabel = planId ? `Selecionar plano ${planId}` : 'Selecionar plano';
      checkbox.setAttribute('aria-label', checkboxLabel);
      checkbox.title = checkboxLabel;
      checkbox.dataset.defaultTitle = checkboxLabel;
      checkbox.addEventListener('change', () => {
        if (checkbox.disabled) {
          return;
        }
        const isChecked = checkbox.checked;
        setOccurrenceSelection(planId, isChecked, { checkbox, row });
        updateOccActionsMenuState();
      });

      const lockButton = document.createElement('button');
      lockButton.type = 'button';
      lockButton.className = 'table__row-action table__row-action--lock';
      if (planId) {
        lockButton.dataset.planId = planId;
      }
      if (planUuid) {
        lockButton.dataset.planUuid = planUuid;
      } else if (lockButton.dataset.planUuid) {
        delete lockButton.dataset.planUuid;
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
          void context.unlockPlans?.([planId]);
        } else {
          void context.lockPlans?.([planId]);
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

      const queueInfo = item?.treatment_queue ?? null;
      const occurrenceDetails = {
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
        lockReason: item?.block_reason ?? null,
        blockedAt: item?.blocked_at ?? null,
        unlockedAt: item?.unlocked_at ?? null,
      };
      if (!occurrenceDetails.number) {
        occurrenceDetails.number = typeof planNumberRaw === 'number'
          ? String(planNumberRaw)
          : (planNumberRaw || '').toString().trim();
      }
      occurrenceDetails.displayNumber = occurrenceDetails.displayNumber
        ? String(occurrenceDetails.displayNumber)
        : occurrenceDetails.number;

      let isLocked = false;
      if (typeof item?.blocked === 'boolean') {
        isLocked = item.blocked;
      } else if (planId) {
        isLocked = lockedPlansSet.has(planId);
      }
      occurrenceDetails.locked = isLocked;

      let detailRecord = occurrenceDetails;
      if (planId) {
        const mergedRecord = { ...existingRecord, ...occurrenceDetails };
        if (!mergedRecord.uuid && existingUuid) {
          mergedRecord.uuid = existingUuid;
        }
        mergedRecord.locked = isLocked;
        state.occurrenceRecords.set(planId, mergedRecord);
        ensurePlanRecords().set(planId, mergedRecord);
        detailRecord = mergedRecord;
      }

      detailsButton.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (typeof context.requestPlanDetails === 'function') {
          context.requestPlanDetails(detailRecord);
        }
      });

      const actionsWrapper = document.createElement('div');
      actionsWrapper.className = 'table__row-actions';
      actionsWrapper.appendChild(checkbox);
      actionsWrapper.appendChild(lockButton);
      actionsWrapper.appendChild(detailsButton);
      actionsCell.appendChild(actionsWrapper);
      row.appendChild(actionsCell);

      occTableBody.appendChild(row);

      if (planId) {
        if (isLocked) {
          lockedPlansSet.add(planId);
        } else {
          lockedPlansSet.delete(planId);
        }
      }

      applyOccurrenceLockedState(row, isLocked);
    });

    if (typeof context.renderFilterChips === 'function') {
      context.renderFilterChips();
    }
    updateOccActionsMenuState();
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
    const selectedSituations = Array.isArray(filtersState.situacao)
      ? filtersState.situacao
      : [];
    const normalizedSituations = selectedSituations.filter((value) =>
      OCCURRENCE_ALLOWED_STATUSES.includes(value),
    );
    if (selectedSituations.length > 0 && normalizedSituations.length === 0) {
      return null;
    }
    const effectiveSituations = normalizedSituations.length
      ? normalizedSituations
      : OCCURRENCE_DEFAULT_STATUSES;
    new Set(effectiveSituations).forEach((value) => {
      url.searchParams.append('situacao', value);
    });
    if (filtersState.diasMin !== null) {
      url.searchParams.set('dias_min', String(filtersState.diasMin));
    }
    if (filtersState.saldoKey) {
      url.searchParams.set('saldo_key', filtersState.saldoKey);
    }
    if (filtersState.dtRange) {
      url.searchParams.set('dt_sit_range', filtersState.dtRange);
    }
    return url.toString();
  };

  const refreshOccurrences = async ({ showLoading, direction = null } = {}) => {
    if (!occTableBody || state.isFetchingOccurrences) {
      return;
    }
    const requestUrl = buildOccurrencesRequestUrl({ direction });
    if (requestUrl === null) {
      state.occurrencesLoaded = true;
      state.occHasResults = false;
      occPager.page = 1;
      occPager.pageSize = DEFAULT_PLAN_PAGE_SIZE;
      occPager.hasMore = false;
      occPager.nextCursor = null;
      occPager.prevCursor = null;
      occPager.showingFrom = 0;
      occPager.showingTo = 0;
      occPager.totalCount = 0;
      occPager.totalPages = 1;
      updateOccPagerUI();
      renderOccurrencesPlaceholder('nenhuma ocorrência encontrada para os filtros aplicados.');
      state.occurrencesBadgeTotal = 0;
      if (typeof state.scheduleOccurrencesCountUpdate === 'function') {
        state.scheduleOccurrencesCountUpdate();
      }
      return;
    }
    if (!context.canAccessBase?.()) {
      state.occurrencesLoaded = true;
      state.occurrencesBadgeTotal = 0;
      if (typeof state.scheduleOccurrencesCountUpdate === 'function') {
        state.scheduleOccurrencesCountUpdate();
      }
      renderOccurrencesPlaceholder('Área disponível apenas para perfil Gestor.', 'empty');
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
      const matricula = state.currentUser?.username?.trim();
      if (matricula) {
        requestHeaders.set('X-User-Registration', matricula);
      }
      const response = await fetch(requestUrl, {
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

      const badgeTotal =
        typeof occPager.totalCount === 'number' ? occPager.totalCount : items.length;
      state.occurrencesBadgeTotal = badgeTotal;
      if (typeof state.scheduleOccurrencesCountUpdate === 'function') {
        state.scheduleOccurrencesCountUpdate();
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

  updateOccActionsMenuState();

  if (occActionsTrigger && occActionsMenu && occActionsMenuContainer) {
    occActionsTrigger.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      toggleOccActionsMenu();
    });

    occActionsTrigger.addEventListener('keydown', (event) => {
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault();
        if (state.isOccActionsMenuOpen) {
          closeOccActionsMenu();
        } else {
          openOccActionsMenu({ focusFirst: true });
        }
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        openOccActionsMenu({ focusFirst: true });
      } else if (event.key === 'Escape' && state.isOccActionsMenuOpen) {
        event.preventDefault();
        closeOccActionsMenu();
      }
    });

    occActionsMenu.addEventListener('click', async (event) => {
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
          deselectAllOccurrencesOnPage();
        } else {
          selectAllOccurrencesOnPage();
        }
      } else if (action === 'lock') {
        const selected = new Set(occSelection);
        if (selected.size === 0 && occTableBody) {
          const checkedBoxes = occTableBody.querySelectorAll(`${occCheckboxSelector}:checked`);
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
            let lockedSelectedCount = 0;
            if (context.lockedPlans instanceof Set) {
              ids.forEach((planId) => {
                if (context.lockedPlans.has(planId)) {
                  lockedSelectedCount += 1;
                }
              });
            }
            if (typeof context.unlockPlans === 'function') {
              await context.unlockPlans(ids);
            }
            if (lockedSelectedCount > 1) {
              ids.forEach((planId) => {
                const row = findOccurrenceRow(planId);
                const checkbox = row?.querySelector(occCheckboxSelector);
                setOccurrenceSelection(planId, false, { checkbox, row });
              });
            }
          } else if (typeof context.lockPlans === 'function') {
            await context.lockPlans(ids);
          }
        }
      }
      updateOccActionsMenuState();
      closeOccActionsMenu();
    });

    occActionsMenu.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeOccActionsMenu({ focusTrigger: true });
      }
    });

    document.addEventListener('click', (event) => {
      if (!state.isOccActionsMenuOpen) {
        return;
      }
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (occActionsMenuContainer.contains(target)) {
        return;
      }
      closeOccActionsMenu();
    });

    document.addEventListener('focusin', (event) => {
      if (!state.isOccActionsMenuOpen) {
        return;
      }
      const target = event.target;
      if (!(target instanceof Node)) {
        return;
      }
      if (occActionsMenuContainer.contains(target)) {
        return;
      }
      closeOccActionsMenu();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && state.isOccActionsMenuOpen) {
        event.preventDefault();
        closeOccActionsMenu({ focusTrigger: true });
      }
    });
  }

  document.addEventListener('sirep:lock-plans', (event) => {
    const detail = event?.detail;
    const planIds = Array.isArray(detail?.planIds) ? detail.planIds : [];
    if (!planIds.length) {
      return;
    }
    planIds.forEach((planId) => {
      const row = findOccurrenceRow(planId);
      applyOccurrenceLockedState(row, true);
      const occRecord = state.occurrenceRecords.get(planId);
      if (occRecord) {
        occRecord.locked = true;
      }
      const sharedRecord = ensurePlanRecords().get(planId);
      if (sharedRecord) {
        sharedRecord.locked = true;
      }
    });
    updateOccActionsMenuState();
  });

  document.addEventListener('sirep:unlock-plans', (event) => {
    const detail = event?.detail;
    const planIds = Array.isArray(detail?.planIds) ? detail.planIds : [];
    if (!planIds.length) {
      return;
    }
    planIds.forEach((planId) => {
      const row = findOccurrenceRow(planId);
      applyOccurrenceLockedState(row, false);
      const occRecord = state.occurrenceRecords.get(planId);
      if (occRecord) {
        occRecord.locked = false;
      }
      const sharedRecord = ensurePlanRecords().get(planId);
      if (sharedRecord) {
        sharedRecord.locked = false;
      }
    });
    updateOccActionsMenuState();
  });

  const setupOccurrencesCounter = () => {
    const countElement = document.getElementById('occurrencesCount');
    const countStatusElement = document.getElementById('occurrencesCountStatus');
    const occurrencesPanel = document.getElementById('occurrencesTablePanel');

    if (!countElement || !occurrencesPanel) {
      state.scheduleOccurrencesCountUpdate = () => {};
      return;
    }

    const updateCount = () => {
      const pagerTotal =
        typeof occPager.totalCount === 'number' ? occPager.totalCount : null;
      const fallbackTotal =
        typeof state.occurrencesBadgeTotal === 'number' ? state.occurrencesBadgeTotal : 0;
      const total = pagerTotal ?? fallbackTotal;
      const clampedTotal = Math.max(0, total);
      const displayValue = clampedTotal > 99 ? '99+' : String(clampedTotal);
      countElement.textContent = displayValue;
      countElement.dataset.count = String(clampedTotal);

      let ariaLabel;
      if (clampedTotal === 0) {
        ariaLabel = 'Nenhuma ocorrência pendente';
      } else if (clampedTotal === 1) {
        ariaLabel = '1 ocorrência pendente';
      } else if (clampedTotal > 99) {
        ariaLabel = 'Mais de 99 ocorrências pendentes';
      } else {
        ariaLabel = `${clampedTotal} ocorrências pendentes`;
      }

      countElement.setAttribute('aria-label', ariaLabel);
      if (countStatusElement) {
        countStatusElement.textContent = ariaLabel;
      }
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
  };

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

  context.renderOccurrencesPlaceholder = renderOccurrencesPlaceholder;
  context.renderOccurrenceRows = renderOccurrenceRows;
  context.resetOccurrencesPagination = resetOccurrencesPagination;
  context.updateOccPagerUI = updateOccPagerUI;
  context.refreshOccurrences = refreshOccurrences;
  context.updateOccActionsMenuState = updateOccActionsMenuState;
  context.openOccActionsMenu = openOccActionsMenu;
  context.closeOccActionsMenu = closeOccActionsMenu;
  context.selectAllOccurrencesOnPage = selectAllOccurrencesOnPage;
  context.deselectAllOccurrencesOnPage = deselectAllOccurrencesOnPage;
  context.setupOccurrencesCounter = setupOccurrencesCounter;
}
